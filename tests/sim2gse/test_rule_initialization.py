"""规则起点通过任务公开入口交付；构造引擎报告不冒充真实角色验收。"""
from task import TaskError, run_task
from test_character_export import sample_profile
from test_search import _apl_task_boundary
import pytest


def _configure_opener(tmp_path, monkeypatch, pack=None):
    """只给旧安全回归提供匹配其外部报告的显式有序配置。"""
    import json
    from test_search import _minimal_rule_pack
    pack = _minimal_rule_pack() if pack is None else pack
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    return pack


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


def test_native_integral_resource_slots_are_accepted_as_json_numbers(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    pack = _configure_opener(tmp_path, monkeypatch)
    spec = pack['specializations']['252']
    spec['facts']['slots'] = dict(type='integer', unit='count', **{'from': 'static.parameter'}, key='rune_recharge_slots')
    spec['initialization']['required_facts'] = ['slots']
    spec['initialization']['recovery'] = dict(model='parallel_discrete', resource='rune', interval_ms=3000, slots={'fact': 'slots'})
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['rune_recharge_slots'] = 3.0
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    assert result['rule_initialization']['recovery']['slots'] == 3.0


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
    _configure_opener(tmp_path, monkeypatch)
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


@pytest.mark.parametrize('gain_status,gain_timing,gains', [
    ('known', 'on_hit', {'runic_power': 20}), ('unknown', 'unknown', {})])
def test_task_does_not_treat_conditional_or_unknown_gains_as_known_zero(
        tmp_path, monkeypatch, gain_status, gain_timing, gains):
    from test_engine import apl_pool_reference
    _configure_opener(tmp_path, monkeypatch)
    native = apl_pool_reference()
    native['static_snapshot']['actions'][0].update(gain_status=gain_status, gain_timing=gain_timing, gains=gains)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert all(row['estimated_resources_after']['runic_power'] is None for row in actions)
    assert all(row['condition_status'] == 'dynamic_condition_unknown' for row in actions)
    assert report['static_snapshot']['actions'][0]['gains'] == gains


def test_task_preserves_recovery_declaration_without_inserting_funding_wait(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    pack = _configure_opener(tmp_path, monkeypatch)
    pack['specializations']['252']['initialization']['recovery'] = dict(
        model='parallel_discrete', resource='rune', interval_ms=5000, slots=1)
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    native['static_snapshot']['resources']['rune'] = dict(current=1, maximum=1)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['recovery'] == dict(model='parallel_discrete', resource='rune', interval_ms=5000, slots=1)
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['outbreak', 'scourge_strike', 'death_coil']
    assert [row['estimated_ms'] for row in actions] == [0, 1000, 2000]
    assert actions[1]['estimated_resources_after']['rune'] is None


def test_task_rejects_invalid_edited_rule_pack_before_initialization(tmp_path, monkeypatch):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = tmp_path / 'rules.json'
    config.write_text('{broken', encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


@pytest.mark.parametrize('fault', ['action', 'fact', 'cycle', 'count', 'operation', 'type', 'unit', 'parameter', 'override', 'source_step'])
def test_task_rejects_invalid_rule_references_before_running(tmp_path, monkeypatch, fault):
    pack = _configure_opener(tmp_path, monkeypatch)
    spec = pack['specializations']['252']
    spec['facts'] = {'duration': dict(type='number', unit='ms', **{'from': 'static.parameter'}, key='rune_recharge_ms'),
                     'slots': dict(type='integer', unit='count', **{'from': 'static.parameter'}, key='rune_recharge_slots')}
    template = dict(intent='parameter boundary', scope='fixture', modifications='none', unknown='record_not_applied',
                    parameters={'enabled': 'predicate'}, binding=dict(action='outbreak', condition={'param': 'enabled'}))
    pack['general']['templates']['shared'] = template
    row = dict(id='one', rules=['shared'], arguments={'enabled': True}, scope=True)
    spec['bindings'] = [row]
    opener = spec['initialization']['openers'][0]
    if fault == 'type': row['condition'] = {'add': [True, 1]}
    elif fault == 'unit': row['condition'] = {'lt': [{'fact': 'duration'}, {'fact': 'slots'}]}
    elif fault == 'parameter': row.pop('arguments')
    elif fault == 'override': row['overrides'] = [dict(path='condition', value=True, source='fixture')]
    elif fault == 'source_step': opener['steps'][0]['source_step'] = -1
    elif fault == 'action': opener['steps'][0]['action'] = 'missing_action'
    elif fault == 'fact': row['condition'] = {'fact': 'undeclared_fact'}
    elif fault == 'cycle': row['after'] = ['one']
    elif fault == 'count': opener['steps'] *= 44
    else: row['condition'] = {'python': 'lambda: True'}
    _configure_opener(tmp_path, monkeypatch, pack)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_task_maps_configured_native_facts_to_existing_button(tmp_path, monkeypatch):
    from test_engine import apl_pool_reference
    pack = _configure_opener(tmp_path, monkeypatch)
    pack['specializations']['252']['actions']['scourge_strike']['native_action'] = 'native_builder'
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
def test_task_rejects_missing_or_negative_explicitly_required_fact(tmp_path, monkeypatch, value):
    from test_engine import apl_pool_reference
    pack = _configure_opener(tmp_path, monkeypatch)
    spec = pack['specializations']['252']
    spec['facts']['stacks'] = dict(type='integer', minimum=0, **{'from': 'static.parameter'}, key='lesser_ghoul_ready_stacks')
    spec['initialization']['required_facts'] = ['stacks']
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['lesser_ghoul_ready_stacks'] = value
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='静态字段|事实'):
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
    draft.write_text(before.decode().replace('"schema_version": 1,', '"schema_version": 2, "schema_version": 1,', 1), encoding='utf-8')
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
        pack['specializations']['252']['templates']['O']['intent'] = f'writer {index}'
        draft = tmp_path / f'draft-{index}.json'
        draft.write_text(json.dumps(pack), encoding='utf-8')
        paths.append(draft)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda path: main(['rules-save', str(path), '--expected-digest', identity]), paths))
    assert sorted(outcomes) == [0, 2]
    assert '冲突' in capsys.readouterr().err
    assert main(['rules-check', str(target)]) == 0


@pytest.mark.parametrize('fault', [
    'recovery_reference', 'recovery_operation', 'recovery_type', 'recovery_unit', 'recovery_phase',
    'opener_student_fact', 'scope_estimate', 'scope_finding', 'feature_phase', 'diagnose_type',
    'unused_diagnose_type', 'unused_edit_type', 'unused_feature_type'])
def test_rule_cli_rejects_invalid_execution_fields_without_overwriting_valid_pack(tmp_path, monkeypatch, capsys, fault):
    import copy, json
    from task import main
    pack = _configure_opener(tmp_path, monkeypatch)
    spec = pack['specializations']['252']
    spec['facts'] = {
        'duration': dict(type='number', unit='ms', **{'from': 'static.parameter'}, key='rune_recharge_ms'),
        'slots': dict(type='integer', unit='count', **{'from': 'static.parameter'}, key='rune_recharge_slots'),
        'estimate': dict(type='number', unit='count', **{'from': 'estimate.resource.current'}, resource='rune'),
        'window': dict(type='boolean', **{'from': 'student.apl_fact'}, phase='02', key='window.up')}
    template = dict(intent='stage boundary', scope='fixture', modifications='none', unknown='record_not_applied',
                    binding=dict(action='outbreak', condition=True), diagnose=dict(when=True),
                    edits=[dict(operation='move', when=True)], features=[dict(value=1)])
    pack['general']['templates'] = {'shared': template, 'unused': copy.deepcopy(template)}
    spec['bindings'] = [dict(id='one', rules=['shared'], scope=True)]
    spec['initialization']['recovery'] = dict(model='parallel_discrete', resource='rune',
        interval_ms={'fact': 'duration'}, slots={'fact': 'slots'})
    _configure_opener(tmp_path, monkeypatch, pack)
    target = tmp_path / 'rules.json'
    assert main(['rules-check', str(target)]) == 0
    identity = json.loads(capsys.readouterr().out)['rule_config_digest']
    before = target.read_bytes()
    recovery = spec['initialization']['recovery']
    if fault.startswith('recovery_'):
        recovery['interval_ms'] = {
            'recovery_reference': {'fact': 'missing_recharge'},
            'recovery_operation': {'unregistered_operation': [1, 2]}, 'recovery_type': True,
            'recovery_unit': {'fact': 'slots'}, 'recovery_phase': {'fact': 'interval.attempt_count'}}[fault]
    elif fault == 'opener_student_fact': spec['initialization']['openers'][0]['scope'] = {'fact': 'window'}
    elif fault == 'scope_estimate': spec['bindings'][0]['scope'] = {'gt': [{'fact': 'estimate'}, 0]}
    elif fault == 'scope_finding': spec['initialization']['openers'][0]['scope'] = {'eq': [{'fact': 'finding.source_position'}, 0]}
    elif fault == 'feature_phase': template['features'][0]['value'] = {'fact': 'plan.current_action_attempts'}
    elif fault == 'diagnose_type': template['diagnose']['when'] = 3
    elif fault == 'unused_diagnose_type': pack['general']['templates']['unused']['diagnose']['when'] = 3
    elif fault == 'unused_edit_type': pack['general']['templates']['unused']['edits'][0]['when'] = 3
    elif fault == 'unused_feature_type': pack['general']['templates']['unused']['features'][0]['value'] = 'not_numeric'
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
    pack = dict(schema_version=1, general=dict(templates={}), specializations={
        '252': dict(actions={'work': dict(button='scourge_strike', native_action='scourge_strike')},
            facts={}, bindings=[], initialization=dict(
                resource='runic_power', recovery=dict(model='none'),
                openers=[dict(id='sample', scope=True, source='fixture: public synthetic guide',
                    steps=[dict(action='work', source_step=i) for i in (1, 2, 3)])]))})
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
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike')},
            facts={},bindings=[],initialization=dict(resource='runic_power',recovery=dict(model='none'),
                openers=[dict(id='bounded',scope=True,source='fixture: native resource boundary',
                    steps=[dict(action='tap',source_step=1)])]))})
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    native=apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']=dict(current=100,maximum=50)
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native),pytest.raises(TaskError,match='当前资源.*上限'):
        run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))


@pytest.mark.parametrize('precombat_gcd', [1253, None])
def test_task_accounts_native_effective_precombat_occupancy_before_freezing_t0(tmp_path, monkeypatch, precombat_gcd):
    import json,burst,result_store
    from test_burst import reviewed_fixture,character_seed_boundary
    from test_engine import apl_pool_reference
    definition,raw=reviewed_fixture();result_store.DATA_ROOT.mkdir();burst.publish(definition)
    native=apl_pool_reference();template=native['apl_actions'][0]
    native['precombat_definitions']=[dict(template,name='raise_dead',signature='raise_dead',data_id=46584,
        base_spell_id=46584,precombat=True,harmful=False,gcd_ms=1500)]
    native['precombat_sequence']=[dict(name='raise_dead')]
    if precombat_gcd is not None:
        native['static_snapshot']['parameters']['precombat_gcd_ms']=precombat_gcd
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike'),
                          'big':dict(button='army_of_the_dead',native_action='army_of_the_dead')},
            facts={},bindings=[],initialization=dict(resource='runic_power',recovery=dict(model='none'),
                openers=[dict(id='occupied',scope=True,source='fixture: effective native precombat GCD',first_burst_step=4,
                    steps=[*[dict(action='tap',source_step=i) for i in (1,2,3)],
                           dict(action='big',source_step=4,mapping='burst')])]))})
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
    source=tmp_path/'role.simc';source.write_text(raw,encoding='utf-8')
    with character_seed_boundary(native_reference=native):
        if precombat_gcd is None:
            with pytest.raises(TaskError,match='战前.*GCD.*未知'):
                run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=200,
                    candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
            return
        result=run_task(source,tmp_path/'task',use_burst=True,search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    assert [row['estimated_ms'] for row in report['positions'] if row['kind']=='action']==[1400,2400,3400]
    assert report['precombat_occupancy']==dict(gcd_ms=1253,first_loop_ms=1400,precision='native_static_estimate')
    assert result['burst']['plan']['start_ms']==4400


def test_task_preserves_shared_guide_conditions_when_dynamic_scope_is_unknown(tmp_path, monkeypatch):
    import json
    pack = dict(schema_version=1, general=dict(templates={}), specializations={
        '252': dict(actions={'tap': dict(button='scourge_strike', native_action='scourge_strike')},
            facts={'window': dict(type='boolean', **{'from': 'student.apl_fact'}, key='window.up', phase='02')},
            templates={'shared': dict(intent='指南条目', scope='来源分支', modifications='移动尝试',
                unknown='record_not_applied', binding=dict(action='tap', condition={'fact': 'window'},
                    source='fixture: shared guide condition'))},
            bindings=[dict(id='one', rules=['shared'], scope={'fact': 'window'}, priority=9),
                      dict(id='two', rules=['shared'], scope=True, priority=3)],
            initialization=dict(resource='runic_power', recovery=dict(model='none'),
                openers=[dict(id='sample', scope=True, source='fixture: public synthetic guide',
                    steps=[dict(action='tap', source_step=1)])]))})
    config = tmp_path / 'rules.json'
    config.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2,
            validation_batches=1))
    rows = result['rule_initialization']['bindings']
    assert [(row['id'], row['priority'], row['scope_status']) for row in rows] == [('one', 9, None), ('two', 3, True)]
    assert all(row['condition'] == {'fact': 'window'} for row in rows)
    assert result['rule_initialization']['rules'][0]['intent'] == '指南条目'


def test_rule_cli_accepts_complete_guide_candidate_and_rejects_broken_opener_reference(tmp_path, capsys):
    import json
    from pathlib import Path
    from task import main
    candidate = Path(__file__).resolve().parents[2] / 'projects/sim2gse/rules.json'
    assert main(['rules-check', str(candidate)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'valid'
    pack = json.loads(candidate.read_text(encoding='utf-8'))
    spec = pack['specializations']['252']
    assert len(spec['templates']) == 22
    assert len(spec['bindings']) == 79
    assert spec['templates']['O']['binding']['action'] == 'putrefy'
    assert spec['templates']['O']['binding']['source_action'] == 'outbreak'
    assert [len(row['steps']) for row in spec['initialization']['openers']] == [12, 12, 14, 14]
    assert all(row['steps'][0]['action'] == 'putrefy'
        and row['steps'][0].get('mapping', 'loop') == 'loop'
        and row['steps'][0]['source_action'] == 'outbreak'
        and 'commands' not in row['steps'][0] for row in spec['initialization']['openers'])
    spec['initialization']['openers'][0]['steps'][0]['action'] = 'missing'
    broken = tmp_path / 'broken.json'
    broken.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-check', str(broken)]) == 2
    assert '起手' in capsys.readouterr().err


@pytest.mark.parametrize('hero,scene,steps', [(True,'single_target',1),(True,'aoe',2),
                                            (False,'single_target',3),(False,'aoe',4),(None,'single_target',None)])
def test_task_selects_opener_by_explicit_scene_and_native_hero_facts(tmp_path, monkeypatch, hero, scene, steps):
    import json
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    if hero is not None:
        native['static_snapshot']['hero_subtree_ids'] = [701] if hero else [702]
    facts = {'hero': dict(type='boolean', **{'from':'static.hero_subtree'}, id=701),
             'scene': dict(type='string', **{'from':'scenario.scene'})}
    openers=[]
    for (is_a, label, count) in ((True,'single_target',1),(True,'aoe',2),
                                (False,'single_target',3),(False,'aoe',4)):
        openers.append(dict(id=f'{is_a}.{label}', source='fixture: four branches',
            scope={'and':[{'eq':[{'fact':'hero'},is_a]}, {'eq':[{'fact':'scene'},label]}]},
            steps=[dict(action='tap',source_step=i) for i in range(1,count+1)]))
    pack = dict(schema_version=1, general=dict(templates={}), specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike')},
            facts=facts, bindings=[], initialization=dict(resource='runic_power',recovery=dict(model='none'),
                required_facts=['hero','scene'],openers=openers))})
    config=tmp_path/'rules.json'
    config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc'
    source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):
        if hero is None:
            with pytest.raises(TaskError,match='缺少静态字段: hero'):
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
    native['static_snapshot']['actions']=[dict(name=name,gcd_ms=1000,cast_ms=0,channeled=False,
        costs={},gains={},gain_status='known_zero',gain_timing='none') for name in spell_ids]
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):
        result=run_task(source,tmp_path/'task',simulation_config=dict(scene=scene,target_count=1 if scene=='single_target' else 5),
            search_config=dict(input_interval_ms=200,candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    assert len(report['source_steps'])==steps
    assert '开场两命令实际GCD/开战边界和原生逐命令guard待核验' not in report['unknown']
    assert '战前快照不能证明FK窗口费用；动态诊断留待02' in report['unknown']
    assert report['source_steps'][0]['source_action']=='outbreak'
    assert next(row for row in report['positions'] if row['kind']=='action')['action']=='putrefy'
    expected='death_coil' if scene=='single_target' else 'epidemic'
    assert [row['action'] for row in report['source_steps'] if row['source_step'] in (9,10)]==[expected,expected]
    payload=next(iter(decode_import(report['export_text'])['sequences'].values()))
    actions=payload['Versions'][0]['Actions']
    assert actions[0]['macro']=='/cast [nocombat] 46584'
    assert 'outbreak' not in [name for row in report['click_mapping'] for name in row.get('commands', [])]


@pytest.mark.parametrize('known_cost', [True, False])
def test_task_uses_configured_replacement_form_cost_and_same_button_mapping(tmp_path, monkeypatch, known_cost):
    import json
    from test_engine import apl_pool_reference
    native=apl_pool_reference()
    template=next(row for row in native['apl_actions'] if row['name']=='epidemic')
    native['apl_actions'].append(dict(template,name='graveyard',signature='graveyard',data_id=1242914))
    native['executed_actions'].extend([template, native['apl_actions'][-1]])
    native['static_snapshot']['resources']['runic_power']['current']=100
    if known_cost:
        native['static_snapshot']['actions'].append(dict(name='graveyard',gcd_ms=1000,cooldown_ms=0,
            cast_ms=0,channeled=False,costs={'runic_power':18},gains={},gain_status='known_zero',gain_timing='none'))
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'area':dict(button='epidemic',native_action='epidemic',variants=['graveyard'])},
            facts={},bindings=[],initialization=dict(resource='runic_power',recovery=dict(model='none'),
                openers=[dict(id='area',scope=True,source='fixture: explicit target form cost',
                    steps=[dict(action='area',native_form='graveyard',source_step=9),
                           dict(action='area',native_form='graveyard',source_step=10)])]))})
    config=tmp_path/'rules.json';config.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(config))
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    with _apl_task_boundary(native):
        result=run_task(source,tmp_path/'task',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    report=result['rule_initialization']
    attempts=[row for row in report['positions'] if row['kind']=='action']
    assert [row['action'] for row in attempts]==['epidemic','epidemic']
    assert [row['costs'] for row in attempts]==([{'runic_power':18}]*2 if known_cost else [None,None])
    assert [row['estimated_resources_after']['runic_power'] for row in attempts]==([82,64] if known_cost else [None,None])
    if not known_cost:
        assert all(row['effective_gcd_ms'] is None and row['estimated_gcd_ms']==1000
                   and row['gcd_basis']=='base_button_static_approximation' for row in attempts)
        assert any('graveyard' in item for item in report['unknown'])
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
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike'),
                          'big':dict(button=mapped_action,native_action=mapped_action),
                          'pet':dict(button='dark_transformation',native_action='dark_transformation')},
            facts={},bindings=[],initialization=dict(resource='runic_power',recovery=dict(model='none'),
                openers=[dict(id='aligned',scope=True,source='fixture: ordered burst boundary',first_burst_step=3,
                    steps=[dict(action='tap',source_step=1),dict(action='tap',source_step=2),
                           dict(action='big',source_step=3,mapping='burst'),
                           dict(action='pet',source_step=4,mapping='burst'),dict(action='tap',source_step=5)])]))})
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
    pack=dict(schema_version=1,general=dict(templates={
        'common':dict(intent='通用定义初版',scope='fixture',modifications='可编辑元数据',
                      unknown='record_not_applied')}),specializations={
        '252':dict(actions={'a':dict(button='scourge_strike',native_action='scourge_strike'),
                          'b':dict(button='death_coil',native_action='death_coil')},facts={},
            templates={'shared':dict(intent='共享定义初版',scope='fixture',modifications='保留来源',
                unknown='record_not_applied',binding=dict(action='a',condition=True,source='fixture: original'))},
            bindings=[dict(id='bound',rules=['common','shared'],scope=True,priority=1)],
            initialization=dict(resource='runic_power',recovery=dict(model='none'),openers=[
                dict(id='one',scope=True,source='fixture: editable guide',steps=[
                    dict(action='a',source_step=1),dict(action='b',source_step=2)])]))})
    target=tmp_path/'rules.json';target.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(target))
    source=tmp_path/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
    native=apl_pool_reference();native['static_snapshot']['resources']['runic_power']['current']=100
    with _apl_task_boundary(native):
        old=run_task(source,tmp_path/'old',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
    digest=old['rule_initialization']['rule_config_digest']
    edited=copy.deepcopy(pack)
    edited['general']['templates']['common']['intent']='通用定义修订'
    edited['specializations']['252']['templates']['shared']['intent']='共享定义修订'
    edited['specializations']['252']['templates']['shared']['binding']['source']='fixture: edited'
    edited['specializations']['252']['initialization']['openers'][0]['steps']=[
        dict(action='b',source_step=2),dict(action='a',source_step=1),dict(action='b',source_step=2)]
    draft=tmp_path/'draft.json';draft.write_text(json.dumps(edited),encoding='utf-8')
    assert main(['rules-save',str(draft),'--expected-digest',digest])==0
    new_digest=json.loads(capsys.readouterr().out)['rule_config_digest']
    with _apl_task_boundary(native):
        new=run_task(source,tmp_path/'new',search_config=dict(input_interval_ms=200,
            candidate_limit=1,batch_targets=(2,),iterations=2,validation_batches=1))
        with pytest.raises(TaskError,match='规则.*变化.*新任务'):
            resume_task(tmp_path/'old')
    assert [row['action'] for row in new['rule_initialization']['positions'] if row['kind']=='action']==[
        'death_coil','scourge_strike','death_coil']
    assert new_digest!=digest
    saved_old = read_task(tmp_path/'old')['rule_initialization']
    assert saved_old == old['rule_initialization']
    assert saved_old['rule_snapshot']['pack'] == pack
    assert new['rule_initialization']['rule_snapshot']['pack'] == edited
    assert read_task(tmp_path/'new')['rule_initialization'] == new['rule_initialization']
    assert {row['id']: row['intent'] for row in saved_old['rules']} == {
        'common': '通用定义初版', 'shared': '共享定义初版'}
    assert {row['id']: row['intent'] for row in new['rule_initialization']['rules']} == {
        'common': '通用定义修订', 'shared': '共享定义修订'}
    assert saved_old['bindings'][0]['source'] == 'fixture: original'
    assert new['rule_initialization']['bindings'][0]['source'] == 'fixture: edited'
    before=target.read_bytes()
    assert main(['rules-save',str(draft),'--expected-digest',digest])==2
    assert '冲突' in capsys.readouterr().err
    draft.write_text('{invalid', encoding='utf-8')
    assert main(['rules-save',str(draft),'--expected-digest',new_digest])==2
    assert '规则配置' in capsys.readouterr().err
    assert target.read_bytes()==before
    draft.write_text('{"schema_version": 1, "schema_version": 1}',encoding='utf-8')
    assert main(['rules-save',str(draft),'--expected-digest',new_digest])==2
    assert '重复' in capsys.readouterr().err
    assert target.read_bytes()==before


def test_rule_cli_rejects_invalid_unreferenced_shared_definition(tmp_path, capsys):
    import json
    from pathlib import Path
    from task import main
    pack=json.loads((Path(__file__).resolve().parents[2]/'projects/sim2gse/rules.json').read_text(encoding='utf-8'))
    pack['specializations']['252']['templates']['unreferenced']=dict(intent='unused',scope='guide',
        modifications='none',unknown='record_not_applied',binding=dict(action='missing',condition=True))
    path=tmp_path/'invalid.json';path.write_text(json.dumps(pack),encoding='utf-8')
    assert main(['rules-check',str(path)])==2
    assert '动作引用' in capsys.readouterr().err


def test_task_ignores_duplicate_native_list_metadata_but_rejects_conflicting_arithmetic(tmp_path, monkeypatch):
    import json
    from test_engine import apl_pool_reference
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'a':dict(button='scourge_strike',native_action='scourge_strike')},facts={},bindings=[],
            initialization=dict(resource='runic_power',recovery=dict(model='none'),openers=[
                dict(id='one',scope=True,source='fixture: duplicate native declarations',steps=[dict(action='a',source_step=1)])]))})
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
    native=dict(base,identity={'spec_id':71,'class_id':1})
    native['executed_actions']=native['apl_actions']=[dict(template,name=name,signature=name,
        data_id=spell,base_spell_id=spell) for name,spell in [('spark',1001),('drain',1002)]]
    native['action_sequence']=[dict(name='spark'),dict(name='drain')]
    native['static_snapshot']=dict(protocol=1,stage='precombat_initialized_before_actions',
        hero_subtree_ids=[777],resources={'energy':dict(current=40,maximum=100)},parameters={},actions=[
            dict(name=name,gcd_ms=1000,cooldown_ms=0,cast_ms=0,channeled=False,costs=cost,gains=gain,
                 gain_status='known' if gain else 'known_zero',gain_timing='on_cast' if gain else 'none')
            for name,cost,gain in [('spark',{},dict(energy=12)),('drain',dict(energy=24),{})]])
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '71':dict(actions={'renamed_x':dict(button='spark',native_action='spark'),
                          'renamed_y':dict(button='drain',native_action='drain')},
            facts={'branch':dict(type='boolean',**{'from':'static.hero_subtree'},id=777)},bindings=[],
            initialization=dict(resource='energy',recovery=dict(model='none'),required_facts=['branch'],openers=[
                dict(id='independent',scope={'fact':'branch'},source='fixture: second independent specialization',steps=[
                    dict(action='renamed_y',source_step=1),dict(action='renamed_x',source_step=2),
                    dict(action='renamed_x',source_step=3)])]))})
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
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike'),
                           'big':dict(button='army_of_the_dead',native_action='army_of_the_dead')},
            facts={'scene':dict(type='string',**{'from':'scenario.scene'})},bindings=[],
            initialization=dict(resource='runic_power',recovery=dict(model='none'),required_facts=['scene'],
                openers=[dict(id=scene,scope={'eq':[{'fact':'scene'},scene]},source='fixture: frozen '+scene,
                    first_burst_step=count+1,
                    steps=[dict(action='tap',source_step=i) for i in range(1,count+1)]+
                          [dict(action='big',source_step=count+1,mapping='burst')])
                    for scene,count in [('single_target',1),('aoe',2)]]))})
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
                    changed['specializations']['252']['initialization']['openers'][1]['steps']=[dict(action='tap',source_step=99)]
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
        assert [row['opener_id'] for row in reports]==['single_target','aoe']
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
    pack=dict(schema_version=1,general=dict(templates={}),specializations={
        '252':dict(actions={'tap':dict(button='scourge_strike',native_action='scourge_strike')},
            facts={'scene':dict(type='string',**{'from':'scenario.scene'})},bindings=[],
            initialization=dict(resource='runic_power',recovery=dict(model='none'),required_facts=['scene'],
                openers=[dict(id='explicit_aoe',scope={'eq':[{'fact':'scene'},'aoe']},source='fixture: explicit API scene',
                    steps=[dict(action='tap',source_step=1)])]))})
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
        assert result['rule_initialization']['opener_id']=='explicit_aoe'
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
    spec = pack['specializations']['252']
    if location == 'general_policy':
        pack['general']['initialization'] = dict(edit_limit=32)
    elif location == 'funding':
        spec['initialization']['funding'] = dict(action='scourge_strike')
    elif location == 'general_template':
        pack['general']['templates']['retired'] = dict(intent='old', scope='old', modifications='old',
            unknown='record_not_applied', initialize=dict(when=True))
    elif location == 'shared_template':
        spec['templates']['O']['initialize'] = dict(when=True)
    elif location == 'shared_binding':
        spec['templates']['O']['binding']['initialize'] = dict(attempt='putrefy', count=1, required=True,
            coverage_id='retired', phases=['skeleton'], unknown='record_not_applied')
    elif location == 'binding':
        spec['bindings'][0]['initialize'] = dict(attempt='putrefy', count=1, required=True,
            coverage_id='retired', phases=['skeleton'], unknown='record_not_applied')
    elif location == 'extra_initializations':
        spec['bindings'][0]['extra_initializations'] = []
    elif location == 'overrides':
        spec['bindings'][0]['overrides'] = []
    else:
        spec['templates']['O']['binding']['condition'] = {'eq': [{'fact': 'plan.target_cost'}, 0]}
    draft = tmp_path / 'draft.json'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    checked = main(['rules-check', str(draft)])
    check_error = capsys.readouterr().err
    saved = main(['rules-save', str(draft), '--expected-digest', identity])
    save_error = capsys.readouterr().err
    assert (checked, saved, target.read_bytes() == before) == (2, 2, True)
    assert '规则配置' in check_error
    assert '规则配置' in save_error
