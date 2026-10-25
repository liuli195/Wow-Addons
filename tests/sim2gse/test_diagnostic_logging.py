"""显式命令控制诊断日志，业务规则与恢复凭据保留。"""
import pytest






@pytest.mark.real
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
