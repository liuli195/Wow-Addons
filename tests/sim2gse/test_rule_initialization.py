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


def test_public_task_selects_and_freezes_one_three_key_configuration(tmp_path, monkeypatch):
    """构造的通用三键配置，不继承旧专精规则结构。"""
    from task import read_task
    from test_engine import apl_pool_reference
    key = dict(specialization_id=252, hero_talent='sample_hero', target_type='single_target')
    pack = dict(schema_version=2,
        identity_mappings=dict(hero_talents={'sample_hero': 17}),
        general=dict(templates={}), execution_evidence={},
        object_sets={'sample': {'work': dict(kind='action', native_action='scourge_strike',
                                           base_button='scourge_strike', native_forms=['scourge_strike'])}},
        configurations=[dict(key=key, objects_ref='sample', execution_ref=None,
            states={'only': dict(effect=None, expected=True, priority=[])},
            opener=dict(source_basis='fixture: three-key ordered opener', source_steps=['work', 'work'],
                precombat=[], burst_anchor=None, independent_burst_source_steps=[],
                ordinary_steps=[dict(action='work', source_step=i, source_form='scourge_strike',
                    attribute_query=dict(native_form='scourge_strike', base_button='scourge_strike',
                                         missing='unknown_no_base_cost_fallback')) for i in (1, 2)]))])
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    native['static_snapshot']['hero_subtree_ids'] = [17]
    native['identity']['resource'] = 'runic_power'
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    report = result['rule_initialization']
    assert report == saved['rule_initialization']
    assert report['configuration_key'] == key
    assert report['rule_snapshot']['pack'] == pack
    assert report['states'] == pack['configurations'][0]['states']
    assert [row['action'] for row in report['positions'] if row['kind'] == 'action'] == [
        'scourge_strike', 'scourge_strike']
    assert result['candidate']['text'].startswith('!GSE3!')


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


@pytest.mark.parametrize('fault', ['component_scope', 'from_action_kind', 'qualification_ref', 'native_identity_type',
                                 'representation_value', 'representation_object'])
def test_rule_cli_rejects_invalid_object_types_and_same_set_references(tmp_path, monkeypatch, capsys, fault):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    pack = json.loads(DEFAULT_PATH.read_bytes())
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    objects = pack['object_sets']['unholy_sanlayn']
    effect = objects['putrefy_diseases']
    if fault == 'component_scope': effect['components'][0]['target_scope'] = 'missing_scope'
    elif fault == 'from_action_kind': effect['from_action'] = 'runic_power'
    elif fault == 'qualification_ref': effect['qualification'] = 'missing_state'
    elif fault == 'representation_value': objects['scythe_qualification']['representation'] = 'any_nonzero'
    elif fault == 'representation_object': objects['scythe_qualification']['representation'] = dict(op='gt')
    else: objects['runic_power']['native_identity'] = {'op': 'python', 'args': []}
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes() == before


def test_rule_cli_rejects_object_algorithm_in_enum_declaration_and_argument(tmp_path, monkeypatch, capsys):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    pack = json.loads(DEFAULT_PATH.read_bytes())
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    algorithm = {'op': 'python', 'args': ['arbitrary specialization algorithm']}
    pack['general']['templates']['条件触发与CD使用']['parameters']['compare']['values'].append(algorithm)
    row = next(row for row in pack['configurations'][0]['states']['normal']['priority']
               if row['template'] == '条件触发与CD使用')
    row['arguments']['compare'] = algorithm
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-check', str(draft)]) == 2
    assert '枚举' in capsys.readouterr().err
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '枚举' in capsys.readouterr().err
    assert target.read_bytes() == before


@pytest.mark.parametrize('fault', ['unknown_argument', 'unknown_operation', 'binding_algorithm'])
def test_rule_cli_checks_unused_template_declarations_without_executing_them(tmp_path, monkeypatch, capsys, fault):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    pack = json.loads(before)
    unused = pack['general']['templates']['资源预留']
    if fault == 'unknown_argument':
        unused['reads'][0]['object'] = {'arg': 'undeclared'}
    elif fault == 'unknown_operation':
        unused['diagnose']['for_each'] = {'op': 'python', 'args': []}
    else:
        pack['configurations'][0]['states']['normal']['priority'][0]['condition'] = {'op': 'eq', 'args': [1, 1]}
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes() == before


@pytest.mark.parametrize('fault', ['missing_hero', 'unknown_hero', 'missing_scene', 'wrong_scene',
                                 'wrong_spec', 'ambiguous_hero', 'duplicate_key'])
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
    elif fault == 'unknown_hero':
        native['static_snapshot']['hero_subtree_ids'] = [999]
    elif fault == 'missing_scene':
        config['scene'] = None
    elif fault == 'wrong_scene':
        config['scene'] = 'aoe'
    elif fault == 'wrong_spec':
        native['identity']['spec_id'] = 999
    elif fault == 'ambiguous_hero':
        pack['identity_mappings']['hero_talents']['other_hero'] = 17
        other = copy.deepcopy(pack['configurations'][0])
        other['key']['hero_talent'] = 'other_hero'
        pack['configurations'].append(other)
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


@pytest.mark.parametrize('fault,message', [('missing_gcd', '静态字段'), ('single_empty', '单空点击'),
                                        ('too_long', '点击或场景边界')])
def test_task_reports_unrepresentable_or_unknown_rule_start(tmp_path, monkeypatch, fault, message):
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    row = native['static_snapshot']['actions'][0]
    if fault == 'missing_gcd':
        row.pop('gcd_ms')
    elif fault == 'single_empty':
        row['gcd_ms'] = 400
    else:
        row['gcd_ms'] = 1000000
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match=message):
        run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


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


@pytest.mark.parametrize('use_burst', [False, True])
def test_task_initialization_timestamps_include_compiled_precombat_click(tmp_path, monkeypatch, use_burst):
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
    if use_burst:
        import burst, result_store
        result_store.DATA_ROOT.mkdir()
        from test_burst import reviewed_fixture, character_seed_boundary
        definition, raw = reviewed_fixture()
        definition = burst.publish(definition)
        source.write_text(raw, encoding='utf-8')
        boundary = character_seed_boundary(native_reference=native)
    with boundary:
        result = run_task(source, tmp_path / 'task', use_burst=use_burst, search_config=dict(
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
    if use_burst:
        assert report['protected_burst']['definition_id'] == definition['definition_id']


@pytest.mark.parametrize('gain_status,gain_timing,gains,first_balances', [
    ('known', 'on_hit', {'runic_power': 20}, {'rune': 2, 'runic_power': None}),
    ('unknown', 'unknown', {}, {'rune': None, 'runic_power': None}),
    ('unknown', 'unknown', None, {'rune': None, 'runic_power': None}),
    ('known', 'on_hit', {'rune': 1}, {'rune': None, 'runic_power': 10}),
])
def test_task_does_not_treat_conditional_or_unknown_gains_as_known_zero(
        tmp_path, monkeypatch, gain_status, gain_timing, gains, first_balances):
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['resources']['rune']['current'] = 3
    native['static_snapshot']['resources']['runic_power']['current'] = 10
    native['static_snapshot']['actions'][0].update(gain_status=gain_status, gain_timing=gain_timing, gains=gains)
    if gains is None:
        native['static_snapshot']['actions'][0]['unknown'] = {'gains': 'unsafe_gain'}
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert actions[0]['estimated_resources_after'] == first_balances
    assert all(row['condition_status'] == 'dynamic_condition_unknown' for row in actions)
    assert report['static_snapshot']['actions'][0]['gains'] == gains


def test_task_preserves_resource_uncertainty_without_inserting_funding_wait(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['resources']['rune'] = dict(current=1, maximum=1)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert [row['estimated_ms'] for row in actions] == [0, 1000, 2000]
    assert actions[1]['estimated_resources_after']['rune'] is None
    assert 'recovery' not in report



def test_task_rejects_invalid_edited_rule_pack_before_initialization(tmp_path, monkeypatch):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = tmp_path / 'rules.json'
    config.write_text('{broken', encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


@pytest.mark.parametrize('fault', ['action', 'object', 'cycle', 'count', 'operation', 'type', 'unit', 'parameter', 'override', 'source_step'])
def test_task_rejects_invalid_rule_references_before_running(tmp_path, monkeypatch, fault):
    pack = _declared_pack()
    template = pack['general']['templates']['fixture']
    configuration = pack['configurations'][0]
    row = configuration['states']['only']['priority'][0]
    opener = configuration['opener']
    if fault == 'type': row['arguments']['enabled'] = 1
    elif fault == 'unit': template['parameters']['count']['unit'] = 'unregistered'
    elif fault == 'parameter': row.pop('arguments')
    elif fault == 'override': row['overrides'] = []
    elif fault == 'source_step': opener['ordinary_steps'][0]['source_step'] = -1
    elif fault == 'action': opener['ordinary_steps'][0]['action'] = 'missing_action'
    elif fault == 'object': row['arguments']['action'] = 'missing_action'
    elif fault == 'cycle': row['arguments']['priority_refs'] = ['first']
    elif fault == 'count': opener['ordinary_steps'] *= 129
    else: template['diagnose']['for_each'] = dict(op='python', args=[])
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))



def test_task_maps_configured_native_facts_to_existing_button(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    pack = _configure_opener(tmp_path, monkeypatch)
    pack['object_sets']['sample']['scourge_strike'].update(native_action='native_builder', native_forms=['native_builder'])
    for configuration in pack['configurations']:
        step = configuration['opener']['ordinary_steps'][1]
        step['source_form'] = step['attribute_query']['native_form'] = 'native_builder'
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    next(row for row in native['static_snapshot']['actions'] if row['name'] == 'scourge_strike')['name'] = 'native_builder'
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    row = next(row for row in result['rule_initialization']['positions'] if row.get('action') == 'scourge_strike')
    assert row['native_action'] == 'native_builder'
    assert 'native_builder' not in result['candidate']['text']


@pytest.mark.parametrize('value', [None, -1])
def test_task_rejects_missing_or_negative_required_action_timing(tmp_path, monkeypatch, value):
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['actions'][0]['gcd_ms'] = value
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='静态字段|gcd_ms'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))



def test_rule_cli_rejects_duplicate_json_keys_without_replacing_valid_file(tmp_path, monkeypatch, capsys):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
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
    from rule_config import DEFAULT_PATH
    from task import main
    target = tmp_path / 'rules.json'
    target.write_bytes(DEFAULT_PATH.read_bytes())
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


@pytest.mark.parametrize('fault', ['identity_list', 'identity_null', 'ref_array_object', 'target_type',
    'opener_list', 'step_list', 'attribute_query_list', 'independent_command_list', 'precombat_list'])
def test_rule_cli_rejects_invalid_execution_fields_without_overwriting_valid_pack(tmp_path, monkeypatch, capsys, fault):
    import copy, json
    from task import main
    pack = _declared_pack()
    _configure_opener(tmp_path, monkeypatch, pack)
    target = tmp_path / 'rules.json'
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    configuration = pack['configurations'][0]
    if fault == 'identity_list': pack['identity_mappings'] = []
    elif fault == 'identity_null': pack['identity_mappings'] = None
    elif fault == 'ref_array_object': configuration['states']['only']['priority'][0]['arguments']['priority_refs'] = [{}]
    elif fault == 'target_type': configuration['key']['target_type'] = 'third_scene'
    elif fault == 'opener_list': configuration['opener'] = []
    elif fault == 'step_list': configuration['opener']['ordinary_steps'][0] = []
    elif fault == 'attribute_query_list': configuration['opener']['ordinary_steps'][0]['attribute_query'] = []
    elif fault == 'independent_command_list': configuration['opener']['independent_burst_source_steps'] = [dict(action='tap', mapping='burst', source_step=2, commands=[[]])]
    else: configuration['opener']['precombat'] = [[]]
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', identity]) == 2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes() == before
    assert main(['rules-check', str(target)]) == 0
    assert json.loads(capsys.readouterr().out)['rule_config_digest'] == identity



@pytest.mark.parametrize('asynchronous', [False, True])
def test_public_task_budget_includes_configuration_read_and_validation(tmp_path, monkeypatch, asynchronous):
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
        if asynchronous:
            handle = start_task(source, tmp_path / 'task', search_config=config)
            result = handle.join(30)
            assert handle.done and handle.error is None
        else:
            result = run_task(source, tmp_path / 'task', search_config=config)
    assert delay[0] == 2.0
    assert result['elapsed_seconds'] >= 2.0


def test_task_uses_configured_ordered_opener_without_funding_or_consumer(tmp_path, monkeypatch):
    """独立构造配置：三个同按钮步骤仍是三个尝试，无旧消费/供资骨架。"""
    import json
    pack = _opener_pack({'work': 'scourge_strike'}, [dict(action='work', source_step=i) for i in (1, 2, 3)])
    config = tmp_path / 'rules.json'
    config.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2,
            validation_batches=1))
    report = result['rule_initialization']
    assert report['program'] == [value for _ in range(3)
        for value in (['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4})]
    assert [row['source_step'] for row in report['positions'] if row['kind'] == 'action'] == [1, 2, 3]
    assert report['rule_snapshot']['pack'] == pack
    assert result['candidate']['text'].startswith('!GSE3!')


def test_task_rejects_resource_current_above_native_capacity(tmp_path, monkeypatch):
    import json
    from test_engine import apl_pool_reference
    pack = _opener_pack({'tap': 'scourge_strike'}, [dict(action='tap', source_step=1)])
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    native=apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']=dict(current=100,maximum=50)
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native),pytest.raises(TaskError,match='当前资源.*上限'):
        run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))


@pytest.mark.parametrize('precombat_gcd,precombat_occupancy,cast_ms,protocol,starts,first_burst', [
    (1253, None, 0, 1, [1400, 2400, 3400], 4400),
    (None, None, 0, 1, None, None),
    (1253, 3000, 0, 1, [3000, 4000, 5000], 6000),
    (1253, 'unknown', 0, 1, None, None),
    (1253, 3000, 2000, 2, [3000, 5000, 7000], 9000),
    (1253, None, 0, 2, None, None),
])
def test_task_accounts_native_effective_precombat_occupancy_before_freezing_t0(
        tmp_path, monkeypatch, precombat_gcd, precombat_occupancy, cast_ms, protocol, starts, first_burst):
    import json,burst,result_store
    from test_burst import reviewed_fixture,character_seed_boundary
    from test_engine import apl_pool_reference
    definition,raw=reviewed_fixture();result_store.DATA_ROOT.mkdir();burst.publish(definition)
    native=apl_pool_reference();template=native['apl_actions'][0]
    native['static_snapshot']['protocol']=protocol
    for row in native['static_snapshot']['actions']:
        row.update(cast_ms=cast_ms,channel_ms=0)
    native['precombat_definitions']=[dict(template,name='raise_dead',signature='raise_dead',data_id=46584,
        base_spell_id=46584,precombat=True,harmful=False,gcd_ms=1500)]
    native['precombat_sequence']=[dict(name='raise_dead')]
    if precombat_gcd is not None:
        native['static_snapshot']['parameters']['precombat_gcd_ms']=precombat_gcd
    if precombat_occupancy == 'unknown':
        native['static_snapshot']['parameter_unknown']={'precombat_occupancy_ms':'unsafe_duration'}
    elif precombat_occupancy is not None:
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
    assert report['precombat_occupancy']['gcd_ms']==precombat_gcd
    assert report['precombat_occupancy']['first_loop_ms']==starts[0]
    if precombat_occupancy is not None:
        assert report['precombat_occupancy']['occupancy_ms']==precombat_occupancy
    assert result['burst']['plan']['start_ms']==first_burst


def test_task_carries_all_declared_states_and_rules_without_diagnosing_them(tmp_path, monkeypatch):
    import copy
    pack = _declared_pack()
    objects = pack['object_sets']['sample']
    objects['window'] = dict(kind='effect', native_identity='window')
    states = pack['configurations'][0]['states']
    states['only']['effect'] = 'window'
    states['other'] = dict(copy.deepcopy(states['only']), expected=False)
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['states'] == states
    assert [row['state'] for row in report['bindings']] == ['only', 'other']
    assert all(row['application_status'] == 'declared_not_diagnosed' for row in report['rules'])
    assert report['rule_snapshot']['pack'] == pack



def test_rule_cli_accepts_complete_guide_candidate_and_rejects_broken_opener_reference(tmp_path, capsys):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    assert main(['rules-check', str(DEFAULT_PATH)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'valid'
    pack = json.loads(DEFAULT_PATH.read_bytes())
    assert len(pack['general']['templates']) == 8
    profiles = pack['configurations']
    assert [len(row['opener']['source_steps']) for row in profiles] == [14, 14, 12, 12]
    assert [sum(len(state['priority']) for state in row['states'].values()) for row in profiles] == [22, 20, 19, 18]
    assert all(row['opener']['ordinary_steps'][0]['action'] == 'putrefy' for row in profiles)
    profiles[0]['opener']['ordinary_steps'][0]['action'] = 'missing'
    broken = tmp_path / 'broken.json'
    broken.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-check', str(broken)]) == 2
    assert '起手' in capsys.readouterr().err



@pytest.mark.parametrize('hero,scene,steps', [(701,'single_target',1),(701,'aoe',2),
                                            (702,'single_target',3),(702,'aoe',4),(None,'single_target',None)])
def test_task_selects_opener_by_explicit_scene_and_native_hero_facts(tmp_path, monkeypatch, hero, scene, steps):
    import copy
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['hero_subtree_ids'] = [] if hero is None else [hero]
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
        if hero is None:
            with pytest.raises(TaskError,match='三键'):
                run_task(source,tmp_path/'task',simulation_config={'target_count':5,'scene':scene})
            return
        result=run_task(source,tmp_path/'task',simulation_config={'target_count':5,'scene':scene},
            search_config=dict(input_interval_ms=200,candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    assert [row['source_step'] for row in result['rule_initialization']['source_steps']] == list(range(1,steps+1))
    assert result['simulation_config']['scene'] == scene



@pytest.mark.parametrize('hero,scene,steps', [(31,'single_target',14),(31,'aoe',14),
                                           (32,'single_target',12),(32,'aoe',12)])
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


@pytest.mark.parametrize('known_cost,form_gcd,starts', [
    (True, 1000, [0, 1000]), (True, 2200, [0, 2200]),
    (False, None, None), (None, 1000, [0, 1000]),
])
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
            cast_ms=0,channeled=False,costs={'runic_power':18} if known_cost else None,
            gains={} if known_cost else None,gain_status='known_zero' if known_cost else 'unknown',
            gain_timing='none',unknown={} if known_cost else {'costs':'unsafe_cost', 'gains':'unsafe_gain'}))
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
    assert [row['costs'] for row in attempts]==([{'runic_power':18}]*2 if known_cost else [None,None])
    assert [row['estimated_resources_after']['runic_power'] for row in attempts]==([82,64] if known_cost else [None,None])
    assert [row['estimated_ms'] for row in attempts]==starts
    if known_cost is None:
        assert all(row['effective_gcd_ms']==1000 for row in attempts)
        assert any('graveyard.costs' in item for item in report['unknown'])
        assert any('graveyard.gains' in item for item in report['unknown'])
    assert report['click_mapping'][0]['commands']==['epidemic','graveyard']
    assert all(row['condition_status']=='dynamic_condition_unknown' for row in attempts)


@pytest.mark.parametrize('mapped_action,input_interval_ms', [
    ('army_of_the_dead',200), ('army_of_the_dead',300), ('blightfall',200)])
def test_task_freezes_first_burst_from_opener_and_reuses_original_macro(tmp_path, monkeypatch, mapped_action, input_interval_ms):
    import json
    import burst,result_store
    from test_burst import reviewed_fixture,character_seed_boundary
    definition,raw=reviewed_fixture()
    result_store.DATA_ROOT.mkdir()
    published=burst.publish(definition)
    pack = _opener_pack({'tap': 'scourge_strike', 'big': mapped_action, 'transformation': 'dark_transformation'}, [dict(action='tap',source_step=i) for i in (1,2,5)], independent=[dict(action='big',source_step=3,mapping='burst'),dict(action='transformation',source_step=4,mapping='burst')], anchor=3)
    config=tmp_path/'rules.json';config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc';source.write_text(raw,encoding='utf-8')
    with character_seed_boundary():
        if mapped_action=='blightfall':
            with pytest.raises(TaskError,match='独立爆发宏未包含.*blightfall'):
                run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=input_interval_ms,
                    candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
            assert burst.load(252)==published
            return
        result=run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=input_interval_ms,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    start_ms, action_times, mapped_times, starts = {
        200: (2000,[0,1000,3000],[2000,2200],'第2、47、92、137秒'),
        300: (2400,[0,1200,3600],[2400,2700],'第2.4、47.4、92.4、137.4秒'),
    }[input_interval_ms]
    assert result['burst']['plan']==dict(published['plan'],start_ms=start_ms)
    assert result['burst']['interval_ms']==input_interval_ms
    assert report['protected_burst']['plan']==result['burst']['plan']
    from sequence import compiled_program
    assert compiled_program(result['burst']['candidate']) == [
        ['army_of_the_dead'], ['potion', 'use_item,slot=trinket1', 'use_item,slot=trinket2', 'dark_transformation']]
    assert all(not start_ms <= row['estimated_ms'] < start_ms+1000
               for row in report['positions'] if row['kind']=='action')
    assert [row['estimated_ms'] for row in report['positions'] if row['kind']=='action']==action_times
    mapped=[row for row in report['source_steps'] if row.get('mapping')=='burst']
    assert [row['estimated_ms'] for row in mapped]==mapped_times
    assert mapped[0]['burst_mapping']==[dict(native_action='army_of_the_dead',block=0,command=0,input_ms=mapped_times[0])]
    assert mapped[1]['burst_mapping']==[dict(native_action='dark_transformation',block=1,command=3,input_ms=mapped_times[1])]
    assert starts in result['burst']['instructions']
    assert f'间隔{input_interval_ms}毫秒' in result['burst']['instructions']
    from gse_import import decode_import
    help_text=next(iter(decode_import(result['burst']['candidate']['text'])['sequences'].values()))['MetaData']['Help']
    assert starts in help_text
    assert f'间隔{input_interval_ms}毫秒' in help_text
    assert '第3、48、93、138秒' not in help_text
    assert burst.load(252)==published
    from task import read_task
    assert read_task(tmp_path/'task')['burst']['plan']==result['burst']['plan']


def test_rule_cli_saves_new_opener_but_old_task_keeps_its_snapshot_and_refuses_resume(tmp_path, monkeypatch, capsys):
    import copy,json
    from task import main,read_task,resume_task
    from test_engine import apl_pool_reference
    pack = _declared_pack()
    _configure_opener(tmp_path, monkeypatch, pack)
    target=tmp_path/'rules.json'
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    native=apl_pool_reference()
    with _apl_task_boundary(native):
        old=run_task(source,tmp_path/'old',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    identity=old['rule_initialization']['rule_config_digest']
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
    for invalid, message in [('{invalid','规则配置'), ('{"schema_version":2,"schema_version":2}','重复')]:
        draft.write_text(invalid, encoding='utf-8')
        assert main(['rules-save',str(draft),'--expected-digest',new_digest])==2
        assert message in capsys.readouterr().err
        assert target.read_bytes()==before



def test_task_ignores_duplicate_native_list_metadata_but_rejects_conflicting_arithmetic(tmp_path, monkeypatch):
    import json
    from test_engine import apl_pool_reference
    pack = _opener_pack({'tap': 'scourge_strike'}, [dict(action='tap',source_step=1)])
    config=tmp_path/'rules.json';config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    native=apl_pool_reference()
    row=next(row for row in native['static_snapshot']['actions'] if row['name']=='scourge_strike')
    native['static_snapshot']['actions'].append(dict(row,signature='scourge_strike,if=source_only',action_list='another'))
    with _apl_task_boundary(native):
        result=run_task(source,tmp_path/'same',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    assert result['rule_initialization']['positions'][0]['effective_gcd_ms']==1000
    native['static_snapshot']['actions'][-1]['gcd_ms']=1500
    with _apl_task_boundary(native),pytest.raises(TaskError,match='静态字段不一致'):
        run_task(source,tmp_path/'conflict',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))


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


@pytest.mark.parametrize('name,spell_id,cast_ms,channel_ms,channeled,starts,finish', [
    ('smite', 585, 2000, 0, False, [0, 2000], 4000),
    ('penance', 47540, 0, 3000, True, [0, 3000], 6000),
    ('penance', 47540, 500, 3000, True, [0, 3600], 7200),
])
def test_task_initializes_non_dk_cast_or_complete_channel_before_next_attempt(
        tmp_path, monkeypatch, name, spell_id, cast_ms, channel_ms, channeled, starts, finish):
    """构造原生时长经公开任务入口排位，不冒充真实牧师验证。"""
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
    source = tmp_path / 'role.simc'
    source.write_text((Path(__file__).with_name('fixtures') / 'discipline.simc').read_text(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(input_interval_ms=200,
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    report = result['rule_initialization']
    assert report == saved['rule_initialization']
    assert [row['estimated_ms'] for row in report['positions'] if row['kind'] == 'action'] == starts
    assert report['duration_ms'] == finish
    assert result['candidate']['text'].startswith('!GSE3!')


@pytest.mark.parametrize('fields,missing,field,protocol', [
    ({'channeled': False, 'channel_ms': 3000}, None, 'channel_ms', 1),
    ({'channeled': True}, 'channel_ms', 'channel_ms', 1),
    ({'channeled': True, 'channel_ms': -1}, None, 'channel_ms', 1),
    ({'unknown': {'channel_ms': 'unsafe_duration'}}, 'channel_ms', 'channel_ms', 1),
    ({}, 'cast_ms', 'cast_ms', 1),
    ({}, 'channeled', 'channeled', 1),
    ({}, 'channel_ms', 'channel_ms', 2),
])
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


@pytest.mark.parametrize('input_interval_ms', [200,300])
def test_http_dual_task_freezes_one_config_and_preserves_scene_labels(tmp_path, monkeypatch, input_interval_ms):
    import json,threading
    from urllib.request import Request,urlopen
    import burst,result_store,sequence
    from interface import create_server
    from test_burst import reviewed_fixture,character_seed_boundary
    from unittest.mock import patch
    definition,raw=reviewed_fixture()
    result_store.DATA_ROOT.mkdir()
    burst.publish(definition)
    pack = _opener_pack({'tap':'scourge_strike','big':'army_of_the_dead'},
        [dict(action='tap',source_step=1)], independent=[dict(action='big',source_step=2,mapping='burst')], anchor=2)
    aoe = _opener_pack({'tap':'scourge_strike','big':'army_of_the_dead'},
        [dict(action='tap',source_step=i) for i in (1,2)], target_type='aoe',
        independent=[dict(action='big',source_step=3,mapping='burst')], anchor=3)
    pack['configurations'].extend(aoe['configurations'])
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    server=create_server(tmp_path/'page',task_options=dict(search_config=dict(input_interval_ms=input_interval_ms,
        candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1)))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    edited=[]
    try:
        with character_seed_boundary():
            score=sequence.evaluate
            def update_current_file(*args,**kwargs):
                if not edited:
                    changed=json.loads(path.read_text(encoding='utf-8'))
                    changed['configurations'][1]['opener']['ordinary_steps'][0]['source_step']=99
                    path.write_text(json.dumps(changed),encoding='utf-8')
                    edited.append(True)
                return score(*args,**kwargs)
            with patch.object(sequence,'evaluate',side_effect=update_current_file):
                request=Request(base+'/api/tasks',json.dumps(dict(profile=raw,mode='dual',input_interval_ms=input_interval_ms)).encode(),
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
        starts = {
            200: ('单体：第1、46、91、136秒','群体：第2、47、92、137秒'),
            300: ('单体：第1.2、46.2、91.2、136.2秒','群体：第2.4、47.4、92.4、137.4秒'),
        }[input_interval_ms]
        assert all(value in detail['burst_instructions'] for value in starts)
        assert detail['input_interval_ms']==input_interval_ms
        assert detail['burst_instructions'].count(f'间隔{input_interval_ms}毫秒')==2
        from gse_import import decode_import
        help_text=next(iter(decode_import(detail['exports']['burst'])['sequences'].values()))['MetaData']['Help']
        assert detail['burst_instructions'] in help_text
    finally:
        server.shutdown();server.server_close();thread.join(5)


@pytest.mark.parametrize('definition_present', [True, False, 'extra_active'])
def test_task_validates_precombat_definition_without_replacing_native_preparations(tmp_path, definition_present):
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
            [*preparations,*([summon] if definition_present else [])]]
        if definition_present=='extra_active':
            report['sim']['players'][0]['sim2gse_precombat_actions'].append(dict(template))
        (folder/'native.pending.json').write_text(json.dumps(report),encoding='utf-8')
        events=[(0,'explicit_precombat',0,-1,'raise_dead'),(0,'input',1,0,'-'),(200,'input',2,1,'-'),
                (200,'dispatch',2,1,'scourge_strike'),(200,'native_execute',2,1,'scourge_strike')]
        (folder/'native.txt').write_text(''.join('S2GSE\t'+ '\t'.join(map(str,[ms,event,origin,step,
            action,1400,10,100,0,0,action,0,-1,-1]))+'\n' for ms,event,origin,step,action in events),encoding='utf-8')
        return 'S2GBLOCK\t0\t-1\t-\nS2GBLOCK\t1\t0\tscourge_strike\n'
    with _apl_task_boundary(native),patch.object(sequence,'evaluate',side_effect=real_evaluate),\
            patch.object(sequence,'run',side_effect=native_boundary):
        if definition_present is True:
            result=run_task(source,tmp_path/'task',mode='single',program=[['scourge_strike']],
                 search_config=dict(input_interval_ms=200,diagnostic_logging=False))
            assert result['status']=='offline_ready'
        else:
            with pytest.raises(TaskError,match='战前'):
                run_task(source,tmp_path/'task',mode='single',program=[['scourge_strike']],
                    search_config=dict(input_interval_ms=200,diagnostic_logging=False))


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


def test_http_task_honors_explicit_scene_without_inferring_a_target_threshold(tmp_path, monkeypatch):
    import json,threading
    from urllib.request import Request,urlopen
    from interface import create_server
    pack = _opener_pack({'tap':'scourge_strike'}, [dict(action='tap',source_step=1)], target_type='aoe')
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    server=create_server(tmp_path/'page',task_options=dict(search_config=dict(input_interval_ms=200,
        candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1)))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with _apl_task_boundary():
            request=Request(base+'/api/tasks',json.dumps(dict(profile=sample_profile(),scene='aoe',target_count=1,
                input_interval_ms=200)).encode(),{'Content-Type':'application/json'})
            with urlopen(request) as response:task_id=json.load(response)['task_id']
            server.tasks[task_id][1].join(15)
            with urlopen(base+'/api/tasks/'+task_id+'?details=rule_initialization') as response:result=json.load(response)
        assert result['status']=='completed',result
        assert result['rule_initialization']['configuration_key']['target_type']=='aoe'
    finally:
        server.shutdown();server.server_close();thread.join(5)


@pytest.mark.parametrize('location', ['general_policy', 'funding', 'general_template', 'shared_template', 'shared_binding', 'binding',
                                      'extra_initializations', 'overrides', 'plan_context'])
def test_rule_cli_rejects_retired_initialization_contract_without_replacing_valid_pack(
        tmp_path, monkeypatch, capsys, location):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    target = tmp_path / 'rules.json'
    target.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(target))
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    configuration = pack['configurations'][0]
    template = next(iter(pack['general']['templates'].values()))
    row = configuration['states']['normal']['priority'][0]
    if location == 'general_policy': pack['general']['initialization'] = dict(edit_limit=32)
    elif location == 'funding': configuration['opener']['funding'] = dict(action='scourge_strike')
    elif location == 'general_template': pack['general']['templates']['retired'] = dict(initialize=dict(when=True))
    elif location == 'shared_template': template['initialize'] = dict(when=True)
    elif location == 'shared_binding': template['binding'] = dict(initialize=dict(attempt='putrefy'))
    elif location == 'binding': row['initialize'] = dict(attempt='putrefy')
    elif location == 'extra_initializations': row['extra_initializations'] = []
    elif location == 'overrides': row['overrides'] = []
    else: row['condition'] = {'op':'eq','args':[{'var':'plan.target_cost'},0]}
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    checked = main(['rules-check', str(draft)])
    check_error = capsys.readouterr().err
    saved = main(['rules-save', str(draft), '--expected-digest', identity])
    save_error = capsys.readouterr().err
    assert (checked, saved, target.read_bytes() == before) == (2, 2, True)
    assert '规则配置' in check_error
    assert '规则配置' in save_error
