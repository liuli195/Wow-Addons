"""Real consumer entry in an isolated connected project, without a user link."""
import json
import os
import pytest
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import Mock

REPOSITORY = Path(__file__).resolve().parents[2]


def test_report_preparation_converts_observations_without_two_full_collections():
    import tracemalloc
    import result_store
    observations = [dict(value=dict(tag=index)) for index in range(5000)]
    row = dict(report=dict(sim=dict(players=[dict(name='test',
        sim2gse_rule_observations=dict(state_observations=observations))])))
    tracemalloc.start()
    try:
        prepared = result_store.prepare_batch(row, diagnostic_logging=True)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    states = prepared['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations']
    assert len(states) == 5000
    assert states[123]['value_storage']['record'] == dict(tag=123)
    assert observations[123] == dict(value=dict(tag=123))
    assert peak < 4 * 1024 * 1024, f'报告转换保留了重复观察集合：{peak}字节'


@pytest.mark.parametrize('logging', [False, True])
def test_report_preparation_preserves_all_value_kinds_and_input_independence(logging):
    from copy import deepcopy
    import result_store
    states = [{}, dict(value=None), dict(value={}), dict(value=True), dict(value=2),
              dict(value=1.25), dict(value=dict(tag=7))]
    actions = [{}, dict(resource_costs=None), dict(resource_costs={}), dict(resource_costs=dict(rune=1))]
    row = dict(report=dict(sim=dict(players=[dict(name='角色', collected_data=dict(
        action_sequence=[dict(name='outbreak')], resource_overflowed={}),
        sim2gse_rule_observations=dict(state_observations=states, action_observations=actions))])))
    retained = deepcopy(row)
    prepared = result_store.prepare_batch(row, diagnostic_logging=logging)
    player = prepared['report']['sim']['players'][0]
    empty = dict(boolean=None, integer=None, number=None, record=None)
    expected = [dict(empty, version=1, kind='missing'), dict(empty, version=1, kind='unknown'),
        dict(empty, version=2, kind='empty_record'), dict(empty, version=1, kind='boolean', boolean=True),
        dict(empty, version=1, kind='integer', integer=2), dict(empty, version=1, kind='number', number=1.25),
        dict(empty, version=1, kind='record', record=dict(tag=7))]
    assert player['sim2gse_rule_observations']['state_observations'] == [dict(value_storage=v) for v in expected]
    assert player['sim2gse_rule_observations']['action_observations'] == [
        dict(resource_costs_storage=dict(version=1, kind='missing', keys=[])),
        dict(resource_costs=None, resource_costs_storage=dict(version=1, kind='unknown', keys=[])),
        dict(resource_costs=None, resource_costs_storage=dict(version=1, kind='record', keys=[])),
        dict(resource_costs=dict(rune=1), resource_costs_storage=dict(version=1, kind='record', keys=['rune']))]
    collected = dict(resource_overflowed=None)
    if logging: collected['action_sequence'] = [dict(name='outbreak')]
    assert player['collected_data'] == collected
    player['sim2gse_rule_observations']['state_observations'][-1]['value_storage']['record']['tag'] = 99
    assert row == retained


def test_binary_write_requires_capability_before_calling_storage(monkeypatch):
    import result_store

    blocked_write = Mock()
    monkeypatch.setattr(result_store, '_SKILL_API', {
        'DATA_STORE_CAPABILITIES': (), 'write': blocked_write})
    with pytest.raises(result_store.DataReadError) as error:
        result_store.write('binary_measurements', 'blocked', [{'payload': bytes([0, 255])}],
                           schema={'payload': 'BLOB'}, binary=True)
    assert 'binary-write-v1' in str(error.value)
    assert '更新技能' in str(error.value) and '重启' in str(error.value)
    blocked_write.assert_not_called()


@pytest.mark.real
def test_connected_consumer_reads_writes_without_old_user_installation(tmp_path, installed_data_store):
    source = installed_data_store
    installed = tmp_path / "installed"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    project = tmp_path / "project"
    adapter = project / "projects/sim2gse/result_store.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "projects/sim2gse/result_store.py", adapter)
    shutil.copy2(REPOSITORY / "projects/sim2gse/action_summary.py", adapter.with_name("action_summary.py"))
    connected = subprocess.run(
        [sys.executable, str(installed / "scripts/project_binding.py"), "connect", "--project", str(project)],
        text=True, capture_output=True,
    )
    assert connected.returncode == 0, connected.stderr
    env = dict(os.environ, USERPROFILE=str(tmp_path / "empty-home"), HOME=str(tmp_path / "empty-home"))
    program = """import json,runpy,sys
sys.path.insert(0,str(__import__('pathlib').Path(sys.argv[1]).parent))
m=runpy.run_path(sys.argv[1]);m['ensure_available']()
assert m['write']('measurements','one',[{'score':7,'parts':[{'value':4}]}])==1
assert m['read_records']('measurements','one',columns=['score'],filters={'score':7})==[{'score':7}]
assert m['read_records']('measurements','one',columns=['score'],filters={'score':8})==[]
assert m['write']('binary_measurements','one',[{'score':8,'payload':bytes([0,255])}],schema={'score':'INTEGER','payload':'BLOB'},binary=True)==1
assert m['read_records']('binary_measurements','one',columns=['payload'],filters={'score':8})==[{'payload':bytes([0,255])}]
summary=dict(version=1,samples=1,duration_ms=180000,successes={'spell:1':2},pairs={},outgoing={},positions={'spell:1@0':2},witnesses={},scope=dict(allowed={'spell:1':True},excluded={},windows='',policy='spell:1',controlled=True))
empty=dict(summary,successes={},positions={},scope=dict(allowed={'spell:2':True},excluded={},windows='',policy='spell:2',controlled=True))
rows=[dict(batch_key=key,report={'sim':{'players':[{'name':'test','sim2gse_action_summary':value}]}}) for key,value in [('first',summary),('second',empty)]]
assert m['write']('batches','mixed',[m['prepare_batch'](row) for row in rows])==2
restored=m['read_records']('batches','mixed')
assert [row['report']['sim']['players'][0]['sim2gse_action_summary'] for row in restored]==[summary,empty]
assert m['one']('batches','batch_key','first',group_key='mixed')['report']['sim']['players'][0]['sim2gse_action_summary']==summary
print(json.dumps(list(m['iter_rows']('SELECT score,parts[1].value AS part FROM measurements',tables=['measurements']))))
"""
    result = subprocess.run([sys.executable, "-c", program, str(adapter)], env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{"score": 7, "part": 4}]


def test_page_classifies_chained_locator_permission_error_without_http(monkeypatch):
    import interface
    import result_store
    import task

    permission_error = PermissionError('fixture: locator access denied')
    storage_error = result_store.DataReadError('report locator unavailable')
    storage_error.__cause__ = permission_error
    task_error = task.TaskError('read task failed')
    task_error.__cause__ = storage_error
    assert interface._is_storage_error(task_error)
    assert interface._friendly_error(task_error) == (
        '共享存储不可读取，请检查数据中心接入与读写权限后重试。')
    # 与真实GET相同的read_task失败分支；只替换文件发现/读取I/O，不替换页面映射。
    monkeypatch.setattr(Path, 'exists', lambda path: False)
    monkeypatch.setattr(interface, 'read_task', Mock(side_effect=task_error))
    state = interface.InterfaceHandler._read_public_state(None, Path('unused-task'), None)
    assert state['phase'] == 'storage_unavailable'
    assert state['storage_unavailable'] and state['recoverable']
    assert '共享存储' in state['error']
