"""已审核爆发通过公开预检查、真实存储和原生引擎。"""
import pytest
import task
from test_character_export import sample_profile
import copy
import json
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from test_seed_training import memory_result_center


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


@contextmanager
def page_task_boundary():
    """页面故障构造外部引擎和编译结果；HTTP、检查点、共享存储和恢复仍真实。"""
    import engine
    import sequence
    from test_search import _fast_search_boundary
    from test_interface import InterfaceTests

    definition, _ = reviewed_fixture()
    identity = engine.identity
    with _fast_search_boundary(), \
         patch.object(engine, 'identity', identity):
        reference = engine.reference
        inspect = engine.inspect

        def reviewed_reference(*args, **kwargs):
            result = reference(*args, **kwargs)
            result['identity']['data_version'] = definition['data_version']
            return result

        def two_item_catalogue(*args, **kwargs):
            capabilities = inspect(*args, **kwargs)
            capabilities['actions'].append(dict(kind='spell', spell_id=42650,
                base_spell_id=42650, simc_action='army_of_the_dead', name='亡者大军', gcd_ms=1500))
            capabilities['actions'].append(dict(kind='item', slot=14, item_id=273796,
                simc_action='use_item,slot=trinket2', name='使用trinket2', gcd_ms=0))
            return capabilities

        with patch.object(engine, 'reference', side_effect=reviewed_reference), \
             patch.object(engine, 'inspect', side_effect=two_item_catalogue), \
             patch.object(sequence, 'evaluate', side_effect=InterfaceTests._ui_score):
            yield


@pytest.fixture
def page_task_engine():
    with page_task_boundary():
        yield


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


def test_public_burst_rejects_draft_corruption_but_accepts_other_talents(tmp_path):
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
    result = task.precheck_burst(profile, tmp_path / 'talents')
    assert result['definition']['version'] == 'test-other-talents'


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


@pytest.mark.parametrize('empty_slot', [False, True])
def test_public_burst_skips_passive_trinkets_without_changing_the_macro(tmp_path, empty_slot):
    import burst
    definition, _ = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    raw = sample_profile()
    if empty_slot:
        raw = raw.replace('trinket2=,id=250228\n', '')
    profile.write_text(raw, encoding='utf-8')
    result = task.precheck_burst(profile, tmp_path / 'passive-trinkets')
    assert result['candidate']['compiled_steps'][1]['macrotext'] == (
        '/use 鲁莽药水\n/use 13\n/use 14\n/cast 黑暗突变')
    assert {row['simc_action'] for row in result['simulation']['skipped_commands']} == {
        'use_item,slot=trinket1', 'use_item,slot=trinket2'}
    assert result['simulation']['effective_blocks'][1] == ['potion', 'dark_transformation']
    assert len(result['simulation']['input_times']) == 20
    assert any(row['reason'] == ('empty_slot' if empty_slot else 'passive_item')
               and row['simc_action'] == 'use_item,slot=trinket2'
               for row in result['simulation']['skipped_commands'])


def test_public_burst_native_skips_an_unlearned_skill_and_preserves_its_block(tmp_path):
    import burst
    from engine import training_template
    from seed_training import template_character
    definition, _ = reviewed_fixture()
    definition['blocks'][0] = [dict(definition['blocks'][0][0], name='吸血打击',
                                   spell_id=433895, simc_action='vampiric_strike')]
    definition['excluded_spell_ids'].append(433895)
    burst.publish(definition)
    profile = tmp_path / 'standard.simc'
    profile.write_text(template_character(training_template().read_text(encoding='utf-8')).raw_text,
                       encoding='utf-8')
    result = task.precheck_burst(profile, tmp_path / 'unlearned')
    skipped = result['simulation']['skipped_commands']
    assert any(row['simc_action'] == 'vampiric_strike' and row['reason'] == 'unselected_talent'
               and row['step'] == 0 for row in skipped)
    assert result['simulation']['effective_blocks'][0] == []
    assert result['candidate']['compiled_steps'][0]['spell'] == 433895
    assert [row['step'] for row in result['simulation']['trace'] if row['event'] == 'input'] == [0, 1] * 10


def test_public_burst_native_rejects_wrong_spell_id_with_a_real_action(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    definition['blocks'][0][0]['spell_id'] = 999999
    definition['excluded_spell_ids'].append(999999)
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    with pytest.raises(task.TaskError, match='optional spell identity does not match action'):
        task.precheck_burst(profile, tmp_path / 'wrong-identity')


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


def test_public_task_runs_loop_and_burst_on_one_native_player(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    published = burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    result = task.run_task(profile, tmp_path / 'dual', mode='single', use_burst=True,
                           program=[['outbreak'], ['festering_strike'], ['scourge_strike'], ['death_coil']],
                           search_config={'input_interval_ms': 200, 'diagnostic_logging': True})
    assert result['burst']['definition_id'] == published['definition_id']
    simulation = result['controlled_simulation']
    assert simulation['consistent']
    assert len(simulation['report']['sim']['players']) == 1
    inputs = [event for event in simulation['trace'] if event['event'] == 'input' and event['battle'] == 0]
    first_burst = [event for event in inputs if 3000 <= event['ms'] < 4000]
    assert [event['ms'] for event in first_burst] == [3000, 3200, 3400, 3600, 3800]
    assert all(event['source'] == 'burst' for event in first_burst)
    assert [event['source_step'] for event in first_burst] == [0, 1, 0, 1, 0]
    assert [event['source_origin'] for event in first_burst] == [1, 2, 3, 4, 5]
    assert all(event['source'] == 'loop' for event in inputs if event['ms'] == 4000)
    before = next(event for event in inputs if event['ms'] == 2800)
    after = next(event for event in inputs if event['ms'] == 4000)
    assert after['source_origin'] == before['source_origin'] + 1
    # This fixture exports one precombat click followed by four loop blocks.
    assert before['source_step'] == 4
    assert after['source_step'] == 0
    second = next(event for event in inputs if event['ms'] == 48000)
    assert second['source'] == 'burst'
    assert second['source_step'] == 1
    from task import read_task
    restored = read_task(tmp_path / 'dual', include_reports=True)
    assert restored['burst']['definition_id'] == published['definition_id']
    assert restored['burst']['candidate']['text'] == result['burst']['candidate']['text']


def test_public_dual_task_uses_fixed_burst_with_disabled_extra_talents(tmp_path, memory_result_center):
    import burst
    definition, raw = reviewed_fixture()
    raw += '\nomnium_talents=1:1\n'
    definition['talent_hashes'] = [burst.talent_hash(task.parse_character(raw))]
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    original = profile.read_bytes()
    result = task.run_task(profile, tmp_path / 'omnium-off', mode='single', use_burst=True,
                           program=[['outbreak'], ['festering_strike']],
                           simulation_config={'enable_omnium_talents': False})
    assert result['status'] == 'offline_ready'
    assert profile.read_bytes() == original



def test_dual_source_castsequence_keeps_native_queued_origins(tmp_path):
    import burst
    from program import from_search_program, compile_program
    from sequence import evaluate
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    prepared = task.precheck_burst(profile, tmp_path / 'prepared')
    program = from_search_program([
        dict(kind='CastSequence', members=['outbreak', 'festering_strike'],
             reset=dict(timeout_seconds=None, flags=['combat'])),
        ['death_coil'],
    ], prepared['capabilities'])
    loop = compile_program(program, tmp_path / 'loop-export', identity=prepared['native_reference']['identity'])
    times, sources = burst.combined_inputs(list(range(0, 180000, 200)), definition, 200)
    simulation = evaluate(profile, loop, tmp_path / 'controlled', character=task.parse_character(raw),
                          iterations=2, input_times=times, input_sources=sources,
                          burst_candidate=prepared['candidate'])
    assert simulation['consistent']
    assert len(simulation['report']['sim']['players']) == 1
    events = simulation['trace']
    assert any(event['event'] == 'native_execute' and event['source'] == 'burst' for event in events)
    assert any(event['event'] == 'native_execute' and event['source'] == 'loop'
               and event['sequence_member'] == 1 for event in events)
    assert all(event['source'] == 'loop' for event in events if event['sequence_member'] >= 0)


def test_dual_sources_share_cooldown_and_reset_between_battles(tmp_path):
    import burst
    from program import from_action_blocks, compile_program
    from sequence import evaluate, select
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    prepared = task.precheck_burst(profile, tmp_path / 'prepared')
    loop = compile_program(from_action_blocks(select(prepared['capabilities'],
                           [['dark_transformation'], ['death_coil']])),
                           tmp_path / 'loop-export', identity=prepared['native_reference']['identity'])
    times, sources = burst.combined_inputs(list(range(0, 180000, 200)), definition, 200)
    simulation = evaluate(profile, loop, tmp_path / 'controlled', character=task.parse_character(raw),
                          iterations=2, input_times=times, input_sources=sources,
                          burst_candidate=prepared['candidate'])
    for battle in (0, 1):
        events = [event for event in simulation['trace'] if event['battle'] == battle]
        assert any(event['event'] == 'native_execute' and event['source'] == 'loop'
                   and event['action'] == 'dark_transformation' and event['ms'] < 3000 for event in events)
        assert any(event['event'] == 'dispatch_failed' and event['source'] == 'burst'
                   and event['action'] == 'dark_transformation' and event['ms'] == 3200
                   and event['cooldown_ms'] > 0 for event in events)
        first = next(event for event in events if event['event'] == 'input' and event['ms'] == 3000)
        assert (first['source'], first['source_origin'], first['source_step']) == ('burst', 1, 0)
    quiet = evaluate(profile, loop, tmp_path / 'quiet', character=task.parse_character(raw),
                     iterations=2, trace=False, input_times=times, input_sources=sources,
                     burst_candidate=prepared['candidate'])
    assert quiet['consistent'] and not quiet['trace']


def test_public_search_excludes_current_burst_content_and_changes_with_definition(tmp_path, monkeypatch, memory_result_center):
    import burst
    from test_search import _minimal_rule_pack
    pack = _minimal_rule_pack()
    pack['specializations']['252']['initialization']['openers'][0]['steps'] = [
        dict(action='scourge_strike', source_step=1)]
    rules = tmp_path / 'rules.json'
    rules.write_text(json.dumps(pack), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(rules))
    simulation = dict(target_count=1, scene='single_target')
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    config = dict(candidate_limit=1, batch_targets=(2,), iterations=2,
                  validation_batches=2, final_batches=1, final_iterations=2,
                  scenarios=('nominal',), diagnostic_logging=True)
    result = task.run_task(profile, tmp_path / 'search', use_burst=True, search_config=config,
                           simulation_config=simulation)
    names = {action['simc_action'] for action in result['capabilities']['actions']}
    assert not names.intersection({'army_of_the_dead', 'dark_transformation', 'potion',
                                  'use_item,slot=trinket1', 'use_item,slot=trinket2'})
    assert result['burst']['definition_id']
    saved = task.read_task(tmp_path / 'search', include_search_records=True)
    assert saved['burst']['candidate']['text'] == result['burst']['candidate']['text']
    resumed = task.resume_task(tmp_path / 'search', simulation_config=simulation)
    assert resumed['burst']['definition_id'] == result['burst']['definition_id']
    # An independently reviewed definition containing only Outbreak changes the
    # exclusion scope: the former burst buttons must become available again.
    revised = copy.deepcopy(definition)
    revised['version'] += '-outbreak'
    revised['blocks'] = [[dict(kind='spell', simc_action='outbreak', name='爆发测试技能',
                              spell_id=77575, slot=None, item_id=None)]]
    revised['excluded_spell_ids'] = [77575]
    burst.publish(revised)
    changed = task.run_task(profile, tmp_path / 'changed', use_burst=True, search_config=config,
                           simulation_config=simulation)
    changed_names = {action['simc_action'] for action in changed['capabilities']['actions']}
    assert 'outbreak' not in changed_names
    assert {'army_of_the_dead', 'dark_transformation', 'use_item,slot=trinket1',
            'use_item,slot=trinket2'} <= changed_names
    assert changed['burst']['definition_id'] != result['burst']['definition_id']
    with pytest.raises(task.TaskError, match='爆发定义已变化'):
        task.resume_task(tmp_path / 'search', simulation_config=simulation)


def test_reviewed_burst_training_rejects_unsafe_adaptation_and_preserves_old_training(tmp_path):
    import burst
    import result_store
    import seed_training
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    candidate = dict(candidate_id='nested-old', class_name='deathknight', spec='unholy',
                     label='nested', source='constructed-test', original='reviewed fixture',
                     instructions='repeat', semantic='preserved', changes=[], family='nested',
                     core=[['outbreak']], program=[dict(kind='Loop', count=2,
                        blocks=[['outbreak'], ['army_of_the_dead']]),
                        dict(kind='CastSequence', members=['army_of_the_dead', 'death_coil'],
                             reset=dict(timeout_seconds=None, flags=[]))])
    source = tmp_path / 'nested-source.json'
    source.write_text(json.dumps({key: value for key, value in candidate.items()
                                  if key != 'candidate_id'}), encoding='utf-8')
    seed_training.register(source)
    legacy = dict(candidate_id='old-selected', condition='old', class_name='deathknight',
                  spec='unholy', targets=1, program=[['army_of_the_dead']], family='old',
                  score=1., scores=[1.], template_sha256='old', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [legacy], schema=seed_training.SELECTED_SCHEMA)
    before = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    outcome = seed_training.run_training(profile, 1, tmp_path / 'training', use_burst=True)
    assert outcome['status'] == 'completed'
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1-burst')
    assert len(processed) == 1 and processed[0]['status'] == 'rejected'
    assert '仅剩一个成员' in processed[0]['error']
    assert json.loads(processed[0]['initial_program']) == [dict(kind='Loop', count=2, blocks=[['outbreak']]),
        dict(kind='CastSequence', members=['death_coil'], reset=dict(timeout_seconds=None, flags=[]))]
    assert json.loads(processed[0]['comparison'])['adaptation']['original_program'] == candidate['program']
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1-burst')
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == before


@pytest.mark.parametrize('program', [
    [['army_of_the_dead']],
    [['dark_transformation']],
    [['use_item,slot=trinket1']],
    [['use_item,slot=trinket2']],
])
def test_public_single_task_refuses_burst_content_in_ordinary_sequence(
        tmp_path, program, page_task_engine, memory_result_center):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    with pytest.raises(task.TaskError, match='不支持的动作|爆发宏的动作'):
        task.run_task(profile, tmp_path / 'single', mode='single', use_burst=True, program=program)


def test_public_search_skips_entire_forbidden_history_structure(
        tmp_path, page_task_engine, memory_result_center):
    import burst
    import result_store
    import seed_training
    from engine import identity
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    forbidden = [dict(kind='CastSequence', members=['outbreak', 'army_of_the_dead'],
                      reset=dict(timeout_seconds=None, flags=[]))]
    safe = [dict(kind='Loop', count=2, blocks=[['outbreak'], ['death_coil']]),
            dict(kind='WaitClicks', clicks=2)]
    rows = [dict(candidate_id=key, condition='historical', class_name='deathknight', spec='unholy',
                 targets=1, program=program, family=key, score=99999., scores=[99999.],
                 template_sha256='historical', engines=engines)
            for key, program in [('forbidden', forbidden), ('safe', safe)]]
    result_store.write('seed_selected', 'deathknight-unholy-1-burst', rows,
                       schema=seed_training.SELECTED_SCHEMA)
    result = task.run_task(profile, tmp_path / 'history', use_burst=True,
                           search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2,
                                              validation_batches=2, diagnostic_logging=True))
    starts = result['search']['starts']
    assert safe in starts and forbidden not in starts
    assert [['outbreak']] not in starts  # No partial deletion of the rejected structure.
    assert result['search_result']['dps'] != 99999.
    for record in result['search']['records']:
        names = {command['simc_action'] for block in record['candidate']['blocks'] for command in block}
        assert not names.intersection({'army_of_the_dead', 'dark_transformation',
                                       'use_item,slot=trinket1', 'use_item,slot=trinket2'})


@contextmanager
def character_seed_boundary(*, native_flags=None, native_reference=None):
    """构造原生目录及外部成绩；角色映射、任务及程序校验保持真实。"""
    import engine
    import sequence
    from test_engine import apl_pool_reference
    from test_interface import InterfaceTests
    from test_search import _fast_search_boundary

    definition, _ = reviewed_fixture()
    native = native_reference if native_reference is not None else apl_pool_reference()
    template = native['apl_actions'][0]
    auto = dict(template, name='auto_attack', signature='auto_attack',
                data_id=6603, base_spell_id=6603, gcd_ms=0)
    native['executed_actions'].append(auto)
    native['apl_actions'] += [auto, *[dict(template, name=name, signature=name,
        data_id=spell, base_spell_id=spell, available=False) for name, spell in
        [('berserking', 26297), ('soul_reaper', 343294)]]]
    if native_flags:
        native['apl_actions'][-2].update(native_flags)
    inspect = engine.inspect
    with _fast_search_boundary():
        reference = engine.reference

        def character_reference(*args, **kwargs):
            result = reference(*args, **kwargs)
            result['identity'].update(native.get('identity', {}))
            result.update({key: value for key, value in native.items() if key != 'identity'},
                          unavailable_actions=[dict(kind='item', slot=slot,
                              reason='passive_item') for slot in (13, 14)])
            result['identity']['data_version'] = definition['data_version']
            return result

        with patch.object(engine, 'reference', side_effect=character_reference), \
                patch.object(engine, 'inspect', side_effect=inspect), \
                patch.object(sequence, 'evaluate', side_effect=InterfaceTests._ui_score):
            yield {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}


def test_page_dual_scores_character_adapted_seed_without_changing_training(
        tmp_path, memory_result_center):
    import burst
    import result_store
    import seed_training
    import threading
    from interface import create_server
    from urllib.request import Request, urlopen

    definition, raw = reviewed_fixture()
    burst.publish(definition)
    original = [['berserking', 'auto_attack'], ['outbreak'], ['soul_reaper'],
                ['death_coil'], ['outbreak']]
    expected = [['auto_attack'], ['outbreak'], ['death_coil'], ['outbreak']]
    with character_seed_boundary() as engines:
        row = dict(candidate_id='standard-troll', condition='old-training',
            class_name='deathknight', spec='unholy', targets=5, program=original,
            family='community', score=99999., scores=[99999.] * 3,
            template_sha256='standard-troll', engines=engines)
        result_store.write('seed_selected', 'deathknight-unholy-5-burst', [row],
                           schema=seed_training.SELECTED_SCHEMA)
        before = result_store.read_records('seed_selected', 'deathknight-unholy-5-burst')
        server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
            candidate_limit=8, batch_targets=(2,), iterations=2, validation_batches=1,
            final_batches=1, final_iterations=2, scenarios=('nominal',))))
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            request = Request(base + '/api/tasks', json.dumps(dict(profile=raw, mode='dual')).encode(),
                              {'Content-Type': 'application/json'})
            with urlopen(request, timeout=3) as response:
                created = json.load(response)
            handle = server.tasks[created['task_id']][1]
            handle.join(20)
            reads = []
            storage_api = result_store._api()
            read_key = storage_api['read_key']
            def audited_read(root, table, key, **options):
                if table == 'runs':
                    reads.append(options.get('columns'))
                return read_key(root, table, key, **options)
            with patch.dict(storage_api, {'read_key': audited_read}):
                with urlopen(base + '/api/tasks/' + created['task_id'], timeout=3) as response:
                    state = json.load(response)
            assert state['status'] == 'completed', state
            assert [scene['target_count'] for scene in state['scenes']] == [1, 5]
            assert reads and all(columns is not None and 'rule_initialization' not in columns
                                 for columns in reads), '双场摘要不得向存储读取完整初始化列'
            assert all(scene['has_rule_initialization'] and 'rule_initialization' not in scene
                       for scene in state['scenes'])
            with urlopen(base + '/api/tasks/' + created['task_id'] +
                         '?details=rule_initialization', timeout=3) as response:
                detail = json.load(response)
            assert all(scene['rule_initialization'] for scene in detail['scenes'])
            _, destination = server.task_paths(created['task_id'])
            saved = task.read_task(destination / 'aoe', include_search_records=True)
            assert any([[command['simc_action'] for command in node['commands']]
                        for node in record['program']['nodes']] == expected
                       for record in saved['search']['records']
                       if all(node['kind'] == 'Action' for node in record['program']['nodes']))
            assert saved['search_result']['dps'] != 99999.
            adaptation = saved['search']['seed_adaptations'][0]
            assert adaptation['original_program'] == original
            assert adaptation['derived_program'] == expected
            assert adaptation['status'] == 'accepted'
            assert [(item['path'], item['action']) for item in adaptation['removed']] == [
                ('segments[0][0]', 'berserking'), ('segments[2][0]', 'soul_reaper')]
            assert all(item['reason'] for item in adaptation['removed'])
            assert result_store.read_records('seed_selected', 'deathknight-unholy-5-burst') == before
        finally:
            for _, handle in server.tasks.values():
                if not handle.done:
                    handle.cancel_event.set()
                    handle.join(5)
            server.shutdown()
            server.server_close()
            thread.join(3)


@pytest.mark.parametrize('original, expected, status', [
    ([dict(kind='Loop', count=3, blocks=[['berserking', 'auto_attack'], ['soul_reaper'],
                                       ['death_coil']]), dict(kind='WaitClicks', clicks=2),
      dict(kind='CastSequence', members=['soul_reaper', 'outbreak', 'death_coil'],
           reset=dict(timeout_seconds=3, flags=['target', 'combat']))],
     [dict(kind='Loop', count=3, blocks=[['auto_attack'], ['death_coil']]),
      dict(kind='WaitClicks', clicks=2),
      dict(kind='CastSequence', members=['outbreak', 'death_coil'],
           reset=dict(timeout_seconds=3, flags=['target', 'combat']))], 'accepted'),
    ([dict(kind='CastSequence', members=['soul_reaper', 'death_coil'], reset=None)],
     [dict(kind='CastSequence', members=['death_coil'], reset=None)], 'rejected'),
    ([dict(kind='Loop', count=4096, blocks=[['berserking'], ['auto_attack']])],
     None, 'rejected'),
])
def test_public_search_preserves_seed_structure_or_records_why_it_cannot(
        tmp_path, memory_result_center, original, expected, status):
    import burst
    import result_store
    import seed_training

    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'role.simc'
    profile.write_text(raw, encoding='utf-8')
    with character_seed_boundary() as engines:
        row = dict(candidate_id='structure', condition='training', class_name='deathknight',
            spec='unholy', targets=5, program=original, family='community', score=99999.,
            scores=[99999.] * 3, template_sha256='training', engines=engines)
        result_store.write('seed_selected', 'deathknight-unholy-5-burst', [row],
                           schema=seed_training.SELECTED_SCHEMA)
        task.run_task(profile, tmp_path / 'search', use_burst=True,
            simulation_config=dict(target_count=5), search_config=dict(candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=1))
        decision = task.read_task(tmp_path / 'search')['search']['seed_adaptations'][0]
    assert decision['original_program'] == original
    assert decision['derived_program'] == expected
    assert decision['status'] == status
    assert bool(decision['reason']) == (status != 'accepted')


@pytest.mark.parametrize('native_flags, status', [
    ({'action_initialized': False}, 'rejected'),
    ({'available': True, 'executions': 0, 'cooldown_ms': 99999, 'resource_cost': 99999}, 'accepted'),
])
def test_public_search_only_prunes_confirmed_static_unavailability(
        tmp_path, memory_result_center, native_flags, status):
    import result_store
    import seed_training

    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    original = [[native_flags.get('signature', 'berserking'), 'auto_attack'], ['outbreak']]
    with character_seed_boundary(native_flags=native_flags) as engines:
        row = dict(candidate_id='availability', condition='training', class_name='deathknight',
            spec='unholy', targets=5, program=original, family='community', score=99999.,
            scores=[99999.] * 3, template_sha256='training', engines=engines)
        result_store.write('seed_selected', 'deathknight-unholy-5', [row],
                           schema=seed_training.SELECTED_SCHEMA)
        task.run_task(profile, tmp_path / 'search', simulation_config=dict(target_count=5),
            search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        decision = task.read_task(tmp_path / 'search')['search']['seed_adaptations'][0]
        if status == 'rejected':
            with pytest.raises(task.TaskError, match='不支持的动作'):
                task.run_task(profile, tmp_path / 'explicit', mode='single', program=original,
                              simulation_config=dict(target_count=5))
    assert decision['derived_program'] == original
    assert decision['removed'] == []
    assert decision['status'] == status


def test_public_search_freezes_deduplicated_seed_adaptations_on_resume(
        tmp_path, memory_result_center):
    import result_store
    import seed_training

    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    original = [['berserking', 'auto_attack'], ['outbreak'], ['death_coil'], ['outbreak']]
    with character_seed_boundary() as engines:
        row = dict(candidate_id='first', condition='training', class_name='deathknight',
            spec='unholy', targets=5, program=original, family='community', score=99999.,
            scores=[99999.] * 3, template_sha256='training', engines=engines)
        result_store.write('seed_selected', 'deathknight-unholy-5',
            [row, dict(row, candidate_id='same-behavior', program=original + [['soul_reaper']])],
            schema=seed_training.SELECTED_SCHEMA)
        destination = tmp_path / 'search'
        task.run_task(profile, destination, simulation_config=dict(target_count=5),
            search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        before = task.read_task(destination)
        assert [decision['status'] for decision in before['search']['seed_adaptations']] == [
            'accepted', 'duplicate']
        result_store.write('seed_selected', 'deathknight-unholy-5',
            [dict(row, program=[['epidemic'], ['death_coil']])], schema=seed_training.SELECTED_SCHEMA)
        read = result_store.read_records

        def no_seed_reload(table, key):
            assert table != 'seed_selected', '恢复不得刷新入选快照'
            return read(table, key)

        with patch.object(result_store, 'read_records', side_effect=no_seed_reload):
            task.resume_task(destination, simulation_config=dict(target_count=5))
        after = task.read_task(destination)
        assert after['search']['seed_adaptations'] == before['search']['seed_adaptations']
        assert after['completed_batches'] == before['completed_batches']
        rules = task._rule_hashes()
        with patch.object(task, '_rule_hashes', return_value=dict(rules, changed='new-rule')):
            with pytest.raises(task.TaskError, match='规则已变化'):
                task.resume_task(destination, simulation_config=dict(target_count=5))
        assert task.read_task(destination)['search']['seed_adaptations'] == before['search']['seed_adaptations']

        def unreadable_snapshot(table, key):
            if table == 'seed_selected':
                raise result_store.DataReadError('selected snapshot unavailable')
            return read(table, key)

        with patch.object(result_store, 'read_records', side_effect=unreadable_snapshot):
            with pytest.raises(task.TaskError, match='selected snapshot unavailable'):
                task.run_task(profile, tmp_path / 'unreadable', simulation_config=dict(target_count=5))


@pytest.mark.parametrize('recover_first', [False, True])
def test_public_search_initialization_cancel_freezes_burst_definition(tmp_path, monkeypatch, recover_first):
    import burst
    import time
    from test_search import _minimal_rule_pack
    rules = tmp_path / 'rules.json'
    rules.write_text(json.dumps(_minimal_rule_pack()), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(rules))
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    output = tmp_path / 'cancel-initialize'
    handle = task.start_task(profile, output, use_burst=True,
                             search_config=dict(iterations=512, candidate_limit=1, batch_targets=(2,)))
    deadline = time.monotonic() + 20
    while not (output / 'reference').exists() and not handle.done and time.monotonic() < deadline:
        time.sleep(0.001)
    assert (output / 'reference').exists() and not handle.done
    task.cancel_task(handle)
    handle.join(10)
    assert handle.done and handle.error is None
    if recover_first:
        with page_task_boundary():
            recovered = task.resume_task(output)
        assert recovered['burst']['definition_id']
    revised = copy.deepcopy(definition)
    revised['version'] += '-new-plan'
    revised['plan']['start_ms'] = 4000
    burst.publish(revised)
    with pytest.raises(task.TaskError, match='爆发定义已变化'):
        task.resume_task(output)


@pytest.mark.parametrize('fault', ['aoe', 'collection', 'registration', 'cancel', 'preparation'])
def test_dual_keeps_completed_child_and_recovers_without_searching_it_again(
        tmp_path, monkeypatch, fault, page_task_engine, memory_result_center):
    import burst
    import dual_task
    import codec
    import threading
    from interface import create_server
    from urllib.request import Request, urlopen
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'frozen.simc'
    profile.write_text(raw, encoding='utf-8')
    destination = tmp_path / 'dual'
    calls, interrupted = [], []
    original_run, original_collection, original_save = task.run_task, codec.collection, dual_task._save

    def run(*args, **kwargs):
        purpose = Path(args[1]).name
        calls.append(purpose)
        if fault == 'aoe' and purpose == 'aoe' and not interrupted:
            interrupted.append(True)
            raise task.TaskError('injected second scene interruption')
        if fault == 'preparation' and purpose == 'single_target' and not interrupted:
            interrupted.append(True)
            Path(args[1]).mkdir()
            (Path(args[1]) / 'preserved.txt').write_text('preparation evidence')
            raise task.TaskError('injected before durable child state')
        return original_run(*args, **kwargs)

    def collect(*args, **kwargs):
        if fault == 'collection' and not interrupted:
            interrupted.append(True)
            raise task.TaskError('injected packaging interruption')
        return original_collection(*args, **kwargs)

    def save(row):
        if fault == 'registration' and row['single_target_status'] == 'completed' and not interrupted:
            interrupted.append(True)
            raise task.TaskError('injected parent registration interruption')
        if (fault == 'cancel' and row['single_target_export'] and row['burst_export']
                and row['aoe_status'] == 'pending' and not interrupted):
            interrupted.append(True)
            threading.Thread(target=lambda: urlopen(Request(
                base + '/api/tasks/' + task_id + '/cancel', method='POST')).close(), daemon=True).start()
            assert server.tasks[task_id][1].cancel_event.wait(5)
        return original_save(row)

    monkeypatch.setattr(task, 'run_task', run)
    monkeypatch.setattr(codec, 'collection', collect)
    monkeypatch.setattr(dual_task, '_save', save)
    server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
        candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2,
        final_batches=1, final_iterations=2, scenarios=('nominal',))))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    request = Request(base + '/api/tasks', json.dumps(dict(profile=raw, mode='dual')).encode(),
                      {'Content-Type': 'application/json'})
    with urlopen(request) as response:
        task_id = json.load(response)['task_id']
    destination, handle = server.tasks[task_id]
    def public_read():
        with urlopen(base + '/api/tasks/' + task_id) as response:
            return json.load(response)
    handle.join(30)
    assert handle.done and handle.error is None
    state = public_read()
    assert interrupted and state['status'] in ('partial', 'cancelled', 'failed'), state
    assert not state['collection_ready']
    if fault == 'collection':
        assert len(state['exports']) == 3
    if fault == 'cancel':
        assert calls == ['single_target'] and state['scenes'][1]['status'] == 'pending'
        assert set(state['exports']) == {'single_target', 'burst'}
    with urlopen(Request(base + '/api/tasks/' + task_id + '/resume', method='POST')) as response:
        assert response.status == 202
    recovered = server.tasks[task_id][1]
    recovered.join(30)
    assert recovered.done and recovered.error is None
    restored = public_read()
    assert restored['status'] == 'completed', (restored, dual_task._load(destination)['error'])
    assert restored['collection_ready'] and len(restored['exports']) == 3
    assert calls.count('single_target') == 1
    parent = dual_task._load(destination)
    children = [task.read_task(destination / parent[purpose + '_path']) for purpose in ('single_target', 'aoe')]
    instructions = '\n'.join(label + '：' + child['burst']['instructions']
        for label, child in zip(('单体', '群体'), children, strict=True))
    assert restored['burst_instructions'] == instructions
    from gse_import import decode_import
    exported = next(iter(decode_import(restored['exports']['burst'])['sequences'].values()))
    assert exported['MetaData']['Help'].partition('爆发按法：')[2] == instructions
    assert burst.load(252)['instructions'] == definition['instructions']
    if fault == 'preparation':
        assert (destination / 'single_target/preserved.txt').read_text() == 'preparation evidence'
        assert any(name.startswith('s-') for name in calls)
    original = (destination / 'input.original.simc').read_bytes()
    (destination / 'input.original.simc').write_bytes(original + b'\n# changed')
    from urllib.error import HTTPError
    with pytest.raises(HTTPError) as raised:
        urlopen(Request(base + '/api/tasks/' + task_id + '/resume', method='POST'))
    assert '冻结输入已变化' in json.load(raised.value)['error']
    server.shutdown()
    server.server_close()
    thread.join(3)


def test_page_reports_real_storage_unavailability_without_disconnect(tmp_path, page_task_engine):
    import burst
    import result_store
    import threading
    from interface import create_server
    from urllib.request import Request, urlopen
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
        candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2,
        final_batches=1, final_iterations=2, scenarios=('nominal',))))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(Request(base + '/api/tasks', json.dumps(dict(profile=raw, mode='dual')).encode(),
                             {'Content-Type': 'application/json'})) as response:
            task_id = json.load(response)['task_id']
        server.tasks[task_id][1].join(30)
        assert server.tasks[task_id][1].done
        moved = result_store.DATA_ROOT.with_name('temporarily-unavailable')
        result_store.DATA_ROOT.rename(moved)
        try:
            with urlopen(base + '/api/tasks/' + task_id) as response:
                state = json.load(response)
            assert state['status'] == 'failed' and state['recoverable']
            assert '存储' in state['error'] and not state['result_ready']
        finally:
            moved.rename(result_store.DATA_ROOT)
        with urlopen(base + '/api/tasks/' + task_id) as response:
            restored = json.load(response)
        assert restored['status'] == 'completed' and restored['collection_ready']
    finally:
        server.shutdown();server.server_close();thread.join(3)


def test_dual_children_reuse_the_frozen_definition_without_rediscovery(tmp_path, monkeypatch):
    import burst
    import dual_task
    import engine
    import result_store
    from runtime import TaskCancelled
    from test_search import _fast_search_boundary

    definition, raw = reviewed_fixture()
    reviewed = burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    queries = []
    api = dict(result_store._api())
    query = api['query']
    def bounded_query(*args, **kwargs):
        queries.append(kwargs.get('tables'))
        if len(queries) > 2:
            raise OSError('child must use frozen point-read identity')
        return query(*args, **kwargs)
    api['query'] = bounded_query
    monkeypatch.setattr(result_store, '_SKILL_API', api)
    def cancelled_reference(*args, **kwargs):
        raise TaskCancelled('fixture stops after frozen child initialization')
    with _fast_search_boundary(), monkeypatch.context() as scoped:
        scoped.setattr(engine, 'reference', cancelled_reference)
        handle = dual_task.start(profile, tmp_path / 'dual', search_config={'candidate_limit': 1})
        handle.join(5)
        assert handle.done
        saved = dual_task.read(handle.output_root)
        assert saved['status'] == 'cancelled', saved
    assert queries == [['burst_definitions'], ['burst_definitions']]
    revised = copy.deepcopy(definition)
    revised['version'] += '-new-plan'
    burst.publish(revised)
    with pytest.raises(task.TaskError, match='爆发定义已变化'):
        task.run_task(profile, tmp_path / 'changed', use_burst=True,
                      burst_identity={'spec_id': reviewed['spec_id'], 'definition_id': reviewed['definition_id']})
