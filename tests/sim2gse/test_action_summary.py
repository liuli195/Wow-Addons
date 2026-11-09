"""真实任务入口拒绝损坏的成功统计；外部原生报告使用明确输入。"""
import json
from pathlib import Path

import pytest

import engine
from test_engine import static_snapshot
from test_search import public_formal_memory, _fast_report
from test_population_training import memory_ga
from test_seed_training import prepared_input
from task import TaskError, run_task

NATIVE_REFERENCE = engine.reference


@pytest.mark.parametrize('invalid', ['duration', 'missing', 'pairs', 'positions', 'scope', 'valid'])
def test_public_task_rejects_corrupt_success_summary_before_search(public_formal_memory, monkeypatch, invalid):
    case = public_formal_memory
    monkeypatch.setattr(engine, 'reference', NATIVE_REFERENCE)

    def native_report(profile, folder, mode='baseline', options=(), **kwargs):
        iterations = next(int(row.split('=', 1)[1]) for row in options if row.startswith('iterations='))
        report = _fast_report(case.character, 100.0, max(1, iterations - 1))
        report['sim']['players'][0].update(
            sim2gse_static_snapshot=static_snapshot(),
            sim2gse_action_summary=dict(scope=dict(allowed={}, excluded={}, windows='', policy='@apl', controlled=False), version=1, samples=max(1, iterations - 1),
                                       duration_ms=0, successes={}, pairs={}, outgoing={}))
        if invalid == 'missing':
            report['sim']['players'][0].pop('sim2gse_action_summary')
        elif invalid in ('pairs', 'positions', 'scope', 'valid'):
            report['sim']['players'][0]['sim2gse_action_summary'].update(
                duration_ms=max(1, iterations - 1) * 180000,
                scope=dict(allowed={'spell:1001': True}, excluded={}, windows='', policy='@apl', controlled=False),
                successes={'spell:1001': 2}, pairs={'spell:1001>spell:1001': 1},
                outgoing={'spell:1001': 1})
        if invalid == 'scope':
            report['sim']['players'][0]['sim2gse_action_summary']['scope']['windows'] = 'broken'
        if invalid == 'pairs':
            report['sim']['players'][0]['sim2gse_action_summary']['outgoing'] = {}
        if invalid == 'positions':
            report['sim']['players'][0]['sim2gse_action_summary']['positions'] = {'spell:1001@0': 3}
        (Path(folder) / 'native.pending.json').write_text(json.dumps(report), encoding='utf-8')
        return ''

    monkeypatch.setattr(engine, 'run', native_report)
    def run():
        return run_task('/memory/role.simc', '/memory/formal',
                        simulation_config=dict(target_count=1, scene='single_target'))
    if invalid == 'valid':
        result = run()
        assert result['native_reference']['action_summary']['successes'] == {'spell:1001': 2}
        assert result['native_reference']['action_summary']['outgoing'] == {'spell:1001': 1}
    else:
        with pytest.raises(TaskError, match='成功摘要'):
            run()


def test_public_training_preparation_rejects_missing_reference_summary(prepared_input, monkeypatch):
    import seed_training
    import result_store
    case = prepared_input
    files = {}
    monkeypatch.setattr(result_store, 'read_records', lambda *args: [])
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'write_text', lambda path, text, **kwargs: files.__setitem__(path, text))
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs: files[path])
    def native_report(profile, folder, **kwargs):
        report = _fast_report(case.inputs['character'], 100., 99)
        report['sim']['players'][0].pop('sim2gse_action_summary')
        files[Path(folder) / 'native.pending.json'] = json.dumps(report)
    monkeypatch.setattr(engine, 'run', native_report)
    with pytest.raises(ValueError, match='成功摘要'):
        seed_training.ensure_prepared('/memory/template', 1, '/memory/work', inputs=case.inputs,
            sources=[case.source('source', [['outbreak']])])
    assert case.writes == []
