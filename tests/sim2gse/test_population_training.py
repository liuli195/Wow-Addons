"""正式GA通过公开训练入口运行；只在原生边界构造可核验报告。"""
import json
from pathlib import Path
import shutil
import pytest


@pytest.fixture(autouse=True)
def connected_center(tmp_path, installed_data_store, monkeypatch):
    import result_store
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, "_BOUND_PROJECT", None)
    shutil.copytree(installed_data_store, tmp_path / ".local/skills/data-store",
                    ignore=shutil.ignore_patterns("__pycache__"))


def test_public_check_freezes_both_verified_heroes_and_four_groups(tmp_path, capsys, monkeypatch):
    import engine
    import simulation_config
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', tmp_path / 'training.toml')
    from test_search import _fast_identity, _fast_training_template
    monkeypatch.setattr(engine, "identity", _fast_identity)
    monkeypatch.setattr(engine, "_training_template", _fast_training_template)
    from seed_training import main
    from burst import publish
    publish(json.loads((Path(__file__).parents[2] / "projects/sim2gse/burst/unholy.json").read_text()))
    assert main(['--project', str(tmp_path), 'check']) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result['templates']) == 2
    assert {row['configuration_key']['hero_talent'] for row in result['groups']} == {
        'rider_of_the_apocalypse', 'sanlayn'}
    assert {row['configuration_key']['target_type'] for row in result['groups']} == {
        'single_target', 'aoe'}
    assert result['training_config']['max_trainings'] == 4
    assert result['training_config']['max_processes'] == 5
    assert result['final_requested_iterations_per_group'] == 15360


def test_public_run_uses_all_materials_ga_and_publishes_four_five_scene_results(tmp_path, capsys, monkeypatch):
    from seed_training import main, shared_scope
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    import result_store
    import simulation_config
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    programs = [[['outbreak'], ['death_coil'], ['scourge_strike']],
                [['death_coil'], ['outbreak'], ['scourge_strike']],
                [['scourge_strike'], ['death_coil'], ['outbreak']],
                [['outbreak'], ['scourge_strike'], ['death_coil']]]
    for index, program in enumerate(programs):
        source = tmp_path / f'source-{index}.json'
        source.write_text(json.dumps(dict(label=str(index), class_name='deathknight', spec='unholy',
            source='constructed native boundary', original='fixture', instructions='fixture',
            semantic='preserved', changes=[], family='fixture', core=[], program=program)))
        assert main(['--project', str(tmp_path), 'register', str(source)]) == 0
    capsys.readouterr()
    # Explicit no-burst evaluation still uses the same default GA, never a helper-added old execution path.
    with training_boundary():
        assert main(['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
                     '--workspace', str(tmp_path / 'work'), '--legacy']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['status'] == 'completed'
    assert outcome['algorithm'] == 'ga-easimple-v1'
    assert outcome['population_size'] == 4
    assert outcome['complete_generations'] == 2
    rows = result_store.read_records('seed_selected', shared_scope(outcome['configuration_key']))
    assert len(rows) == 4
    assert {row['contract_version'] for row in rows} == {2}
    assert len({row['candidate_id'] for row in rows}) == 4
    for row in rows:
        evaluation = json.loads(row['evaluation']) if isinstance(row['evaluation'], str) else row['evaluation']
        assert set(evaluation['scenarios']) == {'nominal', 'jitter', 'pause', 'slow', 'phase'}
        assert all(len(scene['batches']) == 3 for scene in evaluation['scenarios'].values())
        assert all(batch['iterations'] == 128 for scene in evaluation['scenarios'].values() for batch in scene['batches'])
    from task import run_task, resume_task, read_task
    task_folder = tmp_path / 'formal'
    with training_boundary():
        run_task(template, task_folder, search_config=dict(candidate_limit=1))
        formal = read_task(task_folder)
        assert formal['search']['training_champion_snapshot']['status'] == 'not_applicable'
        assert not any(source['source_kind'] == 'training_champion'
            for group in formal['search']['start_sources'].values() for source in group)
        resumed = resume_task(task_folder)
        assert resumed['search']['training_champion_snapshot']['status'] == 'not_applicable'
        assert read_task(task_folder)['status'] == 'completed'


@pytest.fixture
def registered_six(tmp_path):
    from seed_training import register
    from itertools import permutations
    programs = [[list([action]) for action in order]
                for order in permutations(('outbreak', 'death_coil', 'scourge_strike'))]
    for index, program in enumerate(programs):
        path = tmp_path / f'material-{index}.json'
        path.write_text(json.dumps(dict(label=str(index), class_name='deathknight', spec='unholy',
            source='constructed boundary', original='fixture', instructions='fixture', semantic='preserved',
            changes=[], family='fixture', core=[], program=program)))
        register(path)
    return programs


@pytest.mark.parametrize('fail_one', [False, True])
def test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit(
        tmp_path, capsys, monkeypatch, registered_six, fail_one):
    from contextlib import ExitStack
    from copy import deepcopy
    from unittest.mock import patch
    import threading
    import time
    import burst
    import engine
    import sequence
    import simulation_config
    from seed_training import main, shared_scope
    from test_search import _fast_initialization, _fast_reference, _fast_evaluate, _fast_inspect
    import result_store

    config = tmp_path / 'training.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    definition = json.loads((Path(engine.__file__).parent / 'burst/unholy.json').read_text())
    burst.publish(definition)
    from test_search import _fast_identity
    real_identity = _fast_identity
    lock = threading.Lock()
    active, peak, per_group, group_peak, coarse = 0, 0, {}, {}, []
    trajectories = {}
    failure_target = None

    def reference(profile, folder, character, **kwargs):
        result = _fast_reference(profile, folder, character, **kwargs)
        result['identity']['data_version'] = definition['data_version']
        result['static_snapshot']['hero_subtree_ids'] = [31 if "San'layn" in character.name else 32]
        return result

    def inspect(native, folder):
        capabilities = _fast_inspect(native, folder)
        capabilities['actions'].append(dict(kind='item', slot=14, item_id=273796,
            simc_action='use_item,slot=trinket2', name='trinket2', gcd_ms=0))
        return capabilities

    def evaluate(profile, candidate, folder, **kwargs):
        nonlocal active, peak, failure_target
        sources = kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        group = (kwargs['character'].name, kwargs['simulation_config']['scene'])
        times = kwargs['input_times']
        loop = [at for at, source in zip(times, sources) if source == 'loop'] if sources else times
        with lock:
            active += 1
            per_group[group] = per_group.get(group, 0) + 1
            peak = max(peak, active)
            group_peak[group] = max(group_peak.get(group, 0), per_group[group])
            if (fail_one and failure_target is None and kwargs['iterations'] == 32
                    and "San'layn" in group[0] and group[1] == 'single_target'):
                failure_target = str(folder)
            if kwargs['iterations'] == 32:
                coarse.append((group, tuple(tuple(command['simc_action'] for command in block)
                                             for block in candidate['blocks'])))
            if kwargs['iterations'] == 128:
                trajectories.setdefault(group, set()).add(tuple(loop))
        try:
            if str(folder) == failure_target:
                raise engine.CandidateError('constructed one-group failure')
            time.sleep(.01)
            return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
        finally:
            with lock:
                active -= 1
                per_group[group] -= 1
    with _fast_initialization(), patch.object(engine, 'identity', side_effect=real_identity), \
            patch.object(engine, 'reference', side_effect=reference), patch.object(engine, 'inspect', side_effect=inspect), \
            patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(['--project', str(tmp_path), 'prepare', '--workspace', str(tmp_path / 'work')]) == 0
        preparation = json.loads(capsys.readouterr().out)
        assert len(preparation) == 4
        assert {row['population_size'] for row in preparation} == {6}
        assert not coarse
        failed_key = next(row['configuration_key'] for row in preparation
            if row['configuration_key']['hero_talent'] == 'sanlayn' and row['configuration_key']['target_type'] == 'single_target')
        if fail_one:
            from seed_training import SELECTED_SCHEMA
            previous = [dict(configuration_key=failed_key, candidate_id='previous-' + str(index),
                condition='previous', class_name='deathknight', spec='unholy', targets=1, program=program,
                family='previous', score=9., scores=[9.] * 3, template_sha256='previous', engines={})
                for index, program in enumerate(registered_six[:4])]
            result_store.write('seed_selected', shared_scope(failed_key), previous, schema=SELECTED_SCHEMA)
        assert main(['--project', str(tmp_path), 'run', '--workspace', str(tmp_path / 'work')]) == (2 if fail_one else 0)
    outcomes = json.loads(capsys.readouterr().out)
    assert len(outcomes) == 4
    completed = [row for row in outcomes if row['status'] == 'completed']
    assert len(completed) == (3 if fail_one else 4)
    assert all(row['population_size'] == 6 for row in completed)
    assert len({json.dumps(row['configuration_key'], sort_keys=True) for row in completed}) == len(completed)
    assert len(coarse) == (25 if fail_one else 24)
    assert len(set(coarse)) == 24
    assert 5 < peak <= 20
    assert all(1 < value <= 5 for value in group_peak.values())
    assert all(len(values) == 7 for values in trajectories.values())  # nominal, 3 fresh jitters, 3 fixed stresses.
    for row in completed:
        selected = result_store.read_records('seed_selected', shared_scope(row['configuration_key']))
        assert len(selected) == 4
        assert {item['contract_version'] for item in selected} == {2}
    if fail_one:
        previous = result_store.read_records('seed_selected', shared_scope(failed_key))
        assert {row['candidate_id'] for row in previous} == {'previous-' + str(index) for index in range(4)}


@pytest.mark.parametrize('initial_logging,resume_logging', [(True, True), (False, True), (True, False)],
    ids=['on_to_on', 'off_to_on', 'on_to_off'])
@pytest.mark.parametrize('cancel_mode', ['foreground', 'interrupt'])
def test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches(
        tmp_path, capsys, monkeypatch, registered_six, cancel_mode, initial_logging, resume_logging):
    from unittest.mock import patch
    import threading
    import sequence
    import simulation_config
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    from seed_activity import foreground_search
    import time
    import sqlite3
    from search import TaskStore
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy', '--search-timeline']
    if initial_logging:
        args.append('--diagnostic-logging')
    seen, interrupted, cancelled = [], [], threading.Event()
    def evaluate(profile, candidate, folder, **kwargs):
        seen.append(str(folder))
        result = _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
        if kwargs['iterations'] == 128 and not cancelled.is_set():
            cancelled.set()
            if cancel_mode == 'interrupt':
                interrupted.append(str(folder))
                raise KeyboardInterrupt
            with foreground_search():
                time.sleep(.12)
        return result
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(args) == 2
    assert '取消' in capsys.readouterr().err
    folders = [path for path in (tmp_path / 'work' / 'ga').glob('*/*') if path.is_dir()]
    assert len(folders) == 1
    folder = folders[0]
    with sqlite3.connect(folder / 'task.sqlite3') as db:
        paused = TaskStore.load_state(db)
        assert paused['config']['diagnostic_logging'] is initial_logging
        assert paused['status'] == 'paused'
        assert paused['ga']['phase'] == 'retest'
        assert not db.execute('SELECT key FROM report_intents').fetchall()
        successful = [key for key, in db.execute("SELECT key FROM batches WHERE json_extract(value,'$.status')='success'")]
    assert len(successful) > 6
    curves = list(folder.glob('search-timeline-*.json'))
    assert len(curves) == 1
    assert json.loads(curves[0].read_text())['status'] == 'cancelled'
    config.write_text('[training]\ntop_k=8\nretest_iterations=64\nmax_processes=1\nmax_trainings=1\n')
    frozen_manifest = (folder / 'identity.json').read_bytes()
    args = [arg for arg in args if arg != '--diagnostic-logging']
    if resume_logging:
        args.append('--diagnostic-logging')
    resumed_seen = []
    def resumed_evaluate(profile, candidate, target, **kwargs):
        resumed_seen.append(str(target))
        assert kwargs['runtime'].diagnostic_logging is resume_logging
        assert kwargs['iterations'] in (2, 32, 128)
        return _fast_evaluate(profile, candidate, target, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=resumed_evaluate):
        assert main(args) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['task_path'] == str(folder)
    assert outcome['training_config']['top_k'] == 4
    assert outcome['training_config']['max_processes'] == 5
    assert set(seen) & set(resumed_seen) == set(interrupted)  # The interrupted call never committed a receipt.
    assert not set(successful) & {Path(row).name for row in resumed_seen}
    with sqlite3.connect(folder / 'task.sqlite3') as db:
        complete = TaskStore.load_state(db)
    assert complete['config']['diagnostic_logging'] is resume_logging
    assert complete['config']['diagnostics'] == ('summary' if resume_logging else 'off')
    assert (folder / 'identity.json').read_bytes() == frozen_manifest
    assert complete['ga']['phase'] == 'published'
    assert complete['ga']['generation'] == paused['ga']['generation'] == 2
    resumed_curve = next(path for path in folder.glob('search-timeline-*.json') if path not in curves)
    assert json.loads(resumed_curve.read_text())['resumed'] is True
    assert json.loads(resumed_curve.read_text())['status'] == 'completed'
    if cancel_mode == 'foreground' and initial_logging and resume_logging:
        import task
        def forbidden(*args, **kwargs):
            raise AssertionError('GA已有时间曲线的离线比较不得启动评分')
        output = tmp_path / 'ga-comparison.html'
        with patch.object(task, 'run_task', side_effect=forbidden), \
                patch.object(sequence, 'evaluate', side_effect=forbidden):
            assert task.main(['curves', str(folder), '--output', str(output)]) == 0
        capsys.readouterr()
        comparison = json.loads(output.with_suffix('.json').read_text())
        assert len(comparison['groups']) == 1
        assert len(comparison['groups'][0]['runs']) == 2
        assert {row['status'] for row in comparison['groups'][0]['runs']} == {'cancelled', 'completed'}
        assert output.is_file()


def test_public_training_accepts_verified_zero_stress_as_full_loss_without_retry(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import engine
    import sequence
    import simulation_config
    import result_store
    from seed_training import main, shared_scope
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    real_check = engine.check_report
    zero_requests = []
    def evaluate(profile, candidate, folder, **kwargs):
        stress = kwargs['iterations'] == 128 and kwargs['input_times'] != list(range(0, 180000, 300))
        if stress:
            zero_requests.append(str(folder))
        return _fast_evaluate(profile, candidate, folder, score=0. if stress else 100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), \
            patch.object(engine, 'check_report', side_effect=real_check):
        assert main(['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
                     '--workspace', str(tmp_path / 'work'), '--legacy']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert len(zero_requests) == len(set(zero_requests)) == 48
    rows = result_store.read_records('seed_selected', shared_scope(outcome['configuration_key']))
    assert all(json.loads(row['evaluation'])['stability_loss'] == 1.0 for row in rows)


@pytest.mark.parametrize('failure_kind,failures',
    [(kind, count) for kind in ('candidate', 'exit', 'missing', 'json', 'nan', 'inf', 'samples') for count in (1, 2)]
    + [('identity', 1), ('storage', 1), ('duration', 1)])
def test_public_run_retries_original_request_once_and_preserves_exhaustion_on_resume(
        tmp_path, capsys, monkeypatch, registered_six, failures, failure_kind):
    from unittest.mock import patch
    import sequence
    import simulation_config
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate, _fast_report
    import engine
    from types import SimpleNamespace
    from engine import CandidateError
    real_evaluate = sequence.evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\nmax_processes=1\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy', '--diagnostic-logging']
    target, attempts = None, []
    def evaluate(profile, candidate, folder, **kwargs):
        nonlocal target
        if target is None and kwargs['iterations'] == 32:
            target = str(folder)
        if str(folder) == target:
            attempts.append((kwargs['seed'], tuple(kwargs['input_times']), candidate))
            if len(attempts) <= failures or failure_kind in ('nan', 'inf', 'samples'):
                if failure_kind == 'candidate':
                    raise CandidateError('constructed native failure')
                def native_process(command, cwd, **options):
                    if options.get('on_start'):
                        options['on_start']()
                    if failure_kind == 'json':
                        (Path(cwd) / 'native.pending.json').write_text('{broken')
                    if failure_kind in ('identity', 'nan', 'inf', 'samples', 'duration'):
                        bad = len(attempts) <= failures
                        score = float(failure_kind) if bad and failure_kind in ('nan', 'inf') else 100.
                        samples = 30 if bad and failure_kind == 'samples' else 31
                        report = _fast_report(kwargs['character'], score, samples)
                        if failure_kind == 'identity':
                            report['sim']['targets'] *= 5
                        if failure_kind == 'duration':
                            report['sim']['players'][0]['collected_data']['fight_length']['mean'] = 179
                        (Path(cwd) / 'native.pending.json').write_text(json.dumps(report))
                    blocks = sequence.compiled_program(candidate)
                    log = '\n'.join(f'S2GBLOCK\t{step}\t{position}\t{action}'
                        for step, block in enumerate(blocks) for position, action in enumerate(block))
                    return SimpleNamespace(returncode=int(failure_kind == 'exit'),
                        stdout=log.encode(), stderr=b'', elapsed_seconds=.001)
                read_text = Path.read_text
                def guarded_read(path, *args, **options):
                    if failure_kind == 'storage' and path.name == 'native.pending.json':
                        raise PermissionError('constructed report storage denied')
                    return read_text(path, *args, **options)
                with patch.object(engine, 'run_command', side_effect=native_process), \
                        patch.object(Path, 'read_text', guarded_read):
                    return real_evaluate(profile, candidate, folder, **kwargs)
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        retryable = failure_kind not in ('identity', 'storage', 'duration')
        assert main(args) == (0 if failures == 1 and retryable else 2)
        first = capsys.readouterr()
        if not retryable:
            assert ('目标数量不符' if failure_kind == 'identity' else
                    '原生参考数值或实际样本数无效' if failure_kind == 'duration' else 'storage denied') in first.err
            import sqlite3
            from search import TaskStore
            database = next((tmp_path / 'work' / 'ga').glob('*/*/task.sqlite3'))
            with sqlite3.connect(database) as db:
                assert not TaskStore.load_state(db)['training_failures']
        elif failures == 2:
            assert ('constructed native failure' if failure_kind == 'candidate' else
                    '原生引擎失败' if failure_kind == 'exit' else
                    '原生参考数值或实际样本数无效' if failure_kind in ('nan', 'inf', 'samples') else
                    '原生报告缺失') in first.err
            assert main(args) == 2
            assert '已用尽一次重试' in capsys.readouterr().err
        else:
            outcome = json.loads(first.out)[0]
            assert outcome['status'] == 'completed'
    assert len(attempts) == (2 if retryable else 1)
    if retryable:
        assert attempts[0] == attempts[1]


def test_public_run_feedback_failure_uses_same_persistent_single_retry_budget(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import sequence
    import simulation_config
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    from engine import CandidateError
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=1.0\nmax_processes=1\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']
    attempts = []
    def evaluate(profile, candidate, folder, **kwargs):
        if kwargs['iterations'] == 2:
            attempts.append((str(folder), kwargs['seed']))
            raise CandidateError('constructed feedback failure')
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(args) == 2
        capsys.readouterr()
        assert len(attempts) == 2
        assert attempts[0] == attempts[1]
        assert main(args) == 2
        assert '已用尽一次重试' in capsys.readouterr().err
        assert len(attempts) == 2


@pytest.mark.parametrize('overflow', ['clicks', 'macro'])
def test_public_illegal_slot_uses_first_child_and_ten_persistent_extra_regenerations(
        tmp_path, capsys, monkeypatch, overflow):
    import random
    from seed_training import main, register
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    import simulation_config
    operations = []
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow = real_random._randbelow
        """Deterministic randomness boundary; selection, DEAP varAnd and mutate stay real."""
        def random(self):
            return .99
        def choice(self, values):
            if isinstance(values, list) and values and values[0] == 'swap' and 'insert' in values:
                count = getattr(self, 'operations', 0) + 1
                self.operations = count
                operation = ('insert' if overflow == 'clicks' else 'block') if count == 1 or count % 2 == 0 else 'delete'
                operations.append(operation)
                return operation
            if overflow == 'macro' and values == [0, 1]:
                return 0
            return super().choice(values)
        def randrange(self, *args):
            if args == (2,):
                return 1 if overflow == 'clicks' else 0  # Only the unused second child becomes legal.
            return super().randrange(*args)
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=1.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    source = tmp_path / 'source.json'
    source.write_text(json.dumps(dict(label='near click limit', class_name='deathknight', spec='unholy',
        source='constructed fixture', original='fixture', instructions='fixture', semantic='preserved',
        changes=[], family='fixture', core=[],
        program=([['outbreak'], dict(kind='WaitClicks', clicks=4095)] if overflow == 'clicks' else
                 [['scourge_strike'] * 12, ['outbreak']]))))
    register(source)
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']
    with training_boundary(), monkeypatch.context() as boundary:
        boundary.setattr(random, 'Random', BoundaryRandom)
        assert main(args) == 2
        assert '已耗尽10次额外重生' in capsys.readouterr().err
        operation = 'insert' if overflow == 'clicks' else 'block'
        assert operations == [operation, *[operation, 'delete'] * 10]
        assert main(args) == 2
        assert '已耗尽10次额外重生' in capsys.readouterr().err
        assert len(operations) == 21


def test_public_a_tournament_and_block_crossover_keep_duplicate_slots_and_reuse_scores(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import random
    import sequence
    import simulation_config
    import sqlite3
    from seed_training import main
    from search import TaskStore
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    real_random = random.Random
    tournament_draws, coarse = [], []
    class BoundaryRandom(real_random):
        _randbelow = real_random._randbelow
        def random(self):
            return .5
        def choice(self, values):
            if values and hasattr(values[0], 'fitness'):
                offset = len(tournament_draws) % len(values)
                tournament_draws.append(offset)
                return values[offset]
            return super().choice(values)
        def randint(self, first, last):
            return first
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=1.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    def evaluate(profile, candidate, folder, **kwargs):
        if kwargs['iterations'] == 32:
            coarse.append(tuple(tuple(command['simc_action'] for command in block) for block in candidate['blocks']))
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), monkeypatch.context() as boundary:
        boundary.setattr(random, 'Random', BoundaryRandom)
        assert main(['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy', '--diagnostic-logging']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert len(tournament_draws) == 6 * 3 * 2
    assert (('outbreak',), ('scourge_strike',), ('outbreak',)) in coarse
    assert (('death_coil',), ('death_coil',), ('scourge_strike',)) in coarse
    assert len(coarse) == len(set(coarse)) == 8
    with sqlite3.connect(Path(outcome['task_path']) / 'task.sqlite3') as db:
        state = TaskStore.load_state(db)
    slots = [row['key'] for row in state['ga']['population']]
    assert len(slots) == 6
    assert len(set(slots)) == 2
    diagnostics = json.loads((Path(outcome['task_path']) / 'diagnostics.json').read_text())
    assert diagnostics['task_state_writes'] < state['native_batch_starts']
    import result_store
    with result_store.query("SELECT storage_group_key, count(*) AS n FROM batches WHERE purpose != 'seed_reference' "
            'GROUP BY storage_group_key', tables=['batches']) as cursor:
        sizes = [row[1] for row in cursor.fetchall()]
    assert max(sizes) == 12
    assert sum(sizes) == 68  # Eight fresh coarse requests plus 4 x 5 x 3 independent final requests.
    assert len(sizes) <= 8  # Full-generation tails are allowed; no per-score/final-batch flushing.


@pytest.mark.parametrize('invalid_nominal', [False, True])
def test_public_selection_keeps_nominal_and_minimax_stability_champions_and_reports_ineligible(
        tmp_path, capsys, monkeypatch, registered_six, invalid_nominal):
    from unittest.mock import patch
    import threading
    import sequence
    import simulation_config
    import result_store
    from seed_training import main, shared_scope
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=6\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    programs = {tuple(tuple(block) for block in program): index for index, program in enumerate(registered_six)}
    nominal = [200., 180., 160., 140., 120., 100.]
    stress = [150., 162., 144., 139., 115., 110.]
    counts, seeds, lock = {}, {}, threading.Lock()
    def evaluate(profile, candidate, folder, **kwargs):
        program = tuple(tuple(command['simc_action'] for command in block) for block in candidate['blocks'])
        index = programs[program]
        is_nominal = kwargs['input_times'] == list(range(0, 180000, 300))
        value = nominal[index] if is_nominal else stress[index]
        if invalid_nominal and index == 5 and is_nominal and kwargs['iterations'] == 128:
            value = 0.
        with lock:
            counts[kwargs['iterations']] = counts.get(kwargs['iterations'], 0) + 1
            seeds.setdefault(kwargs['iterations'], set()).add(kwargs['seed'])
        return _fast_evaluate(profile, candidate, folder, score=value, **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    rows = result_store.read_records('seed_selected', shared_scope(outcome['configuration_key']))
    assert {row['score'] for row in rows} == ({200., 180., 160., 140.} if invalid_nominal else {200., 180., 160., 100.})
    evaluations = {row['score']: json.loads(row['evaluation']) for row in rows}
    assert evaluations[200.]['nominal_champion']
    assert evaluations[200.]['stability_loss'] == .25
    assert evaluations[140. if invalid_nominal else 100.]['stable_representative']
    if invalid_nominal:
        assert len(outcome['ineligible']) == 1
        assert '正常复测均分≤0' in next(iter(outcome['ineligible'].values()))
    else:
        assert evaluations[100.]['stability_loss'] == -.1
    assert counts == {32: 6, 128: 90}
    assert len(seeds[128]) == 15
    assert not seeds[32] & seeds[128]


@pytest.mark.parametrize('version', [None, 1, 2, 99])
def test_public_formal_entry_reads_legacy_contract_rejects_unknown_and_recycles_completed_winner(
        tmp_path, capsys, registered_six, version):
    import result_store
    from seed_training import SELECTED_SCHEMA, SELECTED_V2_SCHEMA, shared_scope, main
    from task import run_task, read_task, resume_task, TaskError
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    rows = [dict(configuration_key=key, candidate_id='old-' + str(index), condition='old fixture',
        class_name='deathknight', spec='unholy', targets=1, program=program, family='fixture',
        score=99999., scores=[99999.] * 3, template_sha256='different-role', engines={},
        **(dict(contract_version=version, evaluation=None) if version is not None else {}))
        for index, program in enumerate(registered_six[:4])]
    result_store.write('seed_selected', shared_scope(key), rows, schema=SELECTED_SCHEMA if version is None else SELECTED_V2_SCHEMA)
    destination = tmp_path / 'formal'
    with training_boundary():
        if version == 99:
            with pytest.raises(TaskError, match='不支持的训练成果契约版本'):
                run_task(template, destination, search_config=dict(candidate_limit=1))
            return
        run_task(template, destination, search_config=dict(candidate_limit=1))
        saved = read_task(destination)
        assert saved['status'] == 'completed'
        expected = 'not_applicable' if version == 2 else 'absent'
        assert saved['search']['training_champion_snapshot']['status'] == expected
        assert saved['search_result']['dps'] == 100.  # Old template scores are never borrowed.
        assert resume_task(destination)['status'] == 'completed'
        assert main(['--project', str(tmp_path), 'prepare', '--template', str(template), '--targets', '1',
                     '--workspace', str(tmp_path / 'work'), '--legacy']) == 0
    capsys.readouterr()
    assert main(['--project', str(tmp_path), 'list', '--state', 'pending']) == 0
    registry = json.loads(capsys.readouterr().out)
    history = [row for row in registry if row['source_id'].startswith('history:')]
    assert len(history) == 1
    assert history[0]['active']
    assert history[0]['semantic'] == 'preserved'


def test_public_configured_sample_plan_and_stagnation_are_used_without_old_stage_caps(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import sequence
    import simulation_config
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncoarse_iterations=4\nretest_batches=2\nretest_iterations=8\n'
                      'stagnation_generations=3\ntournament_size=7\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    requests = []
    def evaluate(profile, candidate, folder, **kwargs):
        requests.append(kwargs['iterations'])
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(['--project', str(tmp_path), 'check', '--template', str(template), '--legacy']) == 0
        assert json.loads(capsys.readouterr().out)['final_requested_iterations_per_group'] == 320
        assert main(['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
                     '--workspace', str(tmp_path / 'work'), '--legacy']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['complete_generations'] == 3
    assert requests.count(4) == 6
    assert requests.count(8) == 40
    assert len(requests) == 46


def test_public_publication_failure_preserves_old_four_and_resume_repairs_only_missing_report_group(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import sequence
    import simulation_config
    import result_store
    import sqlite3
    from seed_training import main, shared_scope, SELECTED_SCHEMA
    from search import TaskStore
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    scope = shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    old = [dict(configuration_key=dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'),
        candidate_id='previous-' + str(index), condition='previous', class_name='deathknight', spec='unholy',
        targets=1, program=program, family='previous', score=9., scores=[9.] * 3, template_sha256='previous', engines={})
        for index, program in enumerate(registered_six[:4])]
    result_store.write('seed_selected', scope, old, schema=SELECTED_SCHEMA)
    previous = result_store.read_records('seed_selected', scope)
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']
    writer = result_store.write
    def fail_publication(table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise OSError('constructed publication failure')
        return writer(table, key, rows, **kwargs)
    with training_boundary(), patch.object(result_store, 'write', side_effect=fail_publication):
        assert main(args) == 2
    assert 'constructed publication failure' in capsys.readouterr().err
    assert result_store.read_records('seed_selected', scope) == previous
    database = next((tmp_path / 'work' / 'ga').glob('*/*/task.sqlite3'))
    with sqlite3.connect(database) as db:
        state = TaskStore.load_state(db)
        assert state['ga']['phase'] == 'qualified'
        first = state['ga']['finals'][state['ga']['finalists'][0]]['nominal']['0']
        cached = json.loads(db.execute('SELECT value FROM batches WHERE key=?', [first['batch_key']]).fetchone()[0])
        group = cached['storage_group_key']
        first['dps'] = 99999.  # Checkpoint summaries are not independent scoring evidence.
        db.execute("UPDATE state_fields SET value=? WHERE key='ga'", [json.dumps(state['ga'])])
    missing = result_store.read_records('batches', group)
    assert len(missing) == 12
    (result_store.DATA_ROOT / 'batches' / (group + '.parquet')).unlink()  # Isolated test data only.
    fresh = []
    def evaluate(profile, candidate, folder, **kwargs):
        fresh.append(Path(folder).name)
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        assert main(args) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['status'] == 'completed'
    assert set(fresh) == {row['batch_key'] for row in missing}
    assert len(fresh) == len(set(fresh)) == 12
    current = result_store.read_records('seed_selected', scope)
    assert len(current) == 4
    assert {row['score'] for row in current} == {100.}
    assert {row['contract_version'] for row in current} == {2}


def test_public_run_training_defaults_really_cross_and_mutate_without_global_rng_patch(
        tmp_path, monkeypatch, registered_six):
    from unittest.mock import patch
    import random
    import sequence
    import simulation_config
    from seed_training import run_training
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    from deap import algorithms
    original_random = algorithms.random
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow = real_random._randbelow
        def random(self):
            return .5  # Both independent default .8 gates pass, not a mutually exclusive choice.
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    coarse = []
    def evaluate(profile, candidate, folder, **kwargs):
        assert algorithms.random is original_random
        if kwargs['iterations'] == 32:
            coarse.append(Path(folder).name)
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), monkeypatch.context() as boundary:
        boundary.setattr(random, 'Random', BoundaryRandom)
        outcome = run_training(template, 1, tmp_path / 'work')
    assert outcome['algorithm'] == 'ga-easimple-v1'
    assert outcome['complete_generations'] == 2
    assert outcome['population_size'] == 6
    assert len(coarse) == len(set(coarse)) > 6
    assert algorithms.random is original_random


@pytest.mark.parametrize('entry', ['cli', 'api'])
@pytest.mark.parametrize('enabled', [False, True])
def test_public_ga_timeline_switch_exports_existing_scores_without_extra_evaluations(
        tmp_path, capsys, monkeypatch, registered_six, enabled, entry):
    from unittest.mock import patch
    import sequence
    import simulation_config
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    calls = []
    def evaluate(profile, candidate, folder, **kwargs):
        calls.append(str(folder))
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']
    if enabled:
        args.append('--search-timeline')
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        if entry == 'api':
            from seed_training import run_training
            outcome = run_training(template, 1, tmp_path / 'work', search_config=dict(search_timeline=enabled))
        else:
            assert main(args) == 0
            outcome = json.loads(capsys.readouterr().out)[0]
    curves = list(Path(outcome['task_path']).glob('search-timeline-*.json'))
    assert len(curves) == int(enabled)
    assert len(calls) == len(set(calls)) == 66
    if enabled:
        curve = json.loads(curves[0].read_text())
        assert curve['schema'] == 'sim2gse-search-timeline-v1'
        assert curve['status'] == 'completed'
        assert curve['search_start_seconds'] is not None
        assert curve['result_saved_seconds'] is not None
        assert curve['search_start_seconds'] <= curve['search_stop_seconds'] <= curve['result_saved_seconds']
        assert curve['context']['algorithm']['training'] == 'ga-easimple-v1'
        assert {row['series'] for row in curve['events'] if row['kind'] == 'score'} == {
            'search', 'nominal', 'jitter', 'pause', 'slow', 'phase'}
        assert curves[0].with_suffix('.html').is_file()
    else:
        assert not list(Path(outcome['task_path']).glob('search-timeline-*.html'))


def test_public_feedback_commits_at_twelve_and_replays_same_generation_rng(tmp_path, capsys, monkeypatch):
    from copy import deepcopy
    from itertools import islice, product
    from types import SimpleNamespace
    from unittest.mock import patch
    import sqlite3
    import uuid
    import population_training
    import search
    import sequence
    import simulation_config
    from seed_training import main, register
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    from test_search import _fast_evaluate
    config = tmp_path / 'config.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=1.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    monkeypatch.setattr(population_training, 'uuid', SimpleNamespace(uuid4=lambda: uuid.UUID(int=0)))
    for index, order in enumerate(islice(product(('outbreak', 'death_coil', 'scourge_strike'), repeat=4), 70)):
        path = tmp_path / f'material-{index}.json'
        path.write_text(json.dumps(dict(label=str(index), class_name='deathknight', spec='unholy',
            source='constructed native boundary', original='fixture', instructions='fixture', semantic='preserved',
            changes=[], family='fixture', core=[], program=[[name] for name in order])))
        register(path)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile())
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy']
    checkpoints, feedback, mutations = [], [], []
    mode, stopped = 1, False
    real_checkpoint, real_mutate = search.TaskStore.checkpoint, population_training.mutate
    def checkpoint(store):
        nonlocal stopped
        ga = store.state.get('ga')
        if ga and ga['phase'] == 'breed' and feedback:
            checkpoints.append((len(store.report_buffer), len(feedback), ga['pending'] is not None))
        result = real_checkpoint(store)
        if ga and ga['phase'] == 'breed' and not stopped and feedback and (mode == 1 or ga['pending'] is not None):
            stopped = True
            store.runtime.cancel_event.set()
        return result
    def mutate(program, capabilities, rng, **kwargs):
        before = search.digest(rng.getstate())
        result = real_mutate(program, capabilities, rng, **kwargs)
        mutations.append((deepcopy(list(program)), before, deepcopy(result), search.digest(rng.getstate())))
        return result
    def evaluate(profile, candidate, folder, **kwargs):
        if kwargs['iterations'] == 2:
            feedback.append(str(folder))
        return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), \
            patch.object(search.TaskStore, 'checkpoint', checkpoint), patch.object(population_training, 'mutate', mutate):
        assert main(args) == 2
        assert '取消' in capsys.readouterr().err
        assert checkpoints[0] == (12, 12, False)  # Submission timing, not eventual parquet file size.
        assert max(size for size, _, _ in checkpoints) <= 12
        folder = next((tmp_path / 'work' / 'ga').glob('*/*/task.sqlite3')).parent
        with sqlite3.connect(folder / 'task.sqlite3') as db:
            paused = search.TaskStore.load_state(db)['ga']
        assert paused['generation'] == 0 and paused['pending'] is None
        first = deepcopy(mutations)
        mutations.clear()
        mode, stopped = 2, False
        assert main(args) == 2
        assert '取消' in capsys.readouterr().err
    assert mutations[:len(first)] == first
    assert len(feedback) == len(set(feedback)) > 12
    assert max(size for size, _, _ in checkpoints) <= 12
    with sqlite3.connect(folder / 'task.sqlite3') as db:
        resumed = search.TaskStore.load_state(db)['ga']
    assert resumed['generation'] == 0
    assert len(resumed['pending']['programs']) == 70


def test_public_failed_ga_exports_failed_timeline_and_compares_without_scoring(
        tmp_path, capsys, monkeypatch, registered_six):
    from unittest.mock import patch
    import sequence
    import simulation_config
    import task
    from engine import NativeEvaluationError
    from seed_training import main
    from test_character_export import sample_profile
    from test_seed_training import training_boundary
    config = tmp_path / 'settings.toml'
    config.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    source = tmp_path / 'standard.simc'
    source.write_text(sample_profile())
    def failed(*args, **kwargs):
        raise NativeEvaluationError('constructed native exchange failure')
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=failed):
        assert main(['--project', str(tmp_path), 'run', '--template', str(source), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--legacy', '--search-timeline']) == 2
    capsys.readouterr()
    checkpoint, = (tmp_path / 'work' / 'ga').glob('*/*/task.sqlite3')
    folder = checkpoint.parent
    curve, = folder.glob('search-timeline-*.json')
    document = json.loads(curve.read_text())
    assert document['status'] == 'failed'
    assert not [event for event in document['events'] if event['kind'] == 'score']
    original = curve.read_bytes(), (folder / 'identity.json').read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('离线比较不得补跑失败GA')
    output = tmp_path / 'failed-ga-comparison.html'
    with patch.object(task, 'run_task', side_effect=forbidden), \
            patch.object(sequence, 'evaluate', side_effect=forbidden):
        assert task.main(['curves', str(folder), '--output', str(output)]) == 0
    capsys.readouterr()
    result = json.loads(output.with_suffix('.json').read_text())
    assert result['groups'][0]['runs'][0]['status'] == 'failed'
    assert original == (curve.read_bytes(), (folder / 'identity.json').read_bytes())
