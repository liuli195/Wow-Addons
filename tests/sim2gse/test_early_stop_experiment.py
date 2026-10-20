"""隔离MVP运行器通过真实任务入口比较早停，不改变产品默认。"""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from test_search import REPOSITORY, _fast_search_boundary, _guided_search_boundary, sample_profile
from test_rule_diagnostics import _observed_evaluate


def _runner():
    path = REPOSITORY / 'scripts/dev/sim2gse/sanlayn_four_case.py'
    spec = importlib.util.spec_from_file_location('sanlayn_experiment', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_progress_experiment_keeps_global_winner_and_stops_after_new_stagnation(tmp_path):
    import result_store
    import search
    from task import run_task

    starts = [
        [['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
        [['outbreak'], ['scourge_strike'], ['death_coil']],
    ]

    def scored(profile, candidate, folder, **kwargs):
        result = _observed_evaluate(profile, candidate, folder, **kwargs)
        blocks = result['blocks']
        damage = (1000.0 if ['epidemic'] in blocks else
                  100.0 if blocks == starts[1] else 200.0)
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result

    original = Path(search.__file__).read_text(encoding='utf-8')
    outcomes = {}
    for policy in ('on', 'route-progress'):
        directory = tmp_path / policy
        directory.mkdir()
        source = directory / 'role.simc'
        source.write_text(sample_profile(), encoding='utf-8')
        namespace = dict(search.__dict__)
        effective = _runner().experiment_source(original, policy)
        exec(compile(effective, search.__file__, 'exec'), namespace)
        with _guided_search_boundary(directory, starts, evaluate=scored), \
                patch.object(search, 'optimize', namespace['optimize']), \
                patch.object(result_store, 'DATA_ROOT', directory / 'center'):
            outcomes[policy] = run_task(source, directory / 'task', search_config=dict(
                input_interval_ms=200, candidate_limit=16, round_candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=2, max_processes=1))

    control, experiment = outcomes['on'], outcomes['route-progress']
    for result in (control, experiment):
        assert result['status'] == 'completed'
        assert result['search']['stop_reason'] == 'no_improvement'
        assert result['search']['no_improvement_round_limit'] == 2
        assert result['search_result']['dps'] == 1000.0
        assert result['search']['records'][0]['key'] == result['locked_candidate_key']
        records = {row['key']: row for row in result['search']['records']}
        assert records[result['search']['chains'][1]['best']]['score'] == 200.0
    assert control['search']['rounds'] == 2
    assert experiment['search']['rounds'] == 4
    assert Path(search.__file__).read_text(encoding='utf-8') == original


def test_experiment_timeline_records_initial_result_without_waiting_for_save(tmp_path):
    import search
    from task import run_task

    runner = _runner()
    timeline = runner.Timeline('on', expected_paths=1, clock=iter(range(0, 1000)).__next__)
    original = Path(search.__file__).read_text(encoding='utf-8')
    namespace = dict(search.__dict__)
    effective = runner.experiment_source(original, 'on', observe=True)
    exec(compile(effective, search.__file__, 'exec'), namespace)
    observations = []
    original_record = timeline.record

    def observed(kind, state, row=None, reason=None):
        if kind == 'best':
            observations.append(('best', row['key']))
        original_record(kind, state, row, reason)

    real_checkpoint = search.TaskStore.checkpoint

    def checkpoint(store):
        value = real_checkpoint(store)
        observations.append(('checkpoint', store.state.get('best')))
        return value

    namespace['_experiment_event'] = observed
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary(), patch.object(search, 'optimize', namespace['optimize']), \
            patch.object(search.TaskStore, 'checkpoint', checkpoint):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2,
            max_processes=1))
    output = timeline.finish(result['status'])
    winner = result['locked_candidate_key']
    assert [item for item in observations if item[0] == 'best'] == [('best', winner)]
    assert observations.index(('best', winner)) < observations.index(('checkpoint', winner))
    assert output['events'][0]['kind'] == 'initial'
    assert output['events'][0]['dps'] == result['search_result']['dps']
    assert output['events'][0]['candidate_key'] == result['locked_candidate_key']
    assert output['search_stop_seconds'] < output['call_seconds']
    assert output['stop_reason'] == 'candidate_limit'
    assert len(output['samples']) == 60
    assert output['samples'][0]['seconds'] == 10
    assert output['samples'][-1]['seconds'] == 600
    assert output['samples'][-1]['status'] == 'stopped'
    assert Path(search.__file__).read_text(encoding='utf-8') == original


def test_timeline_sampling_does_not_backfill_or_use_future_results():
    runner = _runner()
    timeline = runner.Timeline('on', clock=iter([0, 10.001, 20, 600.001, 605, 606]).__next__)
    state = dict(chains=[{}] * 4, stop_reason='search_deadline')
    for key, score, reason in [('a', 100, 'initial'), ('b', 110, 'global'), ('c', 120, 'global')]:
        state['best'] = key
        timeline.record('best', state,
            dict(key=key, score=score, batches=[dict(samples=2)]), reason)
    timeline.record('search_stopped', state)
    output = timeline.finish('completed')
    assert len(output['samples']) == 60
    assert output['samples'][0]['dps'] is None
    assert output['samples'][1]['dps'] == 110
    assert output['samples'][-1]['dps'] == 110
    assert output['events'][-1]['dps'] == 120
    assert output['search_stop_seconds'] == 605
    assert output['finalization_seconds'] == 1
    assert output['result_saved_seconds'] == 606
    failed = runner.Timeline('on', clock=iter([0, 5, 12]).__next__)
    state['best'] = 'a'
    failed.record('best', state, dict(key='a', score=100, batches=[dict(samples=2)]), 'initial')
    partial = failed.finish('failed')
    assert partial['samples'][0]['dps'] == 100
    assert partial['samples'][1] == dict(seconds=20, dps=None, candidate_key=None, status='incomplete')
    assert partial['samples'][-1]['dps'] is None
    assert partial['events'][0]['dps'] == 100


def test_timeline_rejects_changed_path_count_before_mutation_not_on_interrupt():
    runner = _runner()
    timeline = runner.Timeline('route-progress', expected_burst_start_ms=5000)
    state = dict(chains=[{}] * 3, burst=dict(plan=dict(start_ms=5000)), stop_reason='cancelled')
    with pytest.raises(ValueError, match='Expected 4 effective paths, got 3'):
        timeline.record('paths', state)
    state['chains'].append({})
    state['burst']['plan']['start_ms'] = 6000
    with pytest.raises(ValueError, match='Expected burst start 5000ms, got 6000'):
        timeline.record('paths', state)
    # Interrupted initialization remains an incomplete run, not a new path-count failure.
    state['chains'] = []
    timeline.record('search_stopped', state)
    assert timeline.finish('cancelled')['stop_reason'] == 'cancelled'


def test_original_product_supports_route_progress_timeline_without_invented_checkpoints():
    runner = _runner()
    source = subprocess.check_output([
        'git', '-C', str(REPOSITORY), 'show',
        '80cb3a8b67ca5b86a23b95cec7f6256e79d70b18:projects/sim2gse/search.py',
    ], encoding='utf-8')
    effective = runner.experiment_source(source, 'route-progress', observe=True)
    compile(effective, '<original-experiment-search>', 'exec')
    assert "_experiment_event('paths', state)" in effective
    assert "_experiment_event('best', state, current," in effective
    assert effective.count("_experiment_event('search_stopped', state)") == 2
    assert "_experiment_event('checkpoint', state)" not in effective
    assert 'store.checkpoint()' not in effective
    with pytest.raises(ValueError, match='timeline observation site'):
        runner.experiment_source(source.replace('if all(chain.get', 'if any(chain.get'),
                                 'route-progress', observe=True)
    timeline = runner.Timeline('route-progress', expected_burst_start_ms=3000)
    state = dict(chains=[{}] * 4, burst=dict(plan=dict(start_ms=3000)),
                 stop_reason='no_improvement')
    timeline.record('paths', state)
    state['burst']['plan']['start_ms'] = 5000
    with pytest.raises(ValueError, match='Expected burst start 3000ms, got 5000'):
        timeline.record('paths', state)
    timeline.record('search_stopped', state)
    output = timeline.finish('completed')
    assert output['checkpoints'] == []
    assert len(output['samples']) == 60
