"""规则起点通过任务公开入口交付；构造引擎报告不冒充真实角色验收。"""
from task import TaskError, run_task
from test_character_export import sample_profile
from test_search import _apl_task_boundary
import pytest


def test_task_rejects_missing_static_character_snapshot(tmp_path):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native.pop('static_snapshot')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='静态'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_task_stops_skeleton_after_one_bound_spender_attempt(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['current'] = 100
    next(row for row in snapshot['actions'] if row['name'] == 'death_coil')['costs'] = {'runic_power': 35}
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    # 满资源仅先消费一次腾空间，之后4次生成的有效收益35才完成目标消费。
    skeleton = result['rule_initialization']['skeleton']
    assert skeleton['consumption'] == 70
    assert skeleton['funding']['completed'] == 1
    assert skeleton['funding']['credited'] == 35
    assert skeleton['funding']['preconsumption_attempts'] == 1
    assert skeleton['duration_ms'] == 6000


def test_task_exports_a_resource_skeleton_using_effective_gcd(tmp_path):
    from test_engine import apl_pool_reference
    from task import read_task
    native = apl_pool_reference()
    from test_engine import static_snapshot
    native['static_snapshot'] = static_snapshot()
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    initialization = result['rule_initialization']
    assert initialization == saved['rule_initialization']
    assert initialization['resource'] == 'runic_power'
    assert initialization['skeleton']['consumption'] == 30
    assert initialization['program'][1] == {'kind': 'WaitClicks', 'clicks': 4}
    assert len(initialization['rules']) == 8
    assert initialization['unknown']
    assert result['candidate']['text'].startswith('!GSE3!')
    assert initialization['positions'][0]['effective_gcd_ms'] == 1000


def test_native_integral_resource_slots_are_accepted_as_json_numbers(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['rune_recharge_slots'] = 3.0
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    assert result['rule_initialization']['skeleton']['consumption'] == 30


@pytest.mark.parametrize('fault,message', [
    ('missing_gcd', '静态字段'), ('single_empty', '单空点击'),
    ('too_long', '点击或场景边界'), ('unknown_duration', 'dread_plague_duration_ms')])
def test_task_reports_unrepresentable_or_unknown_rule_start(tmp_path, fault, message):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    if fault == 'missing_gcd':
        snapshot['actions'][0].pop('gcd_ms')
    elif fault == 'single_empty':
        snapshot['actions'][0]['gcd_ms'] = 400
    elif fault == 'too_long':
        snapshot['parameters']['dread_plague_duration_ms'] = 1000000
    else:
        snapshot['parameters'].pop('dread_plague_duration_ms')
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match=message):
        run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,), iterations=2,
            validation_batches=1))


def test_full_charge_rule_keeps_aoe_priority_and_long_cd_only_needs_one_demo(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
                                      data_id=10042, base_spell_id=10042))
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['current'] = 80
    # 保留近满+满充能竞争；初始资源已够10费用，先预消耗，再独立筹资一次。
    next(row for row in snapshot['actions'] if row['name'] == 'epidemic')['costs'] = {'runic_power': 10}
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=120000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power': 10}, gain_status='known', gain_timing='on_cast', charges=2, max_charges=2))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    initialization = result['rule_initialization']
    actions = [row for row in initialization['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == ['epidemic', 'outbreak', 'putrefy', 'epidemic']
    assert actions[2]['rule'] == 'window_or_full'
    assert [row['coverage_id'] for row in actions if row['action'] == 'epidemic'] == [
        'opening_space', 'funded_consumer']
    assert initialization['skeleton']['demonstrated'] == ['putrefy']
    assert initialization['skeleton']['duration_ms'] == 4000
    assert initialization['skeleton']['consumption'] == 20
    assert initialization['skeleton']['funding'] == dict(completed=1, credited=10.0, preconsumption_attempts=1)


@pytest.mark.parametrize('talent,available', [(True, True), (False, True), (True, False)])
def test_task_demonstrates_available_talented_cooldown_in_single_target(tmp_path, talent, available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    for row in native['apl_actions']:
        if row['name'] == 'death_and_decay':
            row['available'] = available
    snapshot = native['static_snapshot']
    snapshot['parameters']['cycle_of_death'] = talent
    snapshot['resources']['runic_power']['maximum'] = 40  # 覆盖CD10之外仍留生成30的空间
    snapshot['actions'].append(dict(name='death_and_decay', gcd_ms=1000, cooldown_ms=12000,
        cast_ms=0, channeled=False, costs={'rune': 1}, gains={'runic_power': 10},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    attempts = [row for row in report['positions'] if row.get('action') == 'death_and_decay']
    assert len(attempts) == int(talent and available)
    assert report['skeleton']['demonstrated'] == (['death_and_decay'] if talent and available else [])
    if attempts:
        assert attempts[0]['bindings'] == ['unholy.cooldowns.2']
        binding = next(row for row in report['bindings'] if row['id'] == 'unholy.cooldowns.2')
        assert 'active_enemies>=3' in binding['signature']
        assert binding['source'].endswith('#L373')
        assert binding['initialization_coverage']['basis'] == 'user_approved_single_target_demo'
        assert binding['initialization_coverage']['upstream_applicable'] is False


@pytest.mark.parametrize('targets,available', [(1, True), (5, True), (1, False), (5, False)])
def test_task_demonstrates_available_soul_reaper_without_claiming_dynamic_conditions(
        tmp_path, targets, available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='soul_reaper', signature='soul_reaper',
        data_id=343294, base_spell_id=343294, available=available))
    snapshot = native['static_snapshot']
    # 本例只验证CD覆盖；满资源+CD挤占来源额度另有明确失败回归。
    snapshot['resources']['runic_power']['current'] = 0
    snapshot['parameters']['dread_plague_duration_ms'] = 3000
    snapshot['actions'].append(dict(name='soul_reaper', gcd_ms=1200, cooldown_ms=60000,
        cast_ms=0, channeled=False, costs={'rune': 1}, gains={'runic_power': 10},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': targets},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    attempts = [row for row in report['positions'] if row.get('action') == 'soul_reaper']
    assert len(attempts) == int(available)
    assert report['skeleton']['demonstrated'] == (['soul_reaper'] if available else [])
    if available:
        attempt = attempts[0]
        assert attempt['effective_gcd_ms'] == 1200
        assert report['program'][attempt['position'] + 1] == {'kind': 'WaitClicks', 'clicks': 5}
        assert attempt['condition_status'] == 'dynamic_condition_unknown'
        binding = next(row for row in report['bindings'] if row['action'] == 'soul_reaper')
        assert attempt['bindings'] == [binding['id']]
        assert binding['signature'].endswith(
            'buff.dark_transformation.up&cooldown.dark_transformation.remains<38|target.health.pct<35')
        assert binding['initialization_coverage']['basis'] == 'user_approved_soul_reaper_demo'
        assert binding['initialization_coverage']['coverage'] == 'unknown'
        rule = next(row for row in report['rules'] if row['id'] == 'ordinary_cooldown')
        assert binding['id'] in rule['bindings']
        assert attempt['position'] in rule['applied_positions']


@pytest.mark.parametrize('blightburst,available', [(True, True), (False, True), (None, True), (True, False)])
def test_task_uses_confirmed_alternative_disease_maintenance(tmp_path, blightburst, available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
        data_id=10042, base_spell_id=10042, available=available))
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['maximum'] = 40  # 留出CD10+生成30；不再让CD收益替代来源目标
    snapshot['parameters']['dread_plague_duration_ms'] = 6000
    if blightburst is not None:
        snapshot['parameters']['blightburst'] = blightburst
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=12000,
        cast_ms=0, channeled=False, costs={'rune': 1}, gains={'runic_power': 10},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    actions = [row['action'] for row in report['positions'] if row['kind'] == 'action']
    if blightburst is True and available:
        assert report['program'] == [
            ['putrefy'], {'kind': 'WaitClicks', 'clicks': 4},
            ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
            ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
            ['death_coil'], {'kind': 'WaitClicks', 'clicks': 4},
            ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4}]
        # 二层可把消费前移；最终排列不被最初来源目标强行锁定。
        assert report['skeleton']['funding']['completed'] == 1
        assert report['duration_ms'] == 5000
        assert report['periodic_edits'] == []
        binding = next(row for row in report['bindings'] if row['id'] == 'unholy.cooldowns.1')
        assert 'time<5' in binding['signature']
        assert 'dot.dread_plague.active_dots=0' in binding['signature']
        assert binding['initialization_coverage']['provider'] == 'putrefy'
        assert binding['initialization_coverage']['coverage'] == 'unknown'
    else:
        assert 'outbreak' in actions
        assert report['duration_ms'] == 6000
    assert ('putrefy' in report['skeleton']['demonstrated']) is available


def test_periodic_spacing_survives_fixed_burst_pause_without_modifying_burst(tmp_path):
    import copy
    from engine import inspect
    from search import initial_programs
    from test_engine import apl_pool_reference
    from test_burst import reviewed_fixture
    native = apl_pool_reference()
    capabilities = inspect(native, tmp_path / 'catalogue')
    definition, _ = reviewed_fixture()
    before = copy.deepcopy(definition)
    report = {}
    starts = initial_programs(capabilities, native, input_interval_ms=200,
                              burst=definition, initialization=report)
    assert starts == initial_programs(capabilities, native, input_interval_ms=200, burst=definition)
    program = starts[0]
    ordinary_clicks = sum(node['clicks'] if isinstance(node, dict) else 1 for node in program)
    assert ordinary_clicks * 200 >= native['static_snapshot']['parameters']['dread_plague_duration_ms']
    assert all(not 3000 <= row['estimated_ms'] < 4000 for row in report['positions']
               if row['kind'] == 'action')
    assert definition == before


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


@pytest.mark.parametrize('spender,binding_id', [
    ('epidemic', 'unholy.aoe.8'), ('death_coil', 'unholy.aoe.9')])
def test_task_preserves_low_priority_aoe_spender_identity_and_unknown(tmp_path, spender, binding_id):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']['current'] = 20
    if spender == 'death_coil':
        native['apl_actions'] = [row for row in native['apl_actions'] if row['name'] != 'epidemic']
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    position = next(row for row in result['rule_initialization']['positions']
                    if row.get('action') == spender)
    assert position['resources_before']['runic_power'] == 30
    assert position['resources_before']['rune'] >= 2
    assert position['bindings'] == [binding_id]
    assert position['rule'] != 'near_cap'
    assert position['condition_status'] == 'dynamic_condition_unknown'


def test_task_does_not_claim_repeated_cooldown_is_full_charge(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
                                      data_id=10042, base_spell_id=10042))
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['current'] = 80
    # 此例观察充能证据；初始20空间可完成独立的20费用来源目标。
    next(row for row in snapshot['actions'] if row['name'] == 'epidemic')['costs'] = {'runic_power': 20}
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=3000,
        cast_ms=0, channeled=False, costs={}, gains={}, gain_status='known_zero', gain_timing='none', charges=2, max_charges=2))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    positions = [row for row in result['rule_initialization']['positions']
                 if row.get('action') == 'putrefy']
    assert positions  # Finite editing no longer invents another cooldown demonstration.
    assert positions[0]['condition_status'] == 'static_branch_estimate'
    assert all(row['condition_status'] == 'dynamic_condition_unknown' for row in positions[1:])
    assert all('充能' in row['condition_basis'] and '未知' in row['condition_basis']
               for row in positions[1:])


def buff_native_reference():
    """Minimal constructed external report; no captured character data."""
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='festering_strike', signature='festering_strike',
                                      data_id=85948, base_spell_id=85948))
    snapshot = native['static_snapshot']
    snapshot['parameters']['lesser_ghoul_ready_stacks'] = 0
    snapshot['actions'].append(dict(name='festering_strike', gcd_ms=1000, cooldown_ms=0,
        cast_ms=0, channeled=False, costs={'rune': 2}, gains={'runic_power': 20},
        gain_timing='on_hit', gain_status='known'))
    return native


@pytest.mark.parametrize('period_ms', [3000, 4000])
def test_task_removes_redundant_periodic_tail_without_repeating_resource_work(tmp_path, period_ms):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['resources'] = {'runic_power': {'current': 0, 'maximum': 30},
                             'rune': {'current': 1, 'maximum': 1}}
    snapshot['parameters'].update(rune_recharge_ms=5000, rune_recharge_slots=1,
                                  dread_plague_duration_ms=period_ms)
    next(row for row in snapshot['actions'] if row['name'] == 'outbreak')['gains']['runic_power'] = 20
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    # One 30-unit turnover: 20 from maintenance, 10 from filler. No second consumer.
    # The redundant maintenance at 5s would leave only 2s across the loop boundary.
    assert report['program'] == [
        ['outbreak'], {'kind': 'WaitClicks', 'clicks': 24},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['death_coil'], {'kind': 'WaitClicks', 'clicks': 4}]
    assert report['periodic_edits'] == [dict(action='outbreak', operation='remove_redundant_tail',
                                            restored_skeleton_actions=['scourge_strike'])]
    assert report['duration_ms'] == 7000
    assert report['duration_ms'] >= period_ms
    assert report['skeleton']['consumption'] == 30


@pytest.mark.parametrize('use_burst', [False, True])
def test_task_initialization_timestamps_include_compiled_precombat_click(tmp_path, use_burst):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['precombat_definitions'] = [dict(template, name='raise_dead', signature='raise_dead',
        data_id=46585, base_spell_id=46585, precombat=True, gcd_ms=0)]
    native['precombat_sequence'] = [dict(name='raise_dead')]
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
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    compiled_actions = [(index, row) for index, row in enumerate(report['click_mapping'])
                        if row['kind'] == 'Action']
    assert compiled_actions[0][1]['commands'] == ['raise_dead']
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert actions[0]['action'] == 'outbreak'
    assert actions[0]['estimated_ms'] == 300
    for row, (index, click) in zip(actions, compiled_actions[1:], strict=True):
        assert click['commands'] == [row['action']]
        expected_ms = index * 300
        if use_burst and expected_ms >= 3000:
            expected_ms += 1200  # The fixed [3000, 4000) window removes four 300ms inputs.
        assert row['estimated_ms'] == expected_ms
    if use_burst:
        assert report['protected_burst']['definition_id'] == definition['definition_id']
        assert all(not 3000 <= row['estimated_ms'] < 4000 for row in actions)


def test_task_keeps_festering_strike_as_one_buff_demo_not_resource_fill(tmp_path):
    native = buff_native_reference()
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    actions = [row for row in result['rule_initialization']['positions'] if row['kind'] == 'action']
    strikes = [row for row in actions if row['action'] == 'festering_strike']
    assert len(strikes) == 1
    assert strikes[0]['rule'] == 'buff_maintenance_demo'
    assert strikes[0]['bindings'] == ['unholy.single_target.11']
    assert all(row['action'] == 'scourge_strike' for row in actions if row['rule'] == 'resource_fill')
    assert any(row['action'] == 'scourge_strike' for row in actions)


@pytest.mark.parametrize('gain_status,gain_timing,gains', [
    ('known', 'on_hit', {'runic_power': 20}), ('unknown', 'unknown', {})])
def test_task_does_not_treat_conditional_or_unknown_gains_as_known_zero(
        tmp_path, gain_status, gain_timing, gains):
    native = buff_native_reference()
    native['static_snapshot']['parameters']['lesser_ghoul_ready_stacks'] = 0
    for row in native['static_snapshot']['actions']:
        if row['name'] == 'festering_strike':
            row.update(gain_status=gain_status, gain_timing=gain_timing, gains=gains)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=300, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    actions = [row for row in result['rule_initialization']['positions'] if row['kind'] == 'action']
    strike = next(row for row in actions if row['action'] == 'festering_strike')
    assert strike['gain_status'] == gain_status
    assert strike['gain_timing'] == gain_timing
    assert strike['static_gains'] == gains
    assert strike['resource_balance_status'] == 'unknown_unaccounted_gain'
    assert strike['estimated_resources_after']['runic_power'] == strike['resources_before']['runic_power']
    later = actions[actions.index(strike)+1:]
    assert later
    assert all(row['resource_balance_status'] == 'unknown_unaccounted_gain' for row in later)
    assert all(row['condition_status'] == 'dynamic_condition_unknown' for row in later
               if row['action'] in ('death_coil', 'epidemic'))


def test_task_replaces_known_resource_work_after_an_uncertain_gain(tmp_path):
    native = buff_native_reference()
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['maximum'] = 60
    snapshot['parameters']['dread_plague_duration_ms'] = 3000
    next(row for row in snapshot['actions'] if row['name'] == 'death_coil')['costs'] = {'runic_power': 60}
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    # Six 10-unit fillers and one 60-unit consumer form the 7s skeleton.
    # Each maintenance supplies the same known 10-unit contribution as one filler.
    # The earlier conditional 20-unit gain stays unaccounted throughout.
    assert report['skeleton']['duration_ms'] == 7000
    assert report['program'] == [
        ['outbreak'], {'kind': 'WaitClicks', 'clicks': 4},
        ['festering_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['outbreak'], {'kind': 'WaitClicks', 'clicks': 4},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['death_coil'], {'kind': 'WaitClicks', 'clicks': 4}]
    assert report['duration_ms'] == 8000
    assert report['periodic_edits'] == [dict(action='outbreak', operation='remove_redundant_tail',
                                            restored_skeleton_actions=['scourge_strike'])]
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert all(row['resource_balance_status'] == 'unknown_unaccounted_gain'
               for row in actions[1:])
    assert all(row['replaced_skeleton_actions'] == ['scourge_strike']
               for row in actions if row['action'] == 'outbreak')
    assert all(row['condition_status'] == 'dynamic_condition_unknown'
               for row in actions if row['action'] == 'death_coil')


@pytest.mark.parametrize('include_dt', [True, False])
def test_task_aligns_first_putrefy_only_with_an_actual_dt_burst_input(tmp_path, include_dt):
    import copy
    import burst, result_store
    from test_burst import reviewed_fixture, character_seed_boundary
    result_store.DATA_ROOT.mkdir()
    definition, raw = reviewed_fixture()
    if not include_dt:
        definition['blocks'][1] = [command for command in definition['blocks'][1]
                                   if command['simc_action'] != 'dark_transformation']
    definition = burst.publish(definition)
    protected = copy.deepcopy(definition)
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
                                      data_id=10042, base_spell_id=10042))
    native['static_snapshot']['actions'].append(dict(name='putrefy', gcd_ms=1000,
        cooldown_ms=120000, cast_ms=0, channeled=False, costs={'rune': 1},
        gains={'runic_power': 10}, gain_status='known', gain_timing='on_cast',
        charges=2, max_charges=2))
    source = tmp_path / 'role.simc'
    source.write_text(raw, encoding='utf-8')
    with character_seed_boundary(native_reference=native):
        result = run_task(source, tmp_path / 'task', use_burst=True, search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    first = next(row for row in report['positions'] if row.get('action') == 'putrefy')
    # 1000ms GCD at 200ms inputs spans five clicks; DT pause releases at 4000ms.
    assert first['estimated_ms'] == (4000 if include_dt else 1000)
    assert burst.load(252) == protected
    rule = next(row for row in report['rules'] if row['id'] == 'protected_burst')
    assert rule['application_status'] == ('approximate_applied' if include_dt else 'unknown_not_applied')
    assert ('protected_burst' in first['applied_rules']) is include_dt
    if include_dt:
        assert first['condition_status'] == 'dynamic_condition_unknown'
        assert '输入尝试' in first['condition_basis']


@pytest.mark.parametrize('period_ms,tail_wait,expected_duration', [(3000, 4, 3000), (6000, 19, 6000)])
def test_task_edits_finite_skeleton_and_only_extends_required_periodic_wait(
        tmp_path, period_ms, tail_wait, expected_duration):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['maximum'] = 30
    snapshot['parameters']['dread_plague_duration_ms'] = period_ms
    next(row for row in snapshot['actions'] if row['name'] == 'outbreak')['gains']['runic_power'] = 20
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    # Worked example: skeleton needs 3 x 10RP fillers and one 30RP spender (4s).
    # The maintenance attempt supplies 20RP, replacing two fillers. No second resource cycle.
    assert report['skeleton']['duration_ms'] == 4000
    assert report['program'] == [
        ['outbreak'], {'kind': 'WaitClicks', 'clicks': 4},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['death_coil'], {'kind': 'WaitClicks', 'clicks': tail_wait}]
    assert report['duration_ms'] == expected_duration
    if period_ms == 3000:
        assert report['duration_ms'] < report['skeleton']['duration_ms']
    else:
        assert report['duration_ms'] > report['skeleton']['duration_ms']
        assert report['positions'][-1]['basis'] == 'periodic_cross_cycle_spacing'


def test_task_does_not_report_resource_fill_as_applied_short_window_rule(tmp_path):
    from test_engine import apl_pool_reference
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(apl_pool_reference()):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert any(row.get('action') == 'scourge_strike' for row in report['positions'])
    rule = next(row for row in report['rules'] if row['id'] == 'short_window')
    assert rule['application_status'] == 'unknown_not_applied'
    assert rule['applied_positions'] == []
    assert not any(row.get('rule') == 'short_window' for row in report['positions'])


@pytest.mark.parametrize('targets,rule,binding_id,condition', [
    (1, 'reserve', 'unholy.single_target.9', 'runic_power.deficit<50'),
    (5, 'near_cap', 'unholy.aoe.7', 'rune<2')])
def test_task_retains_binding_specific_spending_decision_for_same_resource_state(
        tmp_path, targets, rule, binding_id, condition):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['apl_actions'] = [row for row in native['apl_actions'] if row['name'] != 'epidemic']
    snapshot = native['static_snapshot']
    snapshot['resources'] = {'runic_power': {'current': 20, 'maximum': 60},
                             'rune': {'current': 1, 'maximum': 1}}
    snapshot['parameters'].update(rune_recharge_ms=5000, rune_recharge_slots=1,
                                  dread_plague_duration_ms=6000)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': targets},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    decision = next(row for row in result['rule_initialization']['positions']
                    if row.get('action') == 'death_coil')
    assert decision['resources_before'] == {'runic_power': 30, 'rune': 0}
    assert decision['rule'] == rule
    assert decision['bindings'] == [binding_id]
    assert decision['condition_status'] == 'static_branch_estimate'
    assert condition in decision['condition_basis']


def test_task_exposes_selected_resource_recovery_model_and_its_actual_wait(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['resources'] = {'runic_power': {'current': 0, 'maximum': 30},
                             'rune': {'current': 1, 'maximum': 1}}
    snapshot['parameters'].update(rune_recharge_ms=5000, rune_recharge_slots=1,
                                  dread_plague_duration_ms=3000)
    next(row for row in snapshot['actions'] if row['name'] == 'outbreak')['gains']['runic_power'] = 20
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['recovery'] == dict(model='parallel_discrete', resource='rune',
                                     interval_ms=5000, slots=1)
    # One resource unit: maintenance at 0, refill available at 5s, spender at 6s.
    assert report['program'] == [
        ['outbreak'], {'kind': 'WaitClicks', 'clicks': 24},
        ['scourge_strike'], {'kind': 'WaitClicks', 'clicks': 4},
        ['death_coil'], {'kind': 'WaitClicks', 'clicks': 4}]
    assert [row['estimated_ms'] for row in report['positions'] if row['kind'] == 'action'] == [0, 5000, 6000]
    assert report['duration_ms'] == 7000


def test_task_rejects_invalid_edited_rule_pack_before_initialization(tmp_path, monkeypatch):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = tmp_path / 'rules.json'
    config.write_text('{broken', encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_task_freezes_edited_two_library_pack_and_reports_its_digest(tmp_path, monkeypatch):
    import json
    from rule_config import DEFAULT_PATH
    from task import read_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = tmp_path / 'rules.json'
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    pack['general']['templates']['near_cap']['intent'] = '测试改名：近满及时消费'
    config.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    report = result['rule_initialization']
    assert next(row for row in report['rules'] if row['id'] == 'near_cap')['intent'] == '测试改名：近满及时消费'
    assert report['rule_snapshot']['pack'] == pack
    assert len(report['rule_config_digest']) == 64
    assert saved['rule_initialization']['rule_snapshot'] == report['rule_snapshot']


@pytest.mark.parametrize('origin', ['binding', 'template', 'override', 'priority'])
def test_configured_cooldown_count_changes_public_initialization_without_code_changes(tmp_path, monkeypatch, origin):
    import json
    from rule_config import DEFAULT_PATH
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='soul_reaper', signature='soul_reaper',
        data_id=343294, base_spell_id=343294, available=True))
    native['static_snapshot']['actions'].append(dict(name='soul_reaper', gcd_ms=1000,
        cooldown_ms=15000, cast_ms=0, channeled=False, costs={'rune': 1},
        gains={'runic_power': 10}, gain_status='known', gain_timing='on_cast',
        charges=1, max_charges=1))
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    row = next(row for row in pack['specializations']['252']['bindings']
               if row['id'] == 'unholy.single_target.2')
    if origin == 'priority':
        row['initialize']['priority'] = -20
    elif origin == 'binding':
        row['initialize'] = dict(row.get('initialize', {}), count=2)
    elif origin == 'template':
        row['initialize'].pop('count', None)
        pack['general']['templates']['ordinary_cooldown']['initialize']['count'] = 2
    else:
        row.setdefault('overrides', []).append(dict(path='initialize.count', value=2,
                                 source='fixture: approved count edit'))
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
    attempts = [row for row in result['rule_initialization']['positions']
                if row.get('action') == 'soul_reaper']
    if origin == 'priority':
        assert len(attempts) == 1
        assert result['rule_initialization']['positions'][0]['action'] == 'soul_reaper'
    else:
        assert len(attempts) == 2
        assert attempts[1]['estimated_ms'] - attempts[0]['estimated_ms'] >= 15000


@pytest.mark.parametrize('fault', ['action', 'fact', 'cycle', 'count', 'operation', 'type', 'unit', 'parameter', 'override', 'edit_limit'])
def test_task_rejects_invalid_rule_references_before_running(tmp_path, monkeypatch, fault):
    import json
    from rule_config import DEFAULT_PATH
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    row = next(row for row in pack['specializations']['252']['bindings'] if row.get('initialize'))
    if fault == 'type':
        row['initialize']['when'] = {'add': [True, 1]}
    elif fault == 'unit':
        row['initialize']['when'] = {'lt': [{'fact': 'rune_recharge_ms'}, {'fact': 'lesser_ghoul_ready_stacks'}]}
    elif fault == 'parameter':
        row.pop('arguments', None)
    elif fault == 'override':
        row['overrides'] = [dict(path='condition', value=True, source='fixture')]
    elif fault == 'edit_limit':
        pack['general']['initialization']['edit_limit'] = -1
    elif fault == 'action':
        row['initialize']['attempt'] = 'missing_action'
    elif fault == 'fact':
        row['initialize']['when'] = {'fact': 'undeclared_fact'}
    elif fault == 'cycle':
        row['after'] = [row['id']]
    elif fault == 'count':
        row['initialize']['count'] = -1
    else:
        row['initialize']['when'] = {'python': 'lambda: True'}
    config = tmp_path / 'rules.json'
    config.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(), pytest.raises(TaskError, match='规则配置'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_incidental_cooldown_resource_cannot_complete_generator_funded_skeleton(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['blightburst'] = True
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
        data_id=10042, base_spell_id=10042, available=True))
    native['static_snapshot']['actions'].append(dict(name='putrefy', gcd_ms=1000,
        cooldown_ms=15000, cast_ms=0, channeled=False, costs={}, gains={'runic_power':30},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count':5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['skeleton']['funding']['credited'] == 30
    assert report['skeleton']['funding']['completed'] == 1
    assert report['skeleton']['funding']['preconsumption_attempts'] == 1
    assert [row['action'] for row in report['skeleton']['attempts']] == [
        'putrefy', 'epidemic', 'scourge_strike', 'scourge_strike', 'scourge_strike', 'epidemic']
    assert report['skeleton']['consumption'] == 60


def test_task_refuses_resume_after_rule_file_edit_even_for_completed_result(tmp_path, monkeypatch):
    import json
    from rule_config import DEFAULT_PATH
    from task import resume_task
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        pack['general']['templates']['near_cap']['intent'] += ' edited'
        path.write_text(json.dumps(pack), encoding='utf-8')
        with pytest.raises(TaskError, match='规则.*变化.*新任务'):
            resume_task(tmp_path / 'task')


def test_full_resource_with_incidental_gain_reports_one_clear_is_insufficient(tmp_path):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']['current'] = 100
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='soul_reaper', signature='soul_reaper',
        data_id=343294, base_spell_id=343294, available=True))
    native['static_snapshot']['actions'].append(dict(name='soul_reaper', gcd_ms=1000,
        cooldown_ms=15000, cast_ms=0, channeled=False, costs={'rune':1}, gains={'runic_power':10},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='来源额度.*不可达'):
        run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))


def test_public_task_runs_second_synthetic_spec_without_business_names(tmp_path, monkeypatch):
    import json
    from test_engine import apl_pool_reference
    template = apl_pool_reference()['apl_actions'][0]
    native = dict(apl_pool_reference(), identity={'spec_id':71,'class_id':1})
    native['executed_actions'] = native['apl_actions'] = [
        dict(template, name=name, signature=name, data_id=spell, base_spell_id=spell)
        for name, spell in [('spark',1001),('drain',1002)]]
    native['action_sequence'] = [{'name':'spark'},{'name':'drain'}]
    native['static_snapshot'] = dict(protocol=1, stage='precombat_initialized_before_actions',
        resources={'energy':{'current':0,'maximum':100}}, parameters={}, actions=[
        dict(name=name, gcd_ms=1000, cooldown_ms=0, cast_ms=0, channeled=False, costs=cost,
             gains=gain, gain_status='known' if gain else 'known_zero', gain_timing='on_cast' if gain else 'none')
        for name,cost,gain in [('spark',{}, {'energy':12}),('drain',{'energy':24},{})]])
    entry = lambda action, required, count, priority: dict(
        coverage_id='completion' if required else 'optional', required=required, count=count,
        coverage_when=True, when=True, attempt=action, priority=priority, phases=['skeleton','fill'],
        insert=False, reason='custom', rules=['custom_rule'], unknown='record_not_applied',basis='synthetic')
    pack = dict(schema_version=1, general=dict(templates={'custom_rule':dict(intent='测试',scope='测试',
        modifications='测试',unknown='record_not_applied')}, initialization=dict(
        stop={'eq':[{'fact':'plan.required_attempts_remaining'},0]},
        edit_stop={'eq':[{'fact':'plan.pending_attempts_remaining'},0]}, edit_limit=128)),
        specializations={'71':dict(source_revision='synthetic',
            actions={'gain':{'native_action':'spark','button':'spark'}, 'spend':{'native_action':'drain','button':'drain'}},
            facts={}, initialization=dict(resource='energy', recovery={'model':'none'},
                funding=dict(enabled=True, resource='energy',actions=['gain'],coverage_id='completion',
                    gain_policy='known_on_cast_effective_after_cap',
                    preconsumption_coverage='room', completion={'gte':[{'fact':'plan.qualified_credit'},{'fact':'plan.target_cost'}]}),
                approximate=[],unknown=[]),
            bindings=[dict(id='renamed_gain', action='gain', rules=['custom_rule'], scope=True, condition=True, initialize=entry('gain',False,8,20)),
                      dict(id='renamed_spend', action='spend', rules=['custom_rule'], scope=True, condition=True, initialize=entry('spend',True,1,10))])})
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile().replace('deathknight=', 'warrior=').replace('spec=unholy','spec=arms'), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,),iterations=2,validation_batches=1))
    report = result['rule_initialization']
    assert report['resource'] == 'energy'
    assert [row['action'] for row in report['positions'] if row['kind']=='action'] == ['spark','spark','drain']
    assert report['skeleton']['funding']['credited'] == 24


def test_task_maps_configured_native_facts_to_existing_button(tmp_path, monkeypatch):
    import json
    from rule_config import DEFAULT_PATH
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    next(row for row in native['static_snapshot']['actions'] if row['name'] == 'scourge_strike')['name'] = 'native_builder'
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    pack['specializations']['252']['actions']['scourge_strike']['native_action'] = 'native_builder'
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    assert any(row.get('action') == 'scourge_strike' for row in result['rule_initialization']['positions'])
    assert 'native_builder' not in result['candidate']['text']


@pytest.mark.parametrize('value', [None, -1])
def test_task_rejects_missing_or_negative_initial_maintenance_stacks(tmp_path, value):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['lesser_ghoul_ready_stacks'] = value
    native['apl_actions'].append(dict(native['apl_actions'][0], name='festering_strike',
        signature='festering_strike', data_id=85948, base_spell_id=85948))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), pytest.raises(TaskError, match='层数|unknown|事实'):
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))


def test_configured_zero_edit_limit_preserves_first_layer_without_maintenance(tmp_path, monkeypatch):
    import json
    from rule_config import DEFAULT_PATH
    pack = json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    pack['general']['initialization']['edit_limit'] = 0
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']['maximum'] = 30
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert [row['action'] for row in report['positions'] if row['kind'] == 'action'] == [
        'scourge_strike', 'scourge_strike', 'scourge_strike', 'death_coil']
    assert report['duration_ms'] == report['skeleton']['duration_ms']
    assert report['periodic_edits'] == []


def test_rule_cli_validates_saves_atomically_and_new_task_loads_saved_pack(tmp_path, monkeypatch, capsys):
    import json
    from rule_config import DEFAULT_PATH
    from task import main
    current = tmp_path / 'rules.json'
    current.write_bytes(DEFAULT_PATH.read_bytes())
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(current))
    assert main(['rules-check', str(current)]) == 0
    original = json.loads(capsys.readouterr().out)
    before = current.read_bytes()
    draft = tmp_path / 'draft.json'
    draft.write_text('{invalid', encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', original['rule_config_digest']]) == 2
    assert '规则配置' in capsys.readouterr().err
    assert current.read_bytes() == before
    pack = json.loads(before)
    pack['general']['templates']['near_cap']['intent'] = '保存后生效'
    draft.write_text(json.dumps(pack), encoding='utf-8')
    assert main(['rules-save', str(draft), '--expected-digest', 'stale']) == 2
    assert '冲突' in capsys.readouterr().err
    assert current.read_bytes() == before
    assert main(['rules-save', str(draft), '--expected-digest', original['rule_config_digest']]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved['rule_config_digest'] != original['rule_config_digest']
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    assert result['rule_initialization']['rule_config_digest'] == saved['rule_config_digest']
    assert next(row for row in result['rule_initialization']['rules'] if row['id'] == 'near_cap')['intent'] == '保存后生效'


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
        pack['general']['templates']['near_cap']['intent'] = f'writer {index}'
        draft = tmp_path / f'draft-{index}.json'
        draft.write_text(json.dumps(pack), encoding='utf-8')
        paths.append(draft)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda path: main(['rules-save', str(path), '--expected-digest', identity]), paths))
    assert sorted(outcomes) == [0, 2]
    assert '冲突' in capsys.readouterr().err
    assert main(['rules-check', str(target)]) == 0


def test_task_retains_dynamic_apl_targets_and_parent_contract_without_static_substitution(tmp_path):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary():
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
    report = result['rule_initialization']
    bindings = {row['id']: row for row in report['bindings']}
    # Fixed APL line364 chooses the first boss target, not the current target.
    assert bindings['unholy.aoe.3']['target'] == {'mode':'first','fact':'apl_is_boss','phase':'02'}
    facts = report['rule_snapshot']['resolved']['252']['facts']
    assert facts['apl_is_boss'] == {'type':'boolean','from':'student.apl_fact','key':'is_boss','phase':'02'}
    def refs(value):
        if isinstance(value, dict):
            return {value['fact']} if set(value) == {'fact'} else set().union(*(refs(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(refs(v) for v in value))
        return set()
    # APL line406 uses actual active_enemies, including after targets die.
    for identity in ('unholy.aoe.4', 'unholy.aoe.7', 'unholy.aoe.8'):
        assert 'apl_active_enemies' in refs(bindings[identity]['condition'])
        assert 'targets' not in refs(bindings[identity]['condition'])
        assert bindings[identity]['parent_condition'] == {'gte':[{'fact':'apl_active_enemies'},3]}
    assert report['skeleton']['funding']['completed'] == 1


@pytest.mark.parametrize('targets', [1, 5])
def test_task_does_not_claim_burst_rule_without_burst_inputs(tmp_path, targets):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['apl_actions'].append(dict(native['apl_actions'][0], name='putrefy', signature='putrefy',
                                     data_id=10042, base_spell_id=10042))
    native['static_snapshot']['actions'].append(dict(name='putrefy', gcd_ms=1000,
        cooldown_ms=120000, cast_ms=0, channeled=False, costs={}, gains={'runic_power':10},
        gain_status='known', gain_timing='on_cast', charges=2, max_charges=2))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count':targets},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert any(row.get('action') == 'putrefy' for row in report['positions'])
    rule = next(row for row in report['rules'] if row['id'] == 'protected_burst')
    assert rule['application_status'] == 'unknown_not_applied'
    assert rule['applied_positions'] == []


@pytest.mark.parametrize('attempt_limit', [128, 3, 2])
def test_task_evaluates_current_action_attempt_count_before_each_candidate(tmp_path, monkeypatch, attempt_limit):
    import json
    from rule_config import DEFAULT_PATH
    pack = json.loads(DEFAULT_PATH.read_bytes())
    for row in pack['specializations']['252']['bindings']:
        if row.get('arguments', {}).get('action') == 'scourge_strike' and row.get('initialize'):
            row['initialize']['when'] = {'lt':[{'fact':'plan.current_action_attempts'}, attempt_limit]}
            row['initialize']['unknown'] = 'error'
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(path))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['resources']['runic_power']['maximum'] = 30
    with _apl_task_boundary(native):
        if attempt_limit == 2:
            with pytest.raises(TaskError, match='来源额度.*不可达'):
                run_task(source, tmp_path / 'task', search_config=dict(
                    candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        else:
            result = run_task(source, tmp_path / 'task', search_config=dict(
                candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
            attempts = result['rule_initialization']['skeleton']['attempts']
            assert sum(row['action'] == 'scourge_strike' for row in attempts) == 3


@pytest.mark.parametrize('fault', [
    'recovery_reference', 'recovery_operation', 'recovery_type', 'recovery_unit',
    'recovery_phase', 'stop_phase', 'stop_candidate_count', 'when_student_fact',
    'coverage_estimate', 'scope_plan', 'funding_finding', 'feature_plan', 'diagnose_type',
    'unused_diagnose_type', 'unused_edit_type', 'unused_feature_type'])
def test_rule_cli_rejects_invalid_execution_fields_without_overwriting_valid_pack(
        tmp_path, monkeypatch, capsys, fault):
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
    spec = pack['specializations']['252']
    recovery = spec['initialization']['recovery']
    init = next(row['initialize'] for row in spec['bindings'] if row.get('initialize'))
    if fault.startswith('recovery_'):
        recovery['interval_ms'] = {
            'recovery_reference': {'fact':'missing_recharge'},
            'recovery_operation': {'unregistered_operation':[1,2]},
            'recovery_type': True,
            'recovery_unit': {'fact':'rune_recharge_slots'},
            'recovery_phase': {'fact':'interval.attempt_count'},
        }[fault]
    elif fault in ('stop_phase', 'stop_candidate_count'):
        fact = 'interval.attempt_count' if fault == 'stop_phase' else 'plan.current_action_attempts'
        pack['general']['initialization']['stop'] = {'eq':[{'fact':fact},0]}
    elif fault == 'when_student_fact':
        init['when'] = {'gte':[{'fact':'apl_active_enemies'},3]}
    elif fault == 'coverage_estimate':
        init['coverage_when'] = {'gt':[{'fact':'deficit'},0]}
    elif fault == 'scope_plan':
        spec['bindings'][0]['scope'] = {'eq':[{'fact':'plan.required_attempts_remaining'},0]}
    elif fault == 'funding_finding':
        spec['initialization']['funding']['completion'] = {'eq':[{'fact':'finding.source_position'},0]}
    elif fault == 'feature_plan':
        pack['general']['templates']['window_or_full']['features'][0]['value'] = {'fact':'plan.current_action_attempts'}
    elif fault == 'diagnose_type':
        pack['general']['templates']['window_or_full']['diagnose']['when'] = 3
    elif fault == 'unused_diagnose_type':
        pack['general']['templates']['avoid_idle']['diagnose']['when'] = 3
    elif fault == 'unused_edit_type':
        pack['general']['templates']['avoid_idle']['edits'][0]['when'] = 3
    elif fault == 'unused_feature_type':
        pack['general']['templates']['avoid_idle']['features'][0]['value'] = 'not_numeric'
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
    from rule_config import DEFAULT_PATH
    from task import start_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    clock = time.monotonic
    original_open = Path.open
    delay = [0.0]
    def timed_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if path.resolve() == DEFAULT_PATH.resolve():
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


@pytest.mark.parametrize('targets,spender,epidemic_available', [
    (1, 'death_coil', True), (5, 'epidemic', True), (5, 'death_coil', False)])
def test_task_prespends_sufficient_cooldown_income_then_funds_a_distinct_consumer(
        tmp_path, targets, spender, epidemic_available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['parameters']['blightburst'] = True
    snapshot['resources']['runic_power']['maximum'] = 60
    next(row for row in native['apl_actions'] if row['name'] == 'epidemic')['available'] = epidemic_available
    native['apl_actions'].append(dict(native['apl_actions'][0], name='putrefy', signature='putrefy',
                                     data_id=10042, base_spell_id=10042))
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=15000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power':30},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count':targets},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    expected = ['putrefy', spender, 'scourge_strike', 'scourge_strike', 'scourge_strike', spender]
    assert [row['action'] for row in report['skeleton']['attempts']] == expected
    assert report['skeleton']['funding'] == dict(completed=1, credited=30.0, preconsumption_attempts=1)
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == expected
    assert [row['coverage_id'] for row in actions if row['action'] == spender] == [
        'opening_space', 'funded_consumer']
    assert report['skeleton']['consumption'] == 60


@pytest.mark.parametrize('targets,spender', [(1, 'death_coil'), (5, 'epidemic')])
@pytest.mark.parametrize('income', [0, 20])
def test_task_does_not_relabel_funded_pending_as_same_button_preconsumption(tmp_path, targets, spender, income):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    native['static_snapshot']['parameters']['blightburst'] = True
    native['static_snapshot']['resources']['runic_power']['maximum'] = 60
    native['apl_actions'].append(dict(native['apl_actions'][0], name='putrefy', signature='putrefy',
                                     data_id=10042, base_spell_id=10042))
    native['static_snapshot']['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=15000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power':income},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count':targets},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['skeleton']['funding']['preconsumption_attempts'] == 0
    assert report['skeleton']['funding']['completed'] == 1
    assert report['skeleton']['funding']['credited'] == 30
    consumers = [row for row in report['positions'] if row.get('action') == spender]
    assert [row['coverage_id'] for row in consumers] == ['funded_consumer']


@pytest.mark.parametrize('gain_status,gain_timing,gains,fillers', [
    ('known', 'on_cast', {'runic_power': 15}, 2),
    ('unknown', 'unknown', {}, 3)])
def test_task_keeps_preconsumption_eligible_after_second_layer_maintenance(
        tmp_path, gain_status, gain_timing, gains, fillers):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['maximum'] = 60
    next(row for row in snapshot['actions'] if row['name'] == 'outbreak').update(
        gains=gains, gain_status=gain_status, gain_timing=gain_timing)
    native['apl_actions'].append(dict(native['apl_actions'][0], name='putrefy', signature='putrefy',
                                     data_id=10042, base_spell_id=10042))
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=15000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power': 30},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['skeleton']['funding'] == dict(completed=1, credited=30.0, preconsumption_attempts=1)
    actions = [row for row in report['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions] == [
        'outbreak', 'putrefy', 'epidemic', *(['scourge_strike'] * fillers), 'epidemic']
    assert [row['coverage_id'] for row in actions if row['action'] == 'epidemic'] == [
        'opening_space', 'funded_consumer']
    if gain_status == 'unknown':
        assert all(row['resource_balance_status'] == 'unknown_unaccounted_gain' for row in actions)
    else:
        assert actions[0]['replaced_skeleton_actions'] == ['scourge_strike']


def test_task_keeps_repeated_consumer_occurrences_and_renamed_coverage_identities(tmp_path, monkeypatch):
    import json
    from rule_config import DEFAULT_PATH
    from test_engine import apl_pool_reference
    pack = json.loads(DEFAULT_PATH.read_bytes())
    spec = pack['specializations']['252']
    names = {'opening_space':'first_attempt', 'funded_consumer':'later_attempts'}
    funding = spec['initialization']['funding']
    funding['coverage_id'] = names[funding['coverage_id']]
    funding['preconsumption_coverage'] = names[funding['preconsumption_coverage']]
    for row in spec['bindings']:
        for init in ([row['initialize']] if row.get('initialize') else []) + row.get('extra_initializations', []):
            if init['coverage_id'] in names:
                old = init['coverage_id']
                init['coverage_id'] = names[old]
                if old == 'funded_consumer':
                    init['count'] = 2
    config_path = tmp_path / 'rules.json'
    config_path.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(config_path))
    native = apl_pool_reference()
    snapshot = native['static_snapshot']
    snapshot['parameters']['blightburst'] = True
    snapshot['resources']['runic_power']['maximum'] = 60
    native['apl_actions'].append(dict(native['apl_actions'][0], name='putrefy', signature='putrefy',
                                     data_id=10042, base_spell_id=10042))
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=15000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power':30},
        gain_status='known', gain_timing='on_cast', charges=1, max_charges=1))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count':5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    report = result['rule_initialization']
    assert report['skeleton']['funding'] == dict(completed=2, credited=60.0, preconsumption_attempts=1)
    consumers = [row for row in report['positions'] if row.get('action') == 'epidemic']
    assert [row['coverage_id'] for row in consumers] == ['first_attempt', 'later_attempts', 'later_attempts']
    assert len(report['program']) <= 128
