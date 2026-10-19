"""规则起点通过任务公开入口交付；构造引擎报告不冒充真实角色验收。"""
from task import TaskError, run_task
from test_character_export import sample_profile
from test_search import _apl_task_boundary
import pytest


def _opener_pack(objects, ordinary_steps, *, spec_id=252, hero_id=17, target_type='single_target',
                 precombat=(), independent=(), anchor=None, source='fixture: ordered source'):
    """直接构造新契约数据；不接收或执行旧schema/事实/专精策略。"""
    import copy
    objects = {name: (dict(kind='action', native_action=row, base_button=row, native_forms=[row])
                      if isinstance(row, str) else copy.deepcopy(row)) for name, row in objects.items()}
    ordinary = []
    for value in ordinary_steps:
        row = copy.deepcopy(value)
        form = row.setdefault('source_form', objects[row['action']]['native_action'])
        row['attribute_query'] = dict(native_form=form, base_button=objects[row['action']]['base_button'],
                                      missing='unknown_no_base_cost_fallback')
        ordinary.append(row)
    indices = [row['source_step'] for row in [*ordinary, *independent]]
    for name in precombat:
        objects.setdefault(name, dict(kind='action', native_action=name, base_button=name))
    opener = dict(source_basis=source, source_steps=[f'source {i}' for i in range(1, max(indices)+1)],
        ordinary_steps=ordinary, precombat=[dict(action=name, command_count=1, condition='out_of_combat',
            path='existing_supported_path') for name in precombat],
        independent_burst_source_steps=list(independent),
        burst_anchor=None if anchor is None else dict(source_step=anchor, freeze_per_task=True))
    return dict(schema_version=2, identity_mappings=dict(hero_talents={'sample_hero': hero_id}),
        general=dict(templates={}), object_sets={'sample': objects}, execution_evidence=(
            {'fixture_macro': dict(blocks=[[row['action']] for row in independent])} if independent else {}),
        configurations=[dict(key=dict(specialization_id=spec_id, hero_talent='sample_hero', target_type=target_type),
            objects_ref='sample', opener=opener, states={'only': dict(effect=None, expected=True, priority=[])},
            execution_ref='fixture_macro' if independent else None)])


def _configure_opener(tmp_path, monkeypatch, pack=None):
    """只给旧安全回归提供匹配其外部报告的显式有序配置。"""
    import json
    from test_search import _minimal_rule_pack
    pack = _minimal_rule_pack() if pack is None else pack
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    return pack


def _declared_pack():
    pack = _opener_pack({'tap': 'scourge_strike'}, [dict(action='tap', source_step=1)])
    pack['general']['templates']['fixture'] = dict(
        application_phase='post_simulation_diagnosis_and_next_candidate',
        parameters=dict(action=dict(type='action_ref'), priority_refs=dict(type='rule_ref_array'),
                        enabled=dict(type='boolean'), count=dict(type='integer', unit='count', minimum=0)),
        reads=[], diagnose=dict(let={'marker': 'original'}, for_each=[], **{'as': 'row'}, cases=[],
                                export_trigger_records=[]), edits=[])
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='first', template='fixture',
        arguments=dict(action='tap', priority_refs=[], enabled=True, count=3))]
    return pack


def test_rule_cli_preserves_complete_templates_and_rejects_wrong_binding_parameter(tmp_path, monkeypatch, capsys):
    import copy, json
    from rule_config import DEFAULT_PATH
    from task import main
    pack = json.loads(DEFAULT_PATH.read_bytes())
    assert len(pack['general']['templates']) == 8
    assert sum(len(state['priority']) for row in pack['configurations']
               for state in row['states'].values()) == 79
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    invalid = copy.deepcopy(pack)
    invalid['configurations'][0]['states']['normal']['priority'][0]['arguments']['threshold'] = '3'
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(invalid), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '参数' in capsys.readouterr().err
    assert target.read_bytes() == before


@pytest.mark.parametrize('fault', ['qualification_ref', 'native_identity_type'])
def test_rule_cli_rejects_invalid_object_types_and_same_set_references(tmp_path, monkeypatch, capsys, fault):
    import json
    from task import main
    pack = _declared_pack()
    objects = pack['object_sets']['sample']
    objects.update(gate=dict(kind='state', native_identity='literal.true'),
                   resource=dict(kind='resource', native_identity='energy'),
                   effect=dict(kind='effect', native_identity='fixture_effect', qualification='gate'))
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    if fault == 'qualification_ref': objects['effect']['qualification'] = 'missing_state'
    else: objects['resource']['native_identity'] = {'op': 'python', 'args': []}
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes() == before


def test_rule_cli_rejects_object_algorithm_in_enum_declaration_and_argument(tmp_path, monkeypatch, capsys):
    import json
    from task import main
    pack = _declared_pack()
    template = pack['general']['templates']['fixture']
    template['parameters']['compare'] = dict(type='enum', values=['eq'])
    row = pack['configurations'][0]['states']['only']['priority'][0]
    row['arguments']['compare'] = 'eq'
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    algorithm = {'op': 'python', 'args': ['arbitrary specialization algorithm']}
    template['parameters']['compare']['values'].append(algorithm)
    row['arguments']['compare'] = algorithm
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-check', str(draft)]) == 2
    assert '枚举' in capsys.readouterr().err
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '枚举' in capsys.readouterr().err
    assert target.read_bytes() == before


@pytest.mark.parametrize('fault', ['missing_hero', 'duplicate_key'])
def test_public_task_rejects_unknown_or_ambiguous_three_key_identity(tmp_path, monkeypatch, fault):
    import copy
    from test_engine import apl_pool_reference
    from test_search import _minimal_rule_pack
    pack = _minimal_rule_pack()
    pack['configurations'] = pack['configurations'][:1]
    native = apl_pool_reference()
    config = dict(scene='single_target')
    if fault == 'missing_hero':
        native['static_snapshot'].pop('hero_subtree_ids')
    else:
        pack['configurations'].append(copy.deepcopy(pack['configurations'][0]))
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='英雄|三键|目标'):
        run_task(source, tmp_path / 'task', simulation_config=config,
                 search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_task_rejects_missing_static_character_snapshot(tmp_path):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native.pop('static_snapshot')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='静态'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_task_exports_ordered_opener_using_effective_gcd(tmp_path, monkeypatch):
    from task import read_task
    _configure_opener(tmp_path, monkeypatch)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    report = result['rule_initialization']
    assert report == saved['rule_initialization']
    assert report['resource'] == 'runic_power'
    assert report['program'] == [value for name in ('outbreak', 'scourge_strike', 'death_coil')
        for value in ([name], {'kind': 'WaitClicks', 'clicks': 4})]
    assert result['candidate']['text'].startswith('!GSE3!')
    assert [row['effective_gcd_ms'] for row in report['positions'] if row['kind'] == 'action'] == [1000]*3


@pytest.mark.parametrize('fault,message', [('missing_gcd', r'静态字段.*outbreak\.gcd_ms'), ('too_long', '点击或场景边界')])
def test_generate_reports_unrepresentable_or_unknown_rule_start(tmp_path, monkeypatch, fault, message):
    from engine import inspect
    from rule_config import bind, load
    from rule_initialization import generate
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    row = native['static_snapshot']['actions'][0]
    if fault == 'missing_gcd':
        row.pop('gcd_ms')
    else:
        row['gcd_ms'] = 1000000
    capabilities = inspect(native, tmp_path / 'capabilities')
    snapshot = load()
    binding = bind(capabilities, native['static_snapshot'], 1, spec_id=native['identity']['spec_id'],
                   rule_snapshot=snapshot, scene='single_target')
    with pytest.raises(ValueError, match=message):
        generate(capabilities, native, binding=binding, input_interval_ms=300,
                 target_count=1, rule_snapshot=snapshot)


def test_explicit_program_does_not_require_rule_initialization_snapshot(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native.pop('static_snapshot')
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', mode='single', program=[['outbreak']])
    assert result['candidate']['text'].startswith('!GSE3!')
    assert not result.get('rule_initialization')


def test_task_initialization_timestamps_include_compiled_precombat_click(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    from test_search import _minimal_rule_pack
    pack = _minimal_rule_pack()
    pack['object_sets']['sample']['raise_dead'] = dict(kind='action',native_action='raise_dead',base_button='raise_dead')
    for configuration in pack['configurations']:
        configuration['opener']['precombat'] = [dict(action='raise_dead',command_count=1,
            condition='out_of_combat',path='existing_supported_path')]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['precombat_definitions'] = [dict(template, name='raise_dead', signature='raise_dead',
        data_id=46585, base_spell_id=46585, precombat=True, harmful=False)]
    native['precombat_sequence'] = [dict(name='raise_dead')]
    native['static_snapshot']['parameters']['precombat_gcd_ms'] = 0
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    boundary = _apl_task_boundary(native)
    definition = None
    import burst, result_store
    result_store.DATA_ROOT.mkdir()
    from test_burst import reviewed_fixture, character_seed_boundary
    definition, raw = reviewed_fixture()
    definition = burst.publish(definition)
    source.write_text(raw, encoding='utf-8')
    boundary = character_seed_boundary(native_reference=native)
    with boundary:
        result = run_task(source, tmp_path / 'task', use_burst=True, search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    compiled_actions = [(index, row) for index, row in enumerate(report['click_mapping']) if row['kind'] == 'Action']
    assert compiled_actions[0][1]['commands'] == ['raise_dead']
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert [row['estimated_ms'] for row in actions] == [300, 1500, 2700]
    for row, (index, click) in zip(actions, compiled_actions[1:], strict=True):
        assert click['commands'] == [row['action']]
        assert row['estimated_ms'] == index * 300
    assert report['protected_burst']['definition_id'] == definition['definition_id']


def test_generate_preserves_resource_uncertainty_without_inserting_funding_wait(tmp_path, monkeypatch):
    from engine import inspect
    from rule_config import bind, load
    from rule_initialization import generate
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['resources']['rune'] = dict(current=1, maximum=1)
    capabilities = inspect(native, tmp_path / 'capabilities')
    snapshot = load()
    binding = bind(capabilities, native['static_snapshot'], 1, spec_id=native['identity']['spec_id'],
                   rule_snapshot=snapshot, scene='single_target')
    report = generate(capabilities, native, binding=binding, input_interval_ms=200,
                      target_count=1, rule_snapshot=snapshot)
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert [row['estimated_ms'] for row in actions] == [0, 1000, 2000]
    assert actions[1]['estimated_resources_after']['rune'] is None
    assert 'recovery' not in report



@pytest.mark.parametrize('fault', ['cycle', 'unit'])
def test_task_rejects_invalid_rule_references_before_running(tmp_path, monkeypatch, fault):
    pack = _declared_pack()
    template = pack['general']['templates']['fixture']
    configuration = pack['configurations'][0]
    row = configuration['states']['only']['priority'][0]
    opener = configuration['opener']
    if fault == 'unit': template['parameters']['count']['unit'] = 'unregistered'
    else:
        row['arguments']['priority_refs'] = ['first']
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))



def test_rule_cli_rejects_duplicate_json_keys_without_replacing_valid_file(tmp_path, monkeypatch, capsys):
    import json
    from task import main
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(_declared_pack()), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    draft = tmp_path / 'draft.json'
    draft.write_text(before.decode().replace('"schema_version": 2,', '"schema_version": 2, "schema_version": 2,', 1), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '重复' in capsys.readouterr().err
    assert target.read_bytes() == before


def test_rule_cli_concurrent_writers_cannot_overwrite_the_same_expected_version(tmp_path, monkeypatch, capsys):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from task import main
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(_declared_pack()), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    paths = []
    for index in range(2):
        pack = json.loads(target.read_bytes())
        pack['configurations'][0]['opener']['source_basis'] = f'writer {index}'
        draft = tmp_path / f'draft-{index}.json'
        draft.write_text(json.dumps(pack), encoding='utf-8')
        paths.append(draft)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda path: main(['rules-save', str(path), '--expected-digest', identity]), paths))
    assert sorted(outcomes) == [0, 2]
    assert '冲突' in capsys.readouterr().err
    assert main(['rules-check', str(target)]) == 0


def test_public_task_budget_includes_configuration_read_and_validation(tmp_path, monkeypatch):
    import time
    from pathlib import Path
    _configure_opener(tmp_path, monkeypatch)
    config_path = tmp_path / 'rules.json'
    from task import start_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    clock = time.monotonic
    original_open = Path.open
    delay = [0.0]
    def timed_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if path.resolve() == config_path.resolve():
            delay[0] += 2.0  # 外部文件读取耗时；不替换校验或执行层。
        return handle
    monkeypatch.setattr(time, 'monotonic', lambda: clock() + delay[0])
    monkeypatch.setattr(Path, 'open', timed_open)
    with _apl_task_boundary():
        config = dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1)
        handle = start_task(source, tmp_path / 'task', search_config=config)
        result = handle.join(30)
        assert handle.done and handle.error is None
    assert delay[0] == 2.0
    assert result['elapsed_seconds'] >= 2.0


@pytest.mark.parametrize('precombat_occupancy,cast_ms,starts,first_burst', [(3000, 2000, [3000, 5000, 7000], 9000), (None, 0, None, None)])
def test_task_accounts_native_effective_precombat_occupancy_before_freezing_t0(
        tmp_path, monkeypatch, precombat_occupancy, cast_ms, starts, first_burst):
    import json,burst,result_store
    from test_burst import reviewed_fixture,character_seed_boundary
    from test_engine import apl_pool_reference
    definition,raw=reviewed_fixture();result_store.DATA_ROOT.mkdir();burst.publish(definition)
    native=apl_pool_reference();template=native['apl_actions'][0]
    native['static_snapshot']['protocol']=2
    for row in native['static_snapshot']['actions']:
        row.update(cast_ms=cast_ms,channel_ms=0)
    native['precombat_definitions']=[dict(template,name='raise_dead',signature='raise_dead',data_id=46584,
        base_spell_id=46584,precombat=True,harmful=False,gcd_ms=1500)]
    native['precombat_sequence']=[dict(name='raise_dead')]
    native['static_snapshot']['parameters']['precombat_gcd_ms']=1253
    if precombat_occupancy is not None:
        native['static_snapshot']['parameters']['precombat_occupancy_ms']=precombat_occupancy
    pack = _opener_pack({'tap': 'scourge_strike', 'big': 'army_of_the_dead'}, [dict(action='tap', source_step=i) for i in (1, 2, 3)], precombat=['raise_dead'], independent=[dict(action='big', source_step=4, mapping='burst')], anchor=4)
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    source=tmp_path/'role.simc';source.write_text(raw,encoding='utf-8')
    with character_seed_boundary(native_reference=native):
        if starts is None:
            with pytest.raises(TaskError,match='战前.*GCD.*未知'):
                run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=200,
                    candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
            return
        result=run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    assert [row['estimated_ms'] for row in report['positions'] if row['kind']=='action']==starts
    assert report['precombat_occupancy']['gcd_ms']==1253
    assert report['precombat_occupancy']['first_loop_ms']==starts[0]
    if precombat_occupancy is not None:
        assert report['precombat_occupancy']['occupancy_ms']==precombat_occupancy
    assert result['burst']['plan']['start_ms']==first_burst



def test_task_selects_opener_by_explicit_scene_and_native_hero_facts(tmp_path, monkeypatch):
    import copy
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['hero_subtree_ids'] = [702]
    pack = _opener_pack({'tap':'scourge_strike'}, [dict(action='tap',source_step=1)], hero_id=701)
    pack['identity_mappings']['hero_talents'] = {'first':701, 'second':702}
    pack['configurations'] = []
    for hero_name, label, count in [('first','single_target',1),('first','aoe',2),('second','single_target',3),('second','aoe',4)]:
        entry = _opener_pack({'tap':'scourge_strike'}, [dict(action='tap',source_step=i) for i in range(1,count+1)], target_type=label)['configurations'][0]
        entry['key']['hero_talent'] = hero_name
        pack['configurations'].append(entry)
    _configure_opener(tmp_path, monkeypatch, pack)
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):

        result=run_task(source,tmp_path/'task',simulation_config={'target_count':5,'scene':'aoe'},
            search_config=dict(input_interval_ms=200,candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    assert [row['source_step'] for row in result['rule_initialization']['source_steps']] == list(range(1,5))
    assert result['simulation_config']['scene'] == 'aoe'



@pytest.mark.parametrize('hero,scene,steps', [(31, 'single_target', 14), (32, 'aoe', 12)])
def test_task_uses_default_putrefy_opener_after_legacy_single_precombat(tmp_path, monkeypatch, hero, scene, steps):
    """完整默认数据的公共任务契约；静态/原生边界均为公开构造，不冒称角色验收。"""
    from test_engine import apl_pool_reference
    from gse_import import decode_import
    from rule_config import DEFAULT_PATH
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(DEFAULT_PATH))
    native=apl_pool_reference();template=native['apl_actions'][0]
    spell_ids=dict(putrefy=1247378,festering_strike=85948,scourge_strike=55090,
                   death_coil=47541,epidemic=207317,soul_reaper=343294,death_and_decay=43265)
    native['apl_actions']=native['executed_actions']=[dict(template,name=name,signature=name,
        data_id=spell,base_spell_id=spell) for name,spell in spell_ids.items()]
    native['action_sequence']=[dict(name='putrefy')]
    native['precombat_definitions']=[dict(template,name='raise_dead',signature='raise_dead',
        data_id=46584,base_spell_id=46584,harmful=False,precombat=True)]
    native['precombat_sequence']=[dict(name='raise_dead')]
    native['static_snapshot']['hero_subtree_ids']=[hero]
    native['static_snapshot']['parameters']['precombat_gcd_ms']=1253
    # 每个源形态都有独立的构造时序；缺行不能再借基础按钮时序。
    static_names=[*spell_ids,'festering_scythe','necrotic_coil','graveyard','vampiric_strike']
    native['static_snapshot']['actions']=[dict(name=name,gcd_ms=1000,cast_ms=0,channeled=False,
        costs={},gains={},gain_status='known_zero',gain_timing='none') for name in static_names]
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):
        result=run_task(source,tmp_path/'task',simulation_config=dict(scene=scene,target_count=1 if scene=='single_target' else 5),
            search_config=dict(input_interval_ms=200,candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    assert len(report['source_steps'])==steps
    assert '开场两命令实际GCD/开战边界和原生逐命令guard待核验' not in report['unknown']
    assert report['source_steps'][0]['source_label']=='爆发'
    assert report['source_opener']['manual_differences'][0]=='首步爆发改腐化'
    assert next(row for row in report['positions'] if row['kind']=='action')['action']=='putrefy'
    expected='death_coil' if scene=='single_target' else 'epidemic'
    assert [row['action'] for row in report['source_steps'] if row['source_step'] in (9,10)]==[expected,expected]
    payload=next(iter(decode_import(report['export_text'])['sequences'].values()))
    actions=payload['Versions'][0]['Actions']
    assert actions[0]['macro']=='/cast [nocombat] 46584'
    assert 'outbreak' not in [name for row in report['click_mapping'] for name in row.get('commands', [])]


@pytest.mark.parametrize('known_cost,form_gcd,starts', [(True, 2200, [0, 2200]), (False, None, None)])
def test_task_uses_configured_replacement_form_cost_and_same_button_mapping(
        tmp_path, monkeypatch, known_cost, form_gcd, starts):
    import json
    from test_engine import apl_pool_reference
    native=apl_pool_reference()
    template=next(row for row in native['apl_actions'] if row['name']=='epidemic')
    native['apl_actions'].append(dict(template,name='graveyard',signature='graveyard',data_id=1242914))
    native['executed_actions'].extend([template, native['apl_actions'][-1]])
    native['static_snapshot']['resources']['runic_power']['current']=100
    if known_cost is not False:
        native['static_snapshot']['actions'].append(dict(name='graveyard',gcd_ms=form_gcd,cooldown_ms=0,
            cast_ms=0,channeled=False,costs={'runic_power':18},
            gains={},gain_status='known_zero',
            gain_timing='none',unknown={}))
    pack = _opener_pack({'area': dict(kind='action', base_button='epidemic', native_action='epidemic', native_forms=['epidemic','graveyard'])}, [dict(action='area',source_form='graveyard',source_step=i) for i in (1,2)])
    config=tmp_path/'rules.json';config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):
        if known_cost is False:
            with pytest.raises(TaskError, match='静态字段.*graveyard'):
                run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
                    candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
            return
        result=run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    attempts=[row for row in report['positions'] if row['kind']=='action']
    assert [row['action'] for row in attempts]==['epidemic','epidemic']
    assert [row['costs'] for row in attempts]==[{'runic_power':18}]*2
    assert [row['estimated_resources_after']['runic_power'] for row in attempts]==[82,64]
    assert [row['estimated_ms'] for row in attempts]==starts

    assert report['click_mapping'][0]['commands']==['epidemic','graveyard']
    assert all(row['condition_status']=='dynamic_condition_unknown' for row in attempts)


def test_task_rejects_burst_source_missing_from_original_macro(tmp_path, monkeypatch):
    import burst, result_store
    from test_burst import reviewed_fixture, character_seed_boundary
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir()
    published = burst.publish(definition)
    pack = _opener_pack({'tap': 'scourge_strike', 'big': 'blightfall'},
        [dict(action='tap', source_step=1)],
        independent=[dict(action='big', source_step=2, mapping='burst')], anchor=2)
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(raw, encoding='utf-8')
    with character_seed_boundary(), pytest.raises(TaskError, match='独立爆发宏未包含.*blightfall'):
        run_task(source, tmp_path / 'task', use_burst=True, search_config=dict(input_interval_ms=200,
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    assert burst.load(252) == published


def test_rule_cli_saves_new_opener_but_old_task_keeps_its_snapshot_and_refuses_resume(tmp_path, monkeypatch, capsys):
    import copy,json
    from task import main,read_task,resume_task
    from test_engine import apl_pool_reference
    pack = _declared_pack()
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='window')
    states = pack['configurations'][0]['states']
    states['only']['effect'] = 'window'
    states['other'] = dict(copy.deepcopy(states['only']), expected=False)
    _configure_opener(tmp_path, monkeypatch, pack)
    target=tmp_path/'rules.json'
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    native=apl_pool_reference()
    with _apl_task_boundary(native):
        old=run_task(source,tmp_path/'old',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    initialization = old['rule_initialization']
    assert initialization['configuration_key'] == dict(
        specialization_id=252, hero_talent='sample_hero', target_type='single_target')
    assert initialization['states'] == states
    assert [row['state'] for row in initialization['bindings']] == ['only', 'other']
    assert all(row['application_status'] == 'declared_not_diagnosed' for row in initialization['rules'])
    assert initialization['rule_snapshot']['pack'] == pack
    assert old['candidate']['text'].startswith('!GSE3!')
    identity=initialization['rule_config_digest']
    edited=copy.deepcopy(pack)
    edited['general']['templates']['fixture']['diagnose']['let']['marker']='revised'
    opener=edited['configurations'][0]['opener']
    opener['source_basis']='fixture: edited'
    opener['source_steps'].append('second')
    opener['ordinary_steps'].append(dict(copy.deepcopy(opener['ordinary_steps'][0]), source_step=2))
    draft=tmp_path/'draft.json';draft.write_text(json.dumps(edited),encoding='utf-8')
    assert main(['rules-save',str(draft),'--expected-digest',identity])==0
    new_digest=json.loads(capsys.readouterr().out)['rule_config_digest']
    with _apl_task_boundary(native):
        new=run_task(source,tmp_path/'new',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
        with pytest.raises(TaskError,match='规则.*变化.*新任务'):
            resume_task(tmp_path/'old')
    assert [row['action'] for row in new['rule_initialization']['positions'] if row['kind']=='action']==['scourge_strike']*2
    assert new_digest!=identity
    saved_old = read_task(tmp_path/'old')['rule_initialization']
    assert saved_old == old['rule_initialization']
    assert saved_old['rule_snapshot']['pack'] == pack
    assert new['rule_initialization']['rule_snapshot']['pack'] == edited
    assert read_task(tmp_path/'new')['rule_initialization'] == new['rule_initialization']
    before=target.read_bytes()
    assert main(['rules-save',str(draft),'--expected-digest',identity])==2
    assert '冲突' in capsys.readouterr().err
    draft.write_text('{invalid', encoding='utf-8')
    assert main(['rules-save',str(draft),'--expected-digest',new_digest])==2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes()==before



def test_task_runs_independent_spec_and_renamed_aliases_without_class_strategy(tmp_path, monkeypatch):
    import json
    from test_engine import apl_pool_reference
    base=apl_pool_reference()
    template=base['apl_actions'][0]
    native=dict(base,identity={'spec_id':71,'class_id':1,'resource':'energy'})
    native['executed_actions']=native['apl_actions']=[dict(template,name=name,signature=name,
        data_id=spell,base_spell_id=spell) for name,spell in [('spark',1001),('drain',1002)]]
    native['action_sequence']=[dict(name='spark'),dict(name='drain')]
    native['static_snapshot']=dict(protocol=1,stage='precombat_initialized_before_actions',
        hero_subtree_ids=[777],resources={'energy':dict(current=40,maximum=100)},parameters={},actions=[
            dict(name=name,gcd_ms=1000,cooldown_ms=0,cast_ms=0,channeled=False,costs=cost,gains=gain,
                 gain_status='known' if gain else 'known_zero',gain_timing='on_cast' if gain else 'none')
            for name,cost,gain in [('spark',{},dict(energy=12)),('drain',dict(energy=24),{})]])
    pack = _opener_pack({'renamed_x':'spark','renamed_y':'drain'}, [dict(action='renamed_y',source_step=1),dict(action='renamed_x',source_step=2),dict(action='renamed_x',source_step=3)], spec_id=71, hero_id=777)
    config=tmp_path/'rules.json';config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc';source.write_text(sample_profile().replace('deathknight=','warrior=').
        replace('spec=unholy','spec=arms'),encoding='utf-8')
    with _apl_task_boundary(native):
        result=run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    assert report['resource']=='energy'
    assert [row['action'] for row in report['positions'] if row['kind']=='action']==['drain','spark','spark']
    assert '亡者' not in json.dumps(report,ensure_ascii=False)


@pytest.mark.parametrize('name,spell_id,cast_ms,channel_ms,channeled,starts,finish', [('smite', 585, 2000, 0, False, [0, 2000], 4000), ('penance', 47540, 0, 3000, True, [0, 3000], 6000)])
def test_initializes_non_dk_cast_or_complete_channel_before_next_attempt(
        tmp_path, monkeypatch, name, spell_id, cast_ms, channel_ms, channeled, starts, finish):
    """普通施法直接排位；完整引导保公开任务/导出/读回，不冒充真实牧师验证。"""
    from pathlib import Path
    from task import read_task
    from test_engine import apl_pool_reference

    native = apl_pool_reference()
    action = dict(native['apl_actions'][0], name=name, signature=name,
                  data_id=spell_id, base_spell_id=spell_id)
    native.update(identity=dict(spec_id=256, class_id=5), apl_actions=[action],
                  executed_actions=[action], action_sequence=[dict(name=name)])
    native['static_snapshot'] = dict(protocol=2, stage='precombat_initialized_before_actions',
        hero_subtree_ids=[17], resources={'mana': dict(current=1000, maximum=1000)}, parameters={}, actions=[
            dict(name=name, gcd_ms=1500, cast_ms=cast_ms, channel_ms=channel_ms, channeled=channeled,
                 costs={'mana': 100}, gains={}, gain_status='known_zero', gain_timing='none')])
    pack = _opener_pack({'cast': name}, [dict(action='cast',source_step=i) for i in (1,2)], spec_id=256)
    _configure_opener(tmp_path, monkeypatch, pack)
    if channeled:
        source = tmp_path / 'role.simc'
        source.write_text((Path(__file__).with_name('fixtures') / 'discipline.simc').read_text(), encoding='utf-8')
        with _apl_task_boundary(native):
            result = run_task(source, tmp_path / 'task', search_config=dict(input_interval_ms=200,
                candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
            saved = read_task(tmp_path / 'task')
        report = result['rule_initialization']
        assert report == saved['rule_initialization']
        assert result['candidate']['text'].startswith('!GSE3!')
    else:
        from engine import inspect
        from rule_config import bind, load
        from rule_initialization import generate
        capabilities = inspect(native, tmp_path / 'capabilities')
        snapshot = load()
        binding = bind(capabilities, native['static_snapshot'], 1, spec_id=native['identity']['spec_id'],
                       rule_snapshot=snapshot, scene='single_target')
        report = generate(capabilities, native, binding=binding, input_interval_ms=200,
                          target_count=1, rule_snapshot=snapshot)
    assert [row['estimated_ms'] for row in report['positions'] if row['kind'] == 'action'] == starts
    assert report['duration_ms'] == finish


@pytest.mark.parametrize('fields,missing,field,protocol', [({'channeled': True}, 'channel_ms', 'channel_ms', 1)])
def test_task_rejects_unknown_or_inconsistent_action_timing(
        tmp_path, monkeypatch, fields, missing, field, protocol):
    from test_engine import apl_pool_reference

    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['protocol'] = protocol
    row = native['static_snapshot']['actions'][0]
    row.update(fields)
    if missing:
        row.pop(missing, None)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='outbreak.' + field):
        run_task(source, tmp_path / 'task', search_config=dict(input_interval_ms=200,
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_http_dual_task_freezes_one_config_and_preserves_scene_labels(tmp_path, monkeypatch):
    import json,threading
    from urllib.request import Request,urlopen
    import burst,result_store,sequence
    from interface import create_server
    from task import read_task
    from test_burst import reviewed_fixture,character_seed_boundary
    from unittest.mock import patch
    definition,raw=reviewed_fixture()
    result_store.DATA_ROOT.mkdir()
    published = burst.publish(definition)
    definition_path = result_store.DATA_ROOT / 'burst_definitions' / 'current_252.parquet'
    definition_bytes = definition_path.read_bytes()
    pack = _opener_pack({'tap':'scourge_strike','big':'army_of_the_dead',
                         'transformation':'dark_transformation'},
        [dict(action='tap',source_step=i) for i in (1,4)],
        independent=[dict(action='big',source_step=2,mapping='burst'),
                     dict(action='transformation',source_step=3,mapping='burst')], anchor=2)
    aoe = _opener_pack({'tap':'scourge_strike','big':'army_of_the_dead'},
        [dict(action='tap',source_step=i) for i in (1,2)], target_type='aoe',
        independent=[dict(action='big',source_step=3,mapping='burst')], anchor=3)
    pack['configurations'].extend(aoe['configurations'])
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    server=create_server(tmp_path/'page',task_options=dict(search_config=dict(input_interval_ms=200,
        candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1)))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    edited, single_burst_text = [], []
    try:
        with character_seed_boundary():
            score=sequence.evaluate
            def update_current_file(*args,**kwargs):
                if not edited:
                    candidate = kwargs['burst_candidate']
                    assert sequence.compiled_program(candidate) == [
                        ['army_of_the_dead'],
                        ['potion', 'use_item,slot=trinket1', 'use_item,slot=trinket2', 'dark_transformation']]
                    single_burst_text.append(candidate['text'])
                    changed=json.loads(path.read_text(encoding='utf-8'))
                    changed['configurations'][1]['opener']['ordinary_steps'][0]['source_step']=99
                    path.write_text(json.dumps(changed),encoding='utf-8')
                    edited.append(True)
                return score(*args,**kwargs)
            with patch.object(sequence,'evaluate',side_effect=update_current_file):
                request=Request(base+'/api/tasks',json.dumps(dict(profile=raw,mode='dual',input_interval_ms=200)).encode(),
                    {'Content-Type':'application/json'})
                with urlopen(request) as response:
                    task_id=json.load(response)['task_id']
                server.tasks[task_id][1].join(30)
                with urlopen(base+'/api/tasks/'+task_id+'?details=rule_initialization') as response:
                    detail=json.load(response)
        assert detail['status']=='completed',detail
        assert edited
        reports=[row['rule_initialization'] for row in detail['scenes']]
        assert [row['configuration_key']['target_type'] for row in reports]==['single_target','aoe']
        assert reports[0]['rule_config_digest']==reports[1]['rule_config_digest']
        assert [row['source_step'] for row in reports[1]['source_steps']]==[1,2,3]
        assert all(row['rule_snapshot']['pack']==pack for row in reports)
        assert all(row['export_text'].startswith('!GSE3!') for row in reports)
        _, destination = server.task_paths(task_id)
        single = read_task(destination / 'single_target')
        assert single['rule_initialization'] == reports[0]
        assert single['burst']['plan'] == dict(published['plan'], start_ms=1000)
        assert single['burst']['interval_ms'] == 200
        assert reports[0]['protected_burst']['plan'] == single['burst']['plan']
        assert single['burst']['candidate']['text'] == single_burst_text[0]
        actions = [row for row in reports[0]['positions'] if row['kind'] == 'action']
        assert [row['estimated_ms'] for row in actions] == [0, 2000]
        assert all(not 1000 <= row['estimated_ms'] < 2000 for row in actions)
        mapped = [row for row in reports[0]['source_steps'] if row.get('mapping') == 'burst']
        assert [row['estimated_ms'] for row in mapped] == [1000, 1200]
        assert [row['burst_mapping'] for row in mapped] == [
            [dict(native_action='army_of_the_dead', block=0, command=0, input_ms=1000)],
            [dict(native_action='dark_transformation', block=1, command=3, input_ms=1200)]]
        assert burst.load(252) == published
        assert definition_path.read_bytes() == definition_bytes
        starts = {200: ('单体：第1、46、91、136秒','群体：第2、47、92、137秒')}[200]
        assert all(value in detail['burst_instructions'] for value in starts)
        assert detail['input_interval_ms']==200
        assert detail['burst_instructions'].count(f'间隔{200}毫秒')==2
        from gse_import import decode_import
        help_text=next(iter(decode_import(detail['exports']['burst'])['sequences'].values()))['MetaData']['Help']
        assert detail['burst_instructions'] in help_text
    finally:
        server.shutdown();server.server_close();thread.join(5)


def test_task_validates_precombat_definition_without_replacing_native_preparations(tmp_path):
    from unittest.mock import patch
    import sequence
    from test_engine import apl_pool_reference
    from test_search import _fast_report
    native=apl_pool_reference();template=native['apl_actions'][0]
    summon=dict(template,name='raise_dead',signature='raise_dead',data_id=46584,
        base_spell_id=46584,precombat=True,harmful=False,gcd_ms=1500)
    preparations=[dict(template,name='snapshot_stats',signature='snapshot_stats',data_id=0,base_spell_id=0,
        precombat=True,harmful=False,type='other',gcd_ms=0),
        dict(template,name='arbitrary_name',signature='variable,name=arbitrary_name,value=1',data_id=0,
             base_spell_id=0,precombat=True,harmful=False,type='action_variable',quiet=True,gcd_ms=0)]
    native['precombat_definitions']=[*preparations,summon]
    native['precombat_sequence']=[dict(name='raise_dead')]
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    real_evaluate=sequence.evaluate
    def native_boundary(profile,folder,mode,options,**kwargs):
        import json
        from task import parse_character
        generated=profile.read_text(encoding='utf-8')
        assert 'actions.precombat=' not in generated
        assert generated.startswith(sample_profile())
        character=parse_character(sample_profile())
        report=_fast_report(character,100.,99)
        report['sim']['players'][0]['sim2gse_precombat_actions']=[dict(row,executions=0) for row in
            [*preparations,summon]]

        (folder/'native.pending.json').write_text(json.dumps(report),encoding='utf-8')
        events=[(0,'explicit_precombat',0,-1,'raise_dead'),(0,'input',1,0,'-'),(200,'input',2,1,'-'),
                (200,'dispatch',2,1,'scourge_strike'),(200,'native_execute',2,1,'scourge_strike')]
        (folder/'native.txt').write_text(''.join('S2GSE\t'+ '\t'.join(map(str,[ms,event,origin,step,
            action,1400,10,100,0,0,action,0,-1,-1]))+'\n' for ms,event,origin,step,action in events),encoding='utf-8')
        return 'S2GBLOCK\t0\t-1\t-\nS2GBLOCK\t1\t0\tscourge_strike\n'
    with _apl_task_boundary(native),patch.object(sequence,'evaluate',side_effect=real_evaluate),\
            patch.object(sequence,'run',side_effect=native_boundary):
        result=run_task(source,tmp_path/'task',mode='single',program=[['scourge_strike']],
             search_config=dict(input_interval_ms=200,diagnostic_logging=False))
        assert result['status']=='offline_ready'


def test_task_behavior_identity_distinguishes_precombat_prefix_from_combat_clicks(tmp_path):
    import copy
    from test_engine import apl_pool_reference
    from sequence import behavior_key,compiled_program
    native=apl_pool_reference();template=native['apl_actions'][0]
    summon=dict(template,name='raise_dead',signature='raise_dead',data_id=46584,base_spell_id=46584,
                harmful=False,gcd_ms=0)
    native['executed_actions'].append(summon);native['apl_actions'].append(summon)
    precombat=copy.deepcopy(native)
    precombat['precombat_definitions']=[dict(summon,precombat=True)]
    precombat['precombat_sequence']=[dict(name='raise_dead')]
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(precombat):
        before=run_task(source,tmp_path/'precombat',mode='single',program=[['scourge_strike']])
    with _apl_task_boundary(native):
        during=run_task(source,tmp_path/'combat',mode='single',
            program=[['raise_dead'],['scourge_strike']])
    assert compiled_program(before['candidate'])==compiled_program(during['candidate'])
    assert behavior_key(before['candidate'])!=behavior_key(during['candidate'])


def test_rule_cli_rejects_retired_initialization_contract_without_replacing_valid_pack(
        tmp_path, monkeypatch, capsys):
    import json
    from task import main
    pack = _declared_pack()
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    configuration = pack['configurations'][0]
    template = next(iter(pack['general']['templates'].values()))
    row = configuration['states']['only']['priority'][0]
    configuration['opener']['funding'] = dict(action='tap')
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    checked = main(['rules-check', str(draft)])
    check_error = capsys.readouterr().err
    saved = main(['rules-save', str(draft), '--expected-digest', identity])
    save_error = capsys.readouterr().err
    assert (checked, saved, target.read_bytes() == before) == (2, 2, True)
    assert '规则配置' in check_error
    assert '规则配置' in save_error
