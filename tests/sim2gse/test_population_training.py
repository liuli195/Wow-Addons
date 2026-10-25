"""GA规则使用内存输入；公开持久化、共享并发和取消链显式标记real。"""
import json
from pathlib import Path
import shutil
import pytest
from test_seed_training import memory_result_center


@pytest.fixture(autouse=True)
def connected_center(request, monkeypatch):
    if request.node.get_closest_marker('real') is None:
        return
    tmp_path = request.getfixturevalue('tmp_path')
    installed_data_store = request.getfixturevalue('installed_data_store')
    import result_store
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, "_BOUND_PROJECT", None)
    shutil.copytree(installed_data_store, tmp_path / ".local/skills/data-store",
                    ignore=shutil.ignore_patterns("__pycache__"))


@pytest.fixture
def memory_ga(monkeypatch):
    """Existing optimizer/SQLite state with explicit compiler and report IO inputs.

    This does not model a result center or claim file/WAL durability. Publication,
    shared pools and file recovery have separately marked real representatives.
    """
    from copy import deepcopy
    from itertools import permutations
    import random
    import sqlite3
    from types import SimpleNamespace
    import codec
    import engine
    import population_training as training
    import program
    import result_store
    import sequence
    from runtime import TaskRuntime
    from search import TaskStore, config_for, optimize
    from seed_training import template_character
    from simulation_config import TRAINING_DEFAULTS
    from test_search import _fast_capabilities, _fast_report
    from test_character_export import sample_profile
    stores = []
    def make(*, programs=None, settings=None, native=None, score_for=None, formal=False, search_settings=None,
             manifest_fields=None):
        capabilities = _fast_capabilities()
        starts = (deepcopy(programs) if programs is not None else
                  [[[name] for name in order] for order in permutations(
                      ('outbreak', 'death_coil', 'scourge_strike'))])
        config = dict(TRAINING_DEFAULTS, top_k=4, max_processes=1,
                      crossover_probability=0., mutation_probability=0.)
        config.update(settings or {})
        # Overrides must not be duplicated in dict's keyword construction.
        search_values = dict(max_processes=1)
        search_values.update(search_settings or {})
        search_config = config_for(search_values, training=not formal)
        character = template_character(sample_profile())
        store = TaskStore(Path('/memory/ga'), connection=sqlite3.connect(':memory:', check_same_thread=False),
                          reusable_database=':memory:', report_locations={})
        stores.append(store)
        plan = training._stage_plan(config, 20260912)
        if formal:
            from formal_search import contract_for
            if settings: raise ValueError('formal GA settings must come from the production contract')
            frozen = contract_for(search_config)
            config, plan = frozen['config'], frozen['stage_plan']
        manifest = dict(training_config=config, stage_plan=plan, **(manifest_fields or {}))
        from search import digest
        condition = digest(manifest)
        store.state.update(run_id='memory', condition=condition, starts=starts, config=search_config,
            behavior_identity_version=program.BEHAVIOR_IDENTITY_VERSION,
            archive=[], errors=[], ga=dict(algorithm=training.ALGORITHM, phase='initial', generation=0,
            stagnant=0, population=[], pending=None, rng=random.Random(20260912).getstate(), finals={}, baseline=[]))
        if formal: store.state['formal_search'] = frozen
        calls, reports = [], {}
        def compile_input(mapped, folder, **kwargs):
            # A native-compiler response fixture, using the existing Program mapping.
            blocks = program._search_blocks(mapped)
            clicks = program._search_clicks(dict(blocks=blocks), mapped)
            commands = [row.get('commands', []) for row in clicks]
            return program._with_compiled_program(dict(blocks=blocks, compiled_steps=list(range(len(clicks))),
                mapped_blocks=commands, text='verified compiler fixture'), mapped, clicks)
        def evaluate(profile, candidate, folder, **options):
            calls.append((str(folder), deepcopy(candidate), deepcopy({k:v for k,v in options.items()
                          if k not in ('runtime', 'on_native_start', 'character')})))
            if options.get('on_native_start'):
                options['on_native_start']()
            if native is not None:
                return native(profile, candidate, folder, **options)
            score = 100. if score_for is None else score_for(candidate, options)
            report = _fast_report(character, score, max(1, options['iterations'] - 1))
            summary = engine.check_report(report, character, options['iterations'],
                simulation_config=options['simulation_config'], allow_zero=True)
            return dict(report=report, summary=summary, trace=[])
        def stage_report(key, row, stored, **kwargs):
            reports[key] = deepcopy(stored)
            store.put_batch(key, row, verified=True)
        monkeypatch.setattr(codec, 'load_targeting', lambda **kwargs: dict(target_masks={}))
        monkeypatch.setattr(program, 'compile_program', compile_input)
        monkeypatch.setattr(sequence, 'evaluate', evaluate)
        monkeypatch.setattr(result_store, 'DATA_ROOT', Path('/memory/ga-result-center'))
        monkeypatch.setattr(result_store, 'report_locations', lambda keys:
                            {key: key if key in reports else None for key in keys})
        monkeypatch.setattr(result_store, 'write', lambda *args, **kwargs: None)
        monkeypatch.setattr(result_store, 'write_traces', lambda *args, **kwargs: None)
        monkeypatch.setattr(result_store, 'one', lambda table, field, key, **kwargs: deepcopy(reports.get(key)))
        monkeypatch.setattr(result_store, 'read_many', lambda table, keys, **kwargs:
                            [deepcopy(reports[key]) for key in keys if key in reports])
        monkeypatch.setattr(store, 'stage_report', stage_report)
        monkeypatch.setattr(Path, 'unlink', lambda self, **kwargs: None)
        monkeypatch.setattr(engine, 'discard_diagnostic_files', lambda *args: None)
        ready = dict(simulation_config=dict(target_count=1, scene='single_target'),
                     context=dict(capabilities=capabilities), template_sha='memory-template', engines={})
        def run(runner=None, *, timeline=None, runtime=None):
            runtime = runtime or TaskRuntime(float('inf'), diagnostic_logging=search_config['diagnostic_logging'])
            if timeline is not None: runtime.search_timeline=timeline
            if formal and runner is None:
                from formal_search import run as run_formal
                return run_formal(profile=Path('/memory/standard.simc'), character=character,
                    capabilities=capabilities, reference=dict(dps=100., identity=dict(resource='runic_power')),
                    destination=Path('/memory/ga'), runtime=runtime, config=search_config,
                    condition_key=condition, store=store, simulation_config=ready['simulation_config'])
            execute = training._evolution(store, capabilities, runtime, config) if runner is None else runner
            return optimize(profile=Path('/memory/standard.simc'), character=character,
                capabilities=capabilities, reference=dict(identity=dict(resource='runic_power')),
                destination=Path('/memory/ga'), runtime=runtime, config=search_config,
                condition_key=condition, store=store, simulation_config=ready['simulation_config'],
                training=True, training_runner=execute, training_stage_plan=plan)
        return SimpleNamespace(store=store, config=config, starts=starts, capabilities=capabilities,
            character=character, plan=plan, calls=calls, reports=reports, run=run, ready=ready,
            manifest=manifest, condition=condition, search_config=search_config)
    yield make
    for store in stores:
        store.diagnostic_logging_override = False
        store.close()

def test_public_check_freezes_both_verified_heroes_and_four_groups(monkeypatch):
    from unittest.mock import mock_open, patch
    import engine
    import seed_training
    from simulation_config import TRAINING_DEFAULTS
    from test_character_export import sample_profile
    templates = (Path('/templates/Rider.simc'), Path("/templates/San'layn.simc"))
    monkeypatch.setattr(engine, 'training_templates', lambda: templates)
    monkeypatch.setattr(engine, 'identity', lambda mode: (Path('/engine'), dict(upstream_commit='fixed')))
    with patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'read_text', return_value=sample_profile()):
        result = seed_training.check_training(use_burst=False, training_config=dict(TRAINING_DEFAULTS))
    assert len(result['templates']) == 2
    assert {row['configuration_key']['hero_talent'] for row in result['groups']} == {
        'rider_of_the_apocalypse', 'sanlayn'}
    assert {row['configuration_key']['target_type'] for row in result['groups']} == {'single_target', 'aoe'}
    assert result['training_config']['max_trainings'] == 4
    assert result['training_config']['max_processes'] == 5
    assert result['final_requested_iterations_per_group'] == 15360


@pytest.mark.real
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
                     '--workspace', str(tmp_path / 'work'), '--legacy', '--diagnostic-logging', '--search-timeline']) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['status'] == 'completed'
    assert outcome['algorithm'] == 'ga-easimple-v1'
    assert outcome['population_size'] == 4
    assert outcome['complete_generations'] == 2
    import sqlite3
    from search import TaskStore
    folder = Path(outcome['task_path'])
    with sqlite3.connect(folder / 'task.sqlite3') as database:
        state = TaskStore.load_state(database)
    diagnostics = json.loads((folder / 'diagnostics.json').read_text())
    assert diagnostics['task_state_writes'] < state['native_batch_starts']
    with result_store.query("SELECT storage_group_key, count(*) FROM batches WHERE purpose != 'seed_reference' "
            'GROUP BY storage_group_key', tables=['batches']) as cursor:
        sizes = [row[1] for row in cursor.fetchall()]
    assert max(sizes) == 12 and sum(sizes) == 64 and len(sizes) <= 8
    curve, = folder.glob('search-timeline-*.json')
    timeline = json.loads(curve.read_text())
    assert timeline['status'] == 'completed'
    assert timeline['search_start_seconds'] <= timeline['search_stop_seconds'] <= timeline['result_saved_seconds']
    assert curve.with_suffix('.html').is_file()
    assert result_store.DATA_ROOT.joinpath('seed_candidates').is_dir()
    assert outcome['configuration_key'] == dict(specialization_id=252,
        hero_talent='rider_of_the_apocalypse', target_type='single_target')
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
        run_task(template, task_folder, search_config=dict())
        formal = read_task(task_folder)
        assert formal['search']['training_champion_snapshot']['status'] == 'not_applicable'
        assert not any(source['source_kind'] == 'training_champion'
            for group in formal['search']['start_sources'].values() for source in group)
        resumed = resume_task(task_folder)
        assert resumed['search']['training_champion_snapshot']['status'] == 'not_applicable'
        assert read_task(task_folder)['status'] == 'completed'
    from seed_training import sync_history, template_character
    registry = sync_history(template_character(sample_profile()))
    history = [row for row in registry if row['source_id'].startswith('history:')]
    assert len(history) == 1 and history[0]['active'] and history[0]['semantic'] == 'preserved'


@pytest.fixture
def registered_six(request):
    if request.node.get_closest_marker('real') is None:
        pytest.fail('registered_six requires a real result center')
    tmp_path = request.getfixturevalue('tmp_path')
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


def test_public_selection_reads_each_report_group_once_without_skipping_receipts(monkeypatch,memory_ga):
    from copy import deepcopy
    from weakref import WeakValueDictionary
    import population_training
    import result_store
    from search import digest
    case=memory_ga(settings=dict(top_k=6,retest_batches=4))
    ga=case.run()
    finals=[row for row in case.reports.values() if row['purpose']!='search']
    groups={f'group{index}':finals[at:at+12] for index,at in enumerate(range(0,len(finals),12))}
    for group,rows in groups.items():
        for row in rows:
            receipt=case.store.batch(row['batch_key'])
            case.store.put_batch(row['batch_key'],dict(receipt,storage_group_key=group))
    counts=dict(reports=0,summaries=0,validations=0,manifests=0)
    sizes=[]
    live=WeakValueDictionary()
    class Report(dict): pass
    duplicate=False
    def read_many(table,keys,**kwargs):
        counts['reports']+=1
        assert table=='batches' and len(keys)==1 and not live
        rows=[Report(deepcopy(row)) for row in groups[keys[0]]]
        if duplicate: rows[1]=rows[0]
        sizes.append(len(rows))
        live.update((id(row),row) for row in rows)
        assert len(live)<=12
        return rows
    batch,validate,hashed=case.store.batch,population_training._validate_saved_batch,population_training.digest
    first_key=finals[0]['batch_key']
    def summary(key):
        counts['summaries']+=1
        row=batch(key)
        return dict(row,storage_group_key=None) if key==first_key else row
    def verified(*args):
        counts['validations']+=1
        return validate(*args)
    def counted_digest(value):
        counts['manifests']+=value is case.manifest
        return hashed(value)
    monkeypatch.setattr(case.store,'batch',summary)
    monkeypatch.setattr(result_store,'read_many',read_many)
    monkeypatch.setattr(result_store,'report_locations',lambda keys:{first_key:'group0'})
    monkeypatch.setattr(Path,'exists',lambda path:path.name=='.report-locations.jsonl')
    monkeypatch.setattr(population_training,'_validate_saved_batch',verified)
    monkeypatch.setattr(population_training,'digest',counted_digest)
    key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target')
    rows=population_training._selected(ga,case.store,case.manifest,case.character,case.ready,key)
    assert len(rows)==4 and [row['candidate_id'] for row in rows]==sorted(row['candidate_id'] for row in rows)
    assert {row['score'] for row in rows}=={100.}
    assert counts==dict(reports=10,summaries=120,validations=120,manifests=1)
    assert sizes==[12]*10 and not live
    duplicate=True
    with pytest.raises(ValueError,match='发布复测报告重复'):
        population_training._selected(ga,case.store,case.manifest,case.character,case.ready,key)


@pytest.mark.parametrize('fail_one', [False, True])
@pytest.mark.real
def test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit(
        tmp_path, capsys, monkeypatch, registered_six, fail_one):
    from contextlib import ExitStack
    from copy import deepcopy
    from unittest.mock import patch
    import threading
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
    overlapping_scores = threading.Event()
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
            if active > 5:
                overlapping_scores.set()
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
            assert overlapping_scores.wait(10), '未观察到至少6路真实评分重叠'
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


@pytest.mark.parametrize('cancel_mode,initial_logging,resume_logging', [
    pytest.param('foreground', True, True, id='foreground-on_to_on'),
    pytest.param('foreground', False, True, id='foreground-off_to_on'),
    pytest.param('interrupt', True, False, id='interrupt-on_to_off'),
])
@pytest.mark.real
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


def test_public_training_accepts_verified_zero_stress_as_full_loss_without_retry(memory_ga):
    import population_training
    def score(candidate, options):
        stress = options['iterations'] == 128 and options['input_times'] != list(range(0, 180000, 300))
        return 0. if stress else 100.
    case = memory_ga(score_for=score)
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character,
        case.ready, dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    zeros = [folder for folder, _, options in case.calls
             if options['iterations'] == 128 and options['input_times'] != list(range(0,180000,300))]
    assert len(zeros) == len(set(zeros)) == 48
    assert all(row['evaluation']['stability_loss'] == 1. for row in rows)


@pytest.mark.parametrize('failure_kind,failures',
    [(kind, count) for kind in ('candidate', 'exit', 'missing', 'json', 'nan', 'inf', 'samples') for count in (1, 2)]
    + [('identity', 1), ('storage', 1), ('duration', 1)])
def test_public_run_retries_original_request_once_and_preserves_exhaustion_on_resume(
        monkeypatch, memory_ga, failures, failure_kind):
    from copy import deepcopy
    import engine
    from engine import CandidateError, NativeEvaluationError
    from test_search import _fast_report
    attempts = []
    def native(profile, candidate, folder, **options):
        attempts.append((options['seed'], tuple(options['input_times']), deepcopy(candidate)))
        bad = len(attempts) <= failures
        if bad and failure_kind == 'candidate':
            raise CandidateError('constructed native failure')
        if bad and failure_kind == 'exit':
            from types import SimpleNamespace
            from unittest.mock import patch
            process = SimpleNamespace(returncode=1, stdout=b'constructed failure', stderr=b'')
            with patch.object(Path, 'mkdir'), patch.object(engine, 'identity', return_value=(Path('/engine'), {})), \
                    patch.object(engine, 'run_command', return_value=process):
                return engine.run(profile, folder, runtime=options['runtime'])
        if bad and failure_kind in ('missing', 'json', 'storage'):
            # Parse/translate at the existing sequence IO seam, not in retry code.
            import sequence
            from unittest.mock import patch
            log = '\n'.join(f'S2GBLOCK\t{i}\t{j}\t{name}'
                for i, block in enumerate(sequence.compiled_program(candidate)) for j, name in enumerate(block))
            def read(path, **kwargs):
                if path.name == 'native.pending.json':
                    if failure_kind == 'missing': raise FileNotFoundError('missing report')
                    if failure_kind == 'storage': raise PermissionError('constructed report storage denied')
                    return '{broken'
                return 'fixture profile'
            with patch.object(Path, 'mkdir'), patch.object(Path, 'write_text'), \
                    patch.object(Path, 'read_text', read), patch.object(sequence, 'run', return_value=log):
                return original_sequence_evaluate(profile, candidate, folder, **options)
        report = _fast_report(options['character'],
            float(failure_kind) if bad and failure_kind in ('nan','inf') else 100.,
            30 if bad and failure_kind == 'samples' else 31)
        if bad and failure_kind == 'identity': report['sim']['targets'] *= 5
        if bad and failure_kind == 'duration':
            report['sim']['players'][0]['collected_data']['fight_length']['mean'] = 179
        summary = engine.check_report(report, options['character'], options['iterations'],
            simulation_config=options['simulation_config'], allow_zero=True)
        return dict(report=report, summary=summary, trace=[])
    import sequence
    original_sequence_evaluate = sequence.evaluate
    case = memory_ga(native=native)
    runner = lambda **callbacks: callbacks['evaluate'](case.starts[0], 'search', 0)
    retryable = failure_kind not in ('identity', 'storage', 'duration')
    if failures == 1 and retryable:
        assert case.run(runner)['dps'] == 100.
    else:
        error = (PermissionError if failure_kind == 'storage' else ValueError
                 if failure_kind in ('identity', 'duration') else CandidateError
                 if failure_kind == 'candidate' else engine.CandidateScoreError
                 if failure_kind in ('nan', 'inf') else NativeEvaluationError)
        reason = ('constructed native failure' if failure_kind == 'candidate' else
                  '原生引擎失败' if failure_kind == 'exit' else '原生报告缺失' if failure_kind in ('missing', 'json') else
                  '目标数量不符' if failure_kind == 'identity' else 'storage denied' if failure_kind == 'storage' else
                  '原生参考数值或实际样本数无效')
        with pytest.raises(error, match=reason): case.run(runner)
        before = deepcopy(attempts)
        if retryable:
            with pytest.raises(CandidateError, match='已用尽一次重试'): case.run(runner)
            assert attempts == before
        else:
            assert not case.store.state['training_failures']
    assert len(attempts) == (2 if retryable else 1)
    if retryable: assert attempts[0] == attempts[1]


def test_public_run_feedback_failure_uses_same_persistent_single_retry_budget(memory_ga):
    from engine import CandidateError
    def native(*args, **kwargs): raise CandidateError('constructed feedback failure')
    case = memory_ga(native=native)
    runner = lambda **callbacks: callbacks['feedback'](case.starts[0])
    with pytest.raises(CandidateError, match='constructed feedback failure'): case.run(runner)
    assert len(case.calls) == 2 and case.calls[0] == case.calls[1]
    assert list(case.store.state['training_failures'].values()) == [2]
    # Reload the actual persisted SQLite state, not a fabricated retry counter.
    case.store.state = case.store.load_state(case.store.db)
    with pytest.raises(CandidateError, match='已用尽一次重试'): case.run(runner)
    assert len(case.calls) == 2


@pytest.mark.parametrize('overflow', ['clicks', 'macro'])
def test_public_illegal_slot_uses_first_child_and_ten_persistent_extra_regenerations(
        monkeypatch, memory_ga, overflow):
    import random
    from types import SimpleNamespace
    import population_training
    operations = []
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow = real_random._randbelow
        def random(self): return .99
        def choice(self, values):
            if isinstance(values,list) and values and values[0]=='swap' and 'insert' in values:
                count = getattr(self,'operations',0)+1
                self.operations=count
                operation = ('insert' if overflow=='clicks' else 'block') if count==1 or count%2==0 else 'delete'
                operations.append(operation)
                return operation
            if overflow=='macro' and values==[0,1]: return 0
            return super().choice(values)
        def randrange(self,*args):
            if args==(2,): return 1 if overflow=='clicks' else 0
            return super().randrange(*args)
    program = ([['outbreak'],dict(kind='WaitClicks',clicks=4095)] if overflow=='clicks'
               else [['scourge_strike']*12,['outbreak']])
    case=memory_ga(programs=[program],settings=dict(mutation_probability=1.))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    for resume in (False,True):
        if resume: case.store.state=case.store.load_state(case.store.db)
        with pytest.raises(ValueError,match='已耗尽10次额外重生'): case.run()
        operation='insert' if overflow=='clicks' else 'block'
        assert operations==[operation,*[operation,'delete']*10]
        assert case.store.state['ga']['pending']['regenerations']==[10]


def test_public_a_tournament_and_block_crossover_keep_duplicate_slots_and_reuse_scores(monkeypatch,memory_ga):
    import random
    from types import SimpleNamespace
    import population_training
    draws=[]
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow=real_random._randbelow
        def random(self): return .5
        def choice(self,values):
            if values and hasattr(values[0],'fitness'):
                offset=len(draws)%len(values)
                draws.append(offset)
                return values[offset]
            return super().choice(values)
        def randint(self,first,last): return first
    case=memory_ga(settings=dict(crossover_probability=1.))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    ga=case.run()
    coarse=[tuple(tuple(command['simc_action'] for command in block) for block in candidate['blocks'])
            for _,candidate,options in case.calls if options['iterations']==32]
    assert len(draws)==6*3*2
    assert (('outbreak',),('scourge_strike',),('outbreak',)) in coarse
    assert (('death_coil',),('death_coil',),('scourge_strike',)) in coarse
    assert len(coarse)==len(set(coarse))==8
    slots=[row['key'] for row in ga['population']]
    assert len(slots)==6 and len(set(slots))==2
    assert len(case.calls)==68


@pytest.mark.parametrize('invalid_nominal', [False, True])
def test_public_selection_keeps_nominal_and_minimax_stability_champions_and_reports_ineligible(
        memory_ga, invalid_nominal):
    import population_training
    from itertools import permutations
    programs = {tuple((name,) for name in order): index for index, order in enumerate(
        permutations(('outbreak', 'death_coil', 'scourge_strike')))}
    nominal, stress = [200.,180.,160.,140.,120.,100.], [150.,162.,144.,139.,115.,110.]
    def score(candidate, options):
        index = programs[tuple(tuple(row['simc_action'] for row in block) for block in candidate['blocks'])]
        is_nominal = options['input_times'] == list(range(0,180000,300))
        return (0. if invalid_nominal and index == 5 and is_nominal and options['iterations'] == 128
                else nominal[index] if is_nominal else stress[index])
    case = memory_ga(settings=dict(top_k=6), score_for=score)
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character,
        case.ready, dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    assert {row['score'] for row in rows} == ({200.,180.,160.,140.} if invalid_nominal else {200.,180.,160.,100.})
    evaluations = {row['score']:row['evaluation'] for row in rows}
    assert evaluations[200.]['nominal_champion']
    assert evaluations[200.]['stability_loss'] == .25
    assert evaluations[140. if invalid_nominal else 100.]['stable_representative']
    if invalid_nominal:
        assert len(ga['ineligible']) == 1
        assert '正常复测均分≤0' in next(iter(ga['ineligible'].values()))
    else:
        assert evaluations[100.]['stability_loss'] == -.1
    assert sum(options['iterations']==32 for _,_,options in case.calls) == 6
    assert sum(options['iterations']==128 for _,_,options in case.calls) == 90
    seeds = {iterations:{options['seed'] for _,_,options in case.calls if options['iterations']==iterations}
             for iterations in (32,128)}
    assert len(seeds[128]) == 15 and not seeds[32] & seeds[128]


@pytest.mark.parametrize('version',[None,1,2,99])
def test_public_formal_entry_reads_legacy_contract_rejects_unknown_and_recycles_completed_winner(monkeypatch,memory_ga,version):
    from seed_training import selected_contract_version
    from task import _seed_programs
    from runtime import TaskRuntime
    case=memory_ga()
    key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target')
    rows=[dict(configuration_key=key,candidate_id='old-'+str(index),class_name='deathknight',spec='unholy',
        program=program,score=99999.,scores=[99999.]*3,template_sha256='different-role',
        **(dict(contract_version=version) if version is not None else {})) for index,program in enumerate(case.starts[:4])]
    if version==99:
        with pytest.raises(ValueError,match='不支持的训练成果契约版本'): selected_contract_version(rows)
        assert not case.calls
        return
    assert selected_contract_version(rows)==(1 if version is None else version)
    if version != 2:
        import result_store
        from seed_training import training_champion
        monkeypatch.setattr(result_store, 'read_records', lambda *args, **kwargs: [])
        assert training_champion('deathknight', 'unholy', case.ready['simulation_config'],
            engines={}, input_interval_ms=300, configuration_key=key)['status'] == 'absent'
    starts,decisions=_seed_programs([],rows,character=case.character,targets=1,configuration_key=key,
        capabilities=case.capabilities,runtime=TaskRuntime(float('inf')))
    assert len(starts)==4 and {row['status'] for row in decisions}=={'accepted'}
    case.store.state['starts']=starts
    ga=case.run()
    assert {row['score'] for row in ga['population']}=={100.},'旧模板成绩不得借用'
    # The completed-winner registry read/write chain remains in the public real run.


def test_public_configured_sample_plan_and_stagnation_are_used_without_old_stage_caps(memory_ga):
    case = memory_ga(settings=dict(coarse_iterations=4, retest_batches=2, retest_iterations=8,
                                  stagnation_generations=3, tournament_size=7))
    ga = case.run()
    requests = [options['iterations'] for _,_,options in case.calls]
    assert ga['generation'] == ga['stagnant'] == 3
    assert requests.count(4) == 6 and requests.count(8) == 40 and len(requests) == 46
    assert case.config['top_k'] * 5 * case.config['retest_batches'] * case.config['retest_iterations'] == 320


# Coarse recovery stays in memory below; physical publication recovery keeps one retest group.
@pytest.mark.parametrize('missing_stage', ['retest'])
@pytest.mark.real
def test_public_publication_failure_preserves_old_four_and_resume_repairs_only_missing_report_group(
        tmp_path, capsys, monkeypatch, registered_six, missing_stage):
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
        batch_key = first['batch_key']
        cached = json.loads(db.execute('SELECT value FROM batches WHERE key=?', [batch_key]).fetchone()[0])
        group = cached['storage_group_key']
        first['dps'] = 99999.  # Checkpoint summaries are not independent scoring evidence.
        db.execute("UPDATE state_fields SET value=? WHERE key='ga'", [json.dumps(state['ga'])])
    missing = result_store.read_records('batches', group)
    expected_missing = 12
    assert len(missing) == expected_missing
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
    assert len(fresh) == len(set(fresh)) == expected_missing
    current = result_store.read_records('seed_selected', scope)
    assert len(current) == 4
    assert {row['score'] for row in current} == {100.}
    assert {row['contract_version'] for row in current} == {2}


@pytest.mark.parametrize('mixed_new_groups',[False,True],ids=['all_frozen','mixed_new'])
def test_public_four_group_resume_uses_frozen_outer_pool_after_next_batch_toml_changes(monkeypatch,mixed_new_groups):
    from copy import deepcopy
    import population_training
    from simulation_config import TRAINING_DEFAULTS
    templates=[dict(template=str((Path('/templates')/f'{hero}.simc').resolve()),template_sha256=hero) for hero in ('rider','sanlayn')]
    old=dict(TRAINING_DEFAULTS)
    new=dict(old,max_trainings=10,max_processes=2) if mixed_new_groups else dict(old,max_trainings=1,max_processes=1)
    manifests=[(Path('/saved')/f'{index}-{count}',dict(template_path=row['template'],
        environment=dict(template=row['template_sha256'],simulation=dict(target_count=count)),training_config=deepcopy(old)))
        for index,row in enumerate(templates) for count in ((1,) if mixed_new_groups else (1,5))]
    before=deepcopy(manifests)
    monkeypatch.setattr(population_training,'_unfinished',lambda workspace:iter(manifests))
    configs=population_training.group_configs('/memory',templates,new)
    assert len(configs)==4
    assert population_training.group_workers('/memory',templates,new,effective_configs=configs)==4
    for (path,count),config in configs.items():
        fresh=mixed_new_groups and count==5
        assert config['max_trainings']==(10 if fresh else 4)
        assert config['max_processes']==(2 if fresh else 5)
    assert 4*max(row['max_processes'] for row in configs.values())==20
    assert manifests==before


def test_public_resume_verifies_coarse_before_breeding_and_keeps_temporary_read_errors(monkeypatch,memory_ga):
    from copy import deepcopy
    import population_training
    import result_store
    from runtime import TaskCancelled
    case=memory_ga(settings=dict(mutation_probability=1.))
    def pause(**callbacks):
        for program in case.starts: callbacks['evaluate'](program,'search',0)
        raise TaskCancelled('pause before breeding')
    with pytest.raises(TaskCancelled): case.run(pause)
    keys={row['batches'][0]['data_key'] for row in case.store.state['archive']}
    assert len(keys)==6
    case.store.state['ga'].update(phase='breed',population=[dict(program=deepcopy(row['program']),key=row['key'],score=row['score'])
        for row in case.store.state['archive']],baseline=[100.]*4)
    case.store.checkpoint()
    attempts=[]
    def unavailable(table,field,key,**kwargs):
        attempts.append(key)
        raise result_store.DataReadError('constructed temporary coarse read failure')
    case.store.verified_batches.clear()
    case.calls.clear()
    monkeypatch.setattr(result_store,'one',unavailable)
    with pytest.raises(result_store.DataReadError,match='temporary coarse read failure'): case.run()
    assert attempts and len(attempts)==len(set(attempts)) and not case.calls
    # Missing reliable IO evidence is repaired by the original evaluator, before mutation.
    verified=[]
    def missing(table,field,key,**kwargs):
        verified.append(key)
        return None
    monkeypatch.setattr(result_store,'one',missing)
    def mutation(*args,**kwargs): raise TaskCancelled('original feedback may resume after repair')
    with monkeypatch.context() as breeding:
        breeding.setattr(population_training,'mutate',mutation)
        with pytest.raises(TaskCancelled,match='after repair'): case.run()
    assert set(verified)==keys and len(verified)==len(keys)
    assert {Path(folder).name for folder,_,options in case.calls if options['iterations']==32}==keys
    assert len(case.calls)==6

    # Qualified recovery replaces only the missing coarse group, not successful retests.
    case=memory_ga()
    assert case.run()['phase']=='qualified'
    requests={key:deepcopy(case.store.batch(key)['request']) for key in case.reports}
    coarse={key for key,request in requests.items() if request['purpose']=='search'}
    retained={key:(deepcopy(case.reports[key]),deepcopy(case.store.batch(key)))
              for key in requests if key not in coarse}
    assert len(coarse)==6 and len(retained)==60 and len(case.calls)==66
    for key in coarse: case.reports.pop(key)
    case.store.verified_batches.clear()
    case.calls.clear()
    assert case.run()['phase']=='qualified'
    assert {Path(folder).name for folder,_,_ in case.calls}==coarse
    assert len(case.calls)==6 and all(options['iterations']==32 for _,_,options in case.calls)
    assert len(case.reports)==case.store.state['completed_batches']==66
    assert {key:case.store.batch(key)['request'] for key in case.reports}==requests
    assert {key:(case.reports[key],case.store.batch(key)) for key in retained}==retained


def test_public_alias_template_cannot_bypass_frozen_group_scheduling(monkeypatch):
    from copy import deepcopy
    import population_training
    import seed_training
    from simulation_config import TRAINING_DEFAULTS
    original=str(Path('/templates/original.simc').resolve())
    alias=str(Path('/templates/copied.simc').resolve())
    manifest=dict(template_path=original,training_config=dict(TRAINING_DEFAULTS,max_trainings=1,max_processes=16),
        environment=dict(template='same-role-bytes',simulation=dict(target_count=1)))
    frozen=deepcopy(manifest)
    def unfinished(workspace,**options):
        return iter([(Path('/saved/task'),manifest)]) if not options or options.get('scope') else iter(())
    monkeypatch.setattr(population_training,'_unfinished',unfinished)
    templates=[dict(template=alias,template_sha256='same-role-bytes')]
    with pytest.raises(ValueError,match='跨模板路径.*原模板路径'):
        population_training.group_configs('/memory',templates,dict(TRAINING_DEFAULTS,max_trainings=10,max_processes=2))
    # Public API uses the same scope guard before creating a task directory or scoring.
    context=dict(configuration_key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target'),burst=None)
    monkeypatch.setattr(Path,'glob',lambda *args:iter(()))
    monkeypatch.setattr(seed_training,'ensure_prepared',lambda *args,**kwargs:dict(context=context,queue=[{}],
        template_sha='same-role-bytes',engines={},simulation_config=dict(target_count=1),config={}))
    import task
    monkeypatch.setattr(task,'_rule_hashes',lambda **kwargs:{})
    with pytest.raises(ValueError,match='跨模板路径'):
        population_training.run_group(alias,1,'/memory',cancel_event=None,use_burst=False,sources=[],config=TRAINING_DEFAULTS)
    assert manifest==frozen


def test_public_run_training_defaults_really_cross_and_mutate_without_global_rng_patch(monkeypatch,memory_ga):
    import random
    from types import SimpleNamespace
    import population_training
    from deap import algorithms
    original=algorithms.random
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow=real_random._randbelow
        def random(self): return .5
    case=memory_ga(settings=dict(crossover_probability=.8,mutation_probability=.8))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    ga=case.run()
    coarse=[folder for folder,_,options in case.calls if options['iterations']==32]
    assert ga['algorithm']=='ga-easimple-v1' and ga['generation']==2
    assert len(ga['population'])==6 and len(coarse)==len(set(coarse))>6
    assert all(options['iterations']!=2 for _,_,options in case.calls)
    assert algorithms.random is original


@pytest.mark.parametrize('entry',['cli','api'])
@pytest.mark.parametrize('enabled',[False,True])
def test_public_ga_timeline_switch_exports_existing_scores_without_extra_evaluations(monkeypatch,memory_ga,enabled,entry):
    import argparse
    from unittest.mock import patch
    import simulation_config
    from search_timeline import Timeline
    if entry=='cli':
        parser=argparse.ArgumentParser()
        simulation_config.add_search_arguments(parser)
        parsed=parser.parse_args(['--search-timeline'] if enabled else ['--no-search-timeline'])
        options=simulation_config.load_search_config(search_timeline=parsed.search_timeline)
    else: options=simulation_config.load_search_config(search_timeline=enabled)
    assert options['search_timeline'] is enabled
    case=memory_ga()
    timeline=Timeline(context=dict(algorithm=dict(training='ga-easimple-v1'))) if enabled else None
    if timeline is not None: timeline.start()
    case.run(timeline=timeline)
    assert len(case.calls)==len({row[0] for row in case.calls})==66
    writes=[]
    if enabled:
        timeline.stop('stagnation')
        timeline.saved('completed')
        with patch.object(Path,'mkdir'),patch.object(Path,'write_text',lambda path,text,**kwargs:writes.append((path,text))):
            path=timeline.finish('/memory/ga')
        curve=json.loads(next(text for file,text in writes if file.suffix=='.json'))
        assert curve['schema']=='sim2gse-search-timeline-v1' and curve['status']=='completed'
        assert curve['search_start_seconds']<=curve['search_stop_seconds']<=curve['result_saved_seconds']
        assert curve['context']['algorithm']['training']=='ga-easimple-v1'
        assert {row['series'] for row in curve['events'] if row['kind']=='score'}=={'search','nominal','jitter','pause','slow','phase'}
        assert path.with_suffix('.html') in {file for file,text in writes}
    else: assert writes==[]


def test_public_feedback_commits_at_twelve_and_replays_same_generation_rng(monkeypatch,memory_ga):
    from copy import deepcopy
    from itertools import islice,product
    import population_training
    from runtime import TaskCancelled
    from search import digest
    programs=[[[name] for name in order] for order in islice(product(('outbreak','death_coil','scourge_strike'),repeat=4),70)]
    case=memory_ga(programs=programs,settings=dict(mutation_probability=1.))
    # Native scoring remains a report input; this probe concerns the existing
    # bounded feedback checkpoint callback, not physical report publication.
    real_stage,real_checkpoint=case.store.stage_report,case.store.checkpoint
    real_mutate=population_training.mutate
    mutations,checkpoints=[],[]
    mode=1
    def staged(key,row,stored,**kwargs):
        real_stage(key,row,stored,**kwargs)
        if row['request']['purpose']=='feedback': case.store.report_buffer.append((key,row,{}))
    def checkpoint():
        size=len(case.store.report_buffer)
        feedback=sum(options['iterations']==2 for _,_,options in case.calls)
        pending=case.store.state['ga']['pending'] is not None
        if feedback and case.store.state['ga']['phase']=='breed': checkpoints.append((size,feedback,pending))
        case.store.report_buffer.clear()  # Explicit report publisher IO boundary.
        real_checkpoint()
        if feedback and case.store.state['ga']['phase']=='breed' and (mode==1 or pending):
            raise TaskCancelled('checkpoint interruption')
    def mutation(program,capabilities,rng,**kwargs):
        before=digest(rng.getstate())
        result=real_mutate(program,capabilities,rng,**kwargs)
        mutations.append((deepcopy(list(program)),before,deepcopy(result),digest(rng.getstate())))
        return result
    monkeypatch.setattr(case.store,'stage_report',staged)
    monkeypatch.setattr(case.store,'checkpoint',checkpoint)
    monkeypatch.setattr(population_training,'mutate',mutation)
    with pytest.raises(TaskCancelled): case.run()
    assert checkpoints[0]==(12,12,False) and max(row[0] for row in checkpoints)<=12
    paused=case.store.load_state(case.store.db)['ga']
    assert paused['generation']==0 and paused['pending'] is None
    first=deepcopy(mutations)
    mutations.clear()
    case.store.state=case.store.load_state(case.store.db)
    mode=2
    with pytest.raises(TaskCancelled): case.run()
    assert mutations[:len(first)]==first
    feedback=[folder for folder,_,options in case.calls if options['iterations']==2]
    assert len(feedback)==len(set(feedback))>12
    assert max(row[0] for row in checkpoints)<=12
    resumed=case.store.load_state(case.store.db)['ga']
    assert resumed['generation']==0 and len(resumed['pending']['programs'])==70


@pytest.mark.real
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
