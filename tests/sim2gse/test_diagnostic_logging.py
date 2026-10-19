"""显式命令控制诊断日志，业务规则与恢复凭据保留。"""
import runpy
from pathlib import Path

import pytest


def test_task_command_documents_explicit_logging_flag(capsys):
    from task import main
    with pytest.raises(SystemExit) as exit:
        main(['--help'])
    assert exit.value.code == 0
    assert '--diagnostic-logging' in capsys.readouterr().out


def test_interface_command_documents_same_logging_flag(capsys, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    launch = runpy.run_path(str(root / 'scripts/dev/sim2gse/interface.py'))
    monkeypatch.setattr('sys.argv', ['interface.py', '--help'])
    with pytest.raises(SystemExit) as exit:
        launch['main']()
    assert exit.value.code == 0
    assert '--diagnostic-logging' in capsys.readouterr().out


@pytest.mark.parametrize('enabled', [False, True])
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
    from test_search import _apl_task_boundary

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

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=stop_once):
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(total_budget_seconds=20, input_interval_ms=200,
                candidate_limit=5, round_candidate_limit=1,
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


def test_native_engine_default_keeps_only_required_exchange(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    import engine
    commands = []
    monkeypatch.setattr(engine, 'identity', lambda *args: (Path('simc-test'), {}))
    def process(command, *args, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=b'normal result', stderr=b'', elapsed_seconds=.01)
    monkeypatch.setattr(engine, 'run_command', process)
    folder = tmp_path / 'native'
    assert engine.run(tmp_path / 'role.simc', folder) == 'normal result'
    assert 'output=' + os.devnull in commands[0]
    assert not (folder / 'process.log').exists()
    assert not (folder / 'invocation.json').exists()


@pytest.mark.parametrize('enabled', [False, True])
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


@pytest.mark.parametrize('enabled', [False, True])
def test_public_task_exports_current_invocation_stage_totals(tmp_path, monkeypatch, enabled):
    import json
    import sequence
    from unittest.mock import patch
    from task import run_task, read_task
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
    clock_calls = []
    if not enabled:
        import runtime
        def unexpected_clock():
            clock_calls.append('called')
            raise AssertionError('关闭总开关不得额外计时')
        monkeypatch.setattr(runtime.time, 'perf_counter', unexpected_clock)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(total_budget_seconds=20, input_interval_ms=200,
                candidate_limit=5, round_candidate_limit=1, batch_targets=(2,), iterations=2,
                validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',),
                diagnostic_logging=enabled, diagnostics='summary'))
        saved = read_task(destination, include_search_records=True)
    assert any(step.get('selection', {}).get('feedback', {}).get('status') == 'learned'
               for step in saved['search']['rule_steps'].values())
    output = destination / 'diagnostics.json'
    if not enabled:
        assert clock_calls == []
        assert not output.exists()
        return
    performance = json.loads(output.read_text(encoding='utf-8'))['performance']
    assert performance['scope'] == 'current_invocation'
    assert performance['timing'] == 'inclusive_wall_seconds'
    stages = performance['stages']
    for name in ('diagnostic.total', 'diagnostic.read_validate', 'diagnostic.preprocess',
                 'diagnostic.rules', 'diagnostic.finalize',
                 'report.prepare', 'report.write', 'state.persist.full', 'state.persist.partial',
                 'state.transaction', 'state.progress', 'model.load', 'model.predict', 'model.learn',
                 'model.snapshot', 'model.full_write', 'model.control_write'):
        assert stages[name]['calls'] > 0, name
        assert stages[name]['seconds'] >= 0, name
    assert stages['model.predict']['units']['actions'] > 0
    assert stages['model.learn']['units']['common_batches'] > 0
    assert stages['report.write']['units']['rows'] > 0
    assert stages['state.persist.full']['units']['written_bytes'] > 0


def test_timing_failure_does_not_replace_report_error(monkeypatch):
    import runtime
    import result_store
    def broken_clock():
        raise RuntimeError('计时源不可用')
    monkeypatch.setattr(runtime.time, 'perf_counter', broken_clock)
    with pytest.raises(KeyError, match='report'):
        result_store.write_batch('invalid', {}, runtime=runtime.TaskRuntime(diagnostic_logging=True))


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('flow', ['finalizing', 'exhausted_resume', 'continue_resume'])
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
    config = dict(total_budget_seconds=20, input_interval_ms=200, candidate_limit=6,
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
    stages = json.loads(output.read_text(encoding='utf-8'))['performance']['stages']
    assert stages['model.learn']['calls'] == 2
    assert stages['model.learn']['units']['common_batches'] == 2
    if resume:
        assert stages['model.full_write']['calls'] == 2
        assert 'model.predict' not in stages, '本次恢复不能混入旧调用的性能汇总'
