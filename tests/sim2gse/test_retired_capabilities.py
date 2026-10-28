"""用户已移除两可选搜索能力；公开入口拒绝旧键而非静默关闭。"""
from copy import deepcopy
from pathlib import Path
import pytest


RETIRED_SEARCH_PARAMETERS = (
    'total_budget_seconds', 'search_budget_seconds', 'candidate_limit',
    'round_candidate_limit', 'no_improvement_rounds', 'batch_targets',
    'validation_batches', 'final_batches', 'final_iterations', 'trace_search', 'scenarios',
)


@pytest.mark.parametrize('entry,key', [('run', key) for key in RETIRED_SEARCH_PARAMETERS]
    + [(entry, 'total_budget_seconds') for entry in ('resume', 'dual', 'training')])
def test_public_search_rejects_retired_parameters_before_input_or_native_io(monkeypatch, key, entry):
    import task
    import dual_task
    def forbidden(*args, **kwargs):
        raise AssertionError('退役参数必须在角色或任务文件读取前拒绝')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    with pytest.raises(ValueError, match='已退役'):
        if entry == 'run':
            task.run_task('/absent/role.simc', '/absent/task', search_config={key: False})
        elif entry == 'resume':
            task.resume_task('/absent/task', search_config={key: False})
        elif entry == 'dual':
            dual_task.start('/absent/role.simc', '/absent/task', search_config={key: False})
        else:
            from seed_training import run_training
            run_training('/absent/role.simc', 1, '/absent/task', search_config={key: False})


@pytest.mark.parametrize('key',['adaptive_selector_enabled','rule_initialization_enabled','rule_diagnostics_policy'])
@pytest.mark.parametrize('value',[False,True])
def test_public_task_rejects_removed_capability_even_when_disabled(key,value):
    from task import run_task
    with pytest.raises(ValueError,match='已移除'):
        run_task('/absent/role.simc','/absent/task',search_config={key: value})


@pytest.mark.parametrize('key',['adaptive_selector_enabled','rule_initialization_enabled','rule_diagnostics_policy'])
def test_public_task_rejects_removed_toml_before_reading_profile(monkeypatch,key):
    from io import StringIO
    import simulation_config
    from task import run_task
    load_search_config = simulation_config.load_search_config
    monkeypatch.setattr(simulation_config, 'load_search_config', lambda **values:
                        load_search_config(StringIO('[search]\n'+key+' = false\n'), **values))
    def forbidden(*args, **kwargs):
        raise AssertionError('removed configuration must reject before profile IO')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    with pytest.raises(ValueError,match='已移除'):
        run_task('/absent/role.simc','/absent/task')


@pytest.mark.parametrize('key',['adaptive_selector_enabled','rule_initialization_enabled','rule_diagnostics_policy'])
def test_public_resume_rejects_removed_override_before_reading_old_task(key):
    from task import resume_task
    with pytest.raises(ValueError,match='已移除'):
        resume_task('/absent',search_config={key:False})


@pytest.mark.parametrize('options',[{'rule_step':{}},{'diagnostic_candidate_key':'old','diagnostic_budget_seconds':1}])
def test_public_resume_rejects_retired_rule_edit_and_diagnosis_before_reading_task(options):
    from task import resume_task
    with pytest.raises(ValueError,match='已移除'): resume_task('/absent',**options)


@pytest.mark.parametrize('command',['rules-check','rules-save'])
def test_public_cli_rejects_retired_rule_editor(capsys,command):
    from task import main
    assert main([command,'/absent/old.json','--expected-digest','old'])==2
    assert '已移除' in capsys.readouterr().err


def test_research_cli_rejects_retired_per_material_ab_execution_before_loading_materials(monkeypatch,capsys):
    import importlib.util
    import sys
    from unittest.mock import patch
    root=Path(__file__).resolve().parents[2]
    before=list(sys.path)
    spec=importlib.util.spec_from_file_location('retired_population_ab',root/'scripts/dev/sim2gse/population_ab.py')
    module=importlib.util.module_from_spec(spec)
    # Do not install the experiment's Linux-only msvcrt shim in this interpreter.
    with patch.object(sys,'platform','win32'): spec.loader.exec_module(module)
    def forbidden(*args): raise AssertionError('retired mode must reject before material IO')
    monkeypatch.setattr(module,'load_materials',forbidden)
    monkeypatch.setattr(sys,'argv',['population_ab','--materials','/absent/materials.json',
        '--output',str(root/'.local/population-mvp/retired-mode'),'--check-only'])
    try:
        with pytest.raises(SystemExit) as stopped: module.main()
        assert stopped.value.code==2
        assert '旧AB逐材料训练执行已移除' in capsys.readouterr().err
    finally: sys.path[:]=before


@pytest.mark.parametrize('command',['task','seed_training'])
@pytest.mark.parametrize('flag',['--adaptive-selector-enabled','--no-adaptive-selector-enabled',
    '--rule-initialization-enabled','--no-rule-initialization-enabled'])
def test_public_cli_rejects_removed_options_instead_of_silently_disabling(capsys,command,flag):
    from importlib import import_module
    args=['--output','/absent/task'] if command=='task' else ['--project','/absent','run']
    with pytest.raises(SystemExit) as stopped: import_module(command).main([*args,flag])
    assert stopped.value.code==2 and '已移除' in capsys.readouterr().err


@pytest.mark.parametrize('key',['adaptive_selector_enabled','rule_initialization_enabled','rule_diagnostics_policy'])
def test_public_resume_refuses_incompatible_frozen_modes_without_rewriting_identity(monkeypatch,key):
    from contextlib import nullcontext
    from copy import deepcopy
    import hashlib,json,sqlite3
    import result_store,search,task,seed_activity
    from program import BEHAVIOR_IDENTITY_VERSION
    from simulation_config import config_for
    raw=b'fixed original bytes'
    identity=dict(input_original_sha256=hashlib.sha256(raw).hexdigest(),input_effective_sha256=hashlib.sha256(raw).hexdigest())
    original=json.dumps(identity)
    store=search.TaskStore('/memory',connection=sqlite3.connect(':memory:'),reusable_database=':memory:',report_locations={})
    store.state.update(identity,formal_search_version=1,behavior_identity_version=BEHAVIOR_IDENTITY_VERSION,
        config={key:False},simulation_config=config_for())
    before=deepcopy(store.state)
    monkeypatch.setattr(search,'TaskStore',lambda *args:store)
    monkeypatch.setattr(task, '_read_resume_checkpoint', lambda *args: deepcopy(store.state))
    monkeypatch.setattr(result_store,'ensure_available',lambda:None)
    monkeypatch.setattr(seed_activity,'foreground_search',nullcontext)
    monkeypatch.setattr(task,'_task_lease',lambda *args,**kwargs:nullcontext())
    monkeypatch.setattr(Path,'read_text',lambda *args,**kwargs:original)
    monkeypatch.setattr(Path,'read_bytes',lambda *args,**kwargs:raw)
    with pytest.raises(ValueError,match='已移除.*身份不兼容'): task.resume_task('/memory')
    assert store.state==before and json.dumps(identity)==original


def test_public_training_refuses_old_per_material_workspace_before_native(monkeypatch):
    import population_training
    import seed_training
    old=Path('/memory/work/1/old-condition/identity.json')
    monkeypatch.setattr(Path,'glob',lambda path,pattern:iter([old]))
    def forbidden(*args,**kwargs): raise AssertionError('旧任务不允许进入新GA准备')
    monkeypatch.setattr(seed_training,'ensure_prepared',forbidden)
    with pytest.raises(ValueError,match='旧逐材料.*不能.*恢复'):
        population_training.run_group('/memory/role.simc',1,'/memory/work',cancel_event=None,
            use_burst=False,sources=[],config={})


@pytest.mark.parametrize('options',[dict(diagnostics='full'),dict(search_observability='summary'),dict(search_observability='full')])
def test_public_pretraining_rejects_unsupported_observation_levels_before_any_work(monkeypatch,options):
    import engine
    from seed_training import run_training
    def forbidden(*args,**kwargs): raise AssertionError('不支持的预训练观测不得启动计算')
    monkeypatch.setattr(engine,'reference',forbidden)
    with pytest.raises(ValueError,match='预训练仅支持基础性能日志和时间DPS曲线'):
        run_training('/absent/role.simc',1,'/absent/work',diagnostic_logging=True,search_config=options)


def test_current_search_keeps_frozen_reset_semantics_without_a_scenario_switch():
    from search import config_for
    aligned = dict(input_interval_ms=200, reset_events=[(400, 'shift')])
    assert config_for(aligned)['reset_events'] == ((400, 'shift'),)
    with pytest.raises(ValueError, match='点击对齐'):
        config_for(dict(aligned, reset_events=[(401, 'shift')]))
    with pytest.raises(ValueError, match='nominal'):
        config_for(aligned, training=True)
    assert config_for(dict(aligned, scenarios=['nominal']), legacy=True)['scenarios'] == ('nominal',)


@pytest.mark.parametrize('entry', ['prepare', 'restore', 'publish'])
def test_old_champion_intent_cannot_write_or_complete_a_task(entry):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import task
    state = dict(formal_champion_publication_intent=dict(record=dict(contract_version=1)),
                 formal_champion_publication=dict(status='pending'))
    if entry != 'prepare':
        state['formal_search'] = {'version': 1}
    store = SimpleNamespace(state=state, checkpoint=Mock(side_effect=AssertionError('must not write')))
    before = deepcopy(state)
    with pytest.raises(task.TaskError, match='已退役'):
        if entry == 'prepare':
            task._prepare_formal_publication(store)
        elif entry == 'restore':
            task._restore_formal_result(store, None, None)
        else:
            task._publish_formal_champion(store, None)
    assert state == before
    store.checkpoint.assert_not_called()


def test_retired_toml_settings_cannot_reenter_current_defaults():
    from io import StringIO
    from simulation_config import load_search_config
    from search import config_for
    for key in RETIRED_SEARCH_PARAMETERS:
        with pytest.raises(ValueError, match='已退役'):
            load_search_config(StringIO('[search]\n' + key + '=false\n'))
    assert not set(RETIRED_SEARCH_PARAMETERS) & config_for().keys()


@pytest.mark.parametrize('old_state', [
    {'config': {}},
    {'formal_search_version': 1, 'formal_search': {'version': 1}, 'config': {},
     'formal_champion_publication_intent': {'record': {'contract_version': 1}}},
])
def test_public_resume_rejects_old_contract_without_opening_writable_store(monkeypatch, old_state):
    import json
    import sqlite3
    import search
    import task
    import seed_activity
    database = sqlite3.connect(':memory:')
    database.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, value TEXT)')
    database.execute('INSERT INTO state VALUES (1, ?)', (json.dumps(old_state),))
    database.commit()
    statements, connections = [], []
    database.set_trace_callback(statements.append)
    def connect(path, **kwargs):
        connections.append((path, kwargs))
        return database
    def forbidden(*args, **kwargs):
        raise AssertionError('old resume must reject before writable state or foreground/timeline effects')
    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(search.TaskStore, '_initialize', forbidden)
    monkeypatch.setattr(seed_activity, 'foreground_search', forbidden)
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    with pytest.raises(task.TaskError, match='旧正式'):
        task.resume_task('/memory/old', search_timeline=True)
    assert connections and all(path.endswith('?mode=ro') and kwargs == {'uri': True}
                               for path, kwargs in connections)
    assert statements and all(sql.lstrip().upper().startswith('SELECT ') for sql in statements)


@pytest.mark.parametrize('operation', ['resume', 'cancel_saved'])
def test_old_dual_is_read_only_before_leases_or_engine_checks(monkeypatch, operation):
    import dual_task
    import engine
    import task
    monkeypatch.setattr(dual_task, '_load', lambda *args: dict(config={}))
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy parent is read-only')
    monkeypatch.setattr(task, '_task_lease', forbidden)
    monkeypatch.setattr(engine, 'identity', forbidden)
    monkeypatch.setattr(dual_task, '_save', forbidden)
    with pytest.raises(task.TaskError, match='已退役'):
        getattr(dual_task, operation)('/memory/old')
