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
def connected_center(request, isolated_result_center):
    if request.node.get_closest_marker('real') is None:
        return
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


@pytest.fixture(scope='module')
def reviewed_native_preparation(tmp_path_factory, installed_data_store_api):
    """One fixed native precheck per worker; consumers own all mutable outputs.

    Both dual-source cases use exactly this profile, reviewed definition and
    default simulation inputs. The separate precheck tests still run their own
    changed definitions and inputs through the public entry point.
    """
    import burst
    import result_store
    root = tmp_path_factory.mktemp('reviewed-native-burst')
    data = root / 'data'
    data.mkdir()
    definition, raw = reviewed_fixture()
    profile = root / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    with pytest.MonkeyPatch.context() as boundary:
        boundary.setattr(result_store, 'DATA_ROOT', data)
        boundary.setattr(result_store, '_SKILL_API', installed_data_store_api)
        burst.publish(definition)
        prepared = task.precheck_burst(profile, root / 'prepared')
    return definition, raw, prepared


@contextmanager
def page_task_boundary():
    """页面故障构造外部引擎和编译结果；HTTP、检查点、共享存储和恢复仍真实。"""
    import engine
    import sequence
    from test_search import _fast_search_boundary
    from test_interface import InterfaceTests

    definition, _ = reviewed_fixture()
    with _fast_search_boundary():
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


@pytest.fixture
def single_start_formal_task():
    from test_search import _fixed_search_population
    with _fixed_search_population([[['outbreak'], ['death_coil']]]):
        yield


@pytest.mark.real
def test_public_burst_precheck_requires_a_reviewed_definition(tmp_path):
    profile = tmp_path / 'character.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    with pytest.raises(task.TaskError, match='没有已审核'):
        task.precheck_burst(profile, tmp_path / 'burst')


@pytest.mark.real
def test_public_burst_precheck_roundtrip_and_real_potion(tmp_path):
    import burst
    definition, _ = reviewed_fixture()
    definition['version'] = 'test-other-talents'
    definition['talent_hashes'] = ['0' * 64]
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    original = (sample_profile() + 'omnium_talents=1:1\n').encode('utf-8')
    profile.write_bytes(original)
    result = task.precheck_burst(profile, tmp_path / 'burst',
                                simulation_config={'enable_omnium_talents': False})
    assert result['definition']['version'] == 'test-other-talents'
    assert profile.read_bytes() == original
    effective = (tmp_path / 'burst/input.effective.simc').read_text(encoding='utf-8')
    assert 'omnium_talents=' not in effective
    assert result['definition']['potion'] == 'potion_of_recklessness'
    assert result['candidate']['compiled_steps'][1]['macrotext'] == (
        '/use 鲁莽药水\n/use 13\n/use 14\n/cast 黑暗突变')
    from sequence import compiled_program
    assert compiled_program(result['candidate']) == [
        ['army_of_the_dead'], ['potion', 'use_item,slot=trinket1',
                              'use_item,slot=trinket2', 'dark_transformation']]
    assert result['candidate']['name'].startswith('S2G_BURST_')
    assert result['simulation']['consistent']
    assert {row['simc_action'] for row in result['simulation']['skipped_commands']} == {
        'use_item,slot=trinket1', 'use_item,slot=trinket2'}
    assert result['simulation']['effective_blocks'][1] == ['potion', 'dark_transformation']
    assert len(result['simulation']['input_times']) == 20
    assert any(row['reason'] == 'passive_item' and row['simc_action'] == 'use_item,slot=trinket2'
               for row in result['simulation']['skipped_commands'])
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


@pytest.mark.real
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



@pytest.mark.real
def test_dual_source_castsequence_keeps_native_queued_origins(tmp_path, reviewed_native_preparation):
    import burst
    from program import from_search_program, compile_program
    from sequence import evaluate
    definition, raw, prepared = copy.deepcopy(reviewed_native_preparation)
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
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


@pytest.mark.real
def test_dual_sources_share_cooldown_and_reset_between_battles(tmp_path, reviewed_native_preparation):
    import burst
    from program import from_action_blocks, compile_program
    from sequence import evaluate, select
    definition, raw, prepared = copy.deepcopy(reviewed_native_preparation)
    burst.publish(definition)
    profile = tmp_path / 'character.simc'
    profile.write_text(raw, encoding='utf-8')
    loop = compile_program(from_action_blocks(select(prepared['capabilities'],
                           [['dark_transformation'], ['death_coil']])),
                           tmp_path / 'loop-export', identity=prepared['native_reference']['identity'])
    times, sources = burst.combined_inputs(list(range(0, 180000, 200)), definition, 200)
    simulation = evaluate(profile, loop, tmp_path / 'controlled', character=task.parse_character(raw),
                          iterations=2, input_times=times, input_sources=sources,
                          burst_candidate=prepared['candidate'])
    assert len(simulation['report']['sim']['players']) == 1
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


@pytest.mark.real
def test_reviewed_burst_training_rejects_unsafe_adaptation_and_preserves_old_training(tmp_path, page_task_engine):
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
    legacy = dict(configuration_key=None, candidate_id='old-selected', condition='old', class_name='deathknight',
                  spec='unholy', targets=1, program=[['army_of_the_dead']], family='old',
                  score=1., scores=[1.], template_sha256='old', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [legacy], schema=seed_training.SELECTED_SCHEMA)
    before = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    configuration_key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                             target_type='single_target')
    scope = seed_training.shared_scope(configuration_key)
    result_store.write('seed_selected', scope, [dict(legacy, configuration_key=configuration_key)],
                       schema=seed_training.SELECTED_SCHEMA)
    current_before = result_store.read_records('seed_selected', scope)
    with patch('sequence.evaluate', side_effect=AssertionError('非法材料不能启动训练评分')), \
            pytest.raises(ValueError, match='本组没有有效训练材料'):
        seed_training.run_training(profile, 1, tmp_path / 'training', use_burst=True)
    with result_store.query('SELECT DISTINCT config_key FROM seed_prepared', tables=['seed_prepared']) as cursor:
        keys = cursor.fetchall()
    assert len(keys) == 1
    prepared = result_store.read_records('seed_prepared', keys[0][0], filters={'kind': 'source'})
    assert len(prepared) == 1 and prepared[0]['status'] == 'rejected'
    assert '仅剩一个成员' in prepared[0]['reason']
    assert json.loads(prepared[0]['initial_program']) == [dict(kind='Loop', count=2, blocks=[['outbreak']]),
        dict(kind='CastSequence', members=['death_coil'], reset=dict(timeout_seconds=None, flags=[]))]
    assert json.loads(prepared[0]['adaptation'])['original_program'] == candidate['program']
    assert not (tmp_path / 'training/ga').exists()
    assert result_store.read_records('seed_selected', scope) == current_before
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1-burst')
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == before


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
                type='attack', data_id=6603, base_spell_id=6603, gcd_ms=0)
    native['executed_actions'].append(auto)
    native['apl_actions'] += [auto, *[dict(template, name=name, signature=name,
        data_id=spell, base_spell_id=spell, available=False) for name, spell in
        [('berserking', 26297), ('soul_reaper', 343294)]]]
    # 实际非巨魔目录形状：已初始化、静态不可用，同时背景化且没有有效法术数据。
    native['apl_actions'][-2].update(id=0, data_id=0, base_spell_id=0, data_valid=False,
                                   background=True, harmful=False, executions=0)
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


@pytest.mark.parametrize("old_engine", [True])
@pytest.mark.real
def test_page_dual_scores_character_adapted_seed_without_changing_training(
        tmp_path, memory_result_center, single_start_formal_task, old_engine):
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
        row = dict(configuration_key=dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='aoe'), candidate_id='standard-troll', condition='old-training',
            class_name='deathknight', spec='unholy', targets=5, program=original,
            family='community', score=99999., scores=[99999.] * 3,
            template_sha256='standard-troll', engines=({'baseline': 'previous', 'controlled': 'previous'}
                                                     if old_engine else engines))
        result_store.write('seed_selected', seed_training.shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='aoe')), [row],
                           schema=seed_training.SELECTED_SCHEMA)
        before = result_store.read_records('seed_selected', seed_training.shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='aoe')))
        server = create_server(tmp_path / 'page', task_options=dict(
            search_config=dict(iterations=2, max_processes=1)))
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
            assert result_store.read_records('seed_selected', seed_training.shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='aoe'))) == before
        finally:
            for _, handle in server.tasks.values():
                if not handle.done:
                    handle.cancel_event.set()
                    handle.join(5)
            server.shutdown()
            server.server_close()
            thread.join(3)


@pytest.mark.real
def test_dual_keeps_completed_child_and_recovers_without_searching_it_again(
        tmp_path, monkeypatch, page_task_engine, memory_result_center, single_start_formal_task):
    import burst
    import dual_task
    import threading
    from interface import create_server
    from urllib.request import Request, urlopen
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    profile = tmp_path / 'frozen.simc'
    profile.write_text(raw, encoding='utf-8')
    destination = tmp_path / 'dual'
    calls, interrupted = [], []
    original_run = task.run_task

    def run(*args, **kwargs):
        purpose = Path(args[1]).name
        calls.append(purpose)
        if purpose == 'aoe' and not interrupted:
            interrupted.append(True)
            raise task.TaskError('injected second scene interruption')
        return original_run(*args, **kwargs)

    monkeypatch.setattr(task, 'run_task', run)
    server = create_server(tmp_path / 'page', task_options=dict(
        search_config=dict(iterations=2, max_processes=1)))
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
    original = (destination / 'input.original.simc').read_bytes()
    (destination / 'input.original.simc').write_bytes(original + b'\n# changed')
    from urllib.error import HTTPError
    with pytest.raises(HTTPError) as raised:
        urlopen(Request(base + '/api/tasks/' + task_id + '/resume', method='POST'))
    assert '冻结输入已变化' in json.load(raised.value)['error']
    server.shutdown()
    server.server_close()
    thread.join(3)




@pytest.mark.real
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
        handle = dual_task.start(profile, tmp_path / 'dual', search_config={})
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
