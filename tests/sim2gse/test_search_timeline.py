"""曲线规则直接读取内存成绩；一条真实文件链保留任务/CLI/恢复接线。"""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from test_population_training import memory_ga
from test_search import _fast_search_boundary, _initialized_starts, sample_profile
from test_training_champion import unchanged_offspring


def timeline_payload(targets, status='completed', end=45):
    """独立已知成绩：10.001秒100、25秒90，不从采样实现生成期待。"""
    return dict(schema='sim2gse-search-timeline-v1', context=dict(simulation_config=dict(target_count=targets),
            comparison=dict(profile_sha256='known-fixture', engines={'controlled': 'verified-fixture'},
                simulation_config=dict(target_count=targets), input_interval_ms=300, reset_events=[], burst=None)),
        resumed=False, time_origin='本次调用', status=status, stop_reason='stagnation',
        search_start_seconds=2, search_stop_seconds=30, result_saved_seconds=end,
        call_seconds=end, truncated_at=None, events=[
            dict(kind='score', seconds=10.001, series='global', dps=100, candidate_key='a', samples=2),
            dict(kind='score', seconds=25, series='global', dps=90, candidate_key='a', samples=4)])


def test_timeline_switch_has_identical_formal_scores_and_native_requests(memory_ga, unchanged_offspring):
    import builtins
    from search_timeline import Timeline
    from sequence import behavior_key
    original_import = builtins.__import__
    def forbid(name, *args, **kwargs):
        if name == 'search_timeline':
            raise AssertionError('默认关闭不得加载曲线模块')
        return original_import(name, *args, **kwargs)
    results, requests = [], []
    for enabled in (False, True):
        case = memory_ga(formal=True, programs=[[['outbreak'], ['death_coil']]],
                         search_settings=dict(search_timeline=enabled))
        timeline = Timeline(context=dict(algorithm={})) if enabled else None
        with patch.object(builtins, '__import__', original_import if enabled else forbid):
            results.append(case.run(timeline=timeline))
        requests.append(Counter((behavior_key(call[1]), call[2]['seed'],
                                 call[2]['iterations'], call[2].get('trace')) for call in case.calls))
    assert results[0]['search_result'] == results[1]['search_result']
    assert results[0]['completed_batches'] == results[1]['completed_batches']
    assert requests[0] == requests[1]
    assert {request[2] for request in requests[1]} >= {32, 128}
    def records(result):
        return {row['key']: (row['program'], row['score'],
            [(batch['request'], batch['dps'], batch['samples']) for batch in row['batches']])
            for row in result['search']['records']}
    assert records(results[0]) == records(results[1])
    best, = [event for event in timeline.events if event['kind'] == 'score' and event['series'] == 'global']
    assert best['dps'] == results[1]['search_result']['dps']
    assert best['candidate_key'] == results[1]['selected_candidate_key']
    assert best['samples'] == results[1]['search_result']['samples'] == 381


def test_offline_curves_never_start_tasks_or_backfill_future_and_split_targets(monkeypatch):
    import task
    from search_timeline import _groups, resample
    monkeypatch.setattr(task, 'run_task', lambda *a, **k: pytest.fail('离线曲线不得启动任务'))
    payloads = [timeline_payload(1), timeline_payload(1, 'failed', 22), timeline_payload(5)]
    groups = list(_groups(payloads).values())
    assert [len(group) for group in groups] == [2, 1]
    first = {row['seconds']: row for row in resample(payloads[0], horizon=50)}
    assert first[10]['dps'] is None
    assert first[20]['dps'] == 100
    assert first[30]['dps'] == 90
    assert first[50]['dps'] == 90 and first[50]['status'] == 'stopped'
    failed = {row['seconds']: row for row in resample(payloads[1], horizon=50)}
    assert failed[30]['dps'] is None and failed[30]['status'] == 'incomplete'


def test_cancelled_retest_keeps_search_stop_time_but_exports_terminal_reason(monkeypatch):
    import search_timeline
    clock = [0.]
    monkeypatch.setattr(search_timeline, 'monotonic', lambda: clock[0])
    timeline = search_timeline.Timeline(origin=0.)
    timeline.start()
    clock[0] = 10.
    timeline.stop('stagnation')
    clock[0] = 12.
    timeline.saved('cancelled')
    clock[0] = 15.
    writes = {}
    with patch.object(Path, 'mkdir'), patch.object(Path, 'write_text',
            lambda path, text, **kwargs: writes.setdefault(path.suffix, text)):
        timeline.finish('/memory/cancelled-retest')
    payload = json.loads(writes['.json'])
    assert payload['status'] == payload['stop_reason'] == 'cancelled'
    assert payload['search_stop_seconds'] == 10.
    assert payload['result_saved_seconds'] == 12. and payload['call_seconds'] == 15.
    stopped, = [event for event in payload['events'] if event['kind'] == 'search_stopped']
    assert stopped == dict(seconds=10., kind='search_stopped', reason='stagnation')


def test_task_records_distinct_ga_stages_with_independent_clock_and_bounded_events(
        monkeypatch, memory_ga, unchanged_offspring):
    import search_timeline
    starts = [[['outbreak'], ['scourge_strike']], [['outbreak'], ['death_coil']]]
    clock = [100.]
    monkeypatch.setattr(search_timeline, 'monotonic', lambda: clock[0])
    def score(candidate, options):
        first = candidate['blocks'][-1][0]['simc_action'] == 'scourge_strike'
        value = (100. if first else 90.) if options['iterations'] != 128 else (80. if first else 120.)
        clock[0] += 10.001
        return value
    for cap in (10000, 4):
        monkeypatch.setattr(search_timeline, 'MAX_EVENTS', cap)
        timeline = search_timeline.Timeline(origin=clock[0], context=dict(algorithm={}))
        case = memory_ga(formal=True, programs=starts, score_for=score)
        result = case.run(timeline=timeline)
        timeline.saved(result['status'])
        payload = dict(events=timeline.events, status=result['status'],
                       call_seconds=timeline.seconds(), search_stop_seconds=timeline.search_stop_seconds,
                       truncated_at=timeline.truncated_at)
        assert result['status'] == 'completed'
        if cap == 10000:
            scores = [event for event in timeline.events if event['kind'] == 'score']
            coarse = [event for event in scores if event['series'] == 'search']
            retests = [event for event in scores if event['series'] == 'nominal']
            global_events = [event for event in scores if event['series'] == 'global']
            assert coarse and {event['dps'] for event in coarse} == {90., 100.}
            assert retests and {event['dps'] for event in retests} == {80., 120.}
            assert len(global_events) == 1
            assert global_events[0]['dps'] == result['search_result']['dps'] == 120.
            assert global_events[0]['reason'] == 'nominal_retest'
            assert global_events[0]['seconds'] >= max(event['seconds'] for event in retests)
            assert max(event['seconds'] for event in coarse) <= timeline.search_stop_seconds
            assert min(event['seconds'] for event in retests) > timeline.search_stop_seconds
            assert coarse[0]['seconds'] >= 10.001
            assert search_timeline.resample(payload)[0]['dps'] is None
            assert timeline.search_stop_seconds <= timeline.result_saved_seconds <= timeline.seconds()
        else:
            assert len(timeline.events) == 4
            assert timeline.truncated_at is not None
            assert all(row['dps'] is None and row['status'] == 'incomplete'
                       for row in search_timeline.resample(payload)
                       if row['seconds'] >= timeline.truncated_at)


def _damage_inputs():
    """既有原生来源的固定三桶报告；构造数据不冒充实际SimC运行。"""
    import result_store
    import task
    from native_build import build_identity, identity_digest
    from test_search import REPOSITORY, _fast_report
    lock = json.loads((REPOSITORY / 'projects/sim2gse/compatibility/lock.json').read_text())
    manifest = build_identity(lock, 'controlled', 'fixture-compiler')
    manifest['identity_sha256'] = identity_digest(manifest)
    report = _fast_report(task.parse_character(sample_profile()), 777., 2)
    report.update(version='1210-01', report_version='2.0.0')
    player = report['sim']['players'][0]
    player['collected_data']['timeline_dmg'] = dict(data=[10., 30., 20.])
    player['stats_pets'] = [dict(collected_data=dict(timeline_dmg=dict(data=[100., 100., 100.])))]
    batch = dict(batch_key='saved-bucket', run_id='existing-run', purpose='search', report=report)
    run = dict.fromkeys(result_store.RUN_SCHEMA)
    run.update(run_id='existing-run', engines=dict(controlled=manifest))
    return batch, run


def test_damage_curves_read_existing_native_buckets_without_pet_double_count_or_simulation(monkeypatch):
    import result_store
    import task
    from search_timeline import damage_report
    batch, run = _damage_inputs()
    def read_one(table, field, key):
        assert (table, field, key) in [('batches', 'batch_key', 'saved-bucket'), ('runs', 'run_id', 'existing-run')]
        return deepcopy(batch if table == 'batches' else run)
    monkeypatch.setattr(result_store, 'one', read_one)
    monkeypatch.setattr(task, 'run_task', lambda *a, **k: pytest.fail('伤害图不得补模拟'))
    saved = damage_report('batch:saved-bucket')
    assert saved['values'] == [10., 30., 20.]
    assert saved['bucket_seconds'] == 1
    assert saved['metric'] == '原生报告1秒分桶伤害统计'
    original_read = Path.read_text
    def read_unknown(path, *args, **kwargs):
        return json.dumps(batch['report']) if path.name == 'unknown.json' else original_read(path, *args, **kwargs)
    with patch.object(Path, 'is_dir', return_value=False), patch.object(Path, 'read_text', read_unknown):
        unknown = damage_report('/unknown.json')
    assert unknown['status'] == 'unsupported' and '桶宽' in unknown['reason']


def test_curves_group_physical_conditions_not_algorithm_switches():
    from search_timeline import Timeline, _groups
    from task import parse_character
    payloads = []
    for seed, race in [(20260912, 'highmountain_tauren'), (20260913, 'highmountain_tauren'), (20260912, 'orc')]:
        import hashlib
        profile = sample_profile().replace('race=highmountain_tauren', 'race=' + race)
        assert parse_character(profile).race == race
        timeline = Timeline(context=dict(simulation_config=dict(target_count=1)))
        timeline.configure(profile_sha=hashlib.sha256(profile.encode()).hexdigest(),
            engines=dict(controlled=dict(identity_sha256='verified', binary_sha256='binary')),
            simulation_config=dict(target_count=1), config=dict(random_seed=seed, input_interval_ms=300, reset_events=[]))
        payloads.append(dict(context=timeline.context))
    groups = list(_groups(payloads).values())
    assert sorted(len(group) for group in groups) == [1, 2]
    together = next(group for group in groups if len(group) == 2)
    assert together[0][1]['context']['comparison'] == together[1][1]['context']['comparison']
    assert {run['context']['algorithm']['random_seed'] for _, run in together} == {20260912, 20260913}
    unknowns = [dict(payload, context=dict(simulation_config=dict(target_count=1))) for payload in payloads[:2]]
    assert len(_groups(unknowns)) == 2


@pytest.mark.real
def test_timeline_cli_file_lifecycle_preserves_results_and_frozen_resume(
        tmp_path, monkeypatch, unchanged_offspring):
    """一条任务链保留真实发布、异步准备、取消/恢复新段和CLI文件读写。

    绘图故障复用已完成任务，不为每种错误重新跑GA；评分是原有明确外部IO构造。
    """
    import result_store
    import sequence
    import search_timeline
    import simulation_config
    import task
    from test_search import _fast_evaluate
    settings = tmp_path / 'config.toml'
    settings.write_text('[search]\nsearch_timeline = true\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    clock = [100.]
    monkeypatch.setattr(task.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(search_timeline, 'monotonic', lambda: clock[0])
    load_configuration = simulation_config.load_search_config
    delayed = False
    def slow_configuration(*args, **kwargs):
        nonlocal delayed
        if not delayed:
            delayed = True
            clock[0] += 10.001
        return load_configuration(*args, **kwargs)
    monkeypatch.setattr(simulation_config, 'load_search_config', slow_configuration)
    def timed_evaluate(*args, **kwargs):
        clock[0] += .001
        return _fast_evaluate(*args, **kwargs)
    calls = 0
    def cancel_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            kwargs['runtime'].cancel()
            kwargs['runtime'].check()
        return timed_evaluate(*args, **kwargs)
    folder = tmp_path / 'task'
    with _fast_search_boundary(), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=timed_evaluate):
        with patch.object(sequence, 'evaluate', side_effect=cancel_second):
            handle = task.start_task(source, folder, search_config=dict(iterations=2))
            handle.join(10)
            assert handle.done and handle.error is None
            assert handle.result['status'] == 'cancelled'
        old_file, = folder.glob('search-timeline-*.json')
        original = old_file.read_bytes()
        old = json.loads(original)
        assert old['status'] == old['stop_reason'] == 'cancelled'
        collector = next(event for event in old['events'] if event['kind'] == 'collector_started')
        assert collector['seconds'] >= 10
        assert task.main(['--resume', '--output', str(folder), '--search-timeline']) == 0
        saved = task.read_task(folder)
        assert saved['status'] == 'completed'
        assert saved['config']['iterations'] == 2
        assert old_file.read_bytes() == original
        segments = [json.loads(path.read_text()) for path in folder.glob('search-timeline-*.json')]
        fresh, = [segment for segment in segments if segment['resumed']]
        assert fresh['events'][0] == dict(seconds=0., kind='preparation')
        assert not [event for event in fresh['events'] if event['kind'] == 'score' and event['seconds'] == 0]
        best, = [event for event in fresh['events'] if event['kind'] == 'score' and event['series'] == 'global']
        assert best['dps'] == saved['search_result']['dps']
        assert best['candidate_key'] == saved['selected_candidate_key']
        assert best['samples'] == saved['search_result']['samples'] == 381
        assert fresh['search_stop_seconds'] <= fresh['result_saved_seconds'] <= fresh['call_seconds']
        assert all(path.with_suffix('.html').is_file() for path in folder.glob('search-timeline-*.json'))
        comparison = tmp_path / 'comparison.html'
        with patch.object(task, 'run_task', side_effect=AssertionError('离线曲线不得启动任务')):
            assert task.main(['curves', str(folder), '--output', str(comparison)]) == 0
        assert comparison.read_text().count('<svg') == 1
        assert len(json.loads(comparison.with_suffix('.json').read_text())['groups']) == 1
        batch, run = _damage_inputs()
        result_store.write('runs', 'existing-run', [run], schema=result_store.RUN_SCHEMA)
        result_store.write_batch('saved-bucket', batch, diagnostic_logging=False)
        unknown = tmp_path / 'unknown.json'
        unknown.write_text(json.dumps(batch['report']), encoding='utf-8')
        damage = tmp_path / 'damage.html'
        with patch.object(task, 'run_task', side_effect=AssertionError('伤害图不得补模拟')):
            assert task.main(['curves', '--damage', 'batch:saved-bucket', str(unknown), '--output', str(damage)]) == 0
        reports = json.loads(damage.with_suffix('.json').read_text())['reports']
        assert reports[0]['values'] == [10., 30., 20.]
        assert reports[0]['bucket_seconds'] == 1
        assert reports[1]['status'] == 'unsupported'
        assert damage.read_text().count('<svg') == 1
        count = len(segments)
        with patch.object(search_timeline, 'render', side_effect=OSError('draw failure')):
            resumed = task.resume_task(folder, search_config={'search_timeline': True})
        assert resumed['status'] == task.read_task(folder)['status'] == 'completed'
        assert task.read_task(folder)['config']['iterations'] == 2
        assert len(list(folder.glob('search-timeline-*.json'))) == count + 1
        calls = 0
        with patch.object(sequence, 'evaluate', side_effect=cancel_second):
            off = tmp_path / 'cli-off'
            assert task.main([str(source), '--output', str(off), '--no-search-timeline']) == 0
        assert task.read_task(off)['config']['search_timeline'] is False
        assert not list(off.glob('search-timeline-*'))
        with patch.object(result_store, 'DATA_ROOT', tmp_path / 'failure-center'), \
                patch.object(sequence, 'evaluate', side_effect=OSError('native failed first')):
            with pytest.raises(task.TaskError, match='native failed first'):
                task.run_task(source, tmp_path / 'native-failure', search_config=dict(search_timeline=True, iterations=2))
        failure_path, = (tmp_path / 'native-failure').glob('search-timeline-*.json')
        failed = json.loads(failure_path.read_text())
        assert failed['status'] == 'failed'
        assert not [event for event in failed['events'] if event['kind'] == 'score']
