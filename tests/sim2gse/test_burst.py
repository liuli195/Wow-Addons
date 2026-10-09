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


def test_public_dual_task_rejects_burst_review_for_disabled_extra_talents(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    raw += '\nomnium_talents=1:1\n'
    definition['talent_hashes'] = [burst.talent_hash(task.parse_character(raw))]
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    original = profile.read_bytes()
    with pytest.raises(task.TaskError, match='不适用此爆发定义'):
        task.run_task(profile, tmp_path / 'omnium-off', mode='single', use_burst=True,
                      program=[['outbreak'], ['festering_strike']],
                      simulation_config={'enable_omnium_talents': False})
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


def test_public_search_excludes_current_burst_content_and_changes_with_definition(tmp_path):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    config = dict(candidate_limit=1, batch_targets=(2,), iterations=2,
                  validation_batches=2, final_batches=1, final_iterations=2,
                  scenarios=('nominal',), diagnostic_logging=True)
    result = task.run_task(profile, tmp_path / 'search', use_burst=True, search_config=config)
    names = {action['simc_action'] for action in result['capabilities']['actions']}
    assert not names.intersection({'army_of_the_dead', 'dark_transformation', 'potion',
                                  'use_item,slot=trinket1', 'use_item,slot=trinket2'})
    assert result['burst']['definition_id']
    saved = task.read_task(tmp_path / 'search', include_search_records=True)
    assert saved['burst']['candidate']['text'] == result['burst']['candidate']['text']
    resumed = task.resume_task(tmp_path / 'search')
    assert resumed['burst']['definition_id'] == result['burst']['definition_id']
    # An independently reviewed definition containing only Outbreak changes the
    # exclusion scope: the former burst buttons must become available again.
    revised = copy.deepcopy(definition)
    revised['version'] += '-outbreak'
    revised['blocks'] = [[dict(kind='spell', simc_action='outbreak', name='爆发测试技能',
                              spell_id=77575, slot=None, item_id=None)]]
    revised['excluded_spell_ids'] = [77575]
    burst.publish(revised)
    changed = task.run_task(profile, tmp_path / 'changed', use_burst=True, search_config=config)
    changed_names = {action['simc_action'] for action in changed['capabilities']['actions']}
    assert 'outbreak' not in changed_names
    assert {'army_of_the_dead', 'dark_transformation', 'use_item,slot=trinket1',
            'use_item,slot=trinket2'} <= changed_names
    assert changed['burst']['definition_id'] != result['burst']['definition_id']
    with pytest.raises(task.TaskError, match='爆发定义已变化'):
        task.resume_task(tmp_path / 'search')


def test_reviewed_burst_training_rejects_entire_nested_seed_and_preserves_old_training(tmp_path):
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
                        blocks=[['outbreak'], ['army_of_the_dead']])])
    result_store.write('seed_candidates', 'registry', [candidate], schema=seed_training.CANDIDATE_SCHEMA)
    legacy = dict(candidate_id='old-selected', condition='old', class_name='deathknight',
                  spec='unholy', targets=1, program=[['army_of_the_dead']], family='old',
                  score=1., scores=[1.], template_sha256='old', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [legacy], schema=seed_training.SELECTED_SCHEMA)
    before = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    outcome = seed_training.run_training(profile, 1, tmp_path / 'training', use_burst=True)
    assert outcome['status'] == 'completed'
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1-burst')
    assert len(processed) == 1 and processed[0]['status'] == 'rejected'
    assert json.loads(processed[0]['initial_program']) == candidate['program']
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1-burst')
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == before


@pytest.mark.parametrize('program', [
    [['army_of_the_dead']],
    [['dark_transformation']],
    [['use_item,slot=trinket1']],
    [['use_item,slot=trinket2']],
])
def test_public_single_task_refuses_burst_content_in_ordinary_sequence(tmp_path, program):
    import burst
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    with pytest.raises(task.TaskError, match='不支持的动作|爆发宏的动作'):
        task.run_task(profile, tmp_path / 'single', mode='single', use_burst=True, program=program)


def test_public_search_skips_entire_forbidden_history_structure(tmp_path):
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


@pytest.mark.parametrize('recover_first', [False, True])
def test_public_search_initialization_cancel_freezes_burst_definition(tmp_path, recover_first):
    import burst
    import time
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
        recovered = task.resume_task(output)
        assert recovered['burst']['definition_id']
    revised = copy.deepcopy(definition)
    revised['version'] += '-new-plan'
    revised['plan']['start_ms'] = 4000
    burst.publish(revised)
    with pytest.raises(task.TaskError, match='爆发定义已变化'):
        task.resume_task(output)
