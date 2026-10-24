"""第三票：通过同一任务入口驱动搜索、复测与结果隔离。"""

from __future__ import annotations

import tempfile
import time
import shutil
import os
from contextlib import closing, contextmanager, nullcontext, ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import pytest
from test_seed_training import memory_result_center

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))
from test_character_export import sample_profile
from test_engine import apl_pool_reference, static_snapshot
from task import cancel_task, read_task, resume_task, run_task, start_task, TaskError
from search import initial_programs, TaskStore


def test_mutate_fetches_parent_feedback_only_after_its_usage_gate():
    import random
    from search import mutate
    program = [['outbreak'], ['death_coil'], ['scourge_strike']]
    feedback = dict(positions=[dict(source_position=dict(segment=0), unresolved_inputs=1)])
    calls = []
    def get_feedback():
        calls.append('feedback')
        return feedback

    observation = {}
    mutate(program, _fast_capabilities(), random.Random(0),
           feedback_getter=get_feedback, observation=observation)
    assert observation['sampled_mutation'] == 'loop'
    assert calls == []

    mutate(program, _fast_capabilities(), random.Random(1),
           feedback_getter=get_feedback, observation=observation)
    assert observation['sampled_mutation'] == 'insert'  # Its feedback gate is above .5.
    assert calls == []

    rng = random.Random(2)
    child = mutate(program, _fast_capabilities(), rng,
                   feedback_getter=get_feedback, observation=observation)
    assert calls == ['feedback']
    assert child == [['death_coil'], ['scourge_strike'], ['outbreak']]
    assert observation == dict(sampled_mutation='swap', actual_mutation='move',
                               modification_position=dict(segment=0, repair=True, target=2))
    assert rng.random() == 0.25158329759496567


def test_mutate_keeps_legacy_feedback_truthiness_and_random_consumption():
    import random
    from search import mutate
    program = [['outbreak'], ['death_coil'], ['scourge_strike']]
    for feedback in (None, {}):
        rng = random.Random(2)
        assert mutate(program, _fast_capabilities(), rng, feedback=feedback) == [
            ['scourge_strike'], ['death_coil'], ['outbreak']]
        assert rng.random() == 0.3610574739836072
    rng = random.Random(2)
    feedback = dict(positions=[dict(source_position=dict(segment=0), unresolved_inputs=1)])
    assert mutate(program, _fast_capabilities(), rng, feedback=feedback) == [
        ['death_coil'], ['scourge_strike'], ['outbreak']]
    assert rng.random() == 0.25158329759496567



def _fast_capabilities():
    actions = [
        dict(kind="spell", spell_id=1001, simc_action="outbreak", name="outbreak", gcd_ms=1500, base_spell_id=1001),
        dict(kind="spell", spell_id=1002, simc_action="death_coil", name="death_coil", gcd_ms=1500, base_spell_id=1002),
        dict(kind="spell", spell_id=1003, simc_action="scourge_strike", name="scourge_strike", gcd_ms=1500, base_spell_id=1003),
        dict(kind="spell", spell_id=1004, simc_action="dark_transformation", name="dark_transformation", gcd_ms=1500, base_spell_id=1004),
        dict(kind="item", slot=13, item_id=250245, driver_spell_id=1005,
             simc_action="use_item,slot=trinket1", name="使用trinket1", gcd_ms=0),
    ]
    return dict(actions=actions, precombat_actions=[], sources=[], protocol=3,
                scope="test", coverage="constructed-test-boundary")


def _fast_reference(profile, folder, character, *, runtime=None, iterations=100, seed=20260912,
                    simulation_config=None, import_spell_ids=(), import_spell_names=()):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "native.json").write_text(json.dumps(_fast_report(character, 100.0, max(1, iterations-1))),
                                         encoding="utf-8")
    return dict(static_snapshot=static_snapshot(), dps=100.0, metric="dps", personal_dps=100.0, samples=max(1, iterations-1), seconds=180,
                identity=dict(class_id=6, spec_id=252, spec=character.spec, race=character.race,
                              role=character.fields.get("role", "attack"), resource="runic_power"),
                action_sequence=[{"name": "use_item,slot=trinket1", "queue_failed": False}],
                precombat_sequence=[], actions_protocol=1, executed_actions=[], precombat_definitions=[],
                active_items=[{"slot": "trinket1", "id": 250245, "driver_spell_id": 1005}])


def _fast_inspect(reference, folder, *, include_item=True):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    capabilities = _fast_capabilities()
    if not include_item:
        capabilities["actions"] = [row for row in capabilities["actions"]
                                   if row["kind"] != "item" and row["simc_action"] != "dark_transformation"]
        spell_ids = {"outbreak": 77575, "death_coil": 47541, "scourge_strike": 55090}
        for row in capabilities["actions"]:
            row["spell_id"] = row["base_spell_id"] = spell_ids[row["simc_action"]]
    (folder / "catalogue.json").write_text(json.dumps(capabilities), encoding="utf-8")
    return capabilities


def _fast_report(character, score, samples):
    player = {
        "name": character.name, "sim2gse_class": character.class_name, "level": character.level,
        "sim2gse_class_id": 6, "sim2gse_spec": character.spec,
        "role": character.fields.get('role', 'attack'),
        "sim2gse_spec_id": character.spec_id or 252, "race": character.race,
        "talents": character.fields["talents"], "sim2gse_resource": "runic_power",
        "gear": {{'shoulder': 'shoulders', 'wrist': 'wrists'}.get(slot, slot):
                 {'encoded_item': item.raw} for slot, item in character.equipment.items()},
        "collected_data": {"dps": {"mean": score, "count": samples, "variance": 0}, "fight_length": {"mean": 180},
                           "resource_overflowed": {"runic_power": {"mean": 0}}},
    }
    return {"sim": {"players": [player], "targets": [{"name": "Damage_Dummy", "level": 90}],
                    "statistics": {"raid_dps": {"mean": score, "count": samples}},
                    "options": {"dbc": {"Live": {"build_level": 69587, "wow_version": "12.1.0.69587"}, "version_used": "Live"}}}}


def _fast_evaluate(profile, candidate, folder, *, character, iterations=100,
                   seed=20260912, trace=True, mode="controlled", input_times=None,
                   runtime=None, score_offset=0, simulation_config=None, reset_events=None,
                   on_native_start=None, score=None, rule_observation_request=None, allow_zero=False):
    """构造稳定报告，保留 search.optimize 的选择、缓存和发布逻辑。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if on_native_start is not None:
        on_native_start()
    input_times = list(range(0, 180000, 300)) if input_times is None else list(input_times)
    if score is None:
        # Finite native-boundary landscape: repeating an action is not endless improvement.
        score = score_offset + 100.0 + sum({
            command.get("spell_id", command.get("item_id", 0))
            for block in candidate["blocks"] for command in block
        }) / 1000.0
    samples = max(1, iterations - 1)
    report = _fast_report(character, score, samples)
    (folder / "native.json").write_text(json.dumps(report), encoding="utf-8")
    trace_rows = []
    if trace:
        trace_rows = [
            dict(ms=0, event="input", origin=1, step=0, action="-", signature="-",
                 battle=1, rp=0, health=100, gcd=0, cooldown=0, cast_ms=0),
            dict(ms=0, event="busy", origin=1, step=0, action="feedback_probe",
                 signature="feedback_probe", battle=9001, rp=0, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
            dict(ms=0, event="dispatch_failed", origin=1, step=0, action="feedback_probe",
                 signature="feedback_probe", battle=9002, rp=0, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
            dict(ms=0, event="native_execute", origin=1, step=0, action="outbreak",
                 signature="outbreak", battle=1, rp=1, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
        ]
    return dict(blocks=[[a["simc_action"] for a in block] for block in candidate["blocks"]],
                native_blocks=[[a["simc_action"] for a in block] for block in candidate["blocks"]],
                input_times=input_times, consistent=True,
                summary={"dps": score, "samples": samples}, report=report,
                trace=trace_rows, game_validation="not_run", model="constructed-test-boundary")


def _fast_training_template(_manifest):
    """只取固定上游模板作构造输入，不认证或执行旧构建。真实构建门禁另测。"""
    import engine
    from native_build import source_directory
    manifest = json.loads((engine.ROOT / '.local/sim2gse/build/baseline/build.json').read_text())
    fields = ('protocol', 'source_line_endings', 'mode', 'upstream_commit', 'upstream_tree',
              'patches', 'sources', 'build_options', 'compiler_sha256')
    source = source_directory(engine.ROOT, {name: manifest[name] for name in fields})
    return source / 'profiles/MID2/MID2_Death_Knight_Unholy.simc'


def _fast_identity(mode, runtime=None):
    return Path('simc-test.exe'), dict(mode=mode, upstream_commit='test', build_options=[])


@contextmanager
def _fast_initialization(*, real_engine=False):
    """提供明确单目标测试配置，跳过与状态、缓存和进程故障断言无关的原生初始化。"""
    import codec
    import engine
    import simulation_config

    def compiler(command, *args, **kwargs):
        if kwargs.get("on_start") is not None:
            kwargs["on_start"]()
        output = (b"PASS\tcollection_import_compile\n" if command[-1] == "collection"
                  else b"CHECKSUM\ttest\nPASS\ttest\n")
        return SimpleNamespace(returncode=0, stdout=output, stderr=b"")

    def check_report(report, character, iterations, **kwargs):
        damage = report["sim"]["statistics"]["raid_dps"]
        return dict(dps=damage["mean"], metric="dps", personal_dps=damage["mean"],
                    samples=damage["count"], seconds=180, metadata_only=[], notices=[],
                    identity={"spec_id": character.spec_id or 252, "race": character.race,
                              "resource": "runic_power"})

    identity = _fast_identity
    identity_boundary = nullcontext() if real_engine else patch.object(engine, "identity", side_effect=identity)
    with ExitStack() as boundary:
        boundary.enter_context(patch.dict(simulation_config.DEFAULT_CONFIG, scene='single_target'))
        with identity_boundary, \
             patch.object(engine, "_training_template", side_effect=_fast_training_template), \
             patch.object(engine, "reference", side_effect=_fast_reference), \
             patch.object(engine, "inspect", side_effect=lambda reference, folder:
                          _fast_inspect(reference, folder, include_item=not real_engine)), \
             patch.object(engine, "check_report", side_effect=check_report), \
             patch.object(codec, "run_command", side_effect=compiler):
            yield


@contextmanager
def _fast_search_boundary():
    """仅替换搜索结果生产；任务入口、TaskStore 和搜索状态机仍走真实代码。"""
    import sequence

    with _fast_initialization(), patch.object(sequence, "evaluate", side_effect=_fast_evaluate):
        yield


@contextmanager
def _captured_task_connections():
    import search

    original_connect = search.sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    try:
        with patch.object(search.sqlite3, 'connect', side_effect=connect):
            yield connections
    finally:
        for connection in connections:
            connection.close()


@contextmanager
def _apl_task_boundary(native=None):
    import engine
    import sequence
    native = native or apl_pool_reference()
    real_reference, real_inspect = engine.reference, engine.inspect
    real_check_report = engine.check_report

    def native_process(command, folder, **kwargs):
        profile = Path(folder) / command[1]
        from task import parse_character
        character = parse_character(profile.read_text(encoding='utf-8'))
        iterations = int(next(value.split('=', 1)[1] for value in reversed(command)
                              if value.startswith('iterations=')))
        report = _fast_report(character, 100.0, max(1, iterations - 1))
        targets = int(next(value.split('=', 1)[1] for value in command if value.startswith('desired_targets=')))
        report['sim']['targets'] = [dict(name=f'Damage_Dummy_{i}', level=90) for i in range(targets)]
        player = report['sim']['players'][0]
        player['sim2gse_spec_id'] = native.get('identity', {}).get('spec_id', player['sim2gse_spec_id'])
        player['sim2gse_class_id'] = native.get('identity', {}).get('class_id', player['sim2gse_class_id'])
        player['sim2gse_resource'] = native.get('identity', {}).get('resource', player['sim2gse_resource'])
        player.update(sim2gse_actions_protocol=1, sim2gse_actions=native['executed_actions'],
                      sim2gse_apl_actions_protocol=native.get('apl_actions_protocol'),
                      sim2gse_apl_actions=native.get('apl_actions'),
                      sim2gse_items=[], sim2gse_precombat_actions=native.get('precombat_definitions', []),
                      sim2gse_static_snapshot=native.get('static_snapshot'))
        player['collected_data'].update(action_sequence=native['action_sequence'],
                                         action_sequence_precombat=native.get('precombat_sequence', []))
        report_name = next(value.split('=', 1)[1] for value in command if value.startswith('json2='))
        (Path(folder) / report_name).write_text(json.dumps(report), encoding='utf-8')
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'', elapsed_seconds=0.01)

    with _fast_initialization(), \
            patch.object(engine, 'reference', side_effect=real_reference), \
            patch.object(engine, 'inspect', side_effect=real_inspect), \
            patch.object(engine, 'check_report', side_effect=real_check_report), \
            patch.object(engine, 'run_command', side_effect=native_process), \
            patch.object(sequence, 'evaluate', side_effect=_fast_evaluate):
        yield


@contextmanager
def _initialized_starts(starts):
    """指定起点仍由真实初始化先冻结对应配置与来源证据。"""
    import search
    original = search.initial_programs

    def initialized(*args, **kwargs):
        original(*args, **kwargs)
        return starts

    with patch.object(search, 'initial_programs', side_effect=initialized):
        yield


@contextmanager
def _prepared_search_boundary(directory, starts, *, evaluate=None):
    """构造原生报告，保留真实四起点接口、随机变异、评分和存储。"""
    import sequence
    with _apl_task_boundary(), _initialized_starts(starts), \
            patch.object(sequence, 'evaluate', side_effect=evaluate or _fast_evaluate):
        yield


class SearchAndValidationTests(TestCase):
    def test_task_store_initialization_failure_closes_connection(self):
        import sqlite3

        with tempfile.TemporaryDirectory(prefix='sim2gse-store-init-failure-') as directory:
            destination = Path(directory) / 'task'
            destination.mkdir()
            database = sqlite3.connect(destination / 'task.sqlite3')
            try:
                database.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
                database.execute('INSERT INTO state VALUES (1, ?)', ('{invalid-state',))
                database.commit()
            finally:
                database.close()
            with _captured_task_connections() as connections:
                with self.assertRaises(json.JSONDecodeError) as caught:
                    TaskStore(destination)
                self.assertEqual(caught.exception.doc, '{invalid-state')
                self.assertEqual(len(connections), 1)
                with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
                    connections[0].execute('SELECT 1')

    def test_task_final_publish_failure_still_closes_connection(self):
        import sqlite3
        from runtime import TaskRuntime

        original_write = Path.write_text
        failure = OSError('final progress unavailable')
        runtime = TaskRuntime(60)
        failed_writes = []
        with tempfile.TemporaryDirectory(prefix='sim2gse-final-publish-failure-') as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            destination = Path(directory) / 'task'

            def write(path, *args, **kwargs):
                if path == destination / 'progress.pending.json' and runtime.reservation is None:
                    failed_writes.append(path)
                    raise failure
                return original_write(path, *args, **kwargs)

            with _fast_search_boundary(), _captured_task_connections() as connections, \
                    patch.object(Path, 'write_text', new=write):
                with self.assertRaises(OSError) as caught:
                    run_task(source, destination, _runtime=runtime, search_config=dict(
                        candidate_limit=1, batch_targets=(2,), iterations=2,
                        validation_batches=1, scenarios=('nominal',), max_processes=1))
                self.assertIs(caught.exception, failure)
                self.assertEqual(failed_writes, [destination / 'progress.pending.json'])
                self.assertIsNone(runtime.reservation)
                self.assertEqual(len(connections), 1)
                with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
                    connections[0].execute('SELECT 1')

    def test_normal_task_and_dual_scene_still_refuse_four_processes(self):
        import dual_task
        from search import config_for
        self.assertEqual(config_for()['max_processes'], 2)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            for entry in (run_task, dual_task.start):
                with self.subTest(entry=entry.__name__), self.assertRaisesRegex(ValueError, 'max_processes'):
                    entry(source, Path(directory) / 'task', search_config={'max_processes': 4})

    def test_task_uses_full_apl_pool_without_changing_baseline_starts(self):
        native = apl_pool_reference()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _apl_task_boundary(native):
                result = run_task(source, Path(directory) / 'search', search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2))
                single = run_task(source, Path(directory) / 'single', mode='single')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([row['simc_action'] for row in result['capabilities']['actions']],
                         ['outbreak', 'death_coil', 'scourge_strike', 'death_and_decay', 'epidemic'])
        self.assertEqual(initial_programs(result['capabilities'], native,
                         scene='single_target')[1:], [
            [['outbreak'], ['outbreak'], ['death_coil']],
            [['outbreak'], ['death_coil'], ['outbreak'], ['death_coil']],
            [['scourge_strike'], ['death_coil'], ['outbreak']],
        ])
        self.assertEqual([[row['simc_action'] for row in block] for block in single['candidate']['blocks']],
                         [['outbreak'], ['death_coil'], ['scourge_strike']])

    def test_task_mutates_unexecuted_apl_button_and_scores_exports_it(self):
        import result_store
        import search
        import population_training
        actual_mutate = search.mutate
        mutations = []
        class UnexecutedActionRandom:
            def choice(self, values):
                value = 'insert' if 'insert' in values else 'epidemic'
                assert value in values
                return value
            def random(self):
                return 1.  # Do not divert this sampler test into the separate feedback branch.
            def randrange(self, stop):
                return 0
        def insert_unexecuted(program, capabilities, rng, **kwargs):
            child = actual_mutate(program, capabilities, UnexecutedActionRandom(), **kwargs)
            mutations.append(child)
            return child
        from sequence import compiled_program
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _prepared_search_boundary(directory, [[['outbreak'], ['death_coil']]],
                                         evaluate=_fast_evaluate), \
                    patch.object(population_training, 'mutate', side_effect=insert_unexecuted):
                result = run_task(source, Path(directory) / 'search', search_config=dict(input_interval_ms=200, candidate_limit=9, round_candidate_limit=8,
                    batch_targets=(2,), iterations=2, validation_batches=2))
                ground = run_task(source, Path(directory) / 'ground', mode='single',
                                  program=[['death_and_decay'], ['epidemic']])
                saved = read_task(Path(directory) / 'search', include_search_records=True)
            api = dict(result_store._api())
            read_key = api['read_key']
            requests = []

            def observe(root, table, key, **options):
                if table == 'batches':
                    requests.append(options.get('columns'))
                return read_key(root, table, key, **options)

            api['read_key'] = observe
            with patch.object(result_store, '_SKILL_API', api):
                summary = read_task(Path(directory) / 'ground')
                self.assertEqual(requests, [['batch_key', 'dps', 'samples']])
                self.assertEqual(summary['controlled_simulation']['summary'], ground['controlled_simulation']['summary'])
                self.assertNotIn('report', summary['controlled_simulation'])
                full = read_task(Path(directory) / 'ground', include_reports=True)
                self.assertIsNone(requests[-1])
                self.assertEqual(full['controlled_simulation']['report']['sim']['players'][0]['collected_data']['dps']['mean'],
                                 ground['controlled_simulation']['summary']['dps'])
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(mutations, '必须实际进入共享 GA 使用的变异依赖')
        self.assertTrue(all(['epidemic'] in program for program in mutations))
        self.assertNotIn(['epidemic'], result['search']['records'][0]['program'])
        self.assertIn(['epidemic'], compiled_program(result['candidate']))
        self.assertGreater(result['search_result']['dps'], 0)
        self.assertTrue(result['candidate']['text'].startswith('!GSE3!'))
        self.assertEqual(ground['status'], 'offline_ready')
        self.assertEqual(compiled_program(ground['candidate']), [['death_and_decay'], ['epidemic']])
        self.assertEqual(ground['candidate']['compiled_steps'][0],
                         {'type': 'macro', 'macrotext': '/cast [@player] death_and_decay'})
        self.assertGreater(ground['controlled_simulation']['summary']['dps'], 0)

    @pytest.mark.usefixtures('memory_result_center')
    def test_formal_nominal_retest_selects_from_all_finalists_without_paired_ci(self):
        import search
        from program import canonicalize_search_program
        preferred = [['outbreak']]
        def evaluate(profile, candidate, folder, **kwargs):
            blocks = [[row['simc_action'] for row in block] for block in candidate['blocks']]
            damage = (200. if blocks == preferred else 100.) if kwargs['iterations'] == 32 else (
                50. if blocks == preferred else 150.)
            return _fast_evaluate(profile, candidate, folder, score=damage, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _prepared_search_boundary(directory, [preferred, [['death_coil']]], evaluate=evaluate), \
                    patch.object(search, 'paired_ci', side_effect=AssertionError('正式GA不得套旧CI晋级')):
                result = run_task(source, Path(directory) / 'task')
                saved = read_task(Path(directory) / 'task', include_search_records=True)
            preferred_key = canonicalize_search_program(preferred, result['capabilities'])['identity']
        finalists = result['final']['scenarios']['nominal']['finalists']
        self.assertIn(preferred_key, [row['key'] for row in finalists])
        self.assertNotEqual(result['selected_candidate_key'], preferred_key)
        self.assertEqual(result['search_result']['dps'], 150.)
        self.assertEqual(result['search_result']['samples'], 381)
        self.assertTrue(all(len(row['batches']) == 3 for row in finalists))
        self.assertTrue(all(batch['requested_iterations'] == 32 for row in result['search']['records'] for batch in row['batches']))
        self.assertEqual(saved['search_result'], result['search_result'])
        self.assertEqual(saved['candidate']['text'], result['candidate']['text'])


    @pytest.mark.usefixtures('memory_result_center')
    def test_formal_initial_scores_overlap_with_at_most_two_engines(self):
        import threading
        barrier, lock = threading.Barrier(2, timeout=2), threading.Lock()
        active, peak, initial_calls = 0, 0, []
        starts = [[['outbreak']], [['death_coil']]]
        def evaluate(profile, candidate, folder, **kwargs):
            nonlocal active, peak
            blocks = [[row['simc_action'] for row in block] for block in candidate['blocks']]
            with lock:
                active += 1
                peak = max(active, peak)
            try:
                if kwargs['iterations'] == 32 and blocks in starts:
                    initial_calls.append(blocks)
                    barrier.wait()
                return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
            finally:
                with lock:
                    active -= 1
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _prepared_search_boundary(directory, starts, evaluate=evaluate):
                result = run_task(source, Path(directory) / 'task', search_config=dict(max_processes=2))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(peak, 2)
        self.assertCountEqual(initial_calls, starts)
        self.assertEqual(result['search']['starts'], starts)


    @pytest.mark.usefixtures('memory_result_center')
    def test_cancelled_formal_batches_resume_without_repeating_successful_native_requests(self):
        import threading
        import sequence
        cancel, interrupted, calls = threading.Event(), [False], []
        def evaluate(profile, candidate, folder, **kwargs):
            calls.append(Path(folder).name)
            result = _fast_evaluate(profile, candidate, folder, score=100., **kwargs)
            if not interrupted[0]:
                interrupted[0] = True
                cancel.set()
            return result
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            destination = Path(directory) / 'task'
            with _prepared_search_boundary(directory, [[['outbreak']], [['death_coil']]], evaluate=evaluate):
                stopped = run_task(source, destination, cancel_event=cancel, search_config=dict(max_processes=1))
                self.assertEqual(stopped['status'], 'cancelled')
                self.assertIsNone(stopped.get('selected_candidate_key'))
                self.assertTrue(calls)
                first = calls[0]
                cancel.clear()
                resumed = resume_task(destination)
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual(calls.count(first), 1)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(resumed['search_result']['samples'], 381)





    def test_run_task_deduplicates_equivalent_programs_before_native_evaluation(self):
        import codec
        import search
        import sequence

        action = "use_item,slot=trinket1"
        equivalent_programs = [
            [dict(kind="Loop", count=2, blocks=[[action]])],
            [[action], [action]],
        ]
        evaluated = []
        compiler_calls = []

        def compiler(command, *args, **kwargs):
            compiler_calls.append((command[-1], str(kwargs.get("output_dir"))))
            if kwargs.get("on_start") is not None:
                kwargs["on_start"]()
            output = b"CHECKSUM\ttest\nPASS\ttest\n"
            return SimpleNamespace(returncode=0, stdout=output, stderr=b"")

        def evaluate(profile, candidate, folder, **kwargs):
            clicks = candidate["compiled_program"]["clicks"]
            plan = [click.get("commands", []) for click in clicks]
            evaluated.append((kwargs["iterations"], plan))
            return _fast_evaluate(profile, candidate, folder, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-canonical-task-") as directory:
            source = Path(directory) / "角色.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37)
            with _fast_search_boundary(), \
                    _initialized_starts(equivalent_programs), \
                    patch.object(codec, "run_command", side_effect=compiler), \
                    patch.object(sequence, "evaluate", side_effect=evaluate):
                result = run_task(source, Path(directory) / "task", search_config=config)

        expected_plan = [[action], [action]]
        matching_records = [
            record for record in result["search"]["records"]
            if [click.get("commands", []) for click in record["candidate"]["compiled_program"]["clicks"]]
            == expected_plan
        ]
        matching_evaluations = [row for row in evaluated if row == (32, expected_plan)]
        self.assertEqual((len(matching_records), len(matching_evaluations)), (1, 1))
        matching_compiles = [mode for mode, folder in compiler_calls
                             if folder.endswith(matching_records[0]["key"])]
        self.assertEqual(len(matching_compiles), 1)

    def test_search_observability_is_off_by_default_and_preserves_selection(self):
        import sequence
        import result_store

        with tempfile.TemporaryDirectory(prefix="sim2gse-search-observability-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, round_candidate_limit=1, batch_targets=(2,),
                          iterations=2, validation_batches=1, final_batches=1,
                          final_iterations=2, scenarios=("nominal",), max_processes=1,
                          random_seed=37)

            def run(name, mode=None):
                destination = root / name / "task"
                options = dict(config)
                if mode is not None:
                    options["search_observability"] = mode
                    options["diagnostic_logging"] = True
                center = root / (name + '-center')
                center.mkdir()
                requests = []
                with patch.object(result_store, 'DATA_ROOT', center), \
                        _fast_search_boundary(), _initialized_starts([[['outbreak']]]):
                    evaluate = sequence.evaluate
                    def record_request(profile, candidate, folder, **kwargs):
                        requests.append((sequence.behavior_key(candidate), kwargs['seed'],
                                         kwargs['iterations'], kwargs['trace']))
                        return evaluate(profile, candidate, folder, **kwargs)
                    with patch.object(sequence, 'evaluate', side_effect=record_request):
                        result = run_task(source, destination, search_config=options)
                progress = (json.loads((destination / 'diagnostics.json').read_text())['performance']['candidate_progress']
                            if mode is not None else None)
                return result, requests, result['search']['formal_champion_snapshot']['binding']['condition'], progress

            baseline, baseline_requests, baseline_condition, _ = run("off")
            observed, observed_requests, observed_condition, progress = run("full", "full")

        self.assertEqual(baseline['search']['starts'], observed['search']['starts'])
        self.assertEqual(baseline['search']['formal_champion_snapshot']['status'], 'absent')
        self.assertEqual(observed['search']['formal_champion_snapshot']['status'], 'absent')
        self.assertNotIn("observability", baseline["search"])
        self.assertEqual(baseline["selected_candidate_key"], observed["selected_candidate_key"])
        self.assertEqual(baseline_requests, observed_requests)
        self.assertEqual(baseline_condition, observed_condition)

        def score_snapshot(result):
            records = []
            for record in result["search"]["records"]:
                validations = {}
                for name in ("validation", "global_validation"):
                    comparison = record.get(name)
                    if comparison:
                        validations[name] = tuple(
                            tuple((row["dps"], row["samples"], row["request"]["seed"])
                                  for row in comparison[side])
                            for side in ("candidate", "control"))
                records.append((record["key"], record["program"], record["score"],
                                tuple((row["dps"], row["samples"], row["request"]["seed"])
                                      for row in record["batches"]), validations))
            return records

        self.assertEqual(sorted(score_snapshot(baseline)), sorted(score_snapshot(observed)))
        summary = observed['search']['observability']['summary']
        self.assertEqual(summary['initial_candidates'], 1)
        self.assertGreater(summary['mutation_attempts'], 0)
        self.assertEqual(summary['score_completed'], len(observed['search']['records']))
        self.assertTrue(observed['search']['observability']['details'])
        actual_coarse = {key for key, _, iterations, _ in observed_requests if iterations == 32}
        self.assertEqual({row['behavior_identity'] for row in progress['screening_archived']}, actual_coarse)


    def test_resume_rejects_checkpoint_from_an_old_behavior_identity_version(self):
        import sqlite3

        directory = tempfile.mkdtemp(prefix="sim2gse-old-identity-")
        try:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1)
            with _fast_search_boundary():
                run_task(source, destination, search_config=config)
            result_before = json.loads((destination / "result.json").read_text(encoding="utf-8"))
            with sqlite3.connect(destination / "task.sqlite3") as database:
                state = TaskStore.load_state(database)
                state["behavior_identity_version"] = "obsolete-version"
                state["elapsed_seconds"] = config["total_budget_seconds"]
                database.execute("UPDATE state SET value=? WHERE id=1",
                                 (json.dumps(state),))
                database.commit()
            database.close()
            with _fast_search_boundary(), self.assertRaisesRegex(
                    TaskError, "候选行为身份版本已变化"):
                resume_task(destination)
            self.assertEqual(json.loads((destination / "result.json").read_text(encoding="utf-8")),
                             result_before)
        finally:
            for attempt in range(20):
                try:
                    shutil.rmtree(directory)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.05)

    def test_run_task_rejects_canonical_compiler_mismatch_before_native_evaluation(self):
        import program as program_module
        import search
        import sequence

        real_canonicalize = program_module.canonicalize_search_program
        evaluated = []

        def canonicalize(search_program, capabilities):
            result = real_canonicalize(search_program, capabilities)
            if search_program == [["outbreak"]]:
                result["form"] = dict(result["form"], clicks=[["death_coil"]])
            return result

        def evaluate(profile, candidate, folder, **kwargs):
            plan = [click.get("commands", [])
                    for click in candidate["compiled_program"]["clicks"]]
            evaluated.append(plan)
            return _fast_evaluate(profile, candidate, folder, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-canonical-mismatch-") as directory:
            source = Path(directory) / "角色.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=41)
            with _fast_search_boundary(), \
                    _initialized_starts([[['outbreak']], [['death_coil']]]), \
                    patch.object(program_module, "canonicalize_search_program",
                                 side_effect=canonicalize), \
                    patch.object(sequence, "evaluate", side_effect=evaluate):
                with self.assertRaisesRegex(TaskError, "标准形式与编译计划不一致"):
                    run_task(source, Path(directory) / "task", search_config=config)

        self.assertNotIn([["outbreak"]], evaluated)

    def test_canonical_identity_expands_repeat_once_and_preserves_source_tree(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        loop = canonicalize_search_program(
            [dict(kind="Loop", count=1, blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
            capabilities,
        )
        expanded = canonicalize_search_program(
            [["outbreak"], ["use_item,slot=trinket1"]], capabilities
        )

        self.assertEqual(loop["identity"], expanded["identity"])
        repeated = canonicalize_search_program(
            [dict(kind="Loop", count=2, blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
            capabilities,
        )
        self.assertNotEqual(loop["identity"], repeated["identity"])
        self.assertEqual(loop["form"]["clicks"],
                         [["outbreak"], ["use_item,slot=trinket1"]])
        self.assertEqual(loop["form"]["version"], "sim2gse-search-behavior-v2")
        self.assertEqual(loop["form"]["precombat_count"], 0)
        self.assertEqual(loop["program"]["nodes"][0]["kind"], "Loop")
        self.assertNotEqual(loop["program"]["nodes"][0]["source"],
                            expanded["program"]["nodes"][0]["source"])

    def test_canonical_identity_keeps_action_block_boundaries_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        item = "use_item,slot=trinket1"
        one_block = canonicalize_search_program([["outbreak", item]], capabilities)
        two_blocks = canonicalize_search_program([["outbreak"], [item]], capabilities)

        self.assertNotEqual(one_block["identity"], two_blocks["identity"])

    def test_canonical_identity_keeps_castsequence_reset_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        without_reset = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"], reset=None)],
            capabilities,
        )
        with_reset = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3, "flags": ["target"]})], capabilities
        )

        self.assertNotEqual(without_reset["identity"], with_reset["identity"])
        changed_member = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "scourge_strike"], reset=None)],
            capabilities,
        )
        self.assertNotEqual(without_reset["identity"], changed_member["identity"])
        duplicate_flag = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3, "flags": ["target", "target"]})], capabilities
        )
        self.assertEqual(with_reset["identity"], duplicate_flag["identity"])
        self.assertEqual(duplicate_flag["form"]["castsequences"][0]["reset"]["flags"], ["target"])

    def test_canonical_identity_rejects_invalid_wait_click_counts_with_location(self):
        from program import canonicalize_search_program

        for clicks in (1, 4097):
            with self.subTest(clicks=clicks), self.assertRaisesRegex(
                    ValueError, r"segments\[0\].*WaitClicks"):
                canonicalize_search_program(
                    [dict(kind="WaitClicks", clicks=clicks), ["outbreak"]], _fast_capabilities()
                )

    def test_canonical_identity_rejects_expansion_over_4096_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"blocks\[0\].*4096"):
            canonicalize_search_program(
                [dict(kind="Loop", count=4096,
                      blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
                _fast_capabilities(),
            )

    def test_search_starts_match_fixed_baseline_golden(self):
        """导入专用动作目录不改变基线搜索起点或顺序。"""
        capabilities = dict(
            actions=[
                dict(kind="spell", spell_id=77575, simc_action="outbreak"),
                dict(kind="spell", spell_id=47541, simc_action="death_coil"),
                dict(kind="spell", spell_id=55090, simc_action="scourge_strike"),
            ],
            import_actions=[dict(kind="spell", spell_id=316239, simc_action="import_only")],
        )
        reference = dict(identity={"spec_id": 252}, static_snapshot=static_snapshot(), action_sequence=[
            dict(name="outbreak"), dict(name="death_coil"), dict(name="outbreak"),
            dict(name="scourge_strike", queue_failed=True), dict(name="unknown_action"),
        ])
        expected = [
            [["outbreak"], ["outbreak"], ["death_coil"]],
            [["outbreak"], ["death_coil"], ["outbreak"], ["death_coil"]],
            [["scourge_strike"], ["death_coil"], ["outbreak"]],
        ]

        with _fast_initialization():
            starts = initial_programs(capabilities, reference, seed=20260912, scene='single_target')
        self.assertEqual(starts[1:], expected)
        from search import input_times
        first = input_times("jitter", seed=20260912)
        self.assertEqual(first, input_times("jitter", seed=20260912))
        self.assertNotEqual(first, input_times("jitter", seed=20260913))

    def test_public_entry_runs_multi_start_search_with_isolated_validation(self):
        import sequence
        real_evaluate = sequence.evaluate
        native_score = None
        def evaluate(*args, **kwargs):
            nonlocal native_score
            if native_score is None:
                result = real_evaluate(*args, **kwargs)
                native_score = result["summary"]["dps"]
                return result
            return _fast_evaluate(*args, score_offset=native_score, **kwargs)
        with tempfile.TemporaryDirectory(prefix="sim2gse-search-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_initialization(real_engine=True), patch.object(sequence, "evaluate", side_effect=evaluate):
                result = run_task(
                    source,
                    destination,
                    mode="optimize",
                    search_config={
                    "total_budget_seconds": 120,
                    "search_budget_seconds": 90,
                    "candidate_limit": 4,
                    "batch_targets": (2,),
                    "validation_batches": 2,
                    "final_batches": 1,
                    "iterations": 2,
                    "scenarios": ("nominal",),
                    "max_processes": 1,
                    },
                )

            self.assertIsNotNone(native_score)
            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(len(result["search"]["starts"]), 2)
            self.assertIn("validation", result)
            self.assertIn("final", result)
            self.assertEqual(result["improvement"], "search_result")
            self.assertEqual(result["selected_candidate_key"], result["locked_candidate_key"])
            self.assertEqual(read_task(destination)["candidate"]["text"], result["candidate"]["text"])
            self.assertNotEqual(result["search"]["dataset"], result["validation"]["dataset"])
            self.assertNotEqual(result["validation"]["dataset"], result["final"]["dataset"])

            search_seeds={row['request']['seed'] for record in result['search']['records'] for row in record['batches']}
            final_seeds={row['request']['seed'] for finalist in result['final']['scenarios']['nominal']['finalists'] for row in finalist['batches']}
            self.assertTrue(search_seeds and final_seeds)
            self.assertFalse(search_seeds & final_seeds)
            self.assertEqual(result['validation']['records'], [])
            self.assertTrue(result['independent_validation_complete'])


    def test_search_resumes_without_resetting_budget_or_batches(self):
        import sequence
        import threading
        paused = threading.Event()
        calls = 0

        def pause_second_batch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                paused.set()
                if not kwargs["runtime"].cancel_event.wait(5):
                    raise AssertionError("test did not cancel the paused batch")
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-resume-") as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=120, search_budget_seconds=60,
                          candidate_limit=4, batch_targets=(2,), validation_batches=2,
                          final_batches=3, final_iterations=2, iterations=2, max_processes=1,
                          diagnostic_logging=True)
            with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=pause_second_batch):
                handle = start_task(source, destination, search_config=config)
                try:
                    self.assertTrue(paused.wait(5), "search never reached its second batch")
                    deadline = time.monotonic() + 5
                    observed = read_task(destination)
                    while observed.get("phase") not in ("initial", "breed", "retest") and time.monotonic() < deadline:
                        time.sleep(0.01)
                        observed = read_task(destination)
                    self.assertIn(observed.get("phase"), ("initial", "breed", "retest"))
                    self.assertEqual(observed.get("completed_batches", 0), 0)
                    with self.assertRaisesRegex(TaskError, "正在运行"):
                        resume_task(destination)
                    cancel_task(handle)
                finally:
                    if not handle.done:
                        cancel_task(handle)
                    handle.join(5)
                self.assertTrue(handle.done)
                cancelled = read_task(destination, include_search_records=True)
                self.assertEqual(cancelled["status"], "cancelled")
                self.assertGreater(cancelled['completed_batches'], 0)
                resumed = resume_task(destination, diagnostic_logging=True)
            self.assertEqual(resumed['search']['records'][0]['key'], cancelled['search']['records'][0]['key'])
            self.assertGreater(resumed["elapsed_seconds"], cancelled["elapsed_seconds"])
            self.assertGreaterEqual(resumed["completed_batches"], cancelled["completed_batches"])
            for name in ("batch_requests", "batch_cache_hits", "native_batch_starts",
                         "canonicalized_duplicates"):
                self.assertIn(name, cancelled["search"])
                self.assertGreaterEqual(resumed["search"][name], cancelled["search"][name])
            self.assertTrue(resumed["independent_validation_complete"])
            self.assertEqual(set(resumed["final"]["scenarios"]), {"nominal"})

    def test_corrupt_parquet_cache_shard_is_recomputed(self):
        import result_store
        import sequence

        calls = []
        def evaluate(*args, **kwargs):
            calls.append(Path(args[2]).name)
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='sim2gse-corrupt-center-') as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
                          batch_targets=(2,), iterations=2, validation_batches=1,
                          final_batches=1, final_iterations=2, scenarios=('nominal',),
                          max_processes=1, diagnostic_logging=True, diagnostics='summary')
            # Freeze the same starts for all invocations; this case tests cache repair, not champion inheritance.
            with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), \
                    patch.object(result_store, 'read_search_champion', return_value=None):
                first_destination = Path(directory) / 'first'
                first = run_task(source, first_destination, search_config=config)
                saved_task = read_task(first_destination, include_search_records=True)
                performance = json.loads((first_destination / 'diagnostics.json').read_text())['performance']
                progress = performance['candidate_progress']
                keys = {row['key'] for row in saved_task['search']['records']}
                self.assertTrue(keys)
                self.assertGreaterEqual(performance['stages']['candidate.compile']['calls'], len(keys))
                self.assertEqual(performance['stages']['candidate.write']['calls'],
                                 performance['stages']['candidate.compile']['calls'])
                initial_calls = list(calls)
                for kind in ('first_score_published', 'screening_archived'):
                    self.assertEqual({row['behavior_identity'] for row in progress[kind]}, keys)
                    self.assertEqual(len(progress[kind]), len(keys))
                    for event in progress[kind]:
                        self.assertGreaterEqual(event['invocation_seconds'], 0)
                        self.assertGreaterEqual(event['budget_elapsed_seconds'], event['invocation_seconds'])
                cached_destination = Path(directory) / 'cached'
                with patch.object(sequence, 'evaluate', side_effect=AssertionError('复用不得重新评分')):
                    run_task(source, cached_destination, search_config=config)
                cached_performance = json.loads((cached_destination / 'diagnostics.json').read_text())['performance']
                for kind in ('first_score_published', 'screening_archived'):
                    self.assertEqual(cached_performance['candidate_progress'][kind], [])
                self.assertEqual(calls, initial_calls)
                batch_key = first['search']['records'][0]['batches'][0]['data_key']
                # Fault injection only: mimic a damaged Parquet shard behind the read-only API.
                saved = result_store.one('batches', 'batch_key', batch_key)
                lost_keys = {row['batch_key'] for row in result_store.read_records('batches', saved['storage_group_key'])}
                shard = result_store.DATA_ROOT / 'batches' / f"{saved['storage_group_key']}.parquet"
                shard.write_bytes(b'corrupt parquet')
                second = run_task(source, Path(directory) / 'second', search_config=config)

            with closing(__import__('sqlite3').connect(Path(directory) / 'second' / 'task.sqlite3')) as database:
                persisted = json.loads(database.execute('SELECT value FROM batches WHERE key=?', (batch_key,)).fetchone()[0])
                self.assertEqual(persisted['status'], 'success')
                self.assertEqual(TaskStore.load_state(database)['completed_batches'], first['completed_batches'])
            self.assertEqual(set(calls[len(initial_calls):]), lost_keys)
            self.assertEqual(len(calls) - len(initial_calls), len(lost_keys))
            self.assertFalse(second['search']['records'][0]['batches'][0].get('cached', False))
            self.assertIsNotNone(result_store.one('batches', 'batch_key', batch_key)['report'])

    def test_cold_cache_storage_failure_and_cancellation_do_not_resimulate(self):
        import result_store
        import sequence
        import threading

        with tempfile.TemporaryDirectory(prefix='sim2gse-cold-read-') as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, candidate_limit=1, batch_targets=(2,),
                          iterations=2, validation_batches=1, max_processes=1,
                          scenarios=('nominal',))
            original = result_store.one
            with _fast_search_boundary():
                first = run_task(source, Path(directory) / 'first', search_config=config)
                for failure in ('unavailable', 'cancelled'):
                    with self.subTest(failure=failure):
                        cancelled = threading.Event()

                        def read(table, field, value, **kwargs):
                            if table == 'batches' and failure == 'unavailable':
                                raise result_store.DataReadError('storage unavailable')
                            result = original(table, field, value, **kwargs)
                            if table == 'batches':
                                cancelled.set()
                            return result

                        with patch.object(result_store, 'one', side_effect=read), \
                                patch.object(sequence, 'evaluate', side_effect=AssertionError('unexpected resimulation')):
                            if failure == 'unavailable':
                                with self.assertRaisesRegex(TaskError, 'storage unavailable'):
                                    run_task(source, Path(directory) / failure, search_config=config)
                            else:
                                result = run_task(source, Path(directory) / failure,
                                                  search_config=config, cancel_event=cancelled)
                                self.assertEqual(result['status'], 'cancelled')
                self.assertEqual(read_task(Path(directory) / 'first')['status'], first['status'])

    def test_valid_exchange_report_is_kept_when_center_write_fails(self):
        import result_store
        import sequence

        original_write = result_store.write
        exchange_paths = []
        def fail_search_batch_write(table, key, rows, **kwargs):
            if table == 'batches' and rows[0].get('purpose') == 'search':
                raise OSError('synthetic data-center write failure')
            return original_write(table, key, rows, **kwargs)

        def evaluate(*args, **kwargs):
            exchange_paths.append(Path(args[2]) / 'native.json')
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='sim2gse-write-failure-') as directory:
            source = Path(directory) / 'role.simc'
            destination = Path(directory) / 'task'
            source.write_text(sample_profile(), encoding='utf-8')
            with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate), \
                    patch.object(result_store, 'write', side_effect=fail_search_batch_write):
                with self.assertRaisesRegex(TaskError, 'synthetic data-center write failure'):
                    run_task(source, destination, search_config=dict(
                        total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
                        batch_targets=(2,), iterations=2, validation_batches=1,
                        final_batches=1, final_iterations=2, scenarios=('nominal',), max_processes=1))
            self.assertTrue(exchange_paths)
            for path in exchange_paths:
                self.assertTrue(path.is_file(), '保存失败不能删除已成功原生报告: ' + str(path))
                self.assertIsInstance(json.loads(path.read_text(encoding='utf-8')), dict)

    def test_task_hard_exit_preserves_checkpoint_and_cleans_owned_engine(self):
        import os
        import ctypes
        from ctypes import wintypes
        import subprocess
        import json
        class Entry(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                      ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                      ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                      ('exe',wintypes.WCHAR*260)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        def children(pid):
            snapshot=kernel.CreateToolhelp32Snapshot(2,0)
            row=Entry();row.size=ctypes.sizeof(row)
            processes=[]
            try:
                more=kernel.Process32FirstW(snapshot,ctypes.byref(row))
                while more:
                    processes.append((row.pid, row.parent, row.exe.lower()))
                    more=kernel.Process32NextW(snapshot,ctypes.byref(row))
                descendants={pid}
                while True:
                    expanded=descendants | {child for child,parent,_ in processes if parent in descendants}
                    if expanded==descendants:
                        break
                    descendants=expanded
                return [(child, parent) for child,parent,name in processes
                        if child in descendants and name=='simc.exe']
            finally:
                kernel.CloseHandle(snapshot)
        with tempfile.TemporaryDirectory(prefix='sim2gse-crash-') as directory, ExitStack() as outputs:
            source=Path(directory)/'role.simc';destination=Path(directory)/'task'
            source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=60,search_budget_seconds=30,candidate_limit=20,
                        batch_targets=(2,),validation_batches=1,final_batches=2,iterations=2,
                        final_iterations=32,max_processes=2)
            import result_store
            # 此场景提前提交首个真实成功批次；生产报告仍保留原分组缓冲策略。
            code='\n'.join((
                "import sys,json,runpy",
                "from pathlib import Path",
                "sys.path.insert(0,sys.argv[1])",
                "import result_store,search",
                "result_store.DATA_ROOT=Path(sys.argv[5])",
                "result_store._SKILL_API=runpy.run_path(sys.argv[6])",
                # This ownership/recovery smoke keeps real native scoring, not exploration cost.
                "native_starts=search.initial_programs",
                "search.initial_programs=lambda *a,**k: native_starts(*a,**k)[:1]",
                "search.mutate=lambda program,*a,**k: program",
                "class CheckpointStore(search.TaskStore):",
                "    def stage_report(self,key,row,stored,**kwargs):",
                "        super().stage_report(key,row,stored,**kwargs)",
                "        with self.lock:",
                "            if row.get('status')=='success' and self.persisted_batches==0:",
                "                self.checkpoint()",
                "                self.publish()",
                "search.TaskStore=CheckpointStore",
                "from task import run_task",
                "run_task(sys.argv[2],sys.argv[3],search_config=json.loads(sys.argv[4]),"
                "simulation_config=dict(scene='single_target'))"))
            stdout_path, stderr_path = [Path(directory) / name for name in ('child.stdout', 'child.stderr')]
            stdout = outputs.enter_context(stdout_path.open('wb'))
            stderr = outputs.enter_context(stderr_path.open('wb'))
            process=subprocess.Popen([sys.executable,'-c',code,str(REPOSITORY/'projects/sim2gse'),
                                      str(source),str(destination),json.dumps(config),str(result_store.DATA_ROOT),
                                      str(Path(os.environ['DATA_STORE_TEST_SKILL'])/'scripts/data_store.py')],
                                     stdout=stdout, stderr=stderr)
            held=owner=None
            try:
                started=time.monotonic()
                deadline=started+45
                state={}
                while time.monotonic()<deadline and process.poll() is None:
                    try: state=read_task(destination, include_rule_initialization=False)
                    except TaskError: pass
                    completed = state.get('completed_batches')
                    if state.get('phase') == 'retest' and type(completed) is int and completed > 0:
                        for pid,owner_pid in children(process.pid):
                            held=kernel.OpenProcess(0x100000,False,pid)
                            if held:
                                if kernel.WaitForSingleObject(held,0) != 258:
                                    kernel.CloseHandle(held)
                                    held=None
                                    continue
                                owner=kernel.OpenProcess(0x100000,False,owner_pid)
                                if owner: break
                                kernel.CloseHandle(held)
                                held=None
                    if held: break
                    time.sleep(0.02)
                failure_context = {}
                if held is None:
                    failure_context = dict(returncode=process.poll(), elapsed=time.monotonic()-started,
                        state={key: state.get(key) for key in ('status', 'phase', 'completed_batches',
                            'elapsed_seconds', 'stop_reason')})
                    for name, path in (('stdout_tail', stdout_path), ('stderr_tail', stderr_path)):
                        with path.open('rb') as output:
                            output.seek(0, os.SEEK_END)
                            output.seek(max(0, output.tell()-4096))
                            failure_context[name] = output.read().decode('utf-8', errors='replace')
                self.assertIsNotNone(held,'没有在已完成批次检查点后观察到真实引擎进程: ' +
                                     json.dumps(failure_context, ensure_ascii=False))
                self.assertEqual(state['phase'], 'retest')
                self.assertGreater(state['completed_batches'], 0)
                self.assertEqual(kernel.WaitForSingleObject(held,0),258,
                                 '硬退出前真实引擎必须仍在运行，不能用已完成进程证明清理')
                process.kill();process.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(owner,2000),0,'实际任务进程尚未退出，不能恢复')
                self.assertEqual(kernel.WaitForSingleObject(held,2000),0,'任务退出后仍有所属模拟进程')
                # A heartbeat may be newer than the last durable business checkpoint.
                # The crash contract retains committed time, not an uncommitted live tail.
                with closing(__import__('sqlite3').connect(
                        (destination / 'task.sqlite3').as_uri() + '?mode=ro', uri=True)) as database:
                    checkpoint = TaskStore.load_state(database)
                before = checkpoint['elapsed_seconds']
                self.assertGreater(checkpoint['completed_batches'], 0)
                resumed=resume_task(destination, simulation_config=dict(scene='single_target'))
                self.assertGreaterEqual(resumed['elapsed_seconds'], before,
                    f"durable={before}, live_before_crash={state['elapsed_seconds']}")
                self.assertGreaterEqual(resumed['completed_batches'], checkpoint['completed_batches'])
            finally:
                if owner:kernel.CloseHandle(owner)
                if held:kernel.CloseHandle(held)
                if process.poll() is None:process.kill();process.wait(timeout=5)

    def test_owned_process_tree_hard_exit_does_not_stop_other_owner(self):
        # 补充进程系统边界检查；产品恢复仍由上方 run_task 测试覆盖。
        import ctypes
        from ctypes import wintypes
        import subprocess,json
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        directory=tempfile.mkdtemp(prefix='sim2gse-ownership-')
        try:
            owners=[];held=[]
            child="import subprocess,sys,time,os,json;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(60)"
            owner="import sys;sys.path.insert(0,sys.argv[1]);from runtime import run_command;run_command([sys.executable,'-c',sys.argv[2],sys.argv[3]],sys.argv[4],timeout_seconds=60)"
            try:
                for index in range(2):
                    folder=Path(directory)/str(index);folder.mkdir()
                    pids=folder/'pids.json'
                    process=subprocess.Popen([sys.executable,'-c',owner,str(REPOSITORY/'projects/sim2gse'),child,str(pids),str(folder)],creationflags=subprocess.CREATE_NO_WINDOW)
                    owners.append(process)
                    deadline=time.monotonic()+8
                    while not pids.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    ids=json.loads(pids.read_text())
                    handles=[kernel.OpenProcess(0x100000,False,pid) for pid in ids]
                    self.assertTrue(all(handles));held.append(handles)
                owners[0].kill();owners[0].wait(timeout=3)
                for handle in held[0]:self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
                for handle in held[1]:self.assertEqual(kernel.WaitForSingleObject(handle,0),258)
            finally:
                for owner_process in owners:
                    if owner_process.poll() is None:owner_process.kill();owner_process.wait(timeout=3)
                for handles in held:
                    for handle in handles:
                        self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
                        kernel.CloseHandle(handle)
        finally:
            for attempt in range(21):
                try:
                    shutil.rmtree(directory)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if attempt==20:raise
                    time.sleep(0.05)

    def test_completed_search_removes_native_report_exchange_files(self):
        import sequence
        import result_store

        def evaluate_with_damage_detail(*args, **kwargs):
            result = _fast_evaluate(*args, **kwargs)
            collected = result['report']['sim']['players'][0]['collected_data']
            collected['action_sequence'] = [{'time': 0.5, 'name': 'outbreak'}]
            collected['action_sequence_precombat'] = [{'time': -1.0, 'name': 'raise_dead'}]
            collected['combat_end_resource'] = {}
            collected['dps']['distribution'] = [98.25, 102.5]
            collected['damage_sources'] = [{'source': 'outbreak', 'damage': 1250.5}]
            collected['pet_damage'] = [{'source': 'ghoul', 'damage': 250.25}]
            (Path(args[2]) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
            return result

        with tempfile.TemporaryDirectory(prefix='sim2gse-data-store-') as directory:
            source = Path(directory) / 'role.simc'
            destination = Path(directory) / 'task'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
                          batch_targets=(2,), iterations=2, validation_batches=1,
                          final_batches=1, final_iterations=2, scenarios=('nominal',),
                          max_processes=1)
            with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate_with_damage_detail):
                result = run_task(source, destination, search_config=config)

            self.assertEqual(result['status'], 'completed')
            self.assertEqual(list(destination.rglob('native.json')), [])
            batch = result['search']['records'][0]['batches'][0]
            report = result_store.one('batches', 'batch_key', batch['data_key'])['report']
            collected = report['sim']['players'][0]['collected_data']
            self.assertNotIn('action_sequence', collected)
            self.assertNotIn('action_sequence_precombat', collected)
            self.assertIsNone(collected['combat_end_resource'])
            self.assertEqual(collected['dps']['distribution'], [98.25, 102.5])
            self.assertEqual(collected['damage_sources'][0]['damage'], 1250.5)
            self.assertEqual(collected['pet_damage'][0]['damage'], 250.25)
            loaded = read_task(destination, include_search_records=True, include_reports=True)
            self.assertEqual(loaded['candidate']['text'], result['candidate']['text'])
            self.assertEqual(loaded['search_result'], result['search_result'])
            self.assertNotIn('action_sequence', loaded['native_reference'])
            self.assertEqual(loaded['search']['records'][0]['batches'][0]['request']['times'],
                             batch['request']['times'])
            candidates = list(result_store.iter_rows(
                'SELECT candidate_key, export_text FROM candidates WHERE run_id = ?',
                [loaded['run_id']], tables=['candidates']))
            self.assertIn(batch['request']['behavior_identity'],
                          {candidate['candidate_key'] for candidate in candidates})
            self.assertIn(result['candidate']['text'],
                          {candidate['export_text'] for candidate in candidates})
            try:
                stored_traces = list(result_store.iter_rows(
                    'SELECT event_index FROM traces WHERE run_id = ?', [loaded['run_id']], tables=['traces']))
            except result_store.DataReadError:
                stored_traces = []
            self.assertEqual(stored_traces, [])
            reference = result_store.one('batches', 'batch_key', loaded['reference_data_key'])
            self.assertEqual(reference['report']['sim']['statistics']['raid_dps']['mean'], 100.0)
            pointer = json.loads((destination / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(pointer['run_id'], loaded['run_id'])
            self.assertNotIn('report', pointer)
            run = result_store.one('runs', 'run_id', loaded['run_id'])
            self.assertNotIn('result', run)
            for table in ("candidates", "batches"):
                (result_store.DATA_ROOT / table / "foreign.parquet").write_bytes(b"unrelated broken shard")
            known = read_task(destination, include_search_records=True, include_reports=False)
            self.assertEqual(known["candidate"]["text"], result["candidate"]["text"])
            self.assertEqual(len(known["search"]["records"]), len(result["search"]["records"]))
            self.assertEqual(known["search"]["records"][0]["candidate"]["identity"],
                             result["search"]["records"][0]["key"])
            self.assertNotIn("report", known.get("controlled_simulation", {}))

    def test_native_global_failure_stops_task(self):
        import ctypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        def process_boundary(*args):
            if 'batches' in str(args[7]):
                args=list(args)
                args[0]=str(Path(sys.executable).resolve())
                args[1]=ctypes.create_unicode_buffer('"'+args[0]+'" -c "import sys;sys.exit(9)"')
            return original(*args)
        with tempfile.TemporaryDirectory(prefix='sim2gse-engine-error-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            with _fast_initialization(), patch.object(runtime._kernel32,'CreateProcessW',side_effect=process_boundary):
                with self.assertRaisesRegex(TaskError,'原生引擎失败'):
                    run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=60,search_budget_seconds=30,candidate_limit=2))

    @pytest.mark.usefixtures('memory_result_center')
    def test_formal_deduplicates_legal_starts_and_stops_on_complete_generation_stagnation(self):
        starts = [[['outbreak']], [['death_coil']]]
        def equal_damage(*args, **kwargs):
            return _fast_evaluate(*args, score=100., **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _prepared_search_boundary(directory, starts + [starts[0], [['missing_action']]], evaluate=equal_damage):
                result = run_task(source, Path(directory) / 'task')
                saved = read_task(Path(directory) / 'task')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['search']['starts'], starts)
        self.assertEqual(result['search']['stop_reason'], 'stagnation')
        self.assertGreaterEqual(result['search']['complete_generations'], 2)
        self.assertEqual(result['search']['formal_search']['config']['stagnation_generations'], 2)
        self.assertFalse(result['search']['partial_round'])
        self.assertEqual(saved['search']['stop_reason'], 'stagnation')
        self.assertEqual(saved['search_result']['samples'], 381)
        self.assertEqual([row['status'] for row in saved['search']['start_adaptations']],
                         ['accepted', 'accepted', 'duplicate', 'rejected'])




    def test_process_creation_failure_releases_thread_and_temporary_files(self):
        import ctypes
        from ctypes import wintypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        runtime._kernel32.GetHandleInformation.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        held=[]
        def interrupted_create(*args):
            result=original(*args)
            if result:
                info=ctypes.cast(args[9],ctypes.POINTER(runtime._PROCESS_INFORMATION)).contents
                held.append(info.hThread)
                raise OSError('injected after process creation')
            return result
        with tempfile.TemporaryDirectory(prefix='sim2gse-create-failure-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            destination=Path(directory)/'task'
            with patch.object(runtime._kernel32,'CreateProcessW',side_effect=interrupted_create):
                with self.assertRaises(TaskError):run_task(source,destination)
            flags=wintypes.DWORD()
            leaked=[]
            for handle in held:
                if runtime._kernel32.GetHandleInformation(handle,ctypes.byref(flags)):
                    leaked.append(handle);runtime._kernel32.CloseHandle(handle)
            self.assertFalse(leaked,'创建中断泄漏线程句柄')
            self.assertFalse(list(destination.rglob('.stdout-*.tmp'))+list(destination.rglob('.stderr-*.tmp')))



if __name__ == "__main__":
    import unittest

    unittest.main()
