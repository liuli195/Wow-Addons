"""显式命令控制诊断日志，业务规则与恢复凭据保留。"""
import pytest


@pytest.mark.parametrize('enabled', [False])
def test_resume_command_requires_current_logging_intent(tmp_path, monkeypatch, enabled):
    import sequence
    import sqlite3
    from unittest.mock import patch
    from task import main, read_task, run_task
    from search import TaskStore
    from test_character_export import sample_profile
    from test_engine import apl_pool_reference
    from test_rule_initialization import _configure_opener
    from test_rule_diagnostics import _condition_pack, _observed_evaluate
    from test_search import _apl_task_boundary, _initialized_starts

    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source, destination = tmp_path / 'role.simc', tmp_path / 'task'
    source.write_text(sample_profile(), encoding='utf-8')
    cancelled = False
    def stop_once(*args, **kwargs):
        nonlocal cancelled
        result = _observed_evaluate(*args, **kwargs)
        if not cancelled and kwargs.get('rule_observation_request') is not None:
            cancelled = True
            kwargs['runtime'].cancel()
        return result

    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=stop_once):
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(rule_diagnostics_policy='eager', total_budget_seconds=20, input_interval_ms=200,
                candidate_limit=2, round_candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=1, max_processes=1,
                diagnostic_logging=True, diagnostics='summary'))
        assert read_task(destination)['status'] == 'cancelled'
        assert main(['--resume', '--output', str(destination)] +
                    (['--diagnostic-logging'] if enabled else [])) == 0
        result = read_task(destination, include_search_records=True)
    with sqlite3.connect(destination / 'task.sqlite3') as database:
        state = TaskStore.load_state(database)
    assert state['config']['diagnostic_logging'] is enabled
    assert any(step.get('selection', {}).get('feedback', {}).get('status') == 'learned'
               for step in result['search']['rule_steps'].values())
    assert all(('costs' in record['rule_diagnostics']) is enabled
               for record in result['search']['records'])




@pytest.mark.parametrize('enabled', [True])
def test_public_report_write_records_only_opt_in_stage_totals(enabled):
    from runtime import TaskRuntime
    import result_store
    runtime = TaskRuntime(diagnostic_logging=enabled)
    row = dict(batch_key='timed-report', run_id='run',
               report=dict(sim=dict(players=[dict(name='fixture', collected_data=dict(damage=dict(mean=12.0)))])))
    assert result_store.write_batch('timed-report', row, runtime=runtime) == 1
    assert result_store.read_records('batches', 'timed-report')[0]['report'] == row['report']
    if enabled:
        stages = runtime.performance_stages
        assert {'report.prepare', 'report.write'} <= stages.keys()
        for name in ('report.prepare', 'report.write'):
            assert stages[name]['calls'] == 1
            assert stages[name]['seconds'] >= 0
            assert stages[name]['units']['rows'] == 1
    else:
        assert not hasattr(runtime, 'performance_stages')


def test_timing_failure_does_not_replace_report_error(monkeypatch):
    import runtime
    import result_store
    def broken_clock():
        raise RuntimeError('计时源不可用')
    monkeypatch.setattr(runtime.time, 'perf_counter', broken_clock)
    with pytest.raises(KeyError, match='report'):
        result_store.write_batch('invalid', {}, runtime=runtime.TaskRuntime(diagnostic_logging=True))


def test_stage_wall_union_merges_overlaps_across_invocation_owners(monkeypatch):
    from types import SimpleNamespace
    import runtime
    first, second = SimpleNamespace(), SimpleNamespace()
    ends = iter([4.0, 6.0, 9.0, 5.0])
    monkeypatch.setattr(runtime.time, 'perf_counter', lambda: next(ends))
    runtime.diagnostic_finish(first, 'diagnostic.total', 1.0)
    runtime.diagnostic_finish(second, 'diagnostic.total', 3.0)
    runtime.diagnostic_finish(first, 'diagnostic.total', 8.0)
    runtime.diagnostic_finish(first, 'diagnostic.rules', 2.0)
    stages = runtime.diagnostic_summary(first, second)['stages']
    assert stages['diagnostic.total']['seconds'] == 7.0
    assert stages['diagnostic.total']['wall_union_seconds'] == 6.0
    assert stages['diagnostic.total']['calls'] == 3
    assert 'wall_union_seconds' not in stages['diagnostic.rules']
    assert not any('intervals' in value for value in stages.values())


def test_covered_wall_unions_selected_stages_without_wait_or_nested_double_count(monkeypatch):
    from types import SimpleNamespace
    import runtime

    first, second = SimpleNamespace(), SimpleNamespace()
    spans = [
        (first, 'diagnostic.total', 1.0, 4.0),
        (second, 'native.execute', 3.0, 7.0),
        (first, 'report.publish', 6.0, 10.0),
        (second, 'report.write', 7.0, 9.0),
        (first, 'evaluation.report_read_validate', 7.0, 8.0),
        (first, 'evaluation.trace', 8.0, 8.5),
        (second, 'state.persist.full', 9.0, 11.0),
        (first, 'candidate.compile', 12.0, 13.0),
        (first, 'candidate.write', 13.0, 15.0),
        (first, 'main.wait', 0.0, 20.0),
        (first, 'diagnostic.rules', 0.0, 25.0),
    ]
    for owner, name, start, stop in spans:
        monkeypatch.setattr(runtime.time, 'perf_counter', lambda stop=stop: stop)
        runtime.diagnostic_finish(owner, name, start)
    summary = runtime.diagnostic_summary(first, second)
    assert summary['covered_wall_seconds'] == 13.0
    assert summary['covered_stages'] == [
        'candidate.compile', 'candidate.write', 'diagnostic.total',
        'evaluation.report_read_validate', 'evaluation.trace', 'native.execute',
        'report.publish', 'report.write', 'state.persist.full']
    assert summary['stages']['main.wait']['wall_union_seconds'] == 20.0
    assert summary['stages']['report.publish']['wall_union_seconds'] == 4.0
    assert summary['stages']['report.write']['wall_union_seconds'] == 2.0
    assert 'not CPU time' in summary['covered_wall_timing']
    assert 'not the complete public-call wall time' in summary['covered_wall_timing']


@pytest.mark.parametrize('case', ['known'])
def test_detailed_diagnostic_stages_preserve_public_result(monkeypatch, case):
    import copy
    import runtime
    from rule_diagnostics import diagnose
    from test_rule_trigger_prefix import _invocation
    exports = [[dict(input_index=0, trigger=True)]]
    options = {}
    if case == 'unknown':
        exports = [[]]
    elif case == 'duplicate':
        exports = [[dict(input_index=0, trigger=False), dict(input_index=0, trigger=True)]]
    invocation = _invocation(exports, **options)
    enabled = runtime.TaskRuntime(diagnostic_logging=True)
    disabled = runtime.TaskRuntime()
    if case == 'cancelled':
        enabled.cancel()
        disabled.cancel()
    actual = diagnose(**copy.deepcopy(invocation), runtime=enabled)
    actual.pop('costs')
    stages = runtime.diagnostic_summary(enabled)['stages']
    assert {'diagnostic.preprocess.normalize', 'diagnostic.preprocess.digest',
            'diagnostic.preprocess.positions', 'diagnostic.preprocess.observed_rows',
            'diagnostic.preprocess.indexes'} <= stages.keys()
    bindings = [name for name in stages if name.startswith('diagnostic.binding.')]
    assert bindings
    if case != 'cancelled':
        assert any('.read.' in name and name.endswith('.project') for name in bindings)
        assert any('.let.' in name for name in bindings)
    clock_calls = []
    def unexpected_clock():
        clock_calls.append(True)
        raise AssertionError('关闭总开关不得取得细分计时')
    monkeypatch.setattr(runtime.time, 'perf_counter', unexpected_clock)
    assert diagnose(**copy.deepcopy(invocation), runtime=disabled) == actual
    assert clock_calls == []
    assert not hasattr(disabled, 'performance_stages')


@pytest.mark.parametrize('replay', ['cached_task'])
def test_public_candidate_progress_counts_only_new_successful_first_scores(tmp_path, monkeypatch, replay):
    import json
    import sequence
    from unittest.mock import patch
    from task import run_task, resume_task, read_task
    from search import TaskStore
    from test_character_export import sample_profile
    from test_engine import apl_pool_reference
    from test_rule_initialization import _configure_opener
    from test_rule_diagnostics import _condition_pack, _observed_evaluate
    from test_search import _apl_task_boundary
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source, destination = tmp_path / 'role.simc', tmp_path / 'first'
    source.write_text(sample_profile(), encoding='utf-8')
    config = dict(total_budget_seconds=20, input_interval_ms=200, candidate_limit=1,
        batch_targets=(2,), iterations=2, validation_batches=1, max_processes=1,
        diagnostic_logging=True, diagnostics='summary')
    if replay == 'duplicate_publication':
        original_commit = TaskStore._commit_report_group
        def replay_group(self, *args, **kwargs):
            original_commit(self, *args, **kwargs)
            original_commit(self, *args, **kwargs)
        monkeypatch.setattr(TaskStore, '_commit_report_group', replay_group)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        run_task(source, destination, simulation_config=dict(scene='single_target'), search_config=config)
    saved = read_task(destination, include_search_records=True)
    performance = json.loads((destination / 'diagnostics.json').read_text())['performance']
    progress = performance['candidate_progress']
    assert performance['stages']['candidate.compile']['calls'] == 1
    assert performance['stages']['candidate.write']['calls'] == 1
    keys = {row['key'] for row in saved['search']['records']}
    assert len(keys) == 1
    for kind in ('first_score_published', 'screening_archived'):
        assert {row['behavior_identity'] for row in progress[kind]} == keys
        assert len(progress[kind]) == 1
        assert progress[kind][0]['invocation_seconds'] >= 0
        assert progress[kind][0]['budget_elapsed_seconds'] >= progress[kind][0]['invocation_seconds']
    if replay == 'duplicate_publication':
        return
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('复用不得重新评分')):
        if replay == 'resume':
            resume_task(destination, diagnostic_logging=True)
        else:
            destination = tmp_path / 'cached'
            run_task(source, destination, simulation_config=dict(scene='single_target'), search_config=config)
    performance = json.loads((destination / 'diagnostics.json').read_text())['performance']
    progress = performance['candidate_progress']
    assert progress['first_score_published'] == []
    if replay == 'resume':
        assert progress['screening_archived'] == []
        assert 'candidate.compile' not in performance['stages']
        assert 'native.execute' not in performance['stages']


@pytest.mark.parametrize('enabled,flow', [(True, 'finalizing'), (False, 'exhausted_resume')])
def test_public_feedback_logs_follow_current_invocation_switch(
        tmp_path, monkeypatch, installed_data_store_api, enabled, flow):
    resume = flow != 'finalizing'
    import json
    import runtime
    import sequence
    from unittest.mock import patch
    from task import run_task, resume_task, read_task
    from test_character_export import sample_profile
    from test_engine import apl_pool_reference
    from test_rule_initialization import _configure_opener
    from test_rule_diagnostics import _condition_pack, _observed_evaluate
    from test_search import _apl_task_boundary
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source, destination = tmp_path / 'role.simc', tmp_path / 'task'
    source.write_text(sample_profile(), encoding='utf-8')
    scoring_calls = []
    def budget_end(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        if kwargs.get('rule_observation_request') is not None:
            scoring_calls.append(True)
            if len(scoring_calls) == 6 and flow != 'continue_resume':
                kwargs['runtime'].used_seconds = kwargs['runtime'].budget_seconds
        return result
    actual_write = installed_data_store_api['write']
    interrupted = False
    def interrupted_store(root, table, key, rows, **kwargs):
        nonlocal interrupted
        if resume and table == 'search_learners' and rows[0]['settled'] and not interrupted:
            interrupted = True
            raise SystemExit('constructed store interruption before feedback commit')
        return actual_write(root, table, key, rows, **kwargs)
    monkeypatch.setitem(installed_data_store_api, 'write', interrupted_store)
    config = dict(rule_diagnostics_policy='eager', total_budget_seconds=20, input_interval_ms=200, candidate_limit=6,
        round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',),
        diagnostic_logging=True if resume else enabled, diagnostics='summary')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=budget_end):
        if resume:
            with pytest.raises(SystemExit, match='before feedback commit'):
                run_task(source, destination, simulation_config=dict(scene='single_target'), search_config=config)
        else:
            run_task(source, destination, simulation_config=dict(scene='single_target'), search_config=config)
    output = destination / 'diagnostics.json'
    old_output = output.read_bytes() if output.exists() else None
    clock_calls = []
    if resume:
        if not enabled:
            def unexpected_clock():
                clock_calls.append(True)
                raise AssertionError('本次未开启不得沿用旧任务性能设置')
            monkeypatch.setattr(runtime.time, 'perf_counter', unexpected_clock)
        resumed_engine = budget_end if flow == 'continue_resume' else AssertionError('不得新增评分')
        with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=resumed_engine):
            resume_task(destination, diagnostic_logging=enabled)
    saved = read_task(destination, include_search_records=True)
    selections = [step['selection'] for step in saved['search']['rule_steps'].values() if step.get('selection')]
    assert len(scoring_calls) == 6 and len(selections) == 2
    assert all(row['feedback']['status'] == 'learned' for row in selections)
    if not enabled:
        assert clock_calls == []
        assert (output.read_bytes() if output.exists() else None) == old_output
        return
    diagnostics = json.loads(output.read_text(encoding='utf-8'))
    performance = diagnostics['performance']
    assert performance['scope'] == 'current_invocation'
    assert performance['timing'] == 'inclusive_wall_seconds'
    stages = performance['stages']
    for name in ('diagnostic.total', 'diagnostic.read_validate', 'diagnostic.preprocess',
                 'diagnostic.rules', 'diagnostic.finalize',
                 'report.prepare', 'report.write', 'state.persist.full', 'state.persist.partial',
                 'state.transaction', 'state.progress', 'model.load', 'model.predict', 'model.learn',
                 'model.snapshot', 'model.full_write', 'model.control_write',
                 'candidate.compile', 'candidate.write', 'report.publish', 'main.wait'):
        assert stages[name]['calls'] > 0, name
        assert stages[name]['seconds'] >= 0, name
    assert stages['model.predict']['units']['actions'] > 0
    assert stages['model.learn']['units']['common_batches'] > 0
    assert stages['report.write']['units']['rows'] > 0
    assert stages['state.persist.full']['units']['written_bytes'] > 0
    assert stages['candidate.compile']['calls'] == diagnostics['candidate_compilations']
    assert stages['candidate.write']['calls'] == stages['candidate.compile']['calls']
    assert stages['report.publish']['wall_union_seconds'] > 0
    assert 'report.publish' in performance['covered_stages']
    assert stages['main.wait']['wall_union_seconds'] >= 0
    assert 'main.wait' not in performance['covered_stages']
    assert stages['model.learn']['calls'] == 2
    assert stages['model.learn']['units']['common_batches'] == 2
    if resume:
        assert stages['model.full_write']['calls'] == 2
        for name in ('model.full_write', 'state.persist.full', 'state.persist.partial'):
            assert stages[name]['wall_union_seconds'] == pytest.approx(stages[name]['seconds'])
        assert 'model.predict' not in stages, '本次恢复不能混入旧调用的性能汇总'
