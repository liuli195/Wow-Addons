"""已审核爆发的发布和约束规则直接使用内存输入。"""
import pytest
import task
from test_character_export import sample_profile
import copy
import json
from pathlib import Path


def reviewed_fixture():
    definition = json.loads((Path(task.__file__).parent / 'burst/unholy.json').read_text(encoding='utf-8'))
    profile = sample_profile().replace('id=250245', 'id=273795').replace('id=250228', 'id=273796')
    character = task.parse_character(profile)
    from burst import talent_hash
    definition['talent_hashes'] = [talent_hash(character)]
    definition['reviewer'] = 'isolated test fixture'
    return definition, profile


def test_public_burst_rejects_draft_corruption(monkeypatch):
    import burst
    from unittest.mock import Mock
    definition, _ = reviewed_fixture()
    draft = copy.deepcopy(definition)
    draft['status'] = 'draft'
    write = Mock()
    monkeypatch.setattr(burst, 'write', write)
    with pytest.raises(ValueError, match='未审核'):
        burst.publish(draft)
    write.assert_not_called()
    row = dict(definition, definition_id=burst.definition_id(definition))
    corrupted = copy.deepcopy(row)
    corrupted['plan']['start_ms'] = 6000
    monkeypatch.setattr(burst, 'read_records', Mock(return_value=[corrupted]))
    with pytest.raises(ValueError, match='身份不符'):
        burst.load(252)
    assert row['plan']['start_ms'] == 3000


def test_public_burst_storage_failure_keeps_the_previous_version(monkeypatch):
    import burst
    from unittest.mock import Mock
    definition, _ = reviewed_fixture()
    original = dict(definition, definition_id=burst.definition_id(definition))
    newer = copy.deepcopy(definition)
    newer['version'] = 'test-next-version'
    newer['instructions'] += ' New reviewed instruction.'
    read = Mock(return_value=[original])
    monkeypatch.setattr(burst, 'read_records', read)
    write = Mock(side_effect=[1, OSError('injected current publication failure')])
    monkeypatch.setattr(burst, 'write', write)
    with pytest.raises(OSError, match='publication failure'):
        burst.publish(newer)
    assert [call.args[1] for call in write.call_args_list] == [
        'history_' + burst.definition_id(newer), 'current_252']
    assert write.call_args_list[0].args[2][0]['version'] == 'test-next-version'
    assert burst.load(252) == original


def test_public_search_excludes_current_burst_content_and_changes_with_definition():
    import burst
    from program import from_search_program
    from test_search import _fast_capabilities
    definition, raw = reviewed_fixture()
    capabilities = _fast_capabilities()
    capabilities['actions'] += [dict(command, gcd_ms=0 if command['kind'] != 'spell' else 1500)
        for block in definition['blocks'] for command in block
        if command['simc_action'] not in {action['simc_action'] for action in capabilities['actions']}]
    # 审核定义提供真实的按钮身份；不从旧固定名单生成排除期待。
    for action in capabilities['actions']:
        for block in definition['blocks']:
            for command in block:
                if action['simc_action'] == command['simc_action']:
                    action.update(command)
    identity = dict(spec_id=252, data_version=definition['data_version'])
    before = copy.deepcopy(capabilities)
    blocks = burst.prepare(definition, task.parse_character(raw), capabilities, identity)
    filtered = burst.search_capabilities(capabilities, blocks)
    names = {action['simc_action'] for action in filtered['actions']}
    assert not names.intersection({'army_of_the_dead', 'dark_transformation', 'potion',
                                  'use_item,slot=trinket1', 'use_item,slot=trinket2'})
    with pytest.raises(ValueError, match='当前爆发宏'):
        burst.check_loop(from_search_program([['dark_transformation']], capabilities), filtered)
    revised = copy.deepcopy(definition)
    revised['version'] += '-outbreak'
    revised['blocks'] = [[dict(kind='spell', simc_action='outbreak', name='爆发测试技能',
        spell_id=1001, slot=None, item_id=None)]]
    revised['excluded_spell_ids'] = [1001]
    changed = burst.search_capabilities(capabilities,
        burst.prepare(revised, task.parse_character(raw), capabilities, identity))
    changed_names = {action['simc_action'] for action in changed['actions']}
    assert 'outbreak' not in changed_names
    assert {'army_of_the_dead', 'dark_transformation', 'use_item,slot=trinket1',
            'use_item,slot=trinket2'} <= changed_names
    assert burst.definition_id(revised) != burst.definition_id(definition)
    assert capabilities == before
