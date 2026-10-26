"""Ordinary gear rules. Literal domain inputs and public snapshots are not native runs."""
from contextlib import nullcontext
import copy
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace
import threading
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('gear_planner_rules', ROOT / 'projects/gear-planner/server.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def character(cls='deathknight', spec='blood'):
    return {'name': '规则样例', 'character': {'class': cls, 'spec': spec, 'level': '90',
            'race': 'human', 'talents': 'A' * 32}, 'gear': {}}


@pytest.fixture
def rules():
    # Only domain records required by these examples. No simulated engine outputs.
    items = {
        1: {'id': 1, 'name': 'Head', 'itemClass': 4, 'itemSubClass': 4, 'inventoryType': 1},
        2: {'id': 2, 'name': 'Neck', 'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 2,
            'socketInfo': {'sockets': [{'type': 'PRISMATIC'}]}},
        3: {'id': 3, 'name': 'Ring', 'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 11},
        4: {'id': 4, 'name': 'Crafted ring', 'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 11,
            'profession': {'id': 755, 'optionalCraftingSlots': [{'id': 7}]}, 'stats': [{'id': 24}]},
        5: {'id': 5, 'name': 'Chest', 'itemClass': 4, 'itemSubClass': 4, 'inventoryType': 5},
        6: {'id': 6, 'name': 'Wrist', 'itemClass': 4, 'itemSubClass': 4, 'inventoryType': 9},
        7: {'id': 7, 'name': 'Waist', 'itemClass': 4, 'itemSubClass': 4, 'inventoryType': 6},
        10: {'id': 10, 'name': 'One-hand sword', 'itemClass': 2, 'itemSubClass': 7, 'inventoryType': 13},
        11: {'id': 11, 'name': 'Two-hand sword', 'itemClass': 2, 'itemSubClass': 8, 'inventoryType': 17},
        12: {'id': 12, 'name': 'Staff', 'itemClass': 2, 'itemSubClass': 10, 'inventoryType': 17},
        13: {'id': 13, 'name': 'Shield', 'itemClass': 4, 'itemSubClass': 6, 'inventoryType': 14},
        14: {'id': 14, 'name': 'Held off-hand', 'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 23},
        15: {'id': 15, 'name': 'Dagger', 'itemClass': 2, 'itemSubClass': 15, 'inventoryType': 13},
        16: {'id': 16, 'name': 'Axe', 'itemClass': 2, 'itemSubClass': 0, 'inventoryType': 13},
        17: {'id': 17, 'name': 'Bow', 'itemClass': 2, 'itemSubClass': 2, 'inventoryType': 15},
        18: {'id': 18, 'name': 'Mace', 'itemClass': 2, 'itemSubClass': 4, 'inventoryType': 13},
        19: {'id': 19, 'name': 'Converted chest', 'itemClass': 4, 'itemSubClass': 4, 'inventoryType': 5},
    }
    # Two distinct tracks deliberately share one item level.
    upgrades = [
        {'bonusId': 100, 'seasonId': 37, 'group': 616, 'level': 2, 'max': 6, 'itemLevel': 305, 'name': 'Champion'},
        {'bonusId': 101, 'seasonId': 37, 'group': 616, 'level': 3, 'max': 6, 'itemLevel': 308, 'name': 'Champion'},
        {'bonusId': 102, 'seasonId': 37, 'group': 617, 'level': 1, 'max': 6, 'itemLevel': 305, 'name': 'Hero'},
        {'bonusId': 103, 'seasonId': 37, 'group': 618, 'level': 1, 'max': 6, 'itemLevel': 334, 'name': 'Myth'},
    ]
    bonuses = {str(v['bonusId']): {'upgrade': v} for v in upgrades}
    bonuses.update({'13668': {'id': 13668, 'socket': 1}, '13750': {'id': 13750, 'socket': 2},
                    '8790': {'craftedStats': [32, 36]}, '8791': {'craftedStats': [32, 49]},
                    '13751': {'itemLevel': {'amount': 305}}, '13835': {'itemLevel': {'amount': 318}},
                    '13836': {'itemLevel': {'amount': 331}}})
    for q in range(5):
        bonuses[str(12493 + q)] = {'levelOffset': {'amount': q - 4, 'craftingQuality': q + 1}}
    enchants = [
        {'id': 7967, 'equipRequirements': {'itemClass': 4, 'invTypeMask': 1 << 11},
         'displayName': '附魔戒指 - 急速', 'craftingQuality': 3, 'stats': [{'type': 'haste', 'amount': 21}]},
        {'id': 7991, 'equipRequirements': {'itemClass': 4, 'invTypeMask': 1 << 1},
         'displayName': '附魔头部 - 精通', 'stats': []},
        {'id': 3368, 'equipRequirements': {'itemClass': 2, 'itemSubClassMask': 1 << 7},
         'displayName': '堕落十字军符文', 'stats': []},
    ]
    gems = {'240894': {'id': 240894, 'socket': 'PRISMATIC'},
            '240904': {'id': 240904, 'socket': 'PRISMATIC'},
            '240983': {'id': 240983, 'socket': 'PRISMATIC', 'itemLimit': {'category': 42, 'quantity': 1}},
            '240967': {'id': 240967, 'socket': 'PRISMATIC', 'unique': 42},
            '34220': {'id': 34220, 'socket': 'META'}}
    groups = {'mplus': set(items) - {4, 19}, 'crafted_epic': {4}, 'raid_direct': set(),
              'raid_token_products': set(), 'non_set_conversion_forms': {19}}
    catalog = {slot: [] for slot, _ in server.SLOTS}
    for iid, item in items.items():
        for slot in server.SLOT_MAP[item['inventoryType']]:
            catalog[slot].append({'id': iid, 'name': item['name'], 'value': f',id={iid},bonus_id=100',
                                  'conversion': iid == 19, 'fitReasonsBySpec': {}})
    data = {'_DATA_LOADED': True, 'ITEMS': items, 'BONUSES': bonuses, 'GROUPS': groups,
            'CATALOG': catalog, 'GEAR_ENCHANTS': enchants, 'ENCHANTS': {e['id']: e for e in enchants},
            'ALL_GEMS': gems, 'GEM_IDS': set(gems) - {'34220'}, 'CRAFT_PAIRS': {'32/36': '8790', '32/49': '8791'},
            'TRACKS': {g: [v for v in upgrades if v['group'] == g] for g in (614, 615, 616, 617, 618)},
            'CRAFTING': {'slots': {'7': {'reagentIds': [274476, 3445, 3446]}}},
            'ENCOUNTERS': {}, 'INSTANCES': {}, 'INVENTORY': {'excluded_raid_tokens': []}}
    # Patching the explicit read-only input tables is not a fake database/engine.
    with patch.dict(server.__dict__, data):
        yield server


def candidate(s, slot, iid):
    return next(i for i, row in enumerate(s.CATALOG[slot]) if row['id'] == iid)


def test_import_and_all_supported_character_identities_are_pure():
    for cls, specs in server.CLASS_SPECS.items():
        for spec in specs:
            text = f'{cls}=test\nlevel=90\nrace=Human\nspec={spec}\ntalents={"A" * 32}'
            model = server.parse_import(text)
            assert model['character']['class'] == cls
            assert model['character']['spec'] == spec
            assert model['character']['race'] == 'human'
    assert server.SPEC_IDS['mage:frost'] == 64
    assert server.SPEC_IDS['deathknight:frost'] == 251
    parsed = server.parse_import(f'deathknight=x\nlevel=90\nrace=human\nspec=blood\ntalents={"A" * 32}\nshoulders=,id=1\nwrists=,id=2')
    assert set(parsed['gear']) == {'shoulder', 'wrist'}
    assert json.loads(json.dumps(parsed)) == parsed


def test_untrusted_import_and_extra_configuration_are_bounded():
    for text in ('deathknight=x\ninput=private.txt', 'head=,id=1,foo=1', 'head=,id=1\nhead=,id=2',
                 'x' * 131073, 'broken', 'head=,id=1,id=2', 'head=,id=1,ilevel=3\ninput=file'):
        with pytest.raises(ValueError):
            server.parse_import(text)
    for value in ('9' * 100000, '9' * 2999 + '!', '1:1/', '/1:1', '1::1', '1:1/2:', '１:1',
                  123, ['1:1'], 'rune:bad', 'rune\ninput=file', 'rune=1'):
        model = character(); model['character']['omnium_talents'] = value
        with pytest.raises(ValueError): server.validate(model)
    for value in ('1:1', '136814:1/136821:1', '', '136814', 'rune_of_unleashed_fire/rune_of_selfmending', 'rune_of_lingering:1/136814:1'):
        model = character(); model['character']['omnium_talents'] = value; server.validate(model)
    for field, value in (('spec', 'frost\ninput=file'), ('spec', 'holy'), ('timeofday', 'night\ninput=file')):
        model = character(); model['character'][field] = value
        with pytest.raises(ValueError): server.validate(model)
    assert server.gear_fields(',id=237840,embellishment=darkmoon_sigil_hunt')['embellishment'] == 'darkmoon_sigil_hunt'
    for suffix in ('x\ninput=file', 'x,unknown=1'):
        with pytest.raises(ValueError): server.gear_fields(',id=237840,embellishment=' + suffix)


def test_names_inventory_and_static_research_contracts():
    inventory = server.INVENTORY
    assert {k: len(v) for k, v in inventory['groups'].items()} == {
        'mplus': 207, 'raid_direct': 101, 'raid_token_products': 65, 'crafted_epic': 98, 'non_set_conversion_forms': 52}
    ids = {iid for group in inventory['groups'].values() for iid in group}
    assert len(ids) == 523
    assert len(ids - set(inventory['groups']['non_set_conversion_forms'])) == 471
    cache = json.loads((server.HERE / 'names-zhCN.json').read_text(encoding='utf-8'))
    assert not cache['missing']
    for iid, name in server.NAMES.items():
        assert re.search('[\u4e00-\u9fff]', name) or (iid == 268477 and name == 'P.O.W. x3')
    assert ids <= server.NAMES.keys()
    assert len(server.ENCHANT_NAMES) == 100
    assert all(not re.search('[a-zA-Z]', record['name']) for record in server.ENCHANT_NAMES.values())
    assert server.NAMES[273781] == '护卫之牙束带'
    assert server.INSTANCE_NAMES[1309] == '夺目谷'
    assert set(server.ENCOUNTER_NAMES) == {2849, 2888, 2874, 2894, 2882, 2871, 2887, 2883, 2895}
    # The pinned replay inputs are public; historical engines/reports remain manual.
    import hashlib
    for manifest_path in sorted(server.RESEARCH.glob('raidbots-*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for sample in manifest['samples']:
            path = manifest_path.parent / (sample['spec'] + '.input.simc')
            if 'input_sha256' in sample:
                assert hashlib.sha256(path.read_bytes()).hexdigest() == sample['input_sha256']
            assert sample['snapshot']['attribute']
            assert sample['snapshot']['stats']


def test_enchant_masks_localized_labels_and_retained_unknown(rules):
    s = rules
    assert [x['id'] for x in s.enchant_options({'id': '3'})] == ['7967']
    assert not s.enchant_options({'id': '2'})
    assert [x['id'] for x in s.enchant_options({'id': '10'})] == ['3368']
    assert not s.enchant_options({'id': '10'}, 'mage')
    option = s.enchant_options({'id': '3'})[0]
    assert not option['label'].startswith('附魔')
    assert '品质 3' in option['label'] and '21 急速' in option['label']
    assert s.enchant_options({'id': '2', 'enchant_id': '999'})[-1]['label'] == '保留原导入附魔 · 999'
    model = character(); model['gear']['finger1'] = ',id=3,bonus_id=100'
    changed = s.apply_edit(model, {'slot': 'finger1', 'enchant_id': '7967'})
    assert s.apply_edit(changed, {'slot': 'finger1', 'enchant_id': ''}) == model
    for slot, iid, eid in [('neck', 2, '7967'), ('chest', 5, '7991'), ('main_hand', 11, '3368')]:
        model['gear'][slot] = f',id={iid},bonus_id=100'
        with pytest.raises(ValueError): s.apply_edit(model, {'slot': slot, 'enchant_id': eid})


def test_socket_addition_uniqueness_and_position_are_atomic(rules):
    s = rules
    model = character(); model['gear'] = {'neck': ',id=2,bonus_id=100', 'finger1': ',id=3,bonus_id=100/13668'}
    for slot, iid in [('head', 1), ('wrist', 6), ('waist', 7)]:
        model['gear'][slot] = f',id={iid},bonus_id=100'
        changed = s.apply_edit(model, {'slot': slot, 'gem_id': '240904'})
        assert s.gear_fields(changed['gear'][slot])['bonus_id'] == '100/13668'
        assert s.gem_sockets(s.gear_fields(changed['gear'][slot])) == ['PRISMATIC']
        with pytest.raises(ValueError): s.apply_edit(changed, {'slot': slot, 'gem_id': '240904', 'gemIndex': 1})
        removed = s.apply_edit(changed, {'slot': slot, 'gem_id': ''})
        assert 'gem_id' not in s.gear_fields(removed['gear'][slot])
    unique = s.apply_edit(model, {'slot': 'neck', 'gem_id': '240983'})
    before = copy.deepcopy(unique)
    with pytest.raises(ValueError): s.apply_edit(unique, {'slot': 'finger1', 'gem_id': '240967'})
    assert unique == before
    model['gear']['neck'] = ',id=2,bonus_id=100/13668'
    second = s.apply_edit(model, {'slot': 'neck', 'gem_id': '240894', 'gemIndex': 1})
    assert s.gear_fields(second['gear']['neck'])['gem_id'] == '0/240894'
    first = s.apply_edit(second, {'slot': 'neck', 'gem_id': '240904'})
    assert s.gear_fields(s.apply_edit(first, {'slot': 'neck', 'gem_id': ''})['gear']['neck'])['gem_id'] == '0/240894'
    for slot, iid, gid in [('chest', 5, '240894'), ('neck', 2, '34220')]:
        model['gear'][slot] = f',id={iid},bonus_id=100'
        with pytest.raises(ValueError): s.apply_edit(model, {'slot': slot, 'gem_id': gid})
    assert s.gem_sockets({'id': '999'}) == []
    assert s.gem_sockets({'id': '999', 'gem_id': '240894'}) == ['PRISMATIC']


def test_source_aware_levels_keep_distinct_tracks_and_redirects(rules):
    s = rules
    options = s.level_options({'id': '2', 'bonus_id': '100'})
    assert [(x['key'], x['level']) for x in options] == [
        ('upgrade:100', 305), ('upgrade:102', 305), ('upgrade:101', 308), ('upgrade:103', 334)]
    assert s.current_level_key({'id': '2', 'bonus_id': '102'}, options) == 'upgrade:102'
    assert s.level_options({'id': '19', 'redirected_base_stats': '2'}) == s.level_options({'id': '2'})
    assert s.level_options({'id': '19', 'redirected_base_stats': '19'}) == []
    crafted = s.level_options({'id': '4'})
    assert len(crafted) == 15
    assert crafted[-1]['level'] == 331 and crafted[-1]['quality'] == 5
    assert s.current_level_key({'id': '4', 'bonus_id': '13751/13836/12497'}, crafted) == 'craft:13836:12497'
    s.ITEMS[3]['sources'] = [{'instanceId': 1320, 'encounterId': 2895}]
    s.ENCOUNTERS[(1320, 2895)] = {'itemSequenceLevel': 4}
    fixed = s.level_options({'id': '3'})
    assert fixed[-1] == {'key': 'fixed:344', 'level': 344, 'label': '344 · 神话特殊掉落', 'bonuses': [], 'explicit': 344}
    assert s.current_level_key({'id': '3', 'ilevel': '344'}, fixed) == 'fixed:344'


def test_level_and_crafted_edits_preserve_unrelated_variant_fields(rules):
    s = rules
    model = character(); model['gear'] = {'finger1': ',id=3,bonus_id=100/13668,gem_id=240894,enchant_id=7967'}
    changed = s.apply_edit(model, {'slot': 'finger1', 'levelVariant': 'upgrade:102'})
    fields = s.gear_fields(changed['gear']['finger1'])
    assert fields == {'id': '3', 'bonus_id': '13668/102', 'gem_id': '240894', 'enchant_id': '7967'}
    same_level = s.apply_edit(changed, {'slot': 'finger1', 'level': 305})
    assert s.current_level_key(s.gear_fields(same_level['gear']['finger1']), s.level_options(fields)) == 'upgrade:102'
    for edit in ({'level': 999}, {'levelVariant': 'upgrade:12817'}):
        with pytest.raises(ValueError): s.apply_edit(model, {'slot': 'finger1', **edit})
    crafted = character(); crafted['gear']['finger1'] = ',id=4,bonus_id=13751/13836/12497/8790,crafted_stats=32/36'
    updated = s.apply_edit(crafted, {'slot': 'finger1', 'crafted': '32/49'})
    assert s.gear_fields(updated['gear']['finger1'])['crafted_stats'] == '32/49'
    assert '8790' not in s.gear_fields(updated['gear']['finger1'])['bonus_id'].split('/')
    assert '8791' in s.gear_fields(updated['gear']['finger1'])['bonus_id'].split('/')
    for pair in ('49/32', '32/36\ninput=file'):
        with pytest.raises(ValueError): s.apply_edit(crafted, {'slot': 'finger1', 'crafted': pair})
    assert model['gear']['finger1'].endswith('enchant_id=7967')


def test_bulk_levels_min_max_exact_and_restore_keep_edits(rules):
    s = rules
    original = character(); original['gear'] = {'head': ',id=1,bonus_id=100,enchant_id=7991',
                                               'finger1': ',id=3,bonus_id=100/13668,gem_id=240894,enchant_id=7967'}
    maximum = s.apply_edit(original, {'bulkLevel': 'maximum', 'skipUnsupported': True})
    assert all(s.current_level_key(s.gear_fields(v), s.level_options(s.gear_fields(v))) == 'upgrade:103' for v in maximum['gear'].values())
    minimum = s.apply_edit(maximum, {'bulkLevel': 'minimum', 'skipUnsupported': True})
    for value in minimum['gear'].values():
        fields = s.gear_fields(value)
        options = s.level_options(fields)
        selected = s.current_level_key(fields, options)
        assert next(option['level'] for option in options if option['key'] == selected) == 305
    mixed = copy.deepcopy(original)
    mixed['gear']['finger2'] = ',id=4,bonus_id=13751/12497/13668/8790,crafting_quality=5,crafted_stats=32/36,gem_id=240904,enchant_id=7967'
    before = copy.deepcopy(mixed)
    exact = s.apply_edit(mixed, {'bulkLevel': 334, 'skipUnsupported': True})
    for slot in ('head', 'finger1'):
        fields = s.gear_fields(exact['gear'][slot])
        assert s.current_level_key(fields, s.level_options(fields)) == 'upgrade:103'
        previous = s.gear_fields(before['gear'][slot])
        for key in ('gem_id', 'enchant_id', 'crafted_stats'):
            assert fields.get(key) == previous.get(key)
    assert exact['gear']['finger2'] == before['gear']['finger2']
    assert mixed == before
    assert s.apply_edit(original, {'bulkLevel': 999, 'skipUnsupported': True}) == original
    with pytest.raises(ValueError): s.apply_edit(original, {'bulkLevel': 999})
    with pytest.raises(ValueError): s.apply_edit(original, {'bulkLevel': True})
    edited = s.apply_edit(maximum, {'slot': 'head', 'enchant_id': ''})
    # Independent saved reference metadata at the IO boundary, not native scoring.
    reference = {'complete': True, 'items': {'head': {'ilevel': 305, 'fields': {'id': '1', 'bonus_id': '100'}},
        'finger1': {'ilevel': 305, 'fields': {'id': '3', 'bonus_id': '100/13668'}}}}
    with patch.object(s, 'calculate', return_value=reference):
        restored = s.apply_edit(edited, {'bulkLevel': 'restore', 'original': original})
    assert s.gear_fields(restored['gear']['head']) == {'id': '1', 'bonus_id': '100'}
    ring = s.gear_fields(restored['gear']['finger1'])
    assert ring['gem_id'] == '240894' and ring['enchant_id'] == '7967'
    assert '100' in ring['bonus_id'].split('/')
    assert original['gear']['head'].endswith('enchant_id=7991')


def test_replacement_preserves_level_gems_enchants_and_requires_exact_fallback(rules):
    s = rules
    model = character(); model['gear']['finger1'] = ',id=3,bonus_id=100/13668,gem_id=240894,enchant_id=7967'
    index = candidate(s, 'finger1', 4)
    changed = s.apply_edit(model, {'slot': 'finger1', 'candidate': index})
    fields = s.gear_fields(changed['gear']['finger1'])
    assert fields['id'] == '4' and fields['gem_id'] == '240894' and fields['enchant_id'] == '7967'
    assert s.current_level_key(fields, s.level_options(fields)) == 'craft:13751:12497'
    same = s.apply_edit(model, {'slot': 'finger1', 'candidate': candidate(s, 'finger1', 3)})
    assert s.gear_fields(same['gear']['finger1']) == s.gear_fields(model['gear']['finger1'])
    high = copy.deepcopy(model); high['gear']['finger1'] = ',id=3,bonus_id=103/13668,gem_id=240894,enchant_id=7967'
    with pytest.raises(s.ReplacementLevelError) as error:
        s.apply_edit(high, {'slot': 'finger1', 'candidate': index})
    assert error.value.alternative_level == 331
    with pytest.raises(s.ReplacementLevelError):
        s.apply_edit(high, {'slot': 'finger1', 'candidate': index, 'acceptLevelChange': 334})
    accepted = s.apply_edit(high, {'slot': 'finger1', 'candidate': index, 'acceptLevelChange': 331})
    assert s.current_level_key(s.gear_fields(accepted['gear']['finger1']), s.level_options({'id': '4'})) == 'craft:13836:12497'
    assert high['gear']['finger1'].startswith(',id=3,')
    # Outside-pool original restores only the item, not removed gems/enchants.
    removed = s.apply_edit(changed, {'slot': 'finger1', 'gem_id': ''})
    removed = s.apply_edit(removed, {'slot': 'finger1', 'enchant_id': ''})
    restored = s.apply_edit(removed, {'slot': 'finger1', 'originalItem': model['gear']['finger1']})
    assert s.gear_fields(restored['gear']['finger1']) == {'id': '3', 'bonus_id': '102/13668'}
    with pytest.raises(ValueError): s.apply_edit(model, {'slot': 'feet', 'originalItem': model['gear']['finger1']})
    conversion = character(); conversion['gear']['chest'] = ',id=5,bonus_id=100/13662'
    converted = s.apply_edit(conversion, {'slot': 'chest', 'candidate': candidate(s, 'chest', 19)})
    assert s.gear_fields(converted['gear']['chest']) == {'id': '19', 'bonus_id': '100/13662', 'redirected_base_stats': '5'}
    conversion['gear']['chest'] = ',id=5,bonus_id=100'
    with pytest.raises(ValueError): s.apply_edit(conversion, {'slot': 'chest', 'candidate': candidate(s, 'chest', 19)})


def test_sources_crafted_dungeon_raid_token_redirect_and_unknown(rules):
    s = rules
    s.INSTANCES.update({1309: {'id': 1309, 'name': 'Vale', 'type': 'dungeon'}, 1320: {'id': 1320, 'name': 'Raid', 'type': 'raid'}})
    s.ENCOUNTERS[(1320, 2895)] = {'id': 2895, 'name': 'Last boss'}
    s.ITEMS[2]['sources'] = [{'instanceId': 1309, 'encounterId': 1}]
    s.ITEMS[3]['sources'] = [{'instanceId': 1320, 'encounterId': 2895}]
    assert s.equipment_sources({'id': '4'}) == {'summary': '制作 · 珠宝加工', 'details': ['制作专业：珠宝加工']}
    assert s.equipment_sources({'id': '2'}) == {'summary': '大秘境 · 夺目谷', 'details': ['大秘境 · 夺目谷']}
    s.GROUPS['raid_token_products'].add(19)
    s.ITEMS[20] = {'id': 20, 'contains': [19], 'sources': [{'instanceId': 1320, 'encounterId': 2895}]}
    s.INVENTORY['excluded_raid_tokens'] = [20]
    token = s.equipment_sources({'id': '19'})
    assert token == {'summary': '团本 · 烈毒之渊', 'details': ['团本 · 烈毒之渊 · 乌拉特克']}
    redirected = s.equipment_sources({'id': '19', 'redirected_base_stats': '2'})
    assert redirected['summary'] == '催化转化 · 大秘境 · 夺目谷'
    assert redirected['details'][0].startswith('催化转化：原装备 ')
    assert '来源待确认' in s.equipment_sources({'id': '999'})['summary']
    info = s.item_info(',id=2')
    assert info['english'] == 'Neck' and info['id'] == 2


def test_equip_and_fit_separate_armor_primary_loot_and_weapon_rules(rules):
    s = rules
    expected_armor = {'deathknight': 4, 'demonhunter': 2, 'rogue': 2, 'warlock': 1, 'mage': 1,
                      'paladin': 4, 'hunter': 3, 'shaman': 3, 'warrior': 4, 'priest': 1,
                      'druid': 2, 'monk': 2, 'evoker': 3}
    for cls, armor in expected_armor.items():
        for spec in s.CLASS_SPECS[cls]:
            item = {'itemClass': 4, 'itemSubClass': armor, 'inventoryType': 5}
            assert not s.fit_reason(item, spec, 'chest', cls), (cls, spec)
            item['itemSubClass'] = 1 if armor != 1 else 2
            assert s.fit_reason(item, spec, 'chest', cls), (cls, spec)
    for stat, holy, agility in ((72, False, True), (73, True, True), (74, True, False), (71, True, True)):
        item = {'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 12, 'stats': [{'id': stat}]}
        assert (not s.fit_reason(item, 'holy', 'trinket1', 'paladin')) == holy
        assert (not s.fit_reason(item, 'havoc', 'trinket1', 'demonhunter')) == agility
    assert not s.fit_reason({'itemClass': 4, 'inventoryType': 12, 'itemSubClass': 0})  # statless/missing mask stays visible
    assert s.fit_reason({**s.ITEMS[1], 'specs': [64]}, 'blood', 'head') == '掉落专精不含当前专精'
    assert s.equip_reason({**s.ITEMS[1], 'allowableClasses': [8]}, 'deathknight') == '其他职业专属'
    # Independent legal/illegal pairs for every distinct weapon mechanism.
    cases = [
        ('deathknight', 'blood', 'main_hand', 11, 10), ('deathknight', 'frost', 'main_hand', 10, 12),
        ('demonhunter', 'havoc', 'main_hand', 10, 11), ('rogue', 'assassination', 'main_hand', 15, 10),
        ('rogue', 'subtlety', 'main_hand', 15, 10), ('rogue', 'outlaw', 'main_hand', 10, 15),
        ('warlock', 'affliction', 'off_hand', 14, 10), ('mage', 'frost', 'main_hand', 12, 11),
        ('paladin', 'holy', 'main_hand', 10, 11), ('paladin', 'protection', 'off_hand', 13, 14),
        ('paladin', 'retribution', 'main_hand', 11, 10), ('hunter', 'marksmanship', 'main_hand', 17, 10),
        ('hunter', 'survival', 'main_hand', 10, 17), ('shaman', 'enhancement', 'off_hand', 16, 14),
        ('shaman', 'elemental', 'off_hand', 13, 16), ('warrior', 'arms', 'main_hand', 11, 10),
        ('warrior', 'fury', 'off_hand', 11, 10), ('warrior', 'protection', 'off_hand', 13, 11),
        ('priest', 'holy', 'main_hand', 18, 10), ('druid', 'balance', 'off_hand', 14, 18),
        ('monk', 'mistweaver', 'off_hand', 14, 18), ('monk', 'windwalker', 'off_hand', 18, 14),
        ('evoker', 'devastation', 'off_hand', 14, 10),
    ]
    for cls, spec, slot, good, bad in cases:
        assert not s.fit_reason(s.ITEMS[good], spec, slot, cls), (cls, spec, good)
        assert s.fit_reason(s.ITEMS[bad], spec, slot, cls), (cls, spec, bad)
    assert not s.fit_reason({**s.ITEMS[15], 'specs': [259]}, 'outlaw', 'off_hand', 'rogue')
    for subtype in (2, 3, 18):
        assert s.occupies_both_hands({'itemClass': 2, 'itemSubClass': subtype, 'inventoryType': 26})
    assert not s.occupies_both_hands({'itemClass': 2, 'itemSubClass': 19, 'inventoryType': 26})


def test_weapon_replacement_and_offhand_guards_are_atomic(rules):
    s = rules
    # Each class/spec here has a different production weapon policy. No engine calls.
    pairs = [('mage', 'frost', 15, 12, 14), ('warlock', 'affliction', 15, 12, 14),
             ('priest', 'shadow', 18, 12, 14), ('evoker', 'devastation', 15, 12, 14),
             ('druid', 'balance', 18, 12, 14), ('monk', 'mistweaver', 18, 12, 14),
             ('monk', 'windwalker', 18, 12, 18), ('hunter', 'survival', 10, 11, 10),
             ('shaman', 'elemental', 18, 12, 13), ('shaman', 'enhancement', 16, 12, 16),
             ('paladin', 'protection', 10, 11, 13)]
    for cls, spec, one, two, off in pairs:
        model = character(cls, spec)
        model['gear'] = {'main_hand': f',id={one},bonus_id=100', 'off_hand': f',id={off},bonus_id=100'}
        changed = s.apply_edit(model, {'slot': 'main_hand', 'candidate': candidate(s, 'main_hand', two)})
        assert 'off_hand' not in changed['gear'], (cls, spec)
        before = copy.deepcopy(changed)
        with pytest.raises(ValueError, match='先选择单手'):
            s.apply_edit(changed, {'slot': 'off_hand', 'candidate': candidate(s, 'off_hand', off)})
        assert changed == before
        back = s.apply_edit(changed, {'slot': 'main_hand', 'candidate': candidate(s, 'main_hand', one)})
        dual = s.apply_edit(back, {'slot': 'off_hand', 'candidate': candidate(s, 'off_hand', off)})
        assert s.gear_fields(dual['gear']['off_hand'])['id'] == str(off)
    fury = character('warrior', 'fury'); fury['gear'] = {'main_hand': ',id=11,bonus_id=100'}
    dual = s.apply_edit(fury, {'slot': 'off_hand', 'candidate': candidate(s, 'off_hand', 11)})
    assert set(dual['gear']) == {'main_hand', 'off_hand'}
    assert s.apply_edit(dual, {'slot': 'off_hand', 'remove': True}) == fury
    for cls, spec, off in [('warrior', 'arms', 13), ('warrior', 'protection', 10),
                           ('monk', 'mistweaver', 18), ('monk', 'windwalker', 14), ('mage', 'frost', 10)]:
        model = character(cls, spec); model['gear']['main_hand'] = ',id=18,bonus_id=100'
        with pytest.raises(ValueError): s.apply_edit(model, {'slot': 'off_hand', 'candidate': candidate(s, 'off_hand', off)})


def test_tooltip_effects_parse_plaintext_levels_and_all_spec_set_rows_without_io():
    tooltip = ('<!--ilvl-->321<!--useText:0:1--><b>装备：</b>获得 &amp; 护盾<!--useText:1-->'
               '<a href="/item-set=1">套装</a><!--itemeffectspec250:0-->(2) 鲜血效果<!--itemeffectspec-->'
               '<!--itemeffectspec250:0-->(4) 鲜血效果<!--itemeffectspec-->'
               '<!--itemeffectspec64:0-->(2) 冰霜效果<!--itemeffectspec-->'
               '<!--itemeffectspec64:0-->(4) 冰霜效果<!--itemeffectspec-->')
    with patch.object(Path, 'mkdir'), patch.object(Path, 'exists', return_value=False), \
         patch.object(Path, 'write_text'), \
         patch.object(server.urllib.request, 'urlopen', return_value=nullcontext(__import__('io').StringIO(json.dumps({'tooltip': tooltip})))):
        result = server.item_effects({'itemId': 271474, 'level': 321})
        assert result['effects'] == ['装备：获得 & 护盾']
        assert result['setEffects'] == ['(2) 鲜血效果', '(4) 鲜血效果']
        assert result['setEffectsBySpec']['64'] == ['(2) 冰霜效果', '(4) 冰霜效果']
        assert result['setName'] == '套装'
        assert 'error' in server.item_effects({'itemId': 271474, 'level': 311})
    for data in ({'itemId': 1, 'level': 311, 'bonuses': '../secret'}, {'itemId': True, 'level': 311}, {'itemId': 1, 'level': 0}):
        with pytest.raises(ValueError): server.item_effects(data)
    cached = {'effects': [], 'source': 'https://nether.wowhead.com/tooltip/item/271474?bonus=100%3A13668', 'level': 321,
              'setName': '套装', 'setEffectsBySpec': {'250': ['(2) 鲜血', '(4) 鲜血']}}
    with patch.object(Path, 'mkdir'), patch.object(Path, 'exists', return_value=True), \
         patch.object(Path, 'read_text', return_value=json.dumps(cached)), \
         patch.object(Path, 'glob', return_value=[Path('cached.json')]), \
         patch.object(server.urllib.request, 'urlopen', side_effect=AssertionError('cache hit reached network')):
        assert server.item_effects({'itemId': 271474, 'level': 321}) == cached
        assert server.cached_effects() == {'271474|321|100/13668': cached}
    with patch.object(Path, 'mkdir'), patch.object(Path, 'exists', return_value=False), \
         patch.object(server.urllib.request, 'urlopen', side_effect=AssertionError('cache-only reached network')):
        assert server.item_effects({'itemId': 1, 'level': 311}, cache_only=True)['error']


def test_engine_route_flags_and_native_errors_never_become_success(rules):
    s = rules
    experimental = {('priest', 'discipline'), ('priest', 'holy'), ('paladin', 'holy'), ('monk', 'mistweaver'), ('evoker', 'preservation')}
    # Direct local IO mocks: no temporary files, engine process or fake runner.
    with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
         patch.object(Path, 'write_text'), patch.object(Path, 'exists', return_value=False), \
         patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='native rejected input')) as process:
        for cls, specs in s.CLASS_SPECS.items():
            for spec in specs:
                rejected = character(cls, spec)
                rejected['gear']['head'] = ',id=999999999'
                result = s.calculate(rejected)
                assert result['model'] == rejected
                assert result['complete'] is False and 'values' not in result
                args = process.call_args.args[0]
                assert args[0] == str(s.MISTWEAVER_EXE if (cls, spec) == ('monk', 'mistweaver') else s.HOLY_EXE if (cls, spec) == ('paladin', 'holy') else s.EXE)
                assert ('allow_experimental_specializations=1' in args) == ((cls, spec) in experimental)
                assert ('target_level=90' in args) == ((cls, spec) == ('monk', 'mistweaver'))
                assert 'threads=1' in args and 'item_db_source=local' in args
        assert result['diagnostic'] == 'native rejected input'
    empty = {'sim': {'players': [{'collected_data': {'buffed_stats': {'stats': {}, 'attribute': {}}}}]}}
    with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
         patch.object(Path, 'write_text'), patch.object(Path, 'exists', return_value=True), \
         patch.object(Path, 'read_text', return_value=json.dumps(empty)), \
         patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
        result = s.calculate(character())
        assert result['complete'] is False and 'values' not in result
    with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
         patch.object(Path, 'write_text'), patch.object(s.subprocess, 'run', side_effect=s.subprocess.TimeoutExpired('simc', 12)):
        with pytest.raises(s.subprocess.TimeoutExpired): s.calculate(character())


def test_independent_public_snapshot_is_decoded_without_computing_fake_scores(rules):
    s = rules
    # Saved upstream Raidbots data, not synthesized from ITEMS/GEMS/ENCHANTS.
    sample = json.loads((s.RESEARCH / 'raidbots-deathknight/manifest.json').read_text())['samples'][0]
    report = {'sim': {'players': [{'collected_data': {'buffed_stats': sample['snapshot']}, 'gear': sample['gear']}]}}
    model = character(); model['gear']['main_hand'] = ',id=11,bonus_id=100'
    with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
         patch.object(Path, 'write_text'), patch.object(Path, 'exists', return_value=True), \
         patch.object(Path, 'read_text', return_value=json.dumps(report)), \
         patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
        result = s.calculate(model)
    assert result['complete'] and result['values']['strength'] == 2545
    assert result['values']['haste'] == 1228 and result['values']['armor'] == 3957.775
    assert result['values']['crit_pct'] == 32.065217391304344
    assert result['items']['main_hand']['raw'] == sample['gear']['main_hand']
    assert result['items']['main_hand']['ilevel'] == 344
    assert result['values']['ilevel'] == 339.25
    assert result['items']['main_hand']['sourceInfo']['summary'] == '导入装备 · 来源待确认'
    # A native average uses all 16 slots; Fury must not double-count its main hand.
    fury_sample = next(row for row in json.loads((s.RESEARCH / 'raidbots-warrior/manifest.json').read_text())['samples'] if row['spec'] == 'fury')
    assert fury_sample['spec'] == 'fury'
    report['sim']['players'][0]['gear'] = fury_sample['gear']
    model = character('warrior', 'fury'); model['gear'] = {'main_hand': ',id=11,bonus_id=100', 'off_hand': ',id=11,bonus_id=100'}
    with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
         patch.object(Path, 'write_text'), patch.object(Path, 'exists', return_value=True), \
         patch.object(Path, 'read_text', return_value=json.dumps(report)), \
         patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
        result = s.calculate(model)
    assert result['values']['ilevel'] == 338.625


def test_merge_selection_distinguishes_same_id_variants_and_survives_replacement(rules):
    s = rules
    model = character(); model['gear']['head'] = ',id=1,bonus_id=100/6652'
    for row in s.CATALOG['head']:
        row['fitReasonsBySpec']['deathknight:blood'] = ''
    # Existing native-evidence seam: two explicitly distinct outcomes, no score math.
    evidence = {',id=1,bonus_id=100/6652': {'raw': {'speed_rating': 22}},
                ',id=1,bonus_id=100': {'raw': {'speed_rating': 0}}}
    with patch.object(s, 'replacement_signature', side_effect=lambda slot, value, probe_json=None: evidence[value]):
        original = {'head': model['gear']['head']}
        matched = s.original_matches(model, original)
        assert matched['head'] == [] and matched['_selected']['head'] == ['original']
        changed = s.apply_edit(model, {'slot': 'head', 'candidate': 0})
        selected = s.original_matches(changed, original)
        assert selected['head'] == [] and selected['_selected']['head'] == [0]
        returned = s.apply_edit(changed, {'slot': 'head', 'originalItem': original['head']})
        assert s.original_matches(returned, original)['_selected']['head'] == ['original']
    # Equivalent outcomes differing only in non-stat bonus metadata still merge.
    with patch.object(s, 'replacement_signature', return_value={'raw': {'stamina': 3002}}):
        assert s.original_matches(model, {'head': model['gear']['head']})['head'] == [0]
        changed = s.apply_edit(model, {'slot': 'head', 'candidate': 0})
        assert s.original_matches(changed, {'head': model['gear']['head']})['head'] == [0]
    with pytest.raises(ValueError): s.original_matches(model, {'private': ',id=1'})
    assert model['gear']['head'] == ',id=1,bonus_id=100/6652'


def test_replacement_signature_retains_real_stat_and_effect_discriminators(rules):
    s = rules
    s.replacement_signature.cache_clear()
    item = {'id': 1, 'ilevel': 305, 'fields': {'id': '1', 'bonus_id': '100/13668',
            'enchant_id': '7991', 'gem_id': '240894', 'gem_bonus_id': '1'},
            'raw': {'encoded_item': 'display-only-name', 'stamina': 3002, 'speed_rating': 22},
            'gemSlots': ['PRISMATIC']}
    effects = {'effects': ['获得护盾'], 'setEffectsBySpec': {'250': ['(2) 鲜血']}}
    model = character(); model['gear']['head'] = ',id=1,bonus_id=100/13668'
    with patch.object(s, 'calculate', return_value={'complete': True, 'items': {'head': item}}), \
         patch.object(s, 'item_effects', return_value=effects):
        signature = s.replacement_signature('head', model['gear']['head'], json.dumps(model))
    assert signature == {'raw': {'stamina': 3002, 'speed_rating': 22}, 'effects': ['获得护盾'],
        'sets': {'250': ['(2) 鲜血']}, 'id': 1, 'redirected': None, 'gems': '240894',
        'gemBonuses': '1', 'enchant': '7991', 'sockets': ['PRISMATIC']}
    s.replacement_signature.cache_clear()
    with patch.object(s, 'calculate', return_value={'complete': False}):
        with pytest.raises(ValueError, match='无法确认换装结果'):
            s.replacement_signature('head', model['gear']['head'], json.dumps(model))
    with patch.object(s, 'calculate', return_value={'complete': True, 'items': {'head': item}}), \
         patch.object(s, 'item_effects', return_value={'error': 'uncached'}):
        with pytest.raises(ValueError, match='无法确认装备特效'):
            s.replacement_signature('head', model['gear']['head'], json.dumps(model))
    s.replacement_signature.cache_clear()


def test_every_specialization_has_the_expected_primary_and_loot_identity(rules):
    s = rules
    expected = {
        'deathknight': {'blood': 4, 'frost': 4, 'unholy': 4},
        'demonhunter': {'havoc': 3, 'vengeance': 3, 'devourer': 5},
        'rogue': {'assassination': 3, 'outlaw': 3, 'subtlety': 3},
        'warlock': {'affliction': 5, 'demonology': 5, 'destruction': 5},
        'mage': {'arcane': 5, 'fire': 5, 'frost': 5},
        'paladin': {'holy': 5, 'protection': 4, 'retribution': 4},
        'hunter': {'beast_mastery': 3, 'marksmanship': 3, 'survival': 3},
        'shaman': {'elemental': 5, 'enhancement': 3, 'restoration': 5},
        'warrior': {'arms': 4, 'fury': 4, 'protection': 4},
        'priest': {'discipline': 5, 'holy': 5, 'shadow': 5},
        'druid': {'balance': 5, 'feral': 3, 'guardian': 3, 'restoration': 5},
        'monk': {'brewmaster': 3, 'mistweaver': 5, 'windwalker': 3},
        'evoker': {'devastation': 5, 'preservation': 5, 'augmentation': 5},
    }
    for cls, specs in expected.items():
        for spec, primary in specs.items():
            for stat in (3, 4, 5):
                item = {'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 12, 'stats': [{'id': stat}]}
                assert (not s.fit_reason(item, spec, 'trinket1', cls)) == (stat == primary), (cls, spec, stat)
            item = {'itemClass': 4, 'itemSubClass': 0, 'inventoryType': 12, 'specs': [s.CLASS_SPECS[cls][spec]]}
            assert not s.fit_reason(item, spec, 'trinket1', cls)
            item['specs'] = [-1]
            assert s.fit_reason(item, spec, 'trinket1', cls) == '掉落专精不含当前专精'
    for spec in ('feral', 'guardian'):
        assert s.fit_reason({**s.ITEMS[14], 'stats': [{'id': 5}]}, spec, 'off_hand', 'druid')
    for spec in ('beast_mastery', 'marksmanship'):
        for subtype in (2, 3, 18):
            item = {'itemClass': 2, 'itemSubClass': subtype, 'inventoryType': 26}
            assert not s.fit_reason(item, spec, 'main_hand', 'hunter')
            assert s.fit_reason(item, spec, 'off_hand', 'hunter')


def test_average_item_level_empty_cosmetic_missing_and_fury_rules(rules):
    s = rules
    sample = json.loads((s.RESEARCH / 'raidbots-deathknight/manifest.json').read_text())['samples'][0]
    # Known literal gear output shapes exercise averaging only, not native scoring.
    cases = [
        ('deathknight', 'blood', {'main_hand': ',id=11'}, {'main_hand': {'ilevel': 320}}, 40),
        ('mage', 'frost', {'main_hand': ',id=15', 'off_hand': ',id=14'}, {'main_hand': {'ilevel': 320}, 'off_hand': {'ilevel': 304}}, 39),
        ('warrior', 'fury', {'main_hand': ',id=11', 'off_hand': ',id=11'}, {'main_hand': {'ilevel': 320}, 'off_hand': {'ilevel': 304}}, 39),
        ('deathknight', 'blood', {'head': ',id=1'}, {}, None),
        ('deathknight', 'blood', {'shirt': ',id=1,ilevel=999'}, {'shirt': {'ilevel': 999}}, 0),
        ('deathknight', 'blood', {'finger1': ',id=3,ilevel=305'}, {}, 19.0625),
    ]
    for cls, spec, selected, gear, expected in cases:
        model = character(cls, spec); model['gear'] = selected
        # Head is stat-bearing, so missing native gear cannot silently get a level.
        s.ITEMS[1]['stats'] = [{'id': 4}]
        report = {'sim': {'players': [{'collected_data': {'buffed_stats': sample['snapshot']}, 'gear': gear}]}}
        with patch.object(s.tempfile, 'TemporaryDirectory', return_value=nullcontext('/unused-gear-io')), \
             patch.object(Path, 'write_text'), patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'read_text', return_value=json.dumps(report)), \
             patch.object(s.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
            result = s.calculate(model)
        assert result['values']['ilevel'] == expected, (cls, spec)


def test_concurrent_attribute_read_never_observes_unfinished_research_tables():
    spec = importlib.util.spec_from_file_location('gear_atomic_read', SPEC.origin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paused, release, reader_started = threading.Event(), threading.Event(), threading.Event()
    errors, values = [], []
    # Tiny read-boundary records only reach the pause, never form a fake catalog.
    inputs = {'equippable-items.json': '[]', 'bonuses.json': '{}',
              'gems.json': '[{"id":240894,"enchantId":5,"name":"公开宝石"}]',
              'enchantments-all.json': '[{"id":5,"expansion":11,"equipRequirements":{"itemClass":4}}]'}

    def read(path, *args, **kwargs):
        if path.name == 'item-conversions.json':
            paused.set()
            if not release.wait(2):
                raise TimeoutError('controlled initializer was not released')
            raise OSError('incomplete research input')
        return inputs[path.name]

    def initialize():
        try:
            module.load_data()
        except BaseException as error:
            errors.append(error)

    def read_attribute():
        reader_started.set()
        try:
            values.append(module.GEMS)
        except BaseException as error:
            errors.append(error)

    initializer = threading.Thread(target=initialize)
    reader = threading.Thread(target=read_attribute)
    with patch.object(Path, 'read_text', autospec=True, side_effect=read):
        initializer.start()
        try:
            assert paused.wait(2), 'initializer never reached controlled read'
            visible_while_building = set(vars(module)) & set(module._DATA_NAMES)
            reader.start()
            assert reader_started.wait(2)
        finally:
            release.set()
            initializer.join(2)
            if reader.ident is not None:
                reader.join(2)
    assert not initializer.is_alive() and not reader.is_alive()
    assert visible_while_building == set()
    assert values == []
    assert len(errors) == 2 and all(isinstance(error, OSError) for error in errors)
    assert not (set(vars(module)) & set(module._DATA_NAMES))


def test_lazy_research_io_failure_does_not_mark_partial_data_ready():
    assert 'ITEMS' not in vars(server)
    with patch.object(Path, 'read_text', side_effect=['[]', OSError('unavailable research input')]):
        with pytest.raises(OSError, match='unavailable research input'):
            server.load_data()
    assert 'ITEMS' not in vars(server)
    with patch.object(Path, 'read_text', side_effect=OSError('retry requires research input')):
        with pytest.raises(OSError, match='retry requires research input'):
            server.item_info(',id=1')
