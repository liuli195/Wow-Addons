"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
from contextlib import contextmanager


@contextmanager
def training_boundary(damage_for=lambda candidate: 100.):
    from test_search import _fast_search_boundary, _fast_evaluate
    from unittest.mock import patch
    import sequence

    def evaluate(profile, candidate, folder, **kwargs):
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        damage = damage_for(candidate)
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        Path(folder, 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result

    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        yield

import pytest


@pytest.fixture(autouse=True)
def training_center(tmp_path, installed_data_store, monkeypatch):
    import result_store
    (tmp_path / 'data').mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    subprocess.run([sys.executable, str(installed_data_store / 'scripts/project_binding.py'),
                    'connect', '--project', str(tmp_path)], check=True, capture_output=True)


def command(tmp_path, args):
    from seed_training import main
    # These existing cases exercise the explicitly retained legacy training mode.
    if args[0] in ('run', 'list') and '--use-burst' not in args:
        args = [*args, '--legacy']
    return main(['--project', str(tmp_path), *args])


def test_training_check_locates_current_template_without_starting_compute(tmp_path, capsys, monkeypatch):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('只读训练检查不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    assert main(['--project', str(tmp_path), 'check', '--legacy']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'ready'
    assert '/.tools/sim2gse/build/baseline/' in result['template'].replace('\\', '/')
    assert result['engines']['baseline']['upstream_commit'] == result['engines']['controlled']['upstream_commit']
    assert not (tmp_path / 'work').exists()


def test_training_check_refuses_missing_review_before_starting_compute(tmp_path, capsys, monkeypatch):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('未审核角色不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    assert main(['--project', str(tmp_path), 'check']) == 2
    assert '已审核' in capsys.readouterr().err


def test_training_list_defaults_to_burst_and_preserves_legacy_results(tmp_path, capsys):
    from seed_training import main, SELECTED_SCHEMA
    import result_store

    row = dict(candidate_id='legacy-only', condition='fixture', class_name='deathknight', spec='unholy',
               targets=1, program=[['death_coil']], family='fixture', score=1., scores=[1.],
               template_sha256='fixture', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [row], schema=SELECTED_SCHEMA)
    assert main(['--project', str(tmp_path), 'list', '--state', 'selected']) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(['--project', str(tmp_path), 'list', '--state', 'selected', '--legacy']) == 0
    assert json.loads(capsys.readouterr().out)[0]['candidate_id'] == 'legacy-only'


def test_cleaned_candidate_registration_is_reusable_and_rejects_missing_provenance(tmp_path, capsys):
    from seed_training import main
    import result_store

    source = tmp_path / 'cleaned.json'
    source.write_text(json.dumps(dict(label='ABC-C', spec='unholy', class_name='deathknight',
        source='plugin:Smolbreather', original='15 ordered spell ids',
        instructions='continuous unmodified key', semantic='rewritten',
        changes=['remove movement'], family='plugin-opener', core=[['putrefy'], ['death_coil']],
        program=[['outbreak'], ['putrefy'], ['death_coil']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    assert command(tmp_path, ['register', str(source)]) == 0
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    lines = capsys.readouterr().out.splitlines()
    candidates = json.loads(lines[-1])
    assert len(candidates) == 1
    assert candidates[0]['label'] == 'ABC-C'
    assert result_store.DATA_ROOT.joinpath('seed_candidates').is_dir()
    invalid = json.loads(source.read_text())
    invalid.pop('changes')
    source.write_text(json.dumps(invalid), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) != 0
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    assert len(json.loads(capsys.readouterr().out.splitlines()[-1])) == 1


def test_training_command_stops_after_two_unimproved_rounds_and_reuses_completed_work(tmp_path, capsys):
    from seed_training import main
    from test_character_export import sample_profile
    from unittest.mock import patch
    import sequence
    import result_store

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='test', class_name='deathknight', spec='unholy',
        source='constructed-test', original='independent fixture', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile() + '\nactions=auto_attack\n', encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    real_write = result_store.write
    def failing_publish(table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise PermissionError('发布目标暂时不可写')
        return real_write(table, key, rows, **kwargs)
    with training_boundary(), patch.object(result_store, 'write', side_effect=failing_publish):
        assert command(tmp_path, args) == 2
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1')
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert len(processed) == 1
    assert processed[0]['rounds'] == 2
    assert processed[0]['stop_reason'] == 'no_improvement'
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'selected', '--targets', '1']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0


@pytest.mark.parametrize('partial_improvement', [False, True])
def test_training_improvements_reset_stagnation_and_can_exceed_five_rounds(tmp_path, partial_improvement):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import random
    import result_store
    import search

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='improving', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    proposals = {}
    scores = {}

    class NoFallbackShuffle(random.Random):
        def randrange(self, *args, **kwargs):
            return 1 if args == (16,) else super().randrange(*args, **kwargs)

    def growing_program(parent, *args, **kwargs):
        size = len(parent) + 4
        positions = [(a, b) for a in range(size) for b in range(size) if a != b]
        key = json.dumps(parent, sort_keys=True)
        index = proposals.get(key, 0)
        round_index = sum(proposals.values()) // 16
        proposals[key] = index + 1
        if partial_improvement and len(parent) == 3 and index >= 24:
            return None
        a, b = positions[index % len(positions)]
        program = [['outbreak'] for _ in range(size)]
        program[a], program[b] = ['death_coil'], ['scourge_strike']
        if partial_improvement:
            score = 103. if len(parent) == 3 and index < 16 else 107.
        else:
            score = (103., 107., 107., 111., 113., 113., 113.)[round_index]
        scores[json.dumps(program)] = score
        return program

    def damage_for(candidate):
        program = [[action['simc_action'] for action in block] for block in candidate['blocks']]
        return scores.get(json.dumps(program), 103.)

    with training_boundary(damage_for), \
            patch.object(search, 'mutate', side_effect=growing_program), \
            patch.object(search.random, 'Random', NoFallbackShuffle):
        assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
                                  '--workspace', str(tmp_path / 'work')]) == 0
    completed = result_store.read_records('seed_processed', 'deathknight-unholy-1')[0]
    assert completed['status'] == 'completed'
    assert completed['rounds'] == (4 if partial_improvement else 7)
    assert completed['stop_reason'] == 'no_improvement'
    assert completed['scores'] == [107. if partial_improvement else 113.] * 3
    with sqlite3.connect('file:' + Path(completed['task_path'], 'task.sqlite3').as_posix() + '?mode=ro',
                         uri=True) as database:
        state = search.TaskStore.load_state(database)
    assert state['no_improvement'] == 2
    assert len(state['chains']) == 1


def test_training_budget_stop_keeps_progress_and_previous_selected_snapshot(tmp_path):
    from test_character_export import sample_profile
    from unittest.mock import patch
    from runtime import BudgetExceeded
    import result_store
    import sequence
    from test_search import _fast_evaluate

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='budget', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, args) == 0
    previous = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    assert previous
    template.write_text(sample_profile() + '\n# changed template\n', encoding='utf-8')
    def budget_on_first_round(*args, **kwargs):
        if kwargs.get('trace') and kwargs.get('iterations') == 2:
            raise BudgetExceeded('训练预算耗尽')
        return _fast_evaluate(*args, **kwargs)

    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=budget_on_first_round):
        assert command(tmp_path, args) == 2
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == previous
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    failed = next(row for row in processed if row['status'] == 'failed')
    assert failed['stop_reason'] == 'search_deadline'
    assert '未收敛' in failed['error']
    assert Path(failed['task_path'], 'task.sqlite3').exists()


def test_unexpressible_material_is_retained_but_not_trained(tmp_path, capsys):
    source = tmp_path / 'unsupported.json'
    source.write_text(json.dumps(dict(label='two state machines', class_name='deathknight', spec='unholy',
        source='community original', original='/castsequence A,null\n/castsequence B,C',
        instructions='author instructions retained', semantic='unsupported', changes=['multiple stateful commands'],
        family='unexpressible', core=[], program=[])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    assert command(tmp_path, ['list', '--state', 'unsupported']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert rows[0]['original'] == '/castsequence A,null\n/castsequence B,C'
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == []


def test_history_candidate_is_retested_and_changed_template_is_not_reused(tmp_path, capsys):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import sequence
    import result_store

    # Existing public center schemas, not a substitute history reader.
    result_store.write('runs', 'historic-1', [dict(dict.fromkeys(result_store.RUN_SCHEMA),
        run_id='historic-1', status='completed',
        profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
        candidate_data_key='historic-candidate', search_dps=90.)], schema=result_store.RUN_SCHEMA)
    shared = {'adapter': 'search', 'metadata': {}, 'nodes': [
        {'kind': 'Action', 'commands': [{'kind': 'spell', 'simc_action': name}]}
        for name in ('outbreak', 'death_coil', 'scourge_strike')]}
    result_store.write('candidates', 'historic-candidate', [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
        run_id='historic-1',
        candidate_key='historic-key', candidate_data_key='historic-candidate', source='search',
        program=shared)], schema=result_store.CANDIDATE_SCHEMA)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])[0]
    assert json.loads(first['initial_program']) == [['outbreak'], ['death_coil'], ['scourge_strike']]
    template.write_text(sample_profile() + '\n# new template revision\n', encoding='utf-8')
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=ValueError('新条件重新计算')):
        assert command(tmp_path, args) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len({row['condition'] for row in rows}) == 2
    assert any(row['status'] == 'failed' for row in rows)


def test_training_skips_history_matching_completed_final_and_keeps_new_history(tmp_path, capsys):
    from test_character_export import sample_profile
    import result_store

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='training seed', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three ordered actions', instructions='repeat',
        semantic='rewritten', changes=['use a short test program'], family='test-seed', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, args) == 0

    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    existing = json.loads(capsys.readouterr().out.splitlines()[-1])
    completed = next(row for row in existing if row['status'] == 'completed')
    initial = json.loads(completed['initial_program'])
    final = json.loads(completed['program'])
    assert completed['rounds'] == 2

    alternatives = [
        [['scourge_strike'], ['outbreak'], ['death_coil']],
        [['death_coil'], ['scourge_strike'], ['outbreak']],
        [['outbreak', 'death_coil'], ['scourge_strike']],
    ]
    distinct = next(program for program in alternatives if program not in (initial, final))

    def shared_program(program):
        nodes = []
        for segment in program:
            if isinstance(segment, list):
                nodes.append(dict(kind='Action', commands=[
                    dict(kind='spell', simc_action=action) for action in segment]))
            elif isinstance(segment, dict) and segment.get('kind') == 'CastSequence':
                nodes.append(dict(kind='Action', commands=[dict(
                    kind='castsequence', members=segment['members'], reset=segment.get('reset'))]))
            elif isinstance(segment, dict) and segment.get('kind') == 'Loop':
                nodes.append(dict(kind='Loop', step_function='Sequential', count=segment['count'],
                    body=[dict(kind='Action', commands=[dict(kind='spell', simc_action=action)
                           for action in block]) for block in segment['blocks']]))
            elif isinstance(segment, dict) and segment.get('kind') == 'WaitClicks':
                nodes.append(dict(kind='Pause', duration_ms=None, clicks=segment['clicks']))
            else:
                raise AssertionError(f'训练产物有未覆盖的搜索结构: {segment!r}')
        return dict(adapter='search', metadata={}, nodes=nodes)

    history = [
        ('history-final', final),
        ('history-new', distinct),
    ]
    for run_id, program in history:
        data_key = run_id + '-candidate'
        result_store.write('runs', run_id, [dict(dict.fromkeys(result_store.RUN_SCHEMA),
            run_id=run_id, status='completed',
            profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
            candidate_data_key=data_key, search_dps=90.)], schema=result_store.RUN_SCHEMA)
        result_store.write('candidates', data_key, [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
            run_id=run_id, candidate_key=run_id, candidate_data_key=data_key, source='search',
            program=shared_program(program))], schema=result_store.CANDIDATE_SCHEMA)

    with training_boundary():
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    processed = json.loads(capsys.readouterr().out.splitlines()[-1])
    history_rows = [row for row in processed if row['family'] == 'history-search']
    duplicate = next(row for row in history_rows if json.loads(row['initial_program']) == final)
    new_candidate = next(row for row in history_rows if json.loads(row['initial_program']) == distinct)
    assert duplicate['status'] == 'rejected'
    assert '相同行为候选:' in duplicate['error']
    assert new_candidate['status'] == 'completed'
    assert result_store.read_records('runs', 'history-final')
    assert result_store.read_records('candidates', 'history-final-candidate')


def test_normal_search_keeps_four_original_starts_and_reads_one_legal_snapshot(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
    from task import run_task
    from unittest.mock import patch
    import result_store

    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    engines = {mode: dict(mode=mode, upstream_commit='test', build_options=[])
               for mode in ('baseline', 'controlled')}
    accepted = [
        ['outbreak'], ['death_coil'], ['scourge_strike'], ['dark_transformation'], ['outbreak']]
    additional = [accepted,
                  [['scourge_strike'], ['dark_transformation'], ['outbreak'], ['death_coil'], ['scourge_strike']],
                  [['death_coil'], ['dark_transformation'], ['scourge_strike'], ['outbreak'], ['death_coil']],
                  [['dark_transformation'], ['scourge_strike'], ['death_coil'], ['outbreak'], ['dark_transformation']],
                  [['outbreak'], ['scourge_strike'], ['dark_transformation'], ['death_coil'], ['outbreak']]]
    changed_after_start = [['death_coil'], ['outbreak'], ['death_coil'], ['outbreak'], ['death_coil']]
    rows = [
        *[dict(candidate_id=f'valid-{index}', condition='condition', class_name='deathknight', spec='unholy',
               targets=1, program=program, family='community', score=100. - index,
               scores=[100. - index] * 3, template_sha256='template', engines=engines)
          for index, program in enumerate(additional)],
        dict(candidate_id='illegal', condition='condition', class_name='deathknight', spec='unholy',
             targets=1, program=[['not_a_character_action']], family='community', score=99.,
             scores=[99., 99., 99.], template_sha256='template', engines=engines),
        dict(candidate_id='oversized', condition='condition', class_name='deathknight', spec='unholy',
             targets=1, program=[['outbreak'] * 40], family='community', score=98.5,
             scores=[98.5, 98.5, 98.5], template_sha256='template', engines=engines),
        dict(candidate_id='wrong-targets', condition='condition', class_name='deathknight', spec='unholy',
             targets=5, program=changed_after_start, family='community', score=98.,
             scores=[98., 98., 98.], template_sha256='template', engines=engines),
    ]
    result_store.write('seed_selected', 'deathknight-unholy-1', rows,
                       schema=__import__('seed_training').SELECTED_SCHEMA)
    real_read = result_store.read_records
    selected_reads = []

    def changing_snapshot(table, key):
        if table == 'seed_selected':
            selected_reads.append((table, key))
            return rows if len(selected_reads) == 1 else [dict(rows[0], program=changed_after_start)]
        return real_read(table, key)

    config = dict(total_budget_seconds=60, search_budget_seconds=10, candidate_limit=8,
                  round_candidate_limit=1, batch_targets=(2,), validation_batches=2,
                  final_batches=1, iterations=2, final_iterations=2,
                  scenarios=('nominal',), max_processes=1)
    with _fast_search_boundary(), patch.object(result_store, 'read_records', side_effect=changing_snapshot):
        result = run_task(template, tmp_path / 'normal-search', search_config=config)

    assert result['status'] == 'completed'
    starts = result['search']['starts']
    assert len(starts) == 8
    assert starts[-4:] == additional[:4]
    assert additional[4] not in starts
    assert changed_after_start not in starts
    assert [['outbreak'] * 40] not in starts
    assert len(selected_reads) == 1


def test_training_entry_rejects_an_active_foreground_search(tmp_path, monkeypatch):
    from seed_activity import foreground_search
    import seed_training

    calls = []
    template = tmp_path / 'standard.simc'
    template.write_text('unused by the training stub', encoding='utf-8')
    monkeypatch.setattr(seed_training, '_run_training',
                        lambda *args, **kwargs: calls.append((args, kwargs)))
    with foreground_search():
        result = seed_training.main(['--project', str(tmp_path), 'run', '--template', str(template),
                                     '--targets', '1', '--workspace', str(tmp_path / 'work')])

    assert result == 2
    assert calls == []


def test_foreground_search_does_not_wait_for_training_and_stops_it(tmp_path):
    import os
    import subprocess
    import sys
    import time
    from seed_activity import training_activity
    import seed_activity

    root = str(tmp_path)
    module_dir = str(Path(seed_activity.__file__).parent)
    code = '\n'.join((
        'import sys,time',
        'sys.path.insert(0, ' + repr(module_dir) + ')',
        'import result_store',
        'result_store.bind_project(' + repr(root) + ')',
        'from seed_activity import foreground_search',
        'with foreground_search():',
        '    time.sleep(0.3)',
    ))
    environment = os.environ.copy()
    started = time.monotonic()
    with training_activity(poll_seconds=0.01) as cancel_event:
        child = subprocess.Popen([sys.executable, '-c', code], cwd=str(Path(seed_activity.__file__).parents[2]),
                                 env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            _, error = child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise AssertionError('普通搜索被训练等待')
        assert child.returncode == 0, error.decode(errors='replace')
        assert time.monotonic() - started < 2
        assert cancel_event.wait(0.3)


def test_missing_project_and_unreadable_center_are_not_silently_empty(tmp_path, monkeypatch):
    from seed_training import main
    import result_store
    import runpy
    with pytest.raises(SystemExit):
        main(['list'])
    real_loader = runpy.run_path
    def unreadable_loader(path):
        api = real_loader(path)
        def unreadable(*args, **kwargs):
            raise PermissionError('数据中心暂时不可读')
        api['read_key'] = unreadable
        return api
    monkeypatch.setattr(runpy, 'run_path', unreadable_loader)
    assert command(tmp_path, ['list']) == 2


def test_unconnected_public_search_does_not_create_data_root(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from task import run_task
    import result_store

    data_root = tmp_path / 'unconnected' / 'data'
    monkeypatch.setattr(result_store, 'DATA_ROOT', data_root)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    monkeypatch.setattr(result_store, '_SKILL_API', None)
    monkeypatch.setattr(result_store, '_skill_root', lambda: tmp_path / 'missing-skill')
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')

    with pytest.raises(RuntimeError, match='数据中心尚未接入本项目'):
        run_task(template, tmp_path / 'unconnected-task')

    assert not data_root.exists()


def test_connected_public_search_creates_data_root_on_first_run(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
    from task import run_task
    import result_store

    data_root = tmp_path / 'first-run-center' / 'data'
    monkeypatch.setattr(result_store, 'DATA_ROOT', data_root)
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    config = dict(total_budget_seconds=60, search_budget_seconds=10, candidate_limit=2,
                  round_candidate_limit=1, batch_targets=(2,), validation_batches=2,
                  final_batches=1, iterations=2, final_iterations=2,
                  scenarios=('nominal',), max_processes=1)

    assert not data_root.exists()
    with _fast_search_boundary():
        result = run_task(template, tmp_path / 'first-run-task', search_config=config)

    assert result['status'] == 'completed'
    assert data_root.is_dir()
    assert (data_root / '.seed-activity').is_dir()
