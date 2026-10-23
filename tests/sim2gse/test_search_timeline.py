"""轻量诊断从公开任务入口采集，不改变业务搜索。"""
import json
import pytest
from pathlib import Path

from test_search import _fast_search_boundary, sample_profile


def test_task_enabled_timeline_exports_existing_scores_after_completion(tmp_path):
    from task import run_task, read_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            search_timeline=True, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    files = list((tmp_path / 'task').glob('search-timeline-*.json'))
    assert len(files) == 1
    curve = json.loads(files[0].read_text(encoding='utf-8'))
    assert saved['status'] == result['status'] == curve['status'] == 'completed'
    best = next(event for event in curve['events'] if event['kind'] == 'score' and event['series'] == 'global')
    assert best['dps'] == result['search_result']['dps']
    assert best['candidate_key'] == result['selected_candidate_key']
    assert best['samples'] == result['search_result']['samples']
    assert curve['search_stop_seconds'] <= curve['result_saved_seconds'] <= curve['call_seconds']
    assert files[0].with_suffix('.html').is_file()


def test_task_cli_timeline_override_and_default_off_have_identical_results(tmp_path, monkeypatch):
    import builtins
    import simulation_config
    from task import main, run_task, read_task
    settings = tmp_path / 'config.toml'
    settings.write_text('[search]\nsearch_timeline = true\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    import sequence
    from test_search import _fast_evaluate
    count = 0
    def evaluate(*args, **kwargs):
        nonlocal count
        count += 1
        if count > 1:
            kwargs['runtime'].cancel()
            kwargs['runtime'].check()
        return _fast_evaluate(*args, **kwargs)
    with _fast_search_boundary(), monkeypatch.context() as local:
        local.setattr(sequence, 'evaluate', evaluate)
        assert main([str(source), '--output', str(tmp_path / 'cli'), '--no-search-timeline']) == 0
        assert read_task(tmp_path / 'cli')['config']['search_timeline'] is False
    assert not list((tmp_path / 'cli').glob('search-timeline-*'))
    original_import = builtins.__import__
    def forbid(name, *args, **kwargs):
        if name == 'search_timeline':
            raise AssertionError('默认关闭不得加载曲线模块')
        return original_import(name, *args, **kwargs)
    results = []
    native_requests = {}
    for enabled in (False, True):
        with _fast_search_boundary():
            with monkeypatch.context() as local:
                import result_store
                local.setattr(result_store, 'DATA_ROOT', tmp_path / ('center-' + str(enabled)))
                native_requests[enabled] = []
                def observe_native(*args, **kwargs):
                    native_requests[enabled].append((kwargs['seed'], kwargs['iterations'], kwargs['trace']))
                    return _fast_evaluate(*args, **kwargs)
                local.setattr(sequence, 'evaluate', observe_native)
                if not enabled:
                    local.setattr(builtins, '__import__', forbid)
                results.append(run_task(source, tmp_path / str(enabled), search_config=dict(
                    search_timeline=enabled, candidate_limit=2, batch_targets=(2,), iterations=2,
                    validation_batches=1)))
    assert results[0]['search_result'] == results[1]['search_result']
    assert results[0]['completed_batches'] == results[1]['completed_batches']
    assert native_requests[False] == native_requests[True]
    assert all(not request[2] for request in native_requests[True])
    assert [row['key'] for row in results[0]['search']['records']] == [row['key'] for row in results[1]['search']['records']]
    assert not list((tmp_path / 'False').glob('search-timeline-*'))


def test_offline_curves_never_start_tasks_or_backfill_future_and_split_targets(tmp_path, monkeypatch):
    import task
    def forbidden(*args, **kwargs):
        raise AssertionError('离线曲线不得启动任务')
    monkeypatch.setattr(task, 'run_task', forbidden)
    def payload(targets, status='completed', end=45):
        return dict(schema='sim2gse-search-timeline-v1', context=dict(simulation_config=dict(target_count=targets),
                comparison=dict(profile_sha256='known-fixture', engines={'controlled': 'verified-fixture'},
                    simulation_config=dict(target_count=targets), input_interval_ms=300, reset_events=[], burst=None)),
            resumed=False, time_origin='本次调用', status=status, stop_reason='candidate_limit',
            search_start_seconds=2, search_stop_seconds=30, result_saved_seconds=end,
            call_seconds=end, truncated_at=None, events=[
                dict(kind='score', seconds=10.001, series='global', dps=100, candidate_key='a', samples=2),
                dict(kind='score', seconds=25, series='global', dps=90, candidate_key='a', samples=4)])
    inputs = []
    for name, content in [('a', payload(1)), ('b', payload(1, 'failed', 22)), ('c', payload(5))]:
        path = tmp_path / ('search-timeline-' + name + '.json')
        path.write_text(json.dumps(content), encoding='utf-8')
        inputs.append(str(path))
    output = tmp_path / 'comparison.html'
    assert task.main(['curves', *inputs, '--output', str(output)]) == 0
    comparison = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
    assert len(comparison['groups']) == 2
    runs = comparison['groups'][0]['runs']
    assert len(runs) == 2
    first = {row['seconds']: row for row in runs[0]['samples'] if row['series'] == 'global'}
    assert first[10]['dps'] is None
    assert first[20]['dps'] == 100
    assert first[30]['dps'] == 90
    assert first[50]['dps'] == 90 and first[50]['status'] == 'stopped'
    failed = {row['seconds']: row for row in runs[1]['samples'] if row['series'] == 'global'}
    assert failed[30]['dps'] is None and failed[30]['status'] == 'incomplete'
    assert output.read_text(encoding='utf-8').count('<svg') == 2


def test_cancelled_timeline_resumes_as_new_segment_and_export_failure_keeps_result(tmp_path, monkeypatch):
    import sequence
    import search_timeline
    from task import run_task, resume_task, read_task
    from test_search import _fast_evaluate
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    calls = 0
    def cancel_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            kwargs['runtime'].cancel()
            kwargs['runtime'].check()
        return _fast_evaluate(*args, **kwargs)
    with _fast_search_boundary():
        with monkeypatch.context() as local:
            local.setattr(sequence, 'evaluate', cancel_second)
            result = run_task(source, tmp_path / 'task', search_config=dict(search_timeline=True,
                candidate_limit=2, batch_targets=(2,), iterations=2, validation_batches=1))
        assert result['status'] == 'cancelled'
        old_file, = (tmp_path / 'task').glob('search-timeline-*.json')
        original = old_file.read_bytes()
        old = json.loads(original)
        assert old['status'] == old['stop_reason'] == 'cancelled'
        resumed = resume_task(tmp_path / 'task', search_timeline=True)
        assert resumed['status'] == 'completed'
        assert old_file.read_bytes() == original
        segments = [json.loads(path.read_text(encoding='utf-8')) for path in (tmp_path / 'task').glob('search-timeline-*.json')]
        fresh, = [segment for segment in segments if segment['resumed']]
        assert fresh['events'][0]['seconds'] == 0
        assert fresh['events'][0]['kind'] == 'preparation'
        assert not [event for event in fresh['events'] if event['kind'] == 'score' and event['seconds'] == 0]
        def broken(*args, **kwargs):
            raise OSError('draw failure')
        monkeypatch.setattr(search_timeline, 'render', broken)
        result = run_task(source, tmp_path / 'plot-failure', search_config=dict(search_timeline=True,
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        assert result['status'] == read_task(tmp_path / 'plot-failure')['status'] == 'completed'
        assert len(list((tmp_path / 'plot-failure').glob('search-timeline-*.json'))) == 1
        def failed_native(*args, **kwargs):
            raise OSError('native failed first')
        with monkeypatch.context() as local:
            local.setattr(sequence, 'evaluate', failed_native)
            import result_store
            local.setattr(result_store, 'DATA_ROOT', tmp_path / 'failure-center')
            from task import TaskError
            with pytest.raises(TaskError, match='native failed first'):
                run_task(source, tmp_path / 'native-failure', search_config=dict(search_timeline=True,
                    candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        failure_path, = (tmp_path / 'native-failure').glob('search-timeline-*.json')
        failed = json.loads(failure_path.read_text(encoding='utf-8'))
        assert failed['status'] == 'failed'
        assert not [event for event in failed['events'] if event['kind'] == 'score']


def test_task_records_score_revision_with_independent_clock_and_bounded_events(tmp_path, monkeypatch):
    import search_timeline
    from task import run_task
    from test_search import _prepared_search_boundary
    from test_search import _fast_evaluate
    starts = [[['outbreak'], ['scourge_strike']], [['outbreak'], ['death_coil']], [['outbreak'], ['epidemic']]]
    clock = [100.]
    monkeypatch.setattr(search_timeline, 'monotonic', lambda: clock[0])
    def evaluate(profile, candidate, folder, **kwargs):
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        blocks = result['blocks']
        seed = kwargs['seed']
        if blocks == starts[0]:
            score = 100.
        elif blocks == starts[1]:
            score = 80. if seed == 20260913 else 120. if seed == 20260912 else 140.
        else:
            score = 130. if seed == 20260913 else 120. if seed == 20260912 else 150.
        result['summary']['dps'] = score
        result['report']['sim']['statistics']['raid_dps']['mean'] = score
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = score
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        clock[0] += 10.001
        return result
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    for cap in (10000, 4):
        monkeypatch.setattr(search_timeline, 'MAX_EVENTS', cap)
        from runtime import TaskRuntime
        runtime = TaskRuntime(600)
        runtime.timeline_origin = clock[0]
        with _prepared_search_boundary(tmp_path, starts, evaluate=evaluate):
            result = run_task(source, tmp_path / str(cap), _runtime=runtime, search_config=dict(search_timeline=True,
                candidate_limit=3, batch_targets=(2, 4), iterations=2, validation_batches=2))
        path, = (tmp_path / str(cap)).glob('search-timeline-*.json')
        curve = json.loads(path.read_text(encoding='utf-8'))
        assert result['status'] == curve['status'] == 'completed'
        if cap == 10000:
            global_events = [event for event in curve['events'] if event.get('series') == 'global']
            assert [event['dps'] for event in global_events] == [100., 120., 100., 125.]
            assert global_events[2]['reason'] == 'revision'
            assert global_events[0]['seconds'] >= 20.002
            assert curve['samples'][0]['dps'] is None
        else:
            assert len(curve['events']) == 4
            assert curve['truncated_at'] is not None
            assert all(row['dps'] is None and row['status'] == 'incomplete'
                       for row in curve['samples'] if row['seconds'] >= curve['truncated_at'])


def test_damage_curves_read_existing_native_buckets_without_pet_double_count_or_simulation(tmp_path, monkeypatch):
    import task
    import result_store
    from native_build import build_identity, identity_digest
    from test_search import REPOSITORY, _fast_report
    from task import parse_character
    lock = json.loads((REPOSITORY / 'projects/sim2gse/compatibility/lock.json').read_text())
    manifest = build_identity(lock, 'controlled', 'fixture-compiler')
    manifest['identity_sha256'] = identity_digest(manifest)
    run = dict.fromkeys(result_store.RUN_SCHEMA)
    run.update(run_id='existing-run', engines=dict(controlled=manifest))
    result_store.write('runs', 'existing-run', [run], schema=result_store.RUN_SCHEMA)
    report = _fast_report(parse_character(sample_profile()), 777., 2)
    report['version'] = '1210-01'
    report['report_version'] = '2.0.0'
    player = report['sim']['players'][0]
    player['collected_data']['timeline_dmg'] = dict(data=[10., 30., 20.])
    player['stats_pets'] = [dict(collected_data=dict(timeline_dmg=dict(data=[100., 100., 100.])))]
    result_store.write_batch('saved-bucket', dict(batch_key='saved-bucket', run_id='existing-run',
        purpose='search', report=report), diagnostic_logging=False)
    unknown = tmp_path / 'unknown.json'
    unknown.write_text(json.dumps(report), encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('伤害图不得补模拟')
    monkeypatch.setattr(task, 'run_task', forbidden)
    output = tmp_path / 'damage.html'
    assert task.main(['curves', '--damage', 'batch:saved-bucket', str(unknown), '--output', str(output)]) == 0
    saved = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
    assert saved['reports'][0]['values'] == [10., 30., 20.]
    assert saved['reports'][0]['bucket_seconds'] == 1
    assert saved['reports'][0]['metric'] == '原生报告1秒分桶伤害统计'
    assert saved['reports'][1]['status'] == 'unsupported'
    assert '桶宽' in saved['reports'][1]['reason']


def test_resume_timeline_only_override_does_not_reset_frozen_algorithm(tmp_path):
    from task import run_task, resume_task, read_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        run_task(source, tmp_path / 'task', search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        resume_task(tmp_path / 'task', search_config={'search_timeline': True})
        saved = read_task(tmp_path / 'task')
    assert saved['config']['candidate_limit'] == 1
    assert len(list((tmp_path / 'task').glob('search-timeline-*.json'))) == 1


def test_async_task_timeline_includes_pre_worker_configuration_preparation(tmp_path, monkeypatch):
    import os
    import task
    import search_timeline
    import simulation_config
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
    with _fast_search_boundary():
        handle = task.start_task(source, tmp_path / 'async', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        handle.join(10)
        assert handle.done and handle.error is None
        assert handle.result['status'] == 'completed'
    path, = (tmp_path / 'async').glob('search-timeline-*.json')
    curve = json.loads(path.read_text(encoding='utf-8'))
    first = next(event for event in curve['events'] if event['kind'] == 'collector_started')
    assert first['seconds'] >= 10


def test_curves_group_physical_conditions_not_algorithm_switches(tmp_path, monkeypatch):
    import task
    import result_store
    sources = []
    for name, seed, race in [('first-seed', 20260912, 'highmountain_tauren'),
                               ('other-seed', 20260913, 'highmountain_tauren'), ('other', 20260912, 'orc')]:
        source = tmp_path / (name + '.simc')
        source.write_text(sample_profile().replace('race=highmountain_tauren', 'race=' + race), encoding='utf-8')
        with _fast_search_boundary(), monkeypatch.context() as local:
            local.setattr(result_store, 'DATA_ROOT', tmp_path / ('center-' + name))
            task.run_task(source, tmp_path / name, search_config=dict(search_timeline=True,
                random_seed=seed, candidate_limit=1, batch_targets=(2,),
                iterations=2, validation_batches=1))
        sources.append(str(tmp_path / name))
    output = tmp_path / 'physical-groups.html'
    assert task.main(['curves', *sources, '--output', str(output)]) == 0
    groups = json.loads(output.with_suffix('.json').read_text())['groups']
    assert sorted(len(group['runs']) for group in groups) == [1, 2]
    together = next(group['runs'] for group in groups if len(group['runs']) == 2)
    assert together[0]['context']['comparison'] == together[1]['context']['comparison']
    assert {run['context']['algorithm']['random_seed'] for run in together} == {20260912, 20260913}
    # Older or preparation-failed files have no proven conditions: never merge unknowns.
    unknowns = []
    for index in range(2):
        payload = dict(together[index], context=dict(simulation_config=dict(target_count=1)))
        path = tmp_path / f'unknown-{index}.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        unknowns.append(str(path))
    assert task.main(['curves', *unknowns, '--output', str(output)]) == 0
    assert len(json.loads(output.with_suffix('.json').read_text())['groups']) == 2
