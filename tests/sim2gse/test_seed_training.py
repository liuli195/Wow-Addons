"""训练规则与准备缓存使用显式内存输入，不证明物理持久化。"""
import json
from pathlib import Path
import subprocess


import pytest


def command(tmp_path, args):
    from seed_training import main
    # 仅关闭独立爆发；prepare/run均使用唯一GA实现。
    if args[0] in ('run', 'prepare', 'list') and '--use-burst' not in args:
        args = [*args, '--legacy']
    if args[0] == 'list' and '--state' in args and args[args.index('--state') + 1] in ('selected', 'processed') and '--specialization-id' not in args:
        count = int(args[args.index('--targets') + 1]) if '--targets' in args else 1
        args = [*args, '--specialization-id', '252', '--hero-talent', 'rider_of_the_apocalypse',
                '--target-type', 'single_target' if count == 1 else 'aoe']
    return main(['--project', str(tmp_path), *args])


@pytest.fixture
def training_cli(monkeypatch):
    """CLI scheduling with fixed template/registry IO, never a training executor."""
    from contextlib import nullcontext
    import threading
    import engine, result_store, seed_training, seed_activity, simulation_config
    from test_character_export import sample_profile
    monkeypatch.setattr(result_store,'bind_project',lambda project:None)
    monkeypatch.setattr(result_store,'ensure_available',lambda:None)
    monkeypatch.setattr(seed_training,'writer_lock',nullcontext)
    monkeypatch.setattr(seed_activity,'training_activity',lambda:nullcontext(threading.Event()))
    monkeypatch.setattr(seed_training,'registry_rows',lambda:[])
    monkeypatch.setattr(seed_training,'sync_history',lambda character,**kwargs:kwargs.get('sources',[]))
    template=Path('/.tools/sim2gse/build/baseline/Rider.simc').resolve()
    monkeypatch.setattr(engine,'training_templates',lambda:(template,))
    monkeypatch.setattr(engine,'identity',lambda mode:(Path('/engine'),dict(upstream_commit='fixed-engine')))
    monkeypatch.setattr(Path,'is_file',lambda path:True)
    monkeypatch.setattr(Path,'read_text',lambda path,**kwargs:sample_profile())
    monkeypatch.setattr(simulation_config,'DEFAULT_PATH',Path('/absent/training.toml'))
    return template


@pytest.fixture
def prepared_input(monkeypatch):
    """A verified preparation cache is a data input, not an emulated center."""
    from copy import deepcopy
    from types import SimpleNamespace
    import codec,program,result_store,seed_training as seeds,task
    from test_search import _fast_capabilities
    from test_character_export import sample_profile
    from search import config_for,digest
    config=config_for(dict(max_processes=1),training=True)
    character=seeds.template_character(sample_profile())
    capabilities=_fast_capabilities()
    native=dict(identity=dict(spec_id=252,race=character.race,resource='runic_power'),
                static_snapshot=dict(hero_subtree_ids=[32]))
    inputs=dict(text=sample_profile(),character=character,scope='deathknight-unholy-1',config=config,
        simulation_config=dict(target_count=1,scene='single_target',enable_omnium_talents=True),
        engines={'baseline':'fixed'},template_sha='fixed-template',definition=None,rule_snapshot=None)
    preparation=dict(version=seeds.PREPARATION_VERSION,template=inputs['template_sha'],engines=inputs['engines'],
        simulation=inputs['simulation_config'],definition=None,semantics=seeds.semantic_versions(),
        config=seeds._identity_config(config))
    key=digest(preparation)
    header=dict.fromkeys(seeds.PREPARED_SCHEMA)
    header.update(kind='context',config_key=key,version=seeds.PREPARATION_VERSION,
        context=dict(native=native,all_capabilities=capabilities,capabilities=capabilities,burst=None,
                     representations={}))
    header['checksum']=digest([{name:value for name,value in header.items() if name!='checksum'}])
    writes=[]
    monkeypatch.setattr(result_store,'read_records',lambda table,key:deepcopy([header]))
    monkeypatch.setattr(result_store,'write',lambda *args,**kwargs:writes.append(deepcopy(args)))
    monkeypatch.setattr(codec,'load_targeting',lambda **kwargs:dict(target_masks={}))
    monkeypatch.setattr(program,'compile_program',lambda *args,**kwargs:{})
    monkeypatch.setattr(task,'_rule_hashes',lambda **kwargs:{})
    def source(label,program):
        return dict(dict.fromkeys(seeds.CANDIDATE_SCHEMA),candidate_id=label,source_id=label,label=label,
            class_name='deathknight',spec='unholy',source='fixture',original='fixture',instructions='repeat',
            semantic='preserved',changes=[],family='plain',core=[],program=program,active=True)
    return SimpleNamespace(inputs=inputs,header=header,writes=writes,source=source)

def test_training_check_locates_current_template_without_starting_compute(monkeypatch,capsys,training_cli):
    from seed_training import main
    def forbidden(*args,**kwargs): raise AssertionError('只读训练检查不能启动计算进程')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    assert main(['--project','/memory','check','--legacy'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='ready' and Path(result['template']) == training_cli
    assert result['engines']['baseline']['upstream_commit']==result['engines']['controlled']['upstream_commit']


@pytest.mark.parametrize('entry',['run'])
def test_training_entry_refuses_missing_definition_before_starting_compute(monkeypatch,capsys,training_cli,entry):
    from unittest.mock import MagicMock
    import result_store
    from seed_training import main
    cursor=MagicMock()
    cursor.__enter__.return_value.fetchone.return_value=None
    monkeypatch.setattr(result_store,'query',lambda *args,**kwargs:cursor)
    def forbidden(*args,**kwargs): raise AssertionError('缺少审核定义时不能启动计算进程')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    assert main(['--project','/memory',entry,'--workspace','/memory/work'])==2
    assert '已审核' in capsys.readouterr().err


@pytest.mark.parametrize('entry',['run','prepare'])
def test_training_cli_override_repairs_partial_config_without_precheck_losing_it(monkeypatch,capsys,training_cli,entry):
    import population_training,seed_training,simulation_config
    from unittest.mock import Mock
    monkeypatch.setattr(simulation_config,'_load_document',lambda path=None:dict(training=dict(max_trainings=10,top_k=4,
        crossover_probability=0.,mutation_probability=0.)))
    monkeypatch.setattr(population_training,'_unfinished',lambda *args,**kwargs:iter(()))
    execute=Mock(side_effect=lambda *args,**kwargs:dict(status='prepared' if kwargs['prepare_only'] else 'completed',
        training_config=kwargs['training_config']))
    monkeypatch.setattr(seed_training,'_run_training',execute)
    assert seed_training.main(['--project','/memory',entry,'--legacy','--targets','1','--max-processes','2',
                               '--workspace','/memory/work'])==0
    outcome=json.loads(capsys.readouterr().out)[0]
    assert outcome['status']==('completed' if entry=='run' else 'prepared')
    assert outcome['training_config']['max_trainings']==10 and outcome['training_config']['max_processes']==2
    assert execute.call_count==1
    assert seed_training.main(['--project','/memory','check','--legacy'])==2
    assert '乘积不得超过20' in capsys.readouterr().err


@pytest.mark.parametrize(('settings','expected'),[
    ({},('8候选','120请求批','15360请求迭代')),
    (dict(top_k=4,retest_batches=2,retest_iterations=7),('4候选','40请求批','280请求迭代'))])
def test_training_run_shows_requested_retest_maximum_before_compute_and_keeps_it_on_resume(
        monkeypatch,capsys,training_cli,settings,expected):
    import population_training,seed_training,simulation_config
    from runtime import TaskCancelled
    current=dict(max_trainings=1,max_processes=1,**settings)
    monkeypatch.setattr(simulation_config,'_load_document',lambda path=None:dict(training=current))
    frozen=simulation_config.load_training_config()
    manifest=dict(template_path=str(training_cli),environment=dict(template='fixed',simulation=dict(target_count=1)),training_config=frozen)
    monkeypatch.setattr(population_training,'_unfinished',lambda *args,**kwargs:iter([(Path('/saved'),manifest)]))
    for resume in (False,True):
        checked=[]
        def execute(*args,**kwargs):
            message=capsys.readouterr()
            assert all(value in message.err for value in expected)
            assert '五场景复测' in message.err and '非实际有效样本' in message.err and message.out==''
            checked.append(True)
            if not resume: raise TaskCancelled('fixture pause after startup')
            return dict(status='completed')
        monkeypatch.setattr(seed_training,'_run_training',execute)
        assert seed_training.main(['--project','/memory','run','--legacy','--targets','1','--workspace','/memory/work'])==(0 if resume else 2)
        assert checked
        outcome=json.loads(capsys.readouterr().out)[0]
        assert outcome['status']==('completed' if resume else 'paused')
        current=dict(top_k=12,retest_batches=1,retest_iterations=2)


def test_training_list_defaults_to_burst_and_preserves_legacy_results(monkeypatch,capsys,training_cli):
    import result_store
    from seed_training import main
    from unittest.mock import Mock
    reader=Mock(side_effect=[[],[dict(candidate_id='legacy-only')]])
    monkeypatch.setattr(result_store,'read_records',reader)
    assert main(['--project','/memory','list','--state','selected'])==0
    assert json.loads(capsys.readouterr().out)==[]
    assert reader.call_args.args==('seed_selected','deathknight-unholy-1-burst')
    assert main(['--project','/memory','list','--state','selected','--legacy'])==0
    assert json.loads(capsys.readouterr().out)[0]['candidate_id']=='legacy-only'
    assert reader.call_args.args==('seed_selected','deathknight-unholy-1')


def test_cleaned_candidate_registration_is_reusable_and_rejects_missing_provenance(monkeypatch):
    from contextlib import nullcontext
    from copy import deepcopy
    from unittest.mock import Mock
    import result_store,seed_training
    source=dict(label='ABC-C',spec='unholy',class_name='deathknight',source='plugin:Smolbreather',
        original='15 ordered spell ids',instructions='continuous unmodified key',semantic='rewritten',
        changes=['remove movement'],family='plugin-opener',core=[['putrefy'],['death_coil']],
        program=[['outbreak'],['putrefy'],['death_coil']])
    monkeypatch.setattr(Path,'read_text',lambda *args,**kwargs:json.dumps(source))
    monkeypatch.setattr(seed_training,'writer_lock',nullcontext)
    writes=Mock()
    monkeypatch.setattr(result_store,'write',writes)
    monkeypatch.setattr(seed_training,'registry_rows',Mock(return_value=[]))
    first=seed_training.register('/memory/cleaned.json')
    table,key,rows=writes.call_args.args
    assert (table,key)==('seed_candidates','registry') and len(rows)==1 and rows[0]['label']=='ABC-C'
    monkeypatch.setattr(seed_training,'registry_rows',Mock(return_value=deepcopy(rows)))
    writes.reset_mock()
    assert seed_training.register('/memory/cleaned.json')==first
    writes.assert_not_called()
    source.pop('changes')
    with pytest.raises(ValueError,match='清洗件必须包含'): seed_training.register('/memory/cleaned.json')
    writes.assert_not_called()


def test_historical_training_condition_excludes_only_execution_and_keeps_real_inputs():
    from copy import deepcopy
    from search import config_for
    from seed_training import RETEST_SEEDS, TRAINING_VERSION, semantic_condition, semantic_versions
    payload = dict(version=TRAINING_VERSION, template='original-role',
        engines={'baseline': 'original-engine'},
        config=config_for(dict(diagnostic_logging=True, no_improvement_rounds=2), legacy=True),
        simulation=dict(target_count=1, enable_omnium_talents=True), retest=RETEST_SEEDS,
        effective_options=['threads=1'], rule_config_digest='original-rules',
        rules={'projects/sim2gse/seed_training.py': 'original-source'})
    versions = semantic_versions()
    expected = semantic_condition(payload, versions)
    execution = deepcopy(payload)
    execution['config']['max_processes'] = 16
    execution['config'].update(diagnostic_logging=False, diagnostics='full', search_observability='full')
    execution['rules']['projects/sim2gse/seed_training.py'] = 'logging-only-source-change'
    assert semantic_condition(execution, versions) == expected
    for field, value in [('template', 'new-role'), ('engines', {'baseline': 'new-engine'}),
                         ('retest', [20261011]), ('effective_options', ['threads=2']), ('rule_config_digest', 'new-rules')]:
        assert semantic_condition(dict(payload, **{field: value}), versions) != expected
    for key in ('random_seed', 'iterations', 'no_improvement_rounds', 'input_interval_ms'):
        changed = deepcopy(payload)
        changed['config'][key] += 1
        assert semantic_condition(changed, versions) != expected
    assert semantic_condition(payload, dict(versions, search='new-search')) != expected


def test_missing_project_and_unreadable_center_are_not_silently_empty(monkeypatch,capsys,training_cli):
    import result_store
    from seed_training import main
    with pytest.raises(SystemExit): main(['list'])
    def unreadable(*args,**kwargs): raise PermissionError('数据中心暂时不可读')
    monkeypatch.setattr(result_store,'read_records',unreadable)
    assert main(['--project','/memory','list'])==2
    assert '数据中心暂时不可读' in capsys.readouterr().err


def test_unconnected_public_search_does_not_create_data_root(monkeypatch):
    from unittest.mock import Mock
    from task import run_task
    from contextlib import nullcontext
    import seed_activity
    monkeypatch.setattr(seed_activity, 'foreground_search', nullcontext)
    import result_store
    def unavailable(): raise RuntimeError('数据中心尚未接入本项目')
    monkeypatch.setattr(result_store,'ensure_available',unavailable)
    mkdir=Mock(side_effect=AssertionError('unconnected search must not create directories'))
    monkeypatch.setattr(Path,'mkdir',mkdir)
    with pytest.raises(RuntimeError,match='数据中心尚未接入本项目'):
        run_task('/absent/role.simc','/absent/unconnected-task')
    mkdir.assert_not_called()


@pytest.mark.parametrize('illegal_program',[[['death_coil']*16],[dict(kind='CastSequence',members=['death_coil']*32)]])
def test_prepare_rejects_oversize_macro_without_losing_legal_materials(prepared_input,illegal_program):
    from seed_training import ensure_prepared
    case=prepared_input
    result=ensure_prepared('/memory/template',1,'/memory/work',inputs=case.inputs,
        sources=[case.source('oversize',illegal_program),case.source('legal',[['outbreak']])])
    assert result['preparation']['unique_inputs']==1 and result['preparation']['rejected']==1
    sources={row['label']:row for row in result['entries']}
    assert sources['oversize']['status']=='rejected' and '255 字节' in sources['oversize']['reason']
    assert sources['legal']['status']=='ready'
    assert len(case.writes)==1 and case.writes[0][0]=='seed_prepared'


@pytest.mark.parametrize('boundary',['load_targeting','run_command'])
def test_prepare_keeps_tool_failure_explicit_instead_of_rejecting_material(monkeypatch,prepared_input,boundary):
    import codec,program
    from seed_training import ensure_prepared
    case=prepared_input
    def failure(*args,**kwargs): raise ValueError('受检编译工具或目标资料故障')
    monkeypatch.setattr(codec if boundary=='load_targeting' else program,
                        'load_targeting' if boundary=='load_targeting' else 'compile_program',failure)
    with pytest.raises(ValueError,match='受检编译工具或目标资料故障'):
        ensure_prepared('/memory/template',1,'/memory/work',inputs=case.inputs,sources=[case.source('legal',[['outbreak']])])
    assert case.writes==[]


def test_training_prepare_freezes_burst_across_scenes_and_checks_current_definition(monkeypatch):
    from copy import deepcopy
    from unittest.mock import Mock
    import burst,engine,seed_training
    from test_character_export import sample_profile
    original=json.loads(Path('projects/sim2gse/burst/unholy.json').read_text())
    original['definition_id']=burst.definition_id(original)
    changed=dict(deepcopy(original),version=original['version']+'-changed')
    changed['definition_id']=burst.definition_id(changed)
    reads=Mock(side_effect=[[original],[changed]])
    monkeypatch.setattr(burst,'read_records',reads)
    monkeypatch.setattr(Path,'read_text',lambda *args,**kwargs:sample_profile())
    monkeypatch.setattr(engine,'identity',lambda mode:(Path('/engine'),{}))
    identity=dict(spec_id=252,definition_id=original['definition_id'])
    first=seed_training._training_inputs('/memory/template',1,use_burst=True,max_processes=1,burst_identity=identity)
    assert first['definition']==original and first['simulation_config']['scene']=='single_target'
    assert first['config']['input_interval_ms']==200
    with pytest.raises(ValueError,match='爆发定义已变化'):
        seed_training._training_inputs('/memory/template',5,use_burst=True,max_processes=1,burst_identity=identity)
    assert reads.call_count==2
    assert all(call.args==('burst_definitions','current_252') for call in reads.call_args_list)


@pytest.mark.parametrize('failure',['missing','unreadable'])
def test_training_prepare_keeps_history_missing_and_read_failure_semantics(monkeypatch,failure):
    from copy import deepcopy
    from unittest.mock import MagicMock,Mock
    from seed_training import sync_history,template_character
    from test_character_export import sample_profile
    import result_store
    registered=dict(candidate_id='registered',source_id='registered',class_name='deathknight',spec='unholy',
        semantic='preserved',program=[['outbreak']],core=[])
    registry=[registered]
    before=deepcopy(registry)
    histories=[dict(run_id=name,profile=dict(identity=dict(**{'class':'deathknight'},spec='unholy')),
        status='completed',candidate_data_key=name+'_candidate',candidate_key='winner',search_dps=0.) for name in ('valid','affected')]
    valid=dict(candidate_data_key='valid_candidate',run_id='valid',candidate_key='winner',program=[['death_coil']])
    cursor=MagicMock()
    cursor.__enter__.return_value.fetchone.return_value=('runs',)
    monkeypatch.setattr(result_store,'query',lambda *args,**kwargs:cursor)
    monkeypatch.setattr(result_store,'iter_rows',lambda *args,**kwargs:iter(histories))
    def many(*args,**kwargs):
        if failure=='unreadable': raise PermissionError('临时历史读取失败')
        return [valid]
    monkeypatch.setattr(result_store,'read_many',many)
    fallback=Mock(side_effect=[valid,None])
    monkeypatch.setattr(result_store,'one',fallback)
    writer=Mock()
    monkeypatch.setattr(result_store,'write',writer)
    if failure=='unreadable':
        with pytest.raises(PermissionError,match='临时历史读取失败'):
            sync_history(template_character(sample_profile()),sources=registry)
        writer.assert_not_called()
        fallback.assert_not_called()
    else:
        rows=sync_history(template_character(sample_profile()),sources=registry)
        inactive=[row for row in rows if row.get('active') is False]
        assert len(inactive)==1 and inactive[0]['source_id']=='history:affected'
        assert '候选记录缺失' in inactive[0]['unavailable_reason']
        assert {row['source_id'] for row in rows if row.get('active',True)}=={'registered','history:valid'}
        assert {call.args[2] for call in fallback.call_args_list}=={'valid_candidate','affected_candidate'}
        assert writer.call_count==1
    assert registry==before
