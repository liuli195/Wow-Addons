"""训练规则与准备缓存使用显式内存输入，不证明物理持久化。"""
import json
from pathlib import Path
import subprocess


import pytest
from test_population_training import memory_ga


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
    monkeypatch.setattr(seed_training,'registry_rows',lambda **kwargs:[])
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
    records = {}
    def read(table, key, **kwargs):
        return deepcopy([header] if table == 'seed_prepared' else records.get((table, key), []))
    def write(*args, **kwargs):
        records[args[0], args[1]] = deepcopy(args[2])
        writes.append(deepcopy(args))
    monkeypatch.setattr(result_store,'read_records',read)
    monkeypatch.setattr(result_store,'write',write)
    monkeypatch.setattr(codec,'load_targeting',lambda **kwargs:dict(target_masks={}))
    monkeypatch.setattr(program,'compile_program',lambda *args,**kwargs:{})
    monkeypatch.setattr(task,'_rule_hashes',lambda **kwargs:{})
    def source(label,program):
        import hashlib
        records['seed_originals', hashlib.sha256(b'fixture').hexdigest() + '_0'] = [
            dict(version=1, index=0, text='fixture')]
        return dict(dict.fromkeys(seeds.CANDIDATE_SCHEMA),candidate_id=label,source_id=label,label=label,
            class_name='deathknight',spec='unholy',source='fixture',original='fixture',instructions='repeat',
            semantic='preserved',changes=[],family='plain',core=[],program=program,active=True)
    return SimpleNamespace(inputs=inputs,header=header,writes=writes,source=source,records=records,read=read)


def test_prepare_freezes_original_reference_without_copying_archive(prepared_input):
    import seed_training as seeds
    case = prepared_input
    row = case.source('archive', [['outbreak']])
    row.update(active=False, original='保留的完整原文😀' * 10000)
    ready = seeds.ensure_prepared('/profile', 1, '/memory', sources=[row], inputs=case.inputs)
    frozen = ready['entries'][0]
    assert frozen.get('original') is None
    assert frozen['original_ref']['characters'] == len(row['original'])
    assert row['original'].startswith('保留的完整原文')
    assert case.writes[-1][2][1] == frozen


@pytest.mark.parametrize('damaged', [False, True])
def test_prepare_reuses_verified_old_snapshot_without_full_registry_or_resimulation(
        prepared_input, monkeypatch, damaged):
    from copy import deepcopy
    import engine, result_store, seed_training as seeds
    from search import digest
    case = prepared_input
    source = case.source('retained', [['outbreak']])
    ready = seeds.ensure_prepared('/profile', 1, '/memory', sources=[source], inputs=case.inputs)
    old = deepcopy(case.writes[-1][2])
    old_input = dict(ready['context']['preparation_input'], version='seed-preparation-v2-scoped-sources')
    old_key = digest(old_input)
    for row in old:
        row.pop('original_ref')
        row.update(version=old_input['version'], config_key=old_key)
        if row['kind'] == 'source': row['original'] = 'fixture'
    old[0]['checksum'] = digest([{k: v for k, v in row.items() if k != 'checksum'} for row in old])
    if damaged: old[1]['original'] = 'tampered'
    untouched = deepcopy(old)
    monkeypatch.setattr(result_store, 'read_records', lambda table, key, **kw:
        [] if table == 'seed_prepared' else case.read(table, key, **kw))
    monkeypatch.setattr(result_store, 'iter_group', lambda table, key:
        iter(deepcopy(old)) if (table, key) == ('seed_prepared', old_key) else iter(()))
    def reference(*args, **kwargs): raise RuntimeError('需要重建参考')
    monkeypatch.setattr(engine, 'reference', reference)
    if damaged:
        with pytest.raises(RuntimeError, match='需要重建参考'):
            seeds.ensure_prepared('/profile', 1, '/memory', sources=[source], inputs=case.inputs)
    else:
        restored = seeds.ensure_prepared('/profile', 1, '/memory', sources=[source], inputs=case.inputs)
        assert restored['config_key'] != old_key
        assert restored['preparation']['context_rebuilt'] is False
        assert restored['preparation']['sources_rebuilt'] == 0
        assert restored['queue'][0]['program'] == ready['queue'][0]['program']
    assert old == untouched

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
        crossover_probability=0.,target_mutation_probability=0.,random_mutation_probability=0.)))
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
    source=dict(source_id='manual:registration-fixture',label='ABC-C',spec='unholy',class_name='deathknight',source='plugin:Smolbreather',
        original='15 ordered spell ids',instructions='continuous unmodified key',semantic='rewritten',
        changes=['remove movement'],family='plugin-opener',core=[['putrefy'],['death_coil']],
        program=[['outbreak'],['putrefy'],['death_coil']])
    monkeypatch.setattr(Path,'read_text',lambda *args,**kwargs:json.dumps(source))
    monkeypatch.setattr(seed_training,'writer_lock',nullcontext)
    stored = {}
    def save(table, key, rows, **kwargs):
        stored[table, key] = deepcopy(rows)
    writes=Mock(side_effect=save)
    monkeypatch.setattr(result_store,'write',writes)
    monkeypatch.setattr(result_store,'read_records',lambda table,key,**kwargs:deepcopy(stored.get((table,key),[])))
    monkeypatch.setattr(result_store,'iter_group',lambda table,key,**kwargs:iter(deepcopy(stored.get((table,key),[]))))
    with pytest.raises(ValueError, match='新增材料必须提供明确适用组'):
        seed_training.register('/memory/cleaned.json')
    source['allowed_groups'] = [dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',
                                     target_type='single_target',target_count=1)]
    first=seed_training.register('/memory/cleaned.json')
    table,key,rows=writes.call_args.args
    assert (table,key)==('seed_candidates','registry') and len(rows)==1 and rows[0]['label']=='ABC-C'
    writes.reset_mock()
    assert seed_training.register('/memory/cleaned.json')==first
    writes.assert_not_called()
    scope = source.pop('allowed_groups')
    with pytest.raises(ValueError, match='新增材料必须提供明确适用组'):
        seed_training.register('/memory/cleaned.json')
    source['allowed_groups'] = scope
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


def test_prepare_checks_original_structure_before_adaptation_and_cache(prepared_input):
    from seed_training import ensure_prepared
    from search import digest
    from test_search_syntax import SIMPLE
    case = prepared_input
    case.inputs['config']['syntax'] = SIMPLE
    # 缓存输入随策略变化；只读夹具提供已验证角色，材料仍走完整准备入口。
    import seed_training as seeds
    key_input = dict(version=seeds.PREPARATION_VERSION, template=case.inputs['template_sha'],
        engines=case.inputs['engines'], simulation=case.inputs['simulation_config'], definition=None,
        semantics=seeds.semantic_versions(), config=seeds._identity_config(case.inputs['config']))
    case.header['config_key'] = digest(key_input)
    case.header['checksum'] = digest([{k:v for k,v in case.header.items() if k!='checksum'}])
    loop = [dict(kind='Loop', count=2, blocks=[['outbreak']])]
    result = ensure_prepared('/memory/template', 1, '/memory/work', inputs=case.inputs,
        sources=[case.source('loop', loop), case.source('legal', [['outbreak']])])
    assert len(result['queue']) == 1
    rejected = next(row for row in result['entries'] if row['candidate_id']=='loop')
    assert rejected['program'] == loop and rejected['status'] == 'rejected'
    assert 'syntax.loop' in rejected['reason']
    assert result['context']['capabilities']['search_syntax'] == SIMPLE


def test_prepare_rejects_forbidden_cached_representative(prepared_input):
    import seed_training as seeds
    from program import canonicalize_search_program
    from search import digest
    from test_search_syntax import SIMPLE
    case=prepared_input
    # 合法来源和合法上下文摘要不能为一个违规的缓存代表开绿灯。
    config=case.inputs['config']
    config['syntax']=SIMPLE
    caps=dict(case.header['context']['capabilities'],search_syntax=SIMPLE)
    identity=canonicalize_search_program([['outbreak']],caps)['identity']
    case.header['context']['representations']={identity:dict(candidate_id='source',
        program=[dict(kind='Loop',count=1,blocks=[['outbreak']])])}
    key_input=dict(version=seeds.PREPARATION_VERSION,template=case.inputs['template_sha'],engines=case.inputs['engines'],
        simulation=case.inputs['simulation_config'],definition=None,semantics=seeds.semantic_versions(),
        config=seeds._identity_config(config))
    case.header['config_key']=digest(key_input)
    case.header['checksum']=digest([{k:v for k,v in case.header.items() if k!='checksum'}])
    with pytest.raises(ValueError,match='syntax.loop'):
        seeds.ensure_prepared('/memory/template',1,'/memory/work',inputs=case.inputs,
                              sources=[case.source('source',[['outbreak']])])


def test_public_training_runs_from_materials_through_four_policy_receipts(monkeypatch, public_training_memory):
    from copy import deepcopy
    import result_store, seed_training
    from test_search_syntax import SIMPLE
    case = public_training_memory
    writes = []
    monkeypatch.setattr(result_store, 'write', lambda table,key,rows,**kwargs: writes.append((table,key,deepcopy(rows))))
    result = seed_training.run_training(case.template,1,'/memory/work', syntax_config=SIMPLE)
    assert result['status']=='completed' and result['selected']==4
    scope = dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target')
    table,key,rows = next(row for row in writes if row[0]=='seed_selected')
    assert key == seed_training.shared_scope(scope, SIMPLE)
    assert all(row['evaluation']['syntax']['policy']==SIMPLE for row in rows)
    assert seed_training.selected_contract_version(rows, SIMPLE)==2
    rows[0]['evaluation'].pop('syntax')
    with pytest.raises(ValueError, match='语法'):
        seed_training.selected_contract_version(rows, SIMPLE)


@pytest.mark.parametrize('tamper', [None, 'receipt', 'program'])
def test_training_list_reads_policy_scope_and_rejects_tampering(monkeypatch,capsys,public_training_memory,tamper):
    from copy import deepcopy
    import result_store, seed_training, simulation_config
    from test_search_syntax import SIMPLE
    writes = []
    monkeypatch.setattr(result_store,'write',lambda table,key,rows,**kwargs:writes.append((table,key,deepcopy(rows))))
    case=public_training_memory
    seed_training.run_training(case.template,1,'/memory/work',syntax_config=SIMPLE)
    _,scope,rows=next(row for row in writes if row[0]=='seed_selected')
    if tamper=='receipt': rows[0]['evaluation'].pop('syntax')
    if tamper=='program': rows[0]['program']=[dict(kind='Loop',count=2,blocks=[['outbreak']])]
    monkeypatch.setattr(simulation_config,'_load_document',lambda path=None:dict(syntax=SIMPLE))
    monkeypatch.setattr(result_store,'read_records',lambda table,key:deepcopy(rows) if key==scope else [])
    code=seed_training.main(['--project','/memory','list','--state','selected','--legacy',
        '--specialization-id','252','--hero-talent','rider_of_the_apocalypse','--target-type','single_target'])
    assert code==(2 if tamper else 0)
    if not tamper: assert len(json.loads(capsys.readouterr().out))==4


@pytest.mark.parametrize('conflict', [None, 'explicit', 'pending', 'receipt'])
def test_public_training_resume_keeps_frozen_syntax(monkeypatch,public_training_memory,conflict):
    import seed_training, sequence, simulation_config
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case=public_training_memory
    evaluate=sequence.evaluate
    monkeypatch.setattr(sequence,'evaluate',lambda *a,**k:(_ for _ in ()).throw(TaskCancelled('pause')))
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template,1,'/memory/work',syntax_config=SIMPLE)
    monkeypatch.setattr(sequence,'evaluate',evaluate)
    original=simulation_config._load_document
    monkeypatch.setattr(simulation_config,'_load_document',lambda path=None:dict(original(path),syntax={'loop':True}))
    if conflict=='pending':
        case.store.state['ga']['pending']={'programs':[[dict(kind='WaitClicks',clicks=2)]],'regenerations':[0]}
        case.store.checkpoint()
    if conflict=='receipt':
        path=next(p for p in case.files if p.name=='identity.json')
        manifest=json.loads(case.files[path]); manifest.pop('syntax')
        case.files[path]=json.dumps(manifest)
    kwargs={'syntax_config':{'loop':True}} if conflict=='explicit' else {'syntax_config':{'loop':False}}
    if conflict:
        with pytest.raises(ValueError,match='语法|syntax|配置'):
            seed_training.run_training(case.template,1,'/memory/work',**kwargs)
    else:
        assert seed_training.run_training(case.template,1,'/memory/work',**kwargs)['status']=='completed'
        assert case.store.state['config']['syntax']==SIMPLE


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
def test_training_prepare_keeps_history_missing_and_read_failure_semantics(monkeypatch,prepared_input,failure):
    from copy import deepcopy
    from unittest.mock import MagicMock,Mock
    from seed_training import sync_history,template_character
    from test_character_export import sample_profile
    import result_store
    registered=prepared_input.source('registered', [['outbreak']])
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
    stored=deepcopy(registry)
    monkeypatch.setattr(result_store,'iter_group',lambda table,key:iter(deepcopy(stored)))
    monkeypatch.setattr(result_store,'read_records',lambda table,key,**kw:
        [] if table == 'seed_catalog' else [r for r in deepcopy(stored)
        if all(r.get(k)==v for k,v in kw.get('filters',{}).items())])
    from contextlib import nullcontext
    import seed_training
    monkeypatch.setattr(seed_training, 'writer_lock', nullcontext)
    writer=Mock(side_effect=lambda table,key,rows,**kw:stored.__setitem__(slice(None),deepcopy(rows)))
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
        # Every newly synchronized row must satisfy the nullable JSON column contract.
        assert all(row['allowed_groups'] is None for row in rows if row['source_id'].startswith('history:'))
    assert registry==before


@pytest.mark.parametrize('entry', ['run', 'prepare'])
@pytest.mark.parametrize('setting', ['iterations', 'random_seed', 'max_processes', 'coarse_iterations',
    'retest_batches', 'retest_iterations', 'stagnation_generations', 'top_k', 'tournament_size',
    'crossover_probability', 'mutation_probability'])
def test_training_public_inputs_reject_unused_search_parameters_before_io(monkeypatch, entry, setting):
    import seed_training
    def forbidden(*args, **kwargs):
        raise AssertionError('invalid public settings must fail before IO')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    invoke = seed_training.run_training if entry == 'run' else seed_training.ensure_prepared
    with pytest.raises(ValueError, match=setting):
        invoke('/memory/template', 1, '/memory/work', search_config={setting: 1})


@pytest.mark.parametrize('logging, options, expected', [
    (None, {'diagnostic_logging': True, 'diagnostics': 'off'}, (True, 'off')),
    (None, {'diagnostic_logging': True, 'diagnostics': 'summary'}, (True, 'summary')),
    (False, {}, (False, 'off')),
    (True, {}, (True, 'summary')),
])
def test_public_prepare_consumes_explicit_runtime_options(monkeypatch, training_cli, logging, options, expected):
    import result_store, seed_training, simulation_config
    monkeypatch.setattr(result_store, 'read_records', lambda *args: [])
    monkeypatch.setattr(result_store, 'write', lambda *args, **kwargs: None)
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: dict(search=dict(
        iterations=128, random_seed=123, max_processes=5, input_interval_ms=900,
        diagnostic_logging=True, diagnostics='full', search_observability='full', search_timeline=True)))
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'write_text', lambda *args, **kwargs: None)
    ready = seed_training.ensure_prepared(training_cli, 1, '/memory/work', sources=[],
        diagnostic_logging=logging, search_config=dict(options, input_interval_ms=250,
            reset_events=[(500, 'target')], search_timeline=False))
    assert (ready['config']['diagnostic_logging'], ready['config']['diagnostics']) == expected
    assert ready['config']['input_interval_ms'] == 250
    assert ready['config']['reset_events'] == ((500, 'target'),)
    assert ready['config']['search_timeline'] is False
    assert (ready['config']['iterations'], ready['config']['random_seed'], ready['config']['max_processes']) == (100, 20260912, 5)


@pytest.mark.parametrize('entry', ['run', 'prepare'])
@pytest.mark.parametrize('logging', [False, True])
def test_public_training_rejects_duplicate_logging_authority_before_io(monkeypatch, entry, logging):
    import seed_training
    def forbidden(*args, **kwargs): raise AssertionError('duplicate setting must fail before IO')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    invoke = seed_training.run_training if entry == 'run' else seed_training.ensure_prepared
    with pytest.raises(ValueError, match='重复.*diagnostic_logging'):
        invoke('/memory/template', 1, '/memory/work', diagnostic_logging=logging,
               search_config={'diagnostic_logging': logging})


@pytest.mark.parametrize('use_burst, interval', [(False, None), (True, None), (True, 450)])
def test_public_prepare_preserves_interval_defaults_and_explicit_burst_interval(
        monkeypatch, training_cli, use_burst, interval):
    import burst, result_store, seed_training
    monkeypatch.setattr(result_store, 'read_records', lambda *args: [])
    monkeypatch.setattr(result_store, 'write', lambda *args, **kwargs: None)
    monkeypatch.setattr(burst, 'select_definition', lambda character: dict(definition_id='verified'))
    options = {} if interval is None else {'input_interval_ms': interval}
    ready = seed_training.ensure_prepared(training_cli, 1, '/memory/work', sources=[],
        use_burst=use_burst, search_config=options)
    assert ready['config']['input_interval_ms'] == (interval or (200 if use_burst else 300))


@pytest.mark.parametrize('entry', ['run', 'prepare'])
@pytest.mark.parametrize('options', [dict(diagnostics='full'), dict(search_observability='summary'),
                                     dict(search_observability='full')])
def test_public_training_rejects_unsupported_observation_before_io(monkeypatch, entry, options):
    import seed_training
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: pytest.fail('must reject before IO'))
    invoke = seed_training.run_training if entry == 'run' else seed_training.ensure_prepared
    with pytest.raises(ValueError, match='预训练仅支持'):
        invoke('/memory/template', 1, '/memory/work', search_config=options)


@pytest.fixture
def public_training_memory(monkeypatch, training_cli, prepared_input, memory_ga):
    """Real public orchestration + preparation + GA; only filesystem/native/store IO are in memory."""
    from copy import deepcopy
    import population_training, result_store, seed_training, simulation_config, task, search
    from search import digest
    from test_character_export import sample_profile
    case = memory_ga(settings=dict(max_trainings=1), search_settings=dict(input_interval_ms=250,
        reset_events=[(500, 'target')]))
    sources = [prepared_input.source(str(index), program) for index, program in enumerate(case.starts)]
    monkeypatch.setattr(seed_training, 'sync_history', lambda *args, **kwargs: deepcopy(sources))
    monkeypatch.setattr(seed_training, 'registry_rows', lambda **kwargs: deepcopy(sources))
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: dict(training=dict(
        max_processes=1, max_trainings=1, top_k=4, crossover_probability=0., target_mutation_probability=0., random_mutation_probability=0.)))
    files = {}
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'write_text', lambda path, text, **kwargs: files.__setitem__(path, text))
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs: files.get(path, sample_profile()))
    for module in (task, search):
        monkeypatch.setattr(module, 'replace_file', lambda source, target: files.__setitem__(target, files.pop(source)))
    monkeypatch.setattr(Path, 'exists', lambda path: path in files)
    monkeypatch.setattr(Path, 'glob', lambda path, pattern: iter(
        [path for path in files if path.name == 'identity.json']
        if pattern == '*/*/identity.json' else []))
    def open_store(folder, **kwargs): return case.store
    open_store.load_state = search.TaskStore.load_state
    monkeypatch.setattr(population_training, 'TaskStore', open_store)
    import sqlite3
    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, 'connect', lambda database, **kwargs:
        case.store.db if database in {
            'file:' + path.with_name('task.sqlite3').as_posix() + '?mode=ro'
            for path in files if path.name == 'identity.json'} else connect(database, **kwargs))
    close = case.store.close
    monkeypatch.setattr(case.store, 'close', lambda: None)
    case.store.state.clear()
    header = deepcopy(prepared_input.header)
    native = header['context']['native']
    native.update(dps=100., samples=99)
    def read_records(table, key):
        if table != 'seed_prepared': return prepared_input.read(table, key)
        row = deepcopy(header)
        row['config_key'] = key
        row['checksum'] = digest([{name: value for name, value in row.items() if name != 'checksum'}])
        return [row]
    monkeypatch.setattr(result_store, 'read_records', read_records)
    monkeypatch.setattr(result_store, '_api', lambda: {})
    case.files, case.template, case.sources = files, training_cli, sources
    yield case
    monkeypatch.setattr(case.store, 'close', close)


def test_public_run_training_consumes_interval_reset_logging_and_training_defaults(public_training_memory):
    import seed_training
    case = public_training_memory
    result = seed_training.run_training(case.template, 1, '/memory/work', search_config=dict(
        input_interval_ms=250, reset_events=[(500, 'target')], diagnostic_logging=True, diagnostics='off'))
    assert result['status'] == 'completed'
    assert result['training_config']['stagnation_generations'] == 2
    assert (result['training_config']['coarse_iterations'], result['training_config']['retest_batches'],
            result['training_config']['retest_iterations']) == (32, 3, 128)
    assert case.calls and case.calls[0][2]['input_times'][:3] == [0, 250, 500]
    assert all(call[2]['reset_events'] == [(500, 'target')] for call in case.calls)
    assert case.store.state['config']['diagnostic_logging'] is True
    assert case.store.state['config']['diagnostics'] == 'off'
    assert not getattr(case.store, 'diagnostic_summary', None)


def test_public_training_reads_shared_file_once_for_all_configuration(monkeypatch,public_training_memory):
    from unittest.mock import Mock
    import simulation_config,seed_training
    from test_search_syntax import SIMPLE
    case=public_training_memory
    original=simulation_config._load_document
    reader=Mock(side_effect=lambda path=None:dict(original(path),syntax=SIMPLE))
    monkeypatch.setattr(simulation_config,'_load_document',reader)
    result=seed_training.run_training(case.template,1,'/memory/work',syntax_config={'loop':False})
    assert result['status']=='completed'
    assert reader.call_count==1 and case.store.state['config']['syntax']==SIMPLE


def test_training_command_reports_actual_syntax(monkeypatch,capsys,public_training_memory):
    import simulation_config,seed_training
    from test_search_syntax import SIMPLE
    case=public_training_memory
    original=simulation_config._load_document
    monkeypatch.setattr(simulation_config,'_load_document',lambda path=None:dict(original(path),syntax=SIMPLE))
    assert seed_training.main(['--project','/memory','run','--legacy','--targets','1',
        '--template',str(case.template),'--workspace','/memory/work'])==0
    result=json.loads(capsys.readouterr().out)[0]
    assert result['syntax']==SIMPLE and '一键一技能' in result['syntax_summary']


@pytest.mark.parametrize('explicit', [False, True])
def test_public_training_resume_freezes_computation_and_only_changes_explicit_observation(
        monkeypatch, public_training_memory, explicit):
    import seed_training, sequence, simulation_config
    from runtime import TaskCancelled
    case = public_training_memory
    evaluate = sequence.evaluate
    def pause(*args, **kwargs): raise TaskCancelled('pause before native scoring')
    monkeypatch.setattr(sequence, 'evaluate', pause)
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', search_config=dict(
            input_interval_ms=250, reset_events=[(500, 'target')], diagnostic_logging=True, diagnostics='summary'))
    manifest_path = next(path for path in case.files if path.name == 'identity.json')
    frozen = case.files[manifest_path]
    # New files are not current-invocation authority over an unfinished task.
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: dict(
        training=dict(max_processes=2, max_trainings=2, coarse_iterations=7, retest_batches=1,
                      retest_iterations=9, stagnation_generations=4),
        search=dict(input_interval_ms=900, random_seed=456, search_timeline=False)))
    monkeypatch.setattr(sequence, 'evaluate', evaluate)
    options = dict(diagnostic_logging=False, diagnostics='off') if explicit else {}
    result = seed_training.run_training(case.template, 1, '/memory/work', search_config=options)
    assert result['status'] == 'completed'
    assert result['training_config']['coarse_iterations'] == 32
    assert result['training_config']['max_processes'] == 1
    assert case.files[manifest_path] == frozen
    assert case.calls[0][2]['input_times'][:3] == [0, 250, 500]
    assert all(call[2]['reset_events'] == [(500, 'target')] for call in case.calls)
    assert case.store.state['config']['diagnostic_logging'] is (not explicit)
    assert case.store.state['config']['diagnostics'] == ('off' if explicit else 'summary')


@pytest.mark.parametrize('options, parallelism', [
    ({'input_interval_ms': 300}, {}), ({'reset_events': []}, {}),
    ({}, {'max_processes': 2}), ({}, {'max_trainings': 2})])
def test_public_training_resume_rejects_explicit_computation_conflicts_before_native(
        monkeypatch, public_training_memory, options, parallelism):
    import seed_training, sequence
    from runtime import TaskCancelled
    case = public_training_memory
    monkeypatch.setattr(sequence, 'evaluate', lambda *a, **kw: (_ for _ in ()).throw(TaskCancelled('pause')))
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', search_config=dict(
            input_interval_ms=250, reset_events=[(500, 'target')]))
    monkeypatch.setattr(sequence, 'evaluate', lambda *a, **kw: pytest.fail('conflict must fail before native'))
    with pytest.raises(ValueError, match='恢复.*配置.*变化'):
        seed_training.run_training(case.template, 1, '/memory/work', search_config=options, **parallelism)


@pytest.mark.parametrize('entry', ['run', 'prepare'])
@pytest.mark.parametrize('logging_flag', [[], ['--diagnostic-logging'], ['--no-diagnostic-logging']])
def test_training_cli_consumes_logging_selection_through_real_public_execution(
        capsys, public_training_memory, entry, logging_flag):
    import seed_training
    case = public_training_memory
    assert seed_training.main(['--project', '/memory', entry, '--legacy', '--targets', '1',
        '--template', str(case.template), '--workspace', '/memory/work', *logging_flag]) == 0
    result = json.loads(capsys.readouterr().out)[0]
    assert result['status'] == ('completed' if entry == 'run' else 'prepared')
    expected = logging_flag == ['--diagnostic-logging']
    diagnostics = [json.loads(value) for path, value in case.files.items() if path.name == 'diagnostics.json']
    assert bool(diagnostics) is expected
    if entry == 'run':
        assert case.store.state['config']['diagnostic_logging'] is expected
        assert case.store.state['config']['diagnostics'] == ('summary' if expected else 'off')


@pytest.mark.parametrize('explicit, expected', [(None, True), (False, False), (True, True)])
def test_public_training_uses_only_shared_file_curve_and_explicit_choice_wins(
        monkeypatch, public_training_memory, explicit, expected):
    import seed_training, simulation_config
    case = public_training_memory
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: dict(
        training=dict(max_processes=1, max_trainings=1, top_k=4, crossover_probability=0., target_mutation_probability=0., random_mutation_probability=0.),
        search=dict(search_timeline=True, diagnostic_logging=True, diagnostics='full',
                    search_observability='full', iterations=128, random_seed=345, max_processes=5)))
    options = {} if explicit is None else {'search_timeline': explicit}
    result = seed_training.run_training(case.template, 1, '/memory/work', search_config=options)
    assert result['status'] == 'completed'
    curves = [json.loads(value) for path, value in case.files.items() if path.name.startswith('search-timeline-') and path.suffix == '.json']
    assert bool(curves) is expected
    if expected:
        assert curves[0]['status'] == 'completed'
        assert any(event['kind'] == 'score' for event in curves[0]['events'])
    assert case.store.state['config']['diagnostic_logging'] is False
    assert case.store.state['config']['input_interval_ms'] == 300


@pytest.mark.parametrize('initial_enabled, latest_logging, latest_diagnostics, latest_timeline', [
    (True, False, 'off', False), (False, True, 'summary', True), (True, True, 'off', False)])
def test_three_public_training_calls_keep_latest_checkpoint_observation_when_omitted(
        monkeypatch, public_training_memory, initial_enabled, latest_logging, latest_diagnostics, latest_timeline):
    import seed_training, sequence
    from runtime import TaskCancelled
    case = public_training_memory
    evaluate = sequence.evaluate
    def pause(*args, **kwargs): raise TaskCancelled('pause before native scoring')
    monkeypatch.setattr(sequence, 'evaluate', pause)
    def options(enabled):
        return dict(input_interval_ms=250, reset_events=[(500, 'target')],
            diagnostic_logging=enabled, diagnostics='summary' if enabled else 'off',
            search_timeline=enabled)
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', search_config=options(initial_enabled))
    manifest_path = next(path for path in case.files if path.name == 'identity.json')
    frozen = case.files[manifest_path]
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', search_config=dict(options(latest_logging),
            diagnostics=latest_diagnostics, search_timeline=latest_timeline))
    previous_curves = {path for path in case.files if path.name.startswith('search-timeline-') and path.suffix == '.json'}
    monkeypatch.setattr(sequence, 'evaluate', evaluate)
    result = seed_training.run_training(case.template, 1, '/memory/work')
    assert result['status'] == 'completed'
    assert case.store.state['config']['diagnostic_logging'] is latest_logging
    assert case.store.state['config']['diagnostics'] == latest_diagnostics
    assert case.store.state['config']['search_timeline'] is latest_timeline
    new_curves = [json.loads(value) for path, value in case.files.items()
                  if path.name.startswith('search-timeline-') and path.suffix == '.json' and path not in previous_curves]
    assert bool(new_curves) is latest_timeline
    if latest_timeline:
        assert new_curves[0]['resumed'] is True and new_curves[0]['status'] == 'completed'
    assert case.files[manifest_path] == frozen
    assert case.calls[0][2]['input_times'][:3] == [0, 250, 500]
    assert all(call[2]['reset_events'] == [(500, 'target')] for call in case.calls)


def test_public_training_command_releases_registry_lock_before_native_scoring(
        monkeypatch, public_training_memory, capsys):
    from contextlib import contextmanager
    import seed_training
    import sequence
    held = [False]
    @contextmanager
    def registry_lock():
        held[0] = True
        try:
            yield
        finally:
            held[0] = False
    evaluate = sequence.evaluate
    def native_boundary(*args, **kwargs):
        assert not held[0], '正式评分不能占住材料登记锁'
        return evaluate(*args, **kwargs)
    monkeypatch.setattr(seed_training, 'writer_lock', registry_lock)
    monkeypatch.setattr(sequence, 'evaluate', native_boundary)
    assert seed_training.main(['--project', '/memory', 'run', '--template', str(public_training_memory.template),
        '--targets', '1', '--workspace', '/memory/work', '--legacy']) == 0


def test_training_memory_io_recognizes_windows_paths(public_training_memory):
    """Exercise the same fixture IO with Windows drive/separators even on Linux."""
    import sqlite3
    from pathlib import PureWindowsPath
    manifest = PureWindowsPath('Z:/memory/work/ga/scope/task/identity.json')
    Path.write_text(manifest, '{}')
    assert Path.read_text(manifest) == '{}' and Path.exists(manifest)
    assert manifest in Path.glob(manifest.parents[2], '*/*/identity.json')
    uri = 'file:' + manifest.with_name('task.sqlite3').as_posix() + '?mode=ro'
    assert sqlite3.connect(uri, uri=True) is public_training_memory.store.db



def test_public_training_uses_independent_probability_settings(public_training_memory):
    import seed_training
    case = public_training_memory
    result = seed_training.run_training(case.template, 1, '/memory/work')
    assert result['status'] == 'completed'
    assert result['training_config']['target_mutation_probability'] == 0.
    assert result['training_config']['random_mutation_probability'] == 0.
    assert 'mutation_probability' not in result['training_config']



@pytest.fixture
def guided_training_memory(public_training_memory, monkeypatch):
    from copy import deepcopy
    import result_store, simulation_config
    case = public_training_memory
    case.guidance_reference = dict(version=1, samples=99, duration_ms=17820000,
        successes={'spell:1001':99}, pairs={}, outgoing={}, positions={}, witnesses={},
        scope=dict(allowed={'spell:1001':True}, excluded={}, windows='', policy='@apl', controlled=False))
    case.guidance_probabilities = dict(target_mutation_probability=1., random_mutation_probability=1., crossover_probability=1.)
    read_records = result_store.read_records
    def reference_input(table, key):
        rows = read_records(table, key)
        if table == 'seed_prepared':
            for row in rows:
                if row.get('kind') == 'context':
                    native = row['context']['native']
                    native['action_summary'] = deepcopy(case.guidance_reference)
            from search import digest
            for row in rows:
                if row.get('kind') == 'context':
                    row['checksum'] = digest([{k:v for k,v in item.items() if k != 'checksum'} for item in rows])
        return deepcopy(rows)
    monkeypatch.setattr(result_store, 'read_records', reference_input)
    document = simulation_config._load_document
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None:
        dict(document(path), training=dict(document(path)['training'], **case.guidance_probabilities)))
    return case


def test_public_training_executes_target_then_random_then_crossover(monkeypatch, guided_training_memory):
    import random
    from types import SimpleNamespace
    import population_training, seed_training, sequence
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    base_random = random.Random
    class BoundaryRandom(base_random):
        _randbelow = base_random._randbelow
        def random(self): return 0.
        def choice(self, values):
            if values and hasattr(values[0], 'fitness'):
                draws = getattr(self, 'selection_draws', 0)
                self.selection_draws = draws + 1
                return values[0 if (draws // 3) % 2 == 0 else -1]
            return values[0]
        def sample(self, values, count):
            assert count == 2
            return [values[0], values[2]]
        def randint(self, start, end): return start
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=BoundaryRandom))
    evaluate = sequence.evaluate
    def pause_after_variation(*args, **kwargs):
        if case.store.state['ga']['pending'] is not None:
            raise TaskCancelled('inspect complete pending children')
        return evaluate(*args, **kwargs)
    monkeypatch.setattr(sequence, 'evaluate', pause_after_variation)
    with pytest.raises(TaskCancelled, match='pending children'):
        seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE)
    ga = case.store.load_state(case.store.db)['ga']
    assert ga['generation'] == 0 and ga['pending'] is not None
    assert ga['breeding']['order'] == ['target', 'random', 'crossover']
    assert ga['breeding']['probabilities'] == dict(target_mutation_probability=1.,
        random_mutation_probability=1., crossover_probability=1.)
    assert ga['pending']['programs'][0] == [['death_coil'], ['scourge_strike'], ['outbreak'], ['outbreak']]
    assert ga['pending']['programs'][1] == [['death_coil'], ['outbreak'], ['outbreak'], ['scourge_strike']]
    assert all(options['iterations'] != 2 for _, _, options in case.calls)



def test_public_guided_training_completes_four_representatives_and_reuses_scores(guided_training_memory):
    import seed_training
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    case.guidance_probabilities.update(target_mutation_probability=.8,
        random_mutation_probability=.3, crossover_probability=.3)
    result = seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE)
    assert result['status'] == 'completed' and result['selected'] == 4
    ga = case.store.state['ga']
    assert ga['phase'] == 'published' and ga['generation'] >= 2
    assert ga['breeding']['order'] == ['target', 'random', 'crossover']
    assert all(set(scenes) == {'nominal', 'jitter', 'pause', 'slow', 'phase'} for scenes in ga['finals'].values())
    assert all(options['iterations'] != 2 for _, _, options in case.calls)
    assert len(case.calls) == len({folder for folder, _, _ in case.calls})
    assert 'breeding_counts' not in ga


@pytest.mark.parametrize('gate_draw', [2, 3, 13])
def test_public_guided_training_replays_uncommitted_operations(monkeypatch, guided_training_memory, gate_draw):
    import random
    from types import SimpleNamespace
    import population_training, seed_training
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    base_random = random.Random
    paused_rng = []
    armed = [True]
    class InterruptedRandom(base_random):
        _randbelow = base_random._randbelow
        def random(self):
            self.gate_draws = getattr(self, 'gate_draws', 0) + 1
            if armed[0] and self.gate_draws == gate_draw:
                paused_rng.append(case.store.state['ga']['rng'])
                raise TaskCancelled('between independent gates')
            return super().random()
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=InterruptedRandom))
    with pytest.raises(TaskCancelled, match='independent gates'):
        seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE)
    saved = case.store.load_state(case.store.db)['ga']
    assert saved['generation'] == 0 and saved['pending'] is None
    assert json.dumps(saved['rng']) == json.dumps(paused_rng[0])
    reference = case.store.state['breeding_reference']
    armed[0] = False
    result = seed_training.run_training(case.template, 1, '/memory/work')
    assert result['status'] == 'completed' and result['selected'] == 4
    assert case.store.state['breeding_reference'] == reference
    assert all(options['iterations'] != 2 for _, _, options in case.calls)



@pytest.mark.parametrize('key', ['target_mutation_probability', 'random_mutation_probability', 'crossover_probability'])
@pytest.mark.parametrize('value', [False, True, -.1, 1.1, float('inf'), float('nan'), '0.8'])
def test_public_training_rejects_invalid_independent_probabilities_before_io(monkeypatch, key, value):
    import seed_training, simulation_config
    monkeypatch.setattr(simulation_config, '_load_document', lambda *a, **kw: dict(training={key:value}))
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: pytest.fail('invalid probability started IO'))
    with pytest.raises(ValueError, match=key):
        seed_training.run_training('/memory/template', 1, '/memory/work')


@pytest.mark.parametrize('value', [0., False, .8])
def test_public_training_rejects_retired_total_probability_even_when_zero(monkeypatch, value):
    import seed_training, simulation_config
    monkeypatch.setattr(simulation_config, '_load_document', lambda *a, **kw: dict(training={'mutation_probability':value}))
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: pytest.fail('retired setting started IO'))
    with pytest.raises(ValueError, match='mutation_probability.*退役'):
        seed_training.run_training('/memory/template', 1, '/memory/work')



@pytest.mark.parametrize('family, expected', [
    ('insert', [['outbreak'], ['scourge_strike'], ['death_coil'], ['outbreak']]),
    ('move', [['outbreak'], ['scourge_strike'], ['death_coil']])])
def test_public_insufficient_frequency_selects_operation_before_landing(monkeypatch, guided_training_memory, family, expected):
    from copy import deepcopy
    import random
    from types import SimpleNamespace
    import population_training, seed_training, sequence
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    case.guidance_probabilities.update(random_mutation_probability=0., crossover_probability=0.)
    original = deepcopy(case.starts)
    choices = []
    base_random = random.Random
    class FamilyRandom(base_random):
        _randbelow = base_random._randbelow
        def random(self): return 0.
        def choice(self, values):
            if values and hasattr(values[0], 'fitness'): return values[-1]
            if len(values) == 2 and all(isinstance(group, list) and group and isinstance(group[0], dict)
                                      and 'operation' in group[0] for group in values):
                choices.append([(group[0]['operation'], len(group)) for group in values])
                return next(group for group in values if group[0]['operation'] == family)
            return values[0]
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=FamilyRandom))
    checkpoint = case.store.checkpoint
    def stop(*args, **kwargs):
        checkpoint(*args, **kwargs)
        if case.store.state['ga']['pending'] is not None: raise TaskCancelled('inspect family')
    monkeypatch.setattr(case.store, 'checkpoint', stop)
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE)
    assert choices[0] == [('insert', 4), ('move', 2)]
    assert case.store.state['ga']['pending']['programs'][0] == expected
    assert case.starts == original



@pytest.mark.parametrize('rule, reference_pairs, candidate_pairs', [
    ('reverse', {'1>2':6,'1>3':3,'2>1':1,'2>3':8,'3>1':1,'3>2':8},
                {'1>2':1,'1>3':8,'2>1':6,'2>3':3,'3>1':8,'3>2':1}),
    ('repeat', {'1>1':1,'1>2':4,'1>3':4,'2>1':4,'2>3':4,'3>1':4,'3>2':4},
               {'1>1':3,'1>2':4,'1>3':1,'2>1':4,'2>3':4,'3>1':4,'3>2':4}),
    ('connection', {'1>2':8,'1>3':1,'2>1':8,'2>3':1,'3>1':4,'3>2':4},
                   {'1>2':1,'1>3':8,'2>1':8,'2>3':1,'3>1':4,'3>2':4}),
])
def test_public_training_short_sequence_rules_keep_frequency_unchanged(
        monkeypatch, guided_training_memory, rule, reference_pairs, candidate_pairs):
    from collections import Counter
    import random
    from types import SimpleNamespace
    import population_training, seed_training, sequence
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    case.guidance_probabilities.update(random_mutation_probability=0., crossover_probability=0.)
    def summary(samples, coefficients, positions=None):
        pairs = {'spell:100'+a+'>spell:100'+b: n*samples for pair,n in coefficients.items()
                 for a,b in [pair.split('>')]}
        outgoing = Counter()
        for pair, count in pairs.items(): outgoing[pair.split('>')[0]] += count
        keys = ['spell:1001','spell:1002','spell:1003']
        return dict(version=1, samples=samples, duration_ms=samples*180000,
            successes={key:10*samples for key in keys}, pairs=pairs, outgoing=dict(outgoing),
            positions=positions or {}, witnesses={}, scope=dict(allowed=dict.fromkeys(keys,True),
                excluded={},windows='',policy='/'.join(keys) if positions else '@apl',controlled=bool(positions)))
    case.guidance_reference = summary(99, reference_pairs)
    base_random = random.Random
    class LastParent(base_random):
        _randbelow = base_random._randbelow
        def random(self): return 0.
        def choice(self, values):
            return values[2] if values and hasattr(values[0], 'fitness') else values[0]
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=LastParent))
    evaluate = sequence.evaluate
    def native_report(profile, candidate, folder, **kwargs):
        result = evaluate(profile, candidate, folder, **kwargs)
        samples = result['summary']['samples']
        positions = {f"spell:{command['spell_id']}@{index}":10*samples
            for index, block in enumerate(candidate['blocks']) for command in block}
        value = summary(samples, candidate_pairs, positions)
        if rule == 'connection':
            steps = {command['spell_id']:index for index,block in enumerate(candidate['blocks']) for command in block}
            value['witnesses'] = {'spell:1001>spell:1002':[steps[1001],steps[1003],steps[1002]]}
        result['report']['sim']['players'][0]['sim2gse_action_summary'] = value
        return result
    monkeypatch.setattr(sequence, 'evaluate', native_report)
    checkpoint = case.store.checkpoint
    def pause():
        checkpoint()
        if case.store.state['ga']['pending'] is not None: raise TaskCancelled('inspect sequence')
    monkeypatch.setattr(case.store, 'checkpoint', pause)
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE)
    assert case.store.state['ga']['pending']['programs'][0] == [['outbreak'],['death_coil'],['scourge_strike']]



@pytest.mark.parametrize('kind', ['Loop', 'CastSequence'])
def test_public_target_edits_one_complex_source_instead_of_one_expanded_copy(monkeypatch, guided_training_memory, kind):
    from copy import deepcopy
    import random
    from types import SimpleNamespace
    import population_training, seed_training
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    case.guidance_probabilities.update(random_mutation_probability=0., crossover_probability=0.)
    node = (dict(kind='Loop', count=3, blocks=[['scourge_strike'],['death_coil'],['outbreak']])
            if kind == 'Loop' else dict(kind='CastSequence', members=['scourge_strike','death_coil','outbreak'], reset=None))
    source = deepcopy(case.sources[0])
    source['program'] = [node]
    original_node = deepcopy(node)
    case.sources[:] = [source]
    base_random = random.Random
    class SourceRandom(base_random):
        _randbelow = base_random._randbelow
        def random(self): return 0.
        def choice(self, values):
            if len(values) == 2 and all(isinstance(group,list) and group and isinstance(group[0],dict)
                                      and 'operation' in group[0] for group in values):
                return next(group for group in values if group[0]['operation'] == 'move')
            return values[0]
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=SourceRandom))
    checkpoint = case.store.checkpoint
    def pause():
        checkpoint()
        if case.store.state['ga']['pending'] is not None: raise TaskCancelled('inspect source edit')
    monkeypatch.setattr(case.store, 'checkpoint', pause)
    policy = dict(SIMPLE, **({'loop':True} if kind == 'Loop' else {'castsequence':True}))
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template, 1, '/memory/work', syntax_config=policy)
    child, = case.store.state['ga']['pending']['programs'][0]
    assert child['kind'] == kind
    if kind == 'Loop':
        assert child['count'] == 3 and child['blocks'] == [['outbreak'],['scourge_strike'],['death_coil']]
    else:
        assert child['members'] == ['outbreak','scourge_strike','death_coil'] and child['reset'] is None
    assert source['program'] == [original_node] and node == original_node



@pytest.mark.parametrize('probability', [0., 1.])
def test_public_training_distinguishes_zero_reference_from_missing_and_keeps_previous_library(
        monkeypatch, guided_training_memory, probability):
    from unittest.mock import Mock
    import seed_training, result_store
    case = guided_training_memory
    case.guidance_reference['successes'] = {}
    case.guidance_probabilities.update(target_mutation_probability=probability,
        random_mutation_probability=0., crossover_probability=0.)
    writer = Mock(wraps=result_store.write)
    monkeypatch.setattr(result_store, 'write', writer)
    if probability:
        with pytest.raises(ValueError, match='没有可比较普通按钮'):
            seed_training.run_training(case.template, 1, '/memory/work')
        assert not case.calls
        assert not any(call.args[0] == 'seed_selected' for call in writer.call_args_list)
    else:
        result = seed_training.run_training(case.template, 1, '/memory/work')
        assert result['status'] == 'completed' and result['selected'] == 4


def test_public_training_collects_three_gate_counts_without_full_process_history(guided_training_memory):
    import seed_training
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    result = seed_training.run_training(case.template, 1, '/memory/work', syntax_config=SIMPLE,
        diagnostic_logging=True)
    assert result['status'] == 'completed'
    ga = case.store.state['ga']
    size, generations = len(ga['population']), ga['generation']
    assert ga['breeding_counts']['target_triggered'] == size * generations
    assert ga['breeding_counts']['random_triggered'] == size * generations
    assert ga['breeding_counts']['crossover_triggered'] == (size//2) * generations
    assert 0 < ga['breeding_counts']['target_changed'] <= ga['breeding_counts']['target_triggered']
    assert 'search_observability' not in case.store.state
    assert all(options['iterations'] != 2 for _, _, options in case.calls)



@pytest.mark.parametrize('rule, parent, expected, reference_pairs, candidate_pairs, witness', [
    ('reverse', ['outbreak','death_coil','outbreak','scourge_strike'],
     ['outbreak','outbreak','death_coil','scourge_strike'],
     {'1>2':6,'1>3':3,'2>1':1,'2>3':8,'3>1':1,'3>2':8},
     {'1>2':1,'1>3':8,'2>1':6,'2>3':3,'3>1':8,'3>2':1}, ('2>3',[1,2,3])),
    ('repeat', ['outbreak','outbreak','scourge_strike','outbreak','death_coil'],
     ['outbreak','outbreak','death_coil','scourge_strike','outbreak'],
     {'1>1':1,'1>2':4,'1>3':4,'2>1':4,'2>3':4,'3>1':4,'3>2':4},
     {'1>1':3,'1>2':4,'1>3':1,'2>1':4,'2>3':4,'3>1':4,'3>2':4}, ('1>3',[1,3,2])),
    ('ambiguous', [dict(kind='CastSequence',members=['outbreak','outbreak'],reset=None),'outbreak','death_coil','scourge_strike'],
     [dict(kind='CastSequence',members=['outbreak','outbreak'],reset=None),'outbreak','scourge_strike','death_coil'],
     {'1>2':6,'1>3':3,'2>1':1,'2>3':8,'3>1':1,'3>2':8},
     {'1>2':1,'1>3':8,'2>1':6,'2>3':3,'3>1':8,'3>2':1}, None),
])
def test_public_sequence_repair_uses_witness_positions_with_repeated_buttons(
        monkeypatch, guided_training_memory, rule, parent, expected, reference_pairs, candidate_pairs, witness):
    from collections import Counter
    from copy import deepcopy
    import random
    from types import SimpleNamespace
    import population_training, seed_training, sequence
    from runtime import TaskCancelled
    from test_search_syntax import SIMPLE
    case = guided_training_memory
    case.guidance_probabilities.update(random_mutation_probability=0., crossover_probability=0.)
    source = deepcopy(case.sources[0]); source['program'] = [[name] if isinstance(name,str) else deepcopy(name) for name in parent]
    case.sources[:] = [source]
    def summary(samples, coefficients, positions=None, witnesses=None):
        pairs = {'spell:100'+a+'>spell:100'+b:n*samples for key,n in coefficients.items() for a,b in [key.split('>')]}
        outgoing = Counter()
        for key,n in pairs.items(): outgoing[key.split('>')[0]] += n
        keys = ['spell:1001','spell:1002','spell:1003']
        return dict(version=1,samples=samples,duration_ms=180000*samples,
            successes={key:10*samples for key in keys},pairs=pairs,outgoing=dict(outgoing),
            positions=positions or {},witnesses=witnesses or {},scope=dict(allowed=dict.fromkeys(keys,True),
                excluded={},windows='',policy='/'.join(keys) if positions else '@apl',controlled=bool(positions)))
    case.guidance_reference = summary(99, reference_pairs)
    base_random = random.Random
    class First(base_random):
        _randbelow = base_random._randbelow
        def random(self): return 0.
        def choice(self, values): return values[0]
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=First))
    evaluate = sequence.evaluate
    def native_report(profile,candidate,folder,**kwargs):
        result = evaluate(profile,candidate,folder,**kwargs); samples=result['summary']['samples']
        occurrences = {}
        for step,block in enumerate(candidate['blocks']):
            for command in block: occurrences.setdefault(command['spell_id'],[]).append(step)
        positions = {}
        for skill,steps in occurrences.items():
            for i,step in enumerate(steps):
                positions[f'spell:{skill}@{step}'] = samples*(10//len(steps)+(i<10%len(steps)))
        witnesses = {}
        if witness is not None:
            a,b = witness[0].split('>')
            witnesses = {'spell:100'+a+'>spell:100'+b:witness[1]}
        if rule == 'ambiguous':
            positions = {'spell:1001@0':7*samples,'spell:1001@1':3*samples,
                         'spell:1002@2':10*samples,'spell:1003@3':10*samples}
        value = summary(samples,candidate_pairs,positions,witnesses)
        result['report']['sim']['players'][0]['sim2gse_action_summary'] = value
        return result
    monkeypatch.setattr(sequence,'evaluate',native_report)
    checkpoint=case.store.checkpoint
    def pause():
        checkpoint()
        if case.store.state['ga']['pending'] is not None: raise TaskCancelled('inspect witnessed edit')
    monkeypatch.setattr(case.store,'checkpoint',pause)
    with pytest.raises(TaskCancelled):
        seed_training.run_training(case.template,1,'/memory/work',
            syntax_config=dict(SIMPLE,castsequence=rule == 'ambiguous'))
    assert case.store.state['ga']['pending']['programs'][0] == [[name] if isinstance(name,str) else deepcopy(name) for name in expected]
