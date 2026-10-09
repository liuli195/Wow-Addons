"""已审核爆发通过公开预检查、真实存储和原生引擎。"""
import pytest
import task
from test_character_export import sample_profile
import copy
import json
from pathlib import Path


@pytest.fixture(autouse=True)
def connected_center(isolated_result_center):
    import result_store
    result_store.DATA_ROOT.mkdir()


def reviewed_fixture():
    definition = json.loads((Path(task.__file__).parent / 'burst/unholy.json').read_text(encoding='utf-8'))
    profile = sample_profile().replace('id=250245', 'id=273795').replace('id=250228', 'id=273796')
    character = task.parse_character(profile)
    from burst import talent_hash
    definition['talent_hashes'] = [talent_hash(character)]
    definition['reviewer'] = 'isolated test fixture'
    return definition, profile


def test_public_burst_precheck_requires_a_reviewed_definition(tmp_path):
    profile = tmp_path / 'character.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    with pytest.raises(task.TaskError, match='没有已审核'):
        task.precheck_burst(profile, tmp_path / 'burst')


def test_public_burst_precheck_roundtrip_and_real_potion(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    result = task.precheck_burst(profile, tmp_path / 'burst')
    assert result['definition']['potion'] == 'potion_of_recklessness'
    assert result['candidate']['compiled_steps'][1]['macrotext'] == (
        '/use 鲁莽药水\n/use 13\n/use 14\n/cast 黑暗突变')
    from sequence import compiled_program
    assert compiled_program(result['candidate']) == [
        ['army_of_the_dead'], ['potion', 'use_item,slot=trinket1',
                              'use_item,slot=trinket2', 'dark_transformation']]
    assert result['candidate']['name'].startswith('S2G_BURST_')
    assert result['simulation']['consistent']
    events = result['simulation']['trace']
    executions = [event for event in events if event['event'] == 'native_execute' and event['action'] == 'potion']
    assert len(executions) == 1
    assert executions[0]['ms'] == 3200
    denied = [event for event in events if event['action'] == 'potion' and event['event'] == 'dispatch_failed']
    assert denied[0]['ms'] == 3600
    assert denied[0]['cooldown_ms'] == 299600
    buffs = [buff for buff in result['simulation']['report']['sim']['players'][0]['buffs']
             if buff.get('spell') == 1236994]
    assert len(buffs) == 2
    assert all(buff['duration'] == 30 and buff['start_count'] == 1 for buff in buffs)
    import base64, zlib, cbor2
    decoded = cbor2.loads(zlib.decompress(base64.b64decode(result['candidate']['text'][6:]), -15))
    assert definition['instructions'] in decoded[1][b'MetaData'][b'Help'].decode()
    from sequence import behavior_key
    from program import compile_program
    alternate = copy.deepcopy(result['candidate']['program'])
    alternate['metadata']['purpose'] = 'loop'
    displayed = compile_program(alternate, tmp_path / 'renamed', identity=result['native_reference']['identity'])
    assert displayed['name'] != result['candidate']['name']
    assert behavior_key(displayed) == behavior_key(result['candidate'])


def test_public_burst_rejects_draft_corruption_and_unreviewed_talents(tmp_path):
    import burst
    import result_store
    definition, raw = reviewed_fixture()
    draft = copy.deepcopy(definition)
    draft['status'] = 'draft'
    with pytest.raises(ValueError, match='未审核'):
        burst.publish(draft)
    row = burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    corrupted = copy.deepcopy(row)
    corrupted['plan']['start_ms'] = 6000
    result_store.write('burst_definitions', 'current_252', [corrupted])
    with pytest.raises(task.TaskError, match='身份不符'):
        task.precheck_burst(profile, tmp_path / 'corrupt')
    result_store.write('burst_definitions', 'current_252', [row])
    unreviewed = copy.deepcopy(definition)
    unreviewed['version'] = 'test-other-talents'
    unreviewed['talent_hashes'] = ['0' * 64]
    burst.publish(unreviewed)
    with pytest.raises(task.TaskError, match='不适用'):
        task.precheck_burst(profile, tmp_path / 'talents')


def test_public_burst_storage_failure_keeps_the_previous_version(tmp_path, monkeypatch):
    import burst
    import result_store
    definition, raw = reviewed_fixture()
    original = burst.publish(definition)
    newer = copy.deepcopy(definition)
    newer['version'] = 'test-next-version'
    newer['instructions'] += ' New reviewed instruction.'
    real_write = burst.write

    def fail_current(table, key, rows):
        if key == 'current_252':
            raise OSError('injected current publication failure')
        return real_write(table, key, rows)

    monkeypatch.setattr(burst, 'write', fail_current)
    with pytest.raises(OSError, match='publication failure'):
        burst.publish(newer)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    result = task.precheck_burst(profile, tmp_path / 'restored')
    assert result['definition']['definition_id'] == original['definition_id']
    assert result_store.read_records('burst_definitions', 'history_' + original['definition_id']) == [original]


def test_public_burst_can_retry_a_denied_potion_without_consuming_it(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    result = task.precheck_burst(profile, tmp_path / 'denied', failed_actions=[None, 'potion'] + [None] * 18)
    events = result['simulation']['trace']
    executed = [event for event in events if event['event'] == 'native_execute' and event['action'] == 'potion']
    assert len(executed) == 1
    assert executed[0]['ms'] == 3600
    denied = [event for event in events if event['event'] == 'observed_failed' and event['action'] == 'potion']
    assert denied[0]['ms'] == 3200
    assert denied[0]['cooldown_ms'] == 0


def test_public_burst_reports_unavailable_trinket_without_dropping_it(tmp_path):
    import burst
    definition, _ = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    with pytest.raises(task.TaskError, match='不适用当前角色: 饰品13'):
        task.precheck_burst(profile, tmp_path / 'passive-trinkets')


def test_public_burst_reports_a_missing_storage_center(tmp_path):
    import result_store
    result_store.DATA_ROOT.rmdir()
    profile = tmp_path / 'character.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    with pytest.raises(result_store.DataReadError, match='记录不可读'):
        task.precheck_burst(profile, tmp_path / 'storage-error')


def test_public_burst_uses_effective_talents_when_extra_talents_are_disabled(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    # Disabled input must be removed before native initialization and review matching.
    original = (raw + 'omnium_talents=1:1\n').encode('utf-8')
    profile = tmp_path / 'character.simc'
    profile.write_bytes(original)
    result = task.precheck_burst(profile, tmp_path / 'omnium-off',
                                simulation_config={'enable_omnium_talents': False})
    assert result['simulation']['consistent']
    assert profile.read_bytes() == original
    effective = (tmp_path / 'omnium-off/input.effective.simc').read_text(encoding='utf-8')
    assert 'omnium_talents=' not in effective
