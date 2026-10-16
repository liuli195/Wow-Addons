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
    # The binding's spender is already affordable: one 35-unit attempt, not 100 units.
    assert result['rule_initialization']['skeleton'] == dict(
        duration_ms=1000, consumption=35, demonstrated=[])


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
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=120000,
        cast_ms=0, channeled=False, costs={}, gains={'runic_power': 10}, charges=2, max_charges=2))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native):
        result = run_task(source, tmp_path / 'task', simulation_config={'target_count': 5},
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    initialization = result['rule_initialization']
    actions = [row for row in initialization['positions'] if row['kind'] == 'action']
    assert [row['action'] for row in actions[:3]] == ['outbreak', 'putrefy', 'epidemic']
    assert actions[1]['rule'] == 'window_or_full'
    assert initialization['skeleton']['demonstrated'] == ['putrefy']
    assert initialization['skeleton']['duration_ms'] == 2000
    assert initialization['skeleton']['consumption'] == 30


@pytest.mark.parametrize('talent,available', [(True, True), (False, True), (True, False)])
def test_task_demonstrates_available_talented_cooldown_in_single_target(tmp_path, talent, available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    for row in native['apl_actions']:
        if row['name'] == 'death_and_decay':
            row['available'] = available
    snapshot = native['static_snapshot']
    snapshot['parameters']['cycle_of_death'] = talent
    snapshot['resources']['runic_power']['maximum'] = 30
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


@pytest.mark.parametrize('blightburst,available', [(True, True), (False, True), (None, True), (True, False)])
def test_task_uses_confirmed_alternative_disease_maintenance(tmp_path, blightburst, available):
    from test_engine import apl_pool_reference
    native = apl_pool_reference()
    template = native['apl_actions'][0]
    native['apl_actions'].append(dict(template, name='putrefy', signature='putrefy',
        data_id=10042, base_spell_id=10042, available=available))
    snapshot = native['static_snapshot']
    snapshot['resources']['runic_power']['maximum'] = 30
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
            ['death_coil'], {'kind': 'WaitClicks', 'clicks': 4}]
        assert report['duration_ms'] == 4000
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
    snapshot['actions'].append(dict(name='putrefy', gcd_ms=1000, cooldown_ms=3000,
        cast_ms=0, channeled=False, costs={}, gains={}, charges=2, max_charges=2))
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
