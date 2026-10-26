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
    monkeypatch.setattr(seed_training, 'registry_rows', lambda: deepcopy(sources))
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: dict(training=dict(
        max_processes=1, max_trainings=1, top_k=4, crossover_probability=0., mutation_probability=0.)))
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
    def open_store(folder): return case.store
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
        if table != 'seed_prepared': return []
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
        training=dict(max_processes=1, max_trainings=1, top_k=4, crossover_probability=0., mutation_probability=0.),
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
