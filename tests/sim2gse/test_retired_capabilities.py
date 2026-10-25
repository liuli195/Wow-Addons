"""用户已移除两可选搜索能力；公开入口拒绝旧键而非静默关闭。"""
from pathlib import Path
import pytest


@pytest.mark.real
def test_public_formal_search_without_profession_rule_library_keeps_native_three_part_scope(
        tmp_path, monkeypatch):
    from unittest.mock import patch
    import engine
    from task import run_task, read_task, resume_task
    from test_search import _fast_search_boundary, _fast_reference, sample_profile
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(tmp_path / 'removed-rules.json'))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile())
    def reference(*args, **kwargs):
        native = _fast_reference(*args, **kwargs)
        native['static_snapshot']['hero_subtree_ids'] = [32]
        return native
    with _fast_search_boundary(), patch.object(engine, 'reference', side_effect=reference):
        result = run_task(source, tmp_path / 'task', search_config=dict(candidate_limit=1,
            batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task', include_search_records=True)
        assert saved['status'] == 'completed'
        assert saved['search']['configuration_key'] == dict(specialization_id=252,
            hero_talent='rider_of_the_apocalypse', target_type='single_target')
        assert len(result['search']['starts']) == 4
        assert all('rule_observations' not in row['request']
            for record in saved['search']['records'] for row in record['batches'])
        before = saved['search_result']
        assert resume_task(tmp_path / 'task')['status'] == 'completed'
        assert read_task(tmp_path / 'task')['search_result'] == before
    assert not (tmp_path / 'removed-rules.json').exists()


@pytest.mark.parametrize('key',['adaptive_selector_enabled','rule_initialization_enabled','rule_diagnostics_policy'])
@pytest.mark.parametrize('value',[False,True])
def test_public_task_rejects_removed_capability_even_when_disabled(key,value):
    from task import run_task
    with pytest.raises(ValueError,match='已移除'):
        run_task('/absent/role.simc','/absent/task',search_config={key:value,'candidate_limit':1})


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


@pytest.fixture
def training_project(tmp_path, installed_data_store, monkeypatch):
    import shutil
    import result_store
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    shutil.copytree(installed_data_store, tmp_path / '.local/skills/data-store')
    result_store.bind_project(tmp_path)
    return tmp_path


from test_population_training import registered_six


@pytest.mark.real
def test_public_ga_without_profession_rule_library_publishes_native_scope(
        tmp_path, monkeypatch, training_project, registered_six):
    import engine
    from unittest.mock import patch
    from seed_training import run_training
    from test_seed_training import training_boundary
    from test_search import _fast_reference, sample_profile
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(tmp_path / 'removed-rules.json'))
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    def reference(*args, **kwargs):
        native = _fast_reference(*args, **kwargs)
        native['static_snapshot']['hero_subtree_ids'] = [32]
        return native
    import simulation_config
    settings = tmp_path / 'config.toml'
    settings.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    with training_boundary(), patch.object(engine, 'reference', side_effect=reference):
        result = run_training(template, 1, tmp_path / 'work')
    assert result['status'] == 'completed'
    assert result['configuration_key'] == dict(specialization_id=252,
        hero_talent='rider_of_the_apocalypse', target_type='single_target')
    assert result['selected'] == 4


@pytest.mark.real
def test_public_foreground_cancel_stops_both_active_ga_groups_and_keeps_old_publication(
        tmp_path, capsys, training_project, registered_six):
    import json
    import threading
    from unittest.mock import patch
    import sequence
    import result_store
    from seed_training import main, SELECTED_SCHEMA, shared_scope
    from seed_activity import foreground_search
    from test_seed_training import training_boundary
    from test_character_export import sample_profile
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    previous = {}
    for target, scene in ((1, 'single_target'), (5, 'aoe')):
        key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type=scene)
        scope = shared_scope(key)
        row = dict(configuration_key=key, candidate_id='old', condition='old', class_name='deathknight',
            spec='unholy', targets=target, program=[['outbreak']], family='old', score=1., scores=[1.]*3,
            template_sha256='old', engines={})
        result_store.write('seed_selected', scope, [row], schema=SELECTED_SCHEMA)
        previous[scope] = result_store.read_records('seed_selected', scope)
    active, groups, lock, ready = [], set(), threading.Lock(), threading.Event()
    outcome = []
    def blocked(profile, candidate, folder, **options):
        scope = Path(folder).parts[Path(folder).parts.index('ga') + 1]
        with lock:
            active.append(scope)
            groups.add(scope)
            if len(groups) == 2: ready.set()
        try:
            assert options['runtime'].cancel_event.wait(8), '前台搜索须取消全部活跃组'
            options['runtime'].check()
        finally:
            with lock: active.remove(scope)
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1', '5',
        '--legacy', '--workspace', str(tmp_path / 'work'), '--max-trainings', '2', '--max-processes', '1']
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=blocked):
        worker = threading.Thread(target=lambda: outcome.append(main(args)))
        worker.start()
        try:
            assert ready.wait(8), '须真实同时进入两个GA组的原生边界'
            with foreground_search():
                worker.join(8)
        finally:
            worker.join(8)
    assert not worker.is_alive() and active == [] and len(groups) == 2
    assert outcome == [2]
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 2 and {row['status'] for row in output} == {'paused'}
    for scope, rows in previous.items():
        assert result_store.read_records('seed_selected', scope) == rows


@pytest.mark.real
def test_public_concurrent_prepare_uses_check_frozen_burst_identity_without_rediscovery(
        tmp_path, capsys, training_project, registered_six):
    import json
    import threading
    from unittest.mock import patch
    import burst
    import engine
    from seed_training import main
    from test_seed_training import training_boundary
    from test_character_export import sample_profile
    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text())
    definition['blocks'] = [[dict(kind='spell', simc_action='death_coil', name='死亡缠绕', spell_id=1002)]]
    definition['excluded_spell_ids'] = [1002]
    original = burst.publish(definition)
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    barrier, changed = threading.Barrier(2), threading.Event()
    observed = []
    with training_boundary():
        reference, prepare = engine.reference, engine.prepare_loop
        def native(*args, **options):
            result = reference(*args, **options)
            result['identity']['data_version'] = original['data_version']
            barrier.wait(8)
            if options['simulation_config']['target_count'] == 1:
                burst.publish(dict(original, version=original['version'] + '-changed'))
                changed.set()
            assert changed.wait(8)
            return result
        def prepared(*args, **options):
            observed.append(options['definition']['definition_id'])
            return prepare(*args, **options)
        with patch.object(engine, 'reference', side_effect=native), \
                patch.object(engine, 'prepare_loop', side_effect=prepared), \
                patch.object(burst, 'select_definition', wraps=burst.select_definition) as discovery:
            status = main(['--project', str(tmp_path), 'prepare', '--template', str(template), '--targets', '1', '5',
                '--use-burst', '--workspace', str(tmp_path / 'work'), '--max-trainings', '2', '--max-processes', '1'])
    assert status == 0 and discovery.call_count == 1
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 2 and {row['status'] for row in output} == {'prepared'}
    assert observed == [original['definition_id']] * 2
    assert burst.load(original['spec_id'])['definition_id'] != original['definition_id']


@pytest.mark.parametrize('options',[dict(diagnostics='full'),dict(search_observability='summary'),dict(search_observability='full')])
def test_public_pretraining_rejects_unsupported_observation_levels_before_any_work(monkeypatch,options):
    import engine
    from seed_training import run_training
    def forbidden(*args,**kwargs): raise AssertionError('不支持的预训练观测不得启动计算')
    monkeypatch.setattr(engine,'reference',forbidden)
    with pytest.raises(ValueError,match='预训练仅支持基础性能日志和时间DPS曲线'):
        run_training('/absent/role.simc',1,'/absent/work',diagnostic_logging=True,search_config=options)
