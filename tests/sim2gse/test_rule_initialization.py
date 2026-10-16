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
    assert initialization['skeleton']['consumption'] >= 100
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
    assert result['rule_initialization']['skeleton']['consumption'] >= 100


@pytest.mark.parametrize('fault,message', [
    ('missing_gcd', '静态字段'), ('single_empty', '单空点击'),
    ('too_long', '128节点'), ('unknown_duration', 'dread_plague_duration_ms')])
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
    assert initialization['skeleton']['duration_ms'] < 45000
    assert initialization['skeleton']['consumption'] >= 100


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
    assert len(positions) > 1
    assert positions[0]['condition_status'] == 'static_branch_estimate'
    assert all(row['condition_status'] == 'dynamic_condition_unknown' for row in positions[1:])
    assert all('充能' in row['condition_basis'] and '未知' in row['condition_basis']
               for row in positions[1:])
