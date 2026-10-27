"""差异化训练通过既有配置和公开优化器入口验证，不启动原生模拟。"""
from io import BytesIO

import pytest

from test_population_training import memory_ga


def test_training_config_owns_diversity_and_publication_without_formal_tournament():
    from simulation_config import load_training_config, load_search_config
    config = load_training_config(BytesIO(b'[training]\ntop_k=10\nmin_publish=5\nbehavior_alpha=0.25\n'))
    assert config['top_k'] == 10
    assert config['min_publish'] == 5
    assert config['behavior_alpha'] == .25
    assert 'tournament_size' not in config
    assert load_search_config(BytesIO(b''))['top_k'] == 8
    for setting in ('tournament_size=3', 'replacement_window_ratio=0.66',
                    'min_publish=9\ntop_k=8', 'min_publish=0', 'behavior_alpha=1.1'):
        with pytest.raises(ValueError):
            load_training_config(BytesIO(('[training]\n' + setting).encode()))


def test_report_behavior_uses_executions_and_registered_player_buff_not_damage_ticks():
    from copy import deepcopy
    from behavior import context_for, describe, distance
    from test_character_export import sample_profile
    from seed_training import template_character
    from test_search import _fast_report
    character = template_character(sample_profile())
    report = _fast_report(character, 100., 31)
    report.update(report_version='2.0.0', version='1210-01')
    player = report['sim']['players'][0]
    player['stats'] = [dict(name='outbreak', id=77575, sim2gse_actor_index=1,
        sim2gse_actor_name=character.name, sim2gse_owner_type='player',
        num_executes=dict(mean=30.), total_tick_time=dict(mean=9999))]
    player['buffs'] = [dict(name='runic_corruption', spell=51460, uptime=45.)]
    player['buffs_constant'] = []
    capabilities = dict(actions=[dict(kind='spell', simc_action='outbreak', spell_id=77575)])
    context = context_for(report, character, capabilities)
    first = describe(report, character, context)
    assert first == dict(frequencies=[10.], coverage=[.45])
    other = deepcopy(report)
    other['sim']['players'][0]['stats'] = []
    other['sim']['players'][0]['buffs'] = []
    second = describe(other, character, context)
    assert second == dict(frequencies=[0.], coverage=[0.])
    assert distance(first, second, context, .5) == pytest.approx(.475)
    other['sim']['players'][0]['buffs'] = [dict(player['buffs'][0]), dict(player['buffs'][0])]
    with pytest.raises(ValueError, match='增益.*歧义'):
        describe(other, character, context)
    other = deepcopy(report)
    other['report_version'] = 'unknown'
    with pytest.raises(ValueError, match='报告版本'):
        describe(other, character, context)
    other = deepcopy(report)
    del other['sim']['players'][0]['stats'][0]['num_executes']
    with pytest.raises(ValueError, match='执行次数'):
        describe(other, character, context)
    other = deepcopy(report)
    other['sim']['players'][0]['stats'][0]['id'] = 999
    with pytest.raises(ValueError, match='动作.*身份'):
        describe(other, character, context)
    other = deepcopy(report)
    other['sim']['players'][0]['buffs'][0]['spell'] = 999
    with pytest.raises(ValueError, match='增益.*身份'):
        context_for(other, character, capabilities)
    other['sim']['players'][0]['buffs'] = []
    assert context_for(other, character, capabilities)['buffs'] == context['buffs']


def test_reference_omission_and_replacement_executes_follow_verified_unholy_stats():
    from behavior import context_for, describe
    from seed_training import template_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    character = template_character(sample_profile())
    report = _fast_report(character, 100., 31)
    player = report['sim']['players'][0]
    coil = dict(player['stats'][1], id=47541, num_executes=dict(mean=30.))
    replacement = dict(coil, name='necrotic_coil', id=1242174, num_executes=dict(mean=15.))
    player['stats'] = [coil, replacement]
    capabilities = dict(actions=[dict(kind='spell', simc_action=name, spell_id=spell)
        for name, spell in [('death_coil', 47541), ('epidemic', 207317), ('death_and_decay', 43265)]])
    context = context_for(report, character, capabilities)
    assert describe(report, character, context)['frequencies'] == [15., 0., 0.]
    # In ordinary SimC mode replacements are children; the parent already counts them.
    player['stats'] = [dict(coil, children=[replacement], num_executes=dict(mean=45.))]
    assert describe(report, character, context)['frequencies'] == [15., 0., 0.]


@pytest.mark.parametrize('layout', ['top', 'child', 'both'])
@pytest.mark.parametrize('names,ids', [
    (('death_coil', 'necrotic_coil'), (47541, 1242174)),
    (('base_button', 'replacement_button'), (901, 902)),
])
def test_grouped_variant_has_one_coordinate_and_exclusive_report_layout(layout, names, ids):
    from behavior import context_for, describe
    from seed_training import template_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    character = template_character(sample_profile())
    report = _fast_report(character, 100., 31)
    player = report['sim']['players'][0]
    base = dict(player['stats'][0], name=names[0], id=ids[0], num_executes=dict(mean=30.))
    child = dict(base, name=names[1], id=ids[1], num_executes=dict(mean=15.))
    if layout != 'top':
        base.update(children=[child], num_executes=dict(mean=45.))
    player['stats'] = [base] + ([child] if layout != 'child' else [])
    variants = [dict(kind='spell', simc_action=name, spell_id=spell, base_spell_id=ids[0])
                for name, spell in zip(names, ids)]
    capabilities = dict(actions=[dict(variants[0], variants=variants)])
    if layout == 'both':
        with pytest.raises(ValueError, match='统计布局'):
            context_for(report, character, capabilities)
    else:
        context = context_for(report, character, capabilities)
        assert len(context['actions']) == 1
        assert context['reference_rate'] == 15.
        assert describe(report, character, context)['frequencies'] == [15.]


@pytest.mark.parametrize('owner,name,index', [
    ('unknown', 'actor', 1), ('', 'actor', 1), (None, 'actor', 1),
    ('player', '', 1), ('owned_unit', None, 2), ('player', 'actor', None),
])
def test_unknown_actor_identity_cannot_turn_into_zero(owner, name, index):
    from behavior import context_for, describe
    from seed_training import template_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    character = template_character(sample_profile())
    report = _fast_report(character, 100., 31)
    capabilities = dict(actions=[dict(kind='spell', simc_action='outbreak', spell_id=1001)])
    context = context_for(report, character, capabilities)
    row = report['sim']['players'][0]['stats'][0]
    row.update(sim2gse_owner_type=owner, sim2gse_actor_name=name, sim2gse_actor_index=index)
    with pytest.raises(ValueError, match='归属|身份'):
        describe(report, character, context)
    with pytest.raises(ValueError, match='归属|身份|映射'):
        context_for(report, character, capabilities)


@pytest.mark.parametrize('children', [None, []])
def test_known_pet_stat_is_distinct_from_player_and_reliable_omission(children):
    from behavior import context_for, describe
    from seed_training import template_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    character = template_character(sample_profile())
    report = _fast_report(character, 100., 31)
    capabilities = dict(actions=[dict(kind='spell', simc_action='outbreak', spell_id=1001)])
    report['sim']['players'][0]['stats'][0]['children'] = children
    context = context_for(report, character, capabilities)
    row = report['sim']['players'][0]['stats'][0]
    row.update(sim2gse_owner_type='owned_unit', sim2gse_actor_name='pet', sim2gse_actor_index=2)
    assert describe(report, character, context)['frequencies'] == [0.]
    report['sim']['players'][0]['stats'] = []
    assert describe(report, character, context)['frequencies'] == [0.]


def test_training_public_optimizer_retests_only_nominal_and_publishes_all_qualified(memory_ga):
    import population_training
    case = memory_ga(settings=dict(top_k=6))
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character, case.ready,
        dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    assert len(ga['population']) == len(case.starts) == 6
    assert ga['generation'] == 2
    assert len(rows) == 6
    assert {row['contract_version'] for row in rows} == {3}
    assert all(set(row['evaluation']['scenarios']) == {'nominal'} for row in rows)
    assert all('stable_representative' not in row['evaluation'] for row in rows)
    assert len([call for call in case.calls if call[2]['iterations'] == 128]) == 18


@pytest.mark.parametrize('children,expected', [
    ([1003, 1004], [1004, 1002]),  # Minimum-total matching crosses the two children.
    ([1003, None], [1001, 1002]),  # One legal child challenges only the nearest (stronger) parent.
    ([None, 1004], [1004, 1002]),
    ([None, None], [1001, 1002]),
])
def test_training_resume_competes_frozen_children_with_nearest_parents(memory_ga, children, expected):
    from copy import deepcopy
    import engine
    from test_search import _fast_report
    names = {1001:'outbreak', 1002:'death_coil', 1003:'scourge_strike', 1004:'dark_transformation'}
    def native(profile, candidate, folder, **options):
        spell = candidate['blocks'][0][0]['spell_id']
        report = _fast_report(options['character'], {1001:100., 1002:120., 1003:119., 1004:110.}[spell],
                              max(1, options['iterations'] - 1))
        player = report['sim']['players'][0]
        for row in player['stats']:
            row['num_executes']['mean'] = 0.
        player['stats'][0]['num_executes']['mean'] = {1001:10., 1002:100., 1003:90., 1004:20.}[spell]
        return dict(report=report, trace=[], summary=engine.check_report(report, options['character'],
            options['iterations'], simulation_config=options['simulation_config']))
    case = memory_ga(programs=[[['outbreak']], [['death_coil']]], native=native,
                     settings=dict(top_k=2, min_publish=1, stagnation_generations=1))
    case.run()
    ga = case.store.state['ga']
    ga.update(phase='breed', stagnant=0, generation=0, finals={},
        pending=dict(programs=[[[names[spell]]] if spell else [['invalid']] for spell in children],
                     parent_slots=[0, 1], regenerations=[0, 0], rng=deepcopy(ga['rng'])))
    result = case.run()
    assert [row['program'] for row in result['population']] == [[[names[spell]]] for spell in expected]


@pytest.mark.parametrize('limit,boundary', [(8, 15), (10, 19)])
def test_training_quality_prescreen_then_farthest_representatives_owns_actual_publish_count(memory_ga, limit, boundary):
    from itertools import permutations
    import engine
    import population_training
    from test_search import _fast_report
    programs = [[list([name]) for name in order] for order in permutations(
        ('outbreak', 'death_coil', 'scourge_strike', 'dark_transformation'))]
    orders = [tuple(block[0] for block in program) for program in programs]
    def native(profile, candidate, folder, **options):
        index = orders.index(tuple(block[0]['simc_action'] for block in candidate['blocks']))
        report = _fast_report(options['character'], 1000. - index, max(1, options['iterations'] - 1))
        report['sim']['players'][0]['stats'][0]['num_executes']['mean'] = 10000. if index == 23 else float(index)
        return dict(report=report, trace=[], summary=engine.check_report(report, options['character'],
            options['iterations'], simulation_config=options['simulation_config']))
    case = memory_ga(programs=programs, native=native, settings=dict(top_k=limit, stagnation_generations=1))
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character, case.ready,
        dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    indices = [orders.index(tuple(block[0] for block in row['program'])) for row in rows]
    assert len(indices) == limit and 0 in indices and boundary in indices
    assert max(indices) <= boundary
    assert all(row['evaluation']['publication'] == dict(count=limit, top_k=limit, min_publish=4) for row in rows)
