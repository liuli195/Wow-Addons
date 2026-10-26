"""当前角色消费训练起点；真实原生目录形状，纯内存规则边界。"""
from copy import deepcopy

import pytest
from test_population_training import memory_ga


def native_skill(name='unlearned_racial', *, native_type='hostile_spell', spell_id=0, **flags):
    # 无效的种族/天赋数据可同时使原生技能 background，不能靠按钮分类判断资格。
    row = dict(name=name, signature=name, id=spell_id, data_id=spell_id,
                base_spell_id=spell_id, data_valid=bool(spell_id), executions=0,
                type=native_type, background=True, quiet=False, harmful=False,
                player_owned=True, passive=False, action_list='racials', precombat=False,
                gcd_ms=1500, action_initialized=True, available=False)
    return dict(row, **flags)


@pytest.fixture
def consume_seed(monkeypatch):
    import codec
    from engine import inspect
    from runtime import TaskRuntime
    from task import _seed_programs, parse_character
    from test_character_export import sample_profile
    from test_engine import apl_pool_reference

    # 外部客户端目标掩码输入；角色映射、语法、规范化和导出预检仍走生产实现。
    monkeypatch.setattr(codec, 'load_targeting', lambda **kwargs: dict(target_masks={}))
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    character = parse_character(sample_profile())

    def consume(programs, *, native_rows=(), starts=(), change_capabilities=None):
        reference = apl_pool_reference()
        reference['apl_actions'].extend(deepcopy(native_rows))
        capabilities = inspect(reference)
        if change_capabilities is not None:
            change_capabilities(capabilities)
        snapshot = [dict(configuration_key=key, candidate_id=f'trained-{index}',
                         class_name=character.class_name, spec=character.spec, program=program,
                         score=99999., scores=[99999.] * 3, source='unchanged-training')
                    for index, program in enumerate(programs)]
        before = deepcopy((snapshot, capabilities))
        result, decisions = _seed_programs(list(starts), snapshot, character=character, targets=1,
            configuration_key=key, capabilities=capabilities, runtime=TaskRuntime(600))
        assert (snapshot, capabilities) == before
        return result, decisions, capabilities
    return consume


@pytest.mark.parametrize('name, native_type, spell_id, background', [
    ('unlearned_racial', 'hostile_spell', 0, True),
    ('unselected_strike', 'attack', 0, True),
    ('level_locked_spell', 'hostile_spell', 123456, False),
    ('level_locked_attack', 'attack', 234567, False),
    ('unselected_heal', 'heal_spell', 0, True),
    ('unselected_absorb', 'absorb_spell', 0, True),
])
def test_current_seed_uses_native_skill_evidence_not_button_status(
        consume_seed, name, native_type, spell_id, background):
    original = [[name], ['outbreak'], ['death_coil']]
    starts, decisions, capabilities = consume_seed([original], native_rows=[native_skill(
        name, native_type=native_type, spell_id=spell_id, background=background)])
    evidence = capabilities['sources'][-1]
    assert evidence['status'] == ('native_non_button' if background else 'native_unavailable')
    assert starts == [[['outbreak'], ['death_coil']]], decisions
    assert decisions[0]['status'] == 'accepted'
    assert decisions[0]['original_program'] == original
    assert decisions[0]['removed'][0]['path'] == 'segments[0][0]'


@pytest.mark.parametrize('members, remaining', [
    (['unlearned_racial', 'unlearned_racial'], []),
    (['unlearned_racial', 'outbreak'], ['outbreak']),
    (['outbreak', 'unlearned_racial', 'death_coil'], ['outbreak', 'death_coil']),
])
def test_current_seed_filters_castsequence_before_real_binding(consume_seed, members, remaining):
    reset = dict(timeout_seconds=7, flags=['target', 'combat'])
    original = [dict(kind='CastSequence', members=members, reset=reset), ['scourge_strike']]
    starts, decisions, capabilities = consume_seed([original], native_rows=[native_skill()])
    derived = ([dict(kind='CastSequence', members=remaining, reset=reset)] if remaining else [])
    derived.append(['scourge_strike'])
    assert decisions[0]['derived_program'] == derived, decisions
    assert decisions[0]['removed']
    if len(remaining) == 1:
        assert starts == [] and decisions[0]['status'] == 'rejected'
        assert '2 至 32' in decisions[0]['reason']
    else:
        assert starts == [derived] and decisions[0]['status'] == 'accepted'
        if remaining:
            from program import canonicalize_search_program
            command = canonicalize_search_program(derived, capabilities)['program']['nodes'][0]['commands'][0]
            assert command['members'] == ['outbreak', 'death_coil']
            assert command['spell_ids'] == [77575, 47541]


@pytest.mark.parametrize('position', [0, 1, 2])
def test_current_seed_keeps_block_order_when_removing_first_middle_or_last(consume_seed, position):
    block = ['outbreak', 'auto_attack']
    block.insert(position, 'unlearned_racial')
    starts, decisions, _ = consume_seed([[block]], native_rows=[native_skill(), native_skill(
        'auto_attack', native_type='attack', spell_id=6603, available=True, background=False, gcd_ms=0)])
    assert starts == [[['outbreak', 'auto_attack']]]
    assert decisions[0]['removed'][0]['path'] == f'segments[0][{position}]'


def test_current_seed_keeps_loop_order_count_and_waits_but_removes_empty_bodies(consume_seed):
    original = [dict(kind='Loop', count=3, blocks=[['unlearned_racial']]),
                dict(kind='Loop', count=2, blocks=[['unlearned_racial', 'outbreak'],
                     ['unlearned_racial'], ['death_coil', 'unlearned_racial']]),
                dict(kind='WaitClicks', clicks=7), ['scourge_strike']]
    starts, decisions, _ = consume_seed([original], native_rows=[native_skill()])
    assert starts == [[dict(kind='Loop', count=2, blocks=[['outbreak'], ['death_coil']]),
                      dict(kind='WaitClicks', clicks=7), ['scourge_strike']]]
    assert [entry['path'] for entry in decisions[0]['removed']] == [
        'segments[0].blocks[0][0]', 'segments[1].blocks[0][0]',
        'segments[1].blocks[1][0]', 'segments[1].blocks[2][1]']


@pytest.mark.parametrize('missing, flags', [
    *[(field, {}) for field in ('action_initialized', 'available', 'player_owned', 'type',
                               'passive', 'quiet', 'precombat', 'signature')],
    (None, dict(action_initialized=False)), (None, dict(action_initialized=1)),
    (None, dict(available=0)), (None, dict(player_owned=False)),
    (None, dict(passive=True)), (None, dict(quiet=True)), (None, dict(precombat=True)),
    (None, dict(type='unknown')), (None, dict(type='spell')),
    (None, dict(type='call_action_list')), (None, dict(type='action_variable')),
    (None, dict(type='sequence')), (None, dict(type='other')), (None, dict(type='use')),
    (None, dict(catalogue='baseline')),
    (None, dict(signature=None)),
    (None, dict(available=True, executions=0, cooldown_ms=120000, resource=0)),
])
def test_current_seed_does_not_delete_without_conclusive_player_skill_evidence(
        consume_seed, missing, flags):
    def change(capabilities):
        row = capabilities['sources'][-1]
        if missing:
            row.pop(missing)
        row.update(flags)
    starts, decisions, _ = consume_seed([[['unlearned_racial'], ['outbreak']]],
        native_rows=[native_skill()], change_capabilities=change)
    assert starts == []
    assert decisions[0]['status'] == 'rejected' and decisions[0]['reason']
    assert decisions[0]['removed'] == []


def test_current_seed_keeps_available_names_and_never_used_current_skills(consume_seed):
    original = [['outbreak'], ['unused_spell'], ['death_coil']]
    starts, decisions, _ = consume_seed([original], native_rows=[
        native_skill('outbreak'), native_skill('unused_spell', spell_id=345678,
            available=True, background=False, executions=0, cooldown_ms=120000, resource=0)])
    assert starts == [original]
    assert decisions[0]['removed'] == [] and decisions[0]['status'] == 'accepted'


@pytest.mark.parametrize('segment', [
    ['unlearned_racial', 'unknown_action'],
    dict(kind='Loop', count=2, blocks=[['unlearned_racial'], ['unknown_action']]),
    dict(kind='CastSequence', members=['unlearned_racial', 'unknown_action'], reset=None),
])
def test_current_seed_rejects_unknown_members_instead_of_trimming_them(consume_seed, segment):
    starts, decisions, _ = consume_seed([[segment, ['outbreak']]], native_rows=[native_skill()])
    assert starts == [] and decisions[0]['status'] == 'rejected'
    assert '不支持' in decisions[0]['reason']


@pytest.mark.parametrize('program, reason', [
    ([['unlearned_racial']] * 128 + [['outbreak']], '128'),
    ([['unlearned_racial'] * 17, ['outbreak']], '16'),
    ([dict(kind='Loop', count=0, blocks=[['unlearned_racial']]), ['outbreak']], 'Loop'),
    ([dict(kind='Loop', count=4096, blocks=[['unlearned_racial'], ['outbreak']])], '4096'),
    ([dict(kind='Loop', count=2, blocks=[['unlearned_racial']] * 128), ['outbreak']], '128'),
    ([dict(kind='WaitClicks', clicks=1), ['unlearned_racial'], ['outbreak']], 'WaitClicks'),
    ([dict(kind='WaitClicks', clicks=2), ['unlearned_racial']], '没有可执行动作'),
    ([dict(kind='CastSequence', members=['unlearned_racial'], reset=None), ['outbreak']], '2 至 32'),
    ([dict(kind='CastSequence', members=['unlearned_racial'] * 33, reset=None), ['outbreak']], '2 至 32'),
    ([dict(kind='CastSequence', members=['unlearned_racial'] * 2,
           reset=dict(timeout_seconds=0, flags=[])), ['outbreak']], 'reset'),
    ([dict(kind='CastSequence', members=['unlearned_racial'] * 2,
           reset=dict(timeout_seconds=None, flags=['unsupported'])), ['outbreak']], 'reset'),
])
def test_current_seed_cannot_hide_invalid_original_structure_by_trimming(consume_seed, program, reason):
    starts, decisions, _ = consume_seed([program], native_rows=[native_skill()])
    assert starts == [] and decisions[0]['status'] == 'rejected'
    assert reason in decisions[0]['reason']


def test_current_seed_deduplicates_derived_behavior_without_filling_the_start_quota(consume_seed):
    original = [['unlearned_racial'], ['outbreak'], ['death_coil']]
    derived = [['outbreak'], ['death_coil']]
    starts, decisions, _ = consume_seed([original, derived, [['unknown_action']]],
        native_rows=[native_skill()], starts=[[['scourge_strike']]])
    assert starts == [[['scourge_strike']], derived]
    assert [decision['status'] for decision in decisions] == ['accepted', 'duplicate', 'rejected']
    assert decisions[0]['behavior_identity'] == decisions[1]['behavior_identity']


def test_formal_search_rescores_the_adapted_start_instead_of_reusing_training_score(
        consume_seed, memory_ga, monkeypatch):
    from search import TaskStore
    from search import DEFAULT_CONFIG as FORMAL_DEFAULTS
    original = [['unlearned_racial'], ['outbreak'], ['death_coil']]
    starts, decisions, capabilities = consume_seed([original], native_rows=[native_skill()])
    monkeypatch.setitem(FORMAL_DEFAULTS, 'crossover_probability', 0.)
    monkeypatch.setitem(FORMAL_DEFAULTS, 'mutation_probability', 0.)
    case = memory_ga(formal=True, programs=starts, score_for=lambda candidate, options: 321.)
    case.capabilities.clear()
    case.capabilities.update(capabilities)
    case.store.state['seed_adaptations'] = decisions
    result = case.run()
    assert result['status'] == 'completed'
    assert result['search']['starts'] == [[['outbreak'], ['death_coil']]]
    assert result['search_result']['dps'] == 321. and result['search_result']['samples'] == 381
    assert result['selected_candidate_key'] == decisions[0]['behavior_identity']
    assert case.calls and all(command['simc_action'] != 'unlearned_racial'
                              for _, candidate, _ in case.calls
                              for block in candidate['blocks'] for command in block)
    saved = TaskStore.load_state(case.store.db)
    assert saved['seed_adaptations'] == decisions
    assert decisions[0]['original_program'] == original
