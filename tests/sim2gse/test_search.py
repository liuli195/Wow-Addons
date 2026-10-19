"""第三票：通过同一任务入口驱动搜索、复测与结果隔离。"""

from __future__ import annotations

import tempfile
import time
import shutil
import os
from contextlib import contextmanager, nullcontext, ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))
from test_character_export import sample_profile
from test_engine import apl_pool_reference, static_snapshot
from task import cancel_task, read_task, resume_task, run_task, start_task, TaskError
from search import initial_programs, TaskStore


def _minimal_rule_pack():
    """构造报告只覆盖这份有序起手，不冒充完整指南角色。"""
    from copy import deepcopy

    names = ('outbreak', 'scourge_strike', 'death_coil', 'epidemic')
    pack = dict(schema_version=2,
        identity_mappings=dict(hero_talents={'sample_hero': 17}),
        general=dict(templates={}), execution_evidence={},
        object_sets={'sample': {name: dict(kind='action', native_action=name,
            base_button=name, native_forms=[name]) for name in names}},
        configurations=[dict(key=dict(specialization_id=252, hero_talent='sample_hero',
            target_type='single_target'), objects_ref='sample', execution_ref=None,
            states={'only': dict(effect=None, expected=True, priority=[])},
            opener=dict(source_basis='fixture: ordered task boundary', source_steps=list(names[:3]),
                precombat=[], burst_anchor=None, independent_burst_source_steps=[],
                ordinary_steps=[dict(action=name, source_step=index, source_form=name,
                    attribute_query=dict(native_form=name, base_button=name,
                                         missing='unknown_no_base_cost_fallback'))
                    for index, name in enumerate(names[:3], 1)]))])
    aoe = deepcopy(pack['configurations'][0])
    aoe['key']['target_type'] = 'aoe'
    pack['configurations'].append(aoe)
    return pack


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
                   on_native_start=None, score=None, rule_observation_request=None):
    """构造稳定报告，保留 search.optimize 的选择、缓存和发布逻辑。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if on_native_start is not None:
        on_native_start()
    input_times = list(range(0, 180000, 300)) if input_times is None else list(input_times)
    if score is None:
        score = score_offset + 100.0 + sum(
            command.get("spell_id", command.get("item_id", 0))
            for block in candidate["blocks"] for command in block
        ) / 1000.0
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

    identity = lambda mode, runtime=None: (Path("simc-test.exe"),
        {"mode": mode, "upstream_commit": "test", "build_options": []})
    identity_boundary = nullcontext() if real_engine else patch.object(engine, "identity", side_effect=identity)
    with ExitStack() as boundary:
        boundary.enter_context(patch.dict(simulation_config.DEFAULT_CONFIG, scene='single_target'))
        if 'SIM2GSE_RULE_CONFIG' not in os.environ:
            root = REPOSITORY / '.local/tests'
            root.mkdir(parents=True, exist_ok=True)
            folder = boundary.enter_context(tempfile.TemporaryDirectory(prefix='sim2gse-ordered-rules-', dir=root))
            path = Path(folder) / 'rules.json'
            path.write_text(json.dumps(_minimal_rule_pack()), encoding='utf-8')
            boundary.enter_context(patch.dict(os.environ, {'SIM2GSE_RULE_CONFIG': str(path)}))
        with identity_boundary, \
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
def _guided_search_boundary(directory, starts, *, evaluate=None, pack=None):
    """保留真实初始化、规则池和选择器，只构造既有引擎报告边界。"""
    import search
    import sequence
    from test_rule_diagnostics import _condition_pack, _observed_evaluate

    pack = _condition_pack() if pack is None else pack
    path = Path(directory) / 'rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')
    native = apl_pool_reference()
    for action in native['static_snapshot']['actions']:
        action['gcd_ms'] = 200
    with patch.dict(os.environ, SIM2GSE_RULE_CONFIG=str(path)), \
            _apl_task_boundary(native), \
            _initialized_starts(starts), \
            patch.object(sequence, 'evaluate', side_effect=evaluate or _observed_evaluate):
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
                result = run_task(source, Path(directory) / 'search', search_config=dict(
                    candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2))
                single = run_task(source, Path(directory) / 'single', mode='single')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([row['simc_action'] for row in result['capabilities']['actions']],
                         ['outbreak', 'death_coil', 'scourge_strike', 'death_and_decay', 'epidemic'])
        self.assertEqual(initial_programs(result['capabilities'], native,
                         rule_snapshot=result['rule_initialization']['rule_snapshot'], scene='single_target')[1:], [
            [['outbreak'], ['outbreak'], ['death_coil']],
            [['outbreak'], ['death_coil'], ['outbreak'], ['death_coil']],
            [['scourge_strike'], ['death_coil'], ['outbreak']],
        ])
        self.assertEqual([[row['simc_action'] for row in block] for block in single['candidate']['blocks']],
                         [['outbreak'], ['death_coil'], ['scourge_strike']])

    def test_task_mutates_unexecuted_apl_button_and_scores_exports_it(self):
        import result_store
        from sequence import compiled_program
        from test_rule_diagnostics import _condition_pack, _observed_evaluate

        pack = _condition_pack()
        consumer = pack['object_sets']['sample']['consumer']
        consumer.update(native_action='epidemic', base_button='epidemic', native_forms=['epidemic'])
        ordinary = pack['configurations'][0]['opener']['ordinary_steps'][1]
        ordinary['source_form'] = 'epidemic'
        ordinary['attribute_query'].update(native_form='epidemic', base_button='epidemic')

        def evaluate(*args, **kwargs):
            result = _observed_evaluate(*args, **kwargs)
            observations = result['report']['sim']['players'][0]['sim2gse_rule_observations']
            for row in observations['action_observations']:
                row.update(actual_form='epidemic', base_button='epidemic')
            return result

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _guided_search_boundary(directory, [[['outbreak'], ['death_coil']]],
                                         evaluate=evaluate, pack=pack):
                result = run_task(source, Path(directory) / 'search', search_config=dict(
                    input_interval_ms=200, candidate_limit=2, round_candidate_limit=1,
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
        self.assertEqual(len(saved['search']['rule_steps']), 1)
        self.assertTrue(next(iter(saved['search']['rule_steps'].values()))['selection'])
        self.assertNotIn(['epidemic'], result['search']['records'][0]['program'])
        self.assertIn(['epidemic'], compiled_program(result['candidate']))
        self.assertGreater(result['search_result']['dps'], 0)
        self.assertTrue(result['candidate']['text'].startswith('!GSE3!'))
        self.assertEqual(ground['status'], 'offline_ready')
        self.assertEqual(compiled_program(ground['candidate']), [['death_and_decay'], ['epidemic']])
        self.assertEqual(ground['candidate']['compiled_steps'][0],
                         {'type': 'macro', 'macrotext': '/cast [@player] death_and_decay'})
        self.assertGreater(ground['controlled_simulation']['summary']['dps'], 0)

    def test_task_promotion_and_saved_summary_share_one_comparison(self):
        import search
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, candidate_limit=2, batch_targets=(2,),
                          iterations=2, validation_batches=2, max_processes=2)
            with _fast_search_boundary(), \
                    _initialized_starts([[["outbreak"]], [["death_coil"]]]), \
                    patch.object(search, 'paired_ci', wraps=search.paired_ci) as intervals:
                result = run_task(source, Path(directory) / 'task', search_config=config)
            comparisons = [row[key]['comparison'] for row in result['search']['records']
                           for key in ('validation', 'global_validation') if key in row]
            record_keys = {record["key"] for record in result["search"]["records"]}
            export_keys = {path.name for path in (Path(directory) / "task" / "exports").iterdir()}
            self.assertEqual(export_keys, record_keys | {result["rule_initialization"]["behavior_identity"]})
            self.assertIn(result["locked_candidate_key"], record_keys)
            for record in result["search"]["records"]:
                for row in record["batches"]:
                    self.assertEqual(row["request"]["behavior_identity"], record["key"])
        self.assertEqual(result['status'], 'completed')
        self.assertGreater(len(comparisons), 0)
        self.assertEqual(intervals.call_count, len(comparisons))
        self.assertTrue(all(row['status'] == 'improvement_confirmed' for row in comparisons))
        self.assertEqual(result['search']['records'][-1]['key'], result['selected_candidate_key'])

    def test_same_layer_scores_overlap_but_results_keep_candidate_order(self):
        import threading
        import search
        import sequence
        import program
        from test_rule_diagnostics import _observed_evaluate

        entered = threading.Event()
        overlap = []
        finished = []
        generated = []
        initial = ('outbreak', 'death_coil')
        compile_threads = []
        original_compile = program.compile_program
        def compile_program(*args, **kwargs):
            compile_threads.append(threading.current_thread().name)
            candidate = original_compile(*args, **kwargs)
            actions = tuple(action['simc_action'] for block in candidate['blocks'] for action in block)
            if actions != initial and actions not in generated:
                generated.append(actions)
            return candidate
        def evaluate(profile, candidate, folder, **kwargs):
            actions = tuple(action['simc_action'] for block in candidate['blocks'] for action in block)
            if actions != initial and kwargs['iterations'] == 32:
                if actions == generated[0]:
                    overlap.append(entered.wait(2))
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            if actions != initial and kwargs['iterations'] == 32:
                finished.append(actions)
                if actions == generated[1]:
                    entered.set()
            return result

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, candidate_limit=3, round_candidate_limit=2,
                          input_interval_ms=200, batch_targets=(32,), iterations=2,
                          validation_batches=2, max_processes=2)
            with _guided_search_boundary(directory, [[[name] for name in initial]],
                                         evaluate=evaluate), \
                    patch.object(program, 'compile_program', side_effect=compile_program):
                result = run_task(source, Path(directory) / 'task', search_config=config)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(generated), 2)
        self.assertEqual(overlap, [True])
        self.assertEqual(finished, list(reversed(generated)))
        self.assertEqual([tuple(name for block in row['program'] for name in block)
                          for row in result['search']['records']], [initial, *generated])
        self.assertTrue(all(name == threading.current_thread().name for name in compile_threads))

    def test_cancelled_parallel_layer_keeps_other_complete_score_and_stops_dispatch(self):
        import threading
        import collections
        import search
        import sequence
        import program
        from runtime import TaskCancelled
        from test_rule_diagnostics import _observed_evaluate

        cancellation = threading.Event()
        second_complete = threading.Event()
        interrupted = [False]
        calls = []
        generated = []
        initial = ('outbreak', 'scourge_strike', 'death_coil')
        original_compile = program.compile_program

        def compile_program(*args, **kwargs):
            candidate = original_compile(*args, **kwargs)
            actions = tuple(a['simc_action'] for block in candidate['blocks'] for a in block)
            if actions not in (initial, ('outbreak', 'death_coil')) and actions not in generated:
                generated.append(actions)
            return candidate

        def evaluate(profile, candidate, folder, **kwargs):
            actions = tuple(a['simc_action'] for block in candidate['blocks'] for a in block)
            calls.append((actions, kwargs['iterations'], kwargs['seed']))
            if (generated and actions == generated[0] and kwargs['iterations'] == 32
                    and not interrupted[0]):
                if not second_complete.wait(2):
                    raise AssertionError('第二候选没有并行完成')
                interrupted[0] = True
                cancellation.set()
                raise TaskCancelled('test interruption')
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            if len(generated) >= 2 and actions == generated[1] and kwargs['iterations'] == 32:
                second_complete.set()
            return result

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            destination = Path(directory) / 'task'
            config = dict(total_budget_seconds=60, candidate_limit=4, round_candidate_limit=3,
                          input_interval_ms=200, batch_targets=(32,), iterations=2,
                          validation_batches=2, max_processes=2)
            with _guided_search_boundary(directory, [[[name] for name in initial]], evaluate=evaluate), \
                    patch.object(program, 'compile_program', side_effect=compile_program):
                stopped = run_task(source, destination, search_config=config, cancel_event=cancellation)
                self.assertEqual(stopped['status'], 'cancelled')
                self.assertEqual(len(generated), 2)
                stopped_calls = list(calls)
                resumed = resume_task(destination)
            self.assertEqual(resumed['status'], 'completed')
            self.assertEqual(len(generated), 3)
            self.assertNotIn(generated[2], [actions for actions, _, _ in stopped_calls])
            self.assertEqual([tuple(name for block in row['program'] for name in block)
                              for row in resumed['search']['records']], [initial, *generated])
            counts = collections.Counter(calls)
            self.assertEqual(counts[(generated[1], 32, 20260912)], 1)
            self.assertEqual(counts[(generated[0], 32, 20260912)], 2)
            self.assertEqual(counts[(generated[2], 32, 20260912)], 1)

    def test_near_round_resumes_mid_layer_without_repeating_completed_batches(self):
        import threading
        import collections
        import search
        import sequence
        from test_rule_diagnostics import _observed_evaluate

        cancellation = threading.Event()
        calls = []
        initial = ('outbreak', 'death_coil')

        def evaluate(profile, candidate, folder, **kwargs):
            actions = tuple(a['simc_action'] for block in candidate['blocks'] for a in block)
            wanted = 90 if actions == initial else 100
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            result['summary']['dps'] = wanted
            result['report']['sim']['statistics']['raid_dps']['mean'] = wanted
            result['report']['sim']['players'][0]['collected_data']['dps'].update(mean=wanted, variance=10000)
            (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
            calls.append((actions, kwargs['iterations'], kwargs['seed']))
            if actions != initial and kwargs['iterations'] == 96:
                cancellation.set()
            return result

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            destination = Path(directory) / 'task'
            config = dict(rule_diagnostics_policy='eager', total_budget_seconds=60, candidate_limit=3, round_candidate_limit=2,
                          input_interval_ms=200, batch_targets=(32, 128, 512),
                          iterations=2, validation_batches=2)
            with _guided_search_boundary(directory, [[[name] for name in initial]], evaluate=evaluate):
                interrupted = run_task(source, destination, search_config=config, cancel_event=cancellation)
                self.assertEqual(interrupted['status'], 'cancelled')
                cancellation.clear()
                resumed = resume_task(destination)
            self.assertEqual(resumed['status'], 'completed')
            self.assertEqual(resumed['search_result']['dps'], 100)
            search_calls = [(a, n, s) for a, n, s in calls if s < 20260912 + 100000]
            self.assertTrue(all(count == 1 for count in collections.Counter(search_calls).values()))
            children = [tuple(name for block in row['program'] for name in block)
                        for row in resumed['search']['records'][1:]]
            self.assertEqual(len(children), 2)
            for actions in children:
                self.assertEqual([n for a, n, s in search_calls if a == actions], [32, 96, 384])

    def test_resume_original_config_preserves_frozen_diagnostic_policy(self):
        import sequence
        for policy in ('on_demand', 'eager'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'role.simc'
                destination = Path(directory) / 'task'
                source.write_text(sample_profile(), encoding='utf-8')
                config = dict(candidate_limit=1, batch_targets=(2,), iterations=2,
                              validation_batches=1)
                with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=_fast_evaluate):
                    run_task(source, destination, search_config=dict(config, rule_diagnostics_policy=policy))
                    resumed = resume_task(destination, search_config=config)
                    self.assertEqual(resumed['status'], 'completed')
                    self.assertEqual(read_task(destination)['config']['rule_diagnostics_policy'], policy)
                    changed = 'eager' if policy == 'on_demand' else 'on_demand'
                    with self.assertRaisesRegex(TaskError, '恢复配置发生变化'):
                        resume_task(destination, search_config=dict(config, rule_diagnostics_policy=changed))

    def test_local_and_second_global_comparisons_both_record_positions(self):
        import result_store
        import search
        from test_rule_diagnostics import _observed_evaluate

        starts = [[['outbreak'], ['death_coil']], [['scourge_strike'], ['death_coil']]]
        initial_scores = {('outbreak', 'death_coil'): 100, ('scourge_strike', 'death_coil'): 50}

        def evaluate(profile, candidate, folder, **kwargs):
            actions = tuple(a['simc_action'] for block in candidate['blocks'] for a in block)
            damage = initial_scores.get(actions, 110 if 'scourge_strike' in actions else 20)
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            result['summary']['dps'] = damage
            result['report']['sim']['statistics']['raid_dps']['mean'] = damage
            result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
            (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
            return result

        with tempfile.TemporaryDirectory(prefix="sim2gse-global-position-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          input_interval_ms=200,
                          candidate_limit=4, round_candidate_limit=1,
                          no_improvement_rounds=5, batch_targets=(2,), iterations=2,
                          validation_batches=2, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=11,
                          diagnostic_logging=True, search_observability="full")
            with _guided_search_boundary(directory, starts, evaluate=evaluate):
                result = run_task(source, root / "task", search_config=config)

            run_id = json.loads((root / "task" / "profile.json").read_text())["run_id"]
            observation_batches = list(result_store.iter_rows(
                "SELECT batch_key FROM batches WHERE run_id = ? AND purpose = 'position_observation'",
                [run_id], tables=['batches']))
            traces = list(result_store.iter_rows(
                "SELECT t.batch_key, b.purpose FROM traces t LEFT JOIN batches b "
                "ON t.batch_key = b.batch_key AND t.run_id = b.run_id WHERE t.run_id = ?", [run_id], tables=['traces', 'batches']))
            self.assertTrue(observation_batches)
            self.assertTrue(traces)
            self.assertTrue(all(row["batch_key"] is not None for row in traces))
            self.assertTrue(all(row["purpose"] is not None for row in traces))
            self.assertEqual({row["batch_key"] for row in traces
                              if row["purpose"] == "position_observation"},
                             {row["batch_key"] for row in observation_batches})

        candidate = next(row for row in result["search"]["records"]
                         if "global_validation" in row)
        event = next(row for row in result["search"]["observability"]["details"]
                     if row["candidate_identity"] == candidate["key"])
        self.assertTrue(event["route_promotion"]["checked"])
        self.assertTrue(event["global_promotion"]["checked"])
        self.assertEqual(event["position_comparison_count"], 2)
        validation_requests = [row["request"] for side in ("candidate", "control")
                               for record in (candidate["validation"],
                                              candidate["global_validation"])
                               for row in record[side]]
        self.assertFalse(any(request["trace"] for request in validation_requests))

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
            evaluated.append((kwargs.get("seed"), plan))
            return _fast_evaluate(profile, candidate, folder, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-canonical-task-") as directory:
            source = Path(directory) / "角色.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(rule_diagnostics_policy='eager', total_budget_seconds=60, search_budget_seconds=30,
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
        matching_evaluations = [row for row in evaluated if row == (37, expected_plan)]
        self.assertEqual((len(matching_records), len(matching_evaluations)), (1, 1))
        matching_compiles = [mode for mode, folder in compiler_calls
                             if folder.endswith(matching_records[0]["key"])]
        self.assertEqual(len(matching_compiles), 1)

    def test_search_observability_is_off_by_default_and_preserves_selection(self):
        import sqlite3
        import search

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
                with _fast_search_boundary(), _initialized_starts([[['outbreak']]]):
                    result = run_task(source, destination, search_config=options)
                database = sqlite3.connect(destination / "task.sqlite3")
                try:
                    state = TaskStore.load_state(database)
                finally:
                    database.close()
                return result, state.get("rng"), state.get("condition")

            baseline, baseline_rng, baseline_condition = run("off")
            observed, observed_rng, observed_condition = run("full", "full")

        self.assertNotIn("observability", baseline["search"])
        self.assertEqual(baseline["selected_candidate_key"], observed["selected_candidate_key"])
        self.assertEqual(baseline_rng, observed_rng)
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

        self.assertEqual(score_snapshot(baseline), score_snapshot(observed))


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
                result = run_task(source, Path(directory) / "task", search_config=config)

        self.assertNotIn([["outbreak"]], evaluated)
        self.assertTrue(any("标准形式与编译计划不一致" in row["error"]
                            for row in result["search"]["errors"]))

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
                    search_config={'rule_diagnostics_policy': 'eager',
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
            self.assertNotEqual(result["locked_candidate_key"], result["search"]["records"][0]["key"])
            self.assertEqual(result["selected_candidate_key"], result["locked_candidate_key"])
            self.assertEqual(read_task(destination)["candidate"]["text"], result["candidate"]["text"])
            self.assertNotEqual(result["search"]["dataset"], result["validation"]["dataset"])
            self.assertNotEqual(result["validation"]["dataset"], result["final"]["dataset"])

            search_seeds={row['request']['seed'] for record in result['search']['records'] for row in record['batches']}
            validation_seeds={row['request']['seed'] for record in result['validation']['records'] for row in record['candidate']+record['control']}
            final_seeds={row['request']['seed'] for scenario in result['final']['scenarios'].values() for row in scenario['candidate']+scenario['seed']}
            self.assertTrue(search_seeds and validation_seeds)
            self.assertFalse(final_seeds)
            self.assertFalse(search_seeds & validation_seeds or search_seeds & final_seeds or validation_seeds & final_seeds)


    def test_search_batch_targets_add_independent_requested_iterations(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-batches-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                result = run_task(
                    source,
                    destination,
                    mode="optimize",
                    search_config={
                        "total_budget_seconds": 60,
                        "search_budget_seconds": 30,
                        "candidate_limit": 2,
                        "round_candidate_limit": 1,
                        "batch_targets": (2, 4, 8),
                        "validation_batches": 1,
                        "final_batches": 1,
                        "iterations": 2,
                        "final_iterations": 2,
                        "scenarios": ("nominal",),
                        "max_processes": 1,
                    },
                )
            batches = result["search"]["records"][0]["batches"]
            self.assertEqual([row["target"] for row in batches], [2, 4, 8])
            self.assertEqual([row["requested_iterations"] for row in batches], [2, 2, 4])
            self.assertEqual([row["samples"] for row in batches], [1, 1, 3])

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
                    while observed.get("phase") != "search" and time.monotonic() < deadline:
                        time.sleep(0.01)
                        observed = read_task(destination)
                    self.assertEqual(observed.get("phase"), "search")
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
            self.assertFalse(resumed["independent_validation_complete"])
            self.assertEqual(resumed["final"]["scenarios"], {})

    def test_corrupt_parquet_cache_shard_is_recomputed(self):
        import result_store
        import sequence

        calls = []
        def evaluate(*args, **kwargs):
            calls.append(1)
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='sim2gse-corrupt-center-') as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            config = dict(total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
                          batch_targets=(2,), iterations=2, validation_batches=1,
                          final_batches=1, final_iterations=2, scenarios=('nominal',),
                          max_processes=1, diagnostic_logging=True, diagnostics='summary')
            with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
                first_destination = Path(directory) / 'first'
                first = run_task(source, first_destination, search_config=config)
                saved_task = read_task(first_destination, include_search_records=True)
                performance = json.loads((first_destination / 'diagnostics.json').read_text())['performance']
                progress = performance['candidate_progress']
                self.assertEqual(performance['stages']['candidate.compile']['calls'], 1)
                self.assertEqual(performance['stages']['candidate.write']['calls'], 1)
                keys = {row['key'] for row in saved_task['search']['records']}
                self.assertEqual(len(keys), 1)
                for kind in ('first_score_published', 'screening_archived'):
                    self.assertEqual({row['behavior_identity'] for row in progress[kind]}, keys)
                    self.assertEqual(len(progress[kind]), 1)
                    self.assertGreaterEqual(progress[kind][0]['invocation_seconds'], 0)
                    self.assertGreaterEqual(progress[kind][0]['budget_elapsed_seconds'],
                                            progress[kind][0]['invocation_seconds'])
                cached_destination = Path(directory) / 'cached'
                with patch.object(sequence, 'evaluate', side_effect=AssertionError('复用不得重新评分')):
                    run_task(source, cached_destination, search_config=config)
                cached_performance = json.loads((cached_destination / 'diagnostics.json').read_text())['performance']
                self.assertEqual(cached_performance['candidate_progress']['first_score_published'], [])
                batch_key = first['search']['records'][0]['batches'][0]['data_key']
                # Fault injection only: mimic a damaged Parquet shard behind the read-only API.
                saved = result_store.one('batches', 'batch_key', batch_key)
                shard = result_store.DATA_ROOT / 'batches' / f"{saved['storage_group_key']}.parquet"
                shard.write_bytes(b'corrupt parquet')
                second = run_task(source, Path(directory) / 'second', search_config=config)

            self.assertEqual(len(calls), 2)
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
            self.assertEqual(len(exchange_paths), 1)
            self.assertTrue(exchange_paths[0].is_file())
            self.assertIsInstance(json.loads(exchange_paths[0].read_text(encoding='utf-8')), dict)

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
                "class CheckpointStore(search.TaskStore):",
                "    def stage_report(self,key,row,stored,**kwargs):",
                "        super().stage_report(key,row,stored,**kwargs)",
                "        with self.lock:",
                "            if row.get('status')=='success' and self.persisted_batches==0:",
                "                self.flush_reports()",
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
                    if state.get('phase') == 'search' and type(completed) is int and completed > 0:
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
                self.assertEqual(kernel.WaitForSingleObject(held,0),258,
                                 '硬退出前真实引擎必须仍在运行，不能用已完成进程证明清理')
                process.kill();process.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(owner,2000),0,'实际任务进程尚未退出，不能恢复')
                self.assertEqual(kernel.WaitForSingleObject(held,2000),0,'任务退出后仍有所属模拟进程')
                before=state['elapsed_seconds']
                resumed=resume_task(destination, simulation_config=dict(scene='single_target'))
                self.assertGreaterEqual(resumed['elapsed_seconds'],before)
                self.assertGreaterEqual(resumed['completed_batches'], state['completed_batches'])
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
            self.assertEqual(len(known["search"]["records"]), 1)
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

    def test_normal_search_no_improvement_limit_matches_valid_start_count(self):
        import itertools
        import search
        import sequence
        import result_store
        from test_rule_diagnostics import _observed_evaluate

        def equal_damage(profile, candidate, folder, **kwargs):
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            # 同一程序的构造成绩固定，后续诊断不能把已发布请求从100改成200。
            key = json.dumps(sequence.compiled_identity(candidate), sort_keys=True)
            if key not in scores:
                if result['blocks'] not in starts:
                    generated.append(key)
                scores[key] = 200.0 if len(generated) >= 2 and result['blocks'] not in starts else 100.0
            damage = scores[key]
            result['summary']['dps'] = damage
            result['report']['sim']['statistics']['raid_dps']['mean'] = damage
            result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
            (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
            return result

        count = 2
        with tempfile.TemporaryDirectory() as directory:
            generated = []
            scores = {}
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            names = ('outbreak', 'death_coil', 'scourge_strike', 'epidemic')
            starts = [[[name] for name in order]
                      for order in itertools.islice(itertools.permutations(names), count)]
            inputs = starts + [starts[0], [['missing_action']]]
            # 构造评分仅写入本次隔离报告库。
            with _guided_search_boundary(directory, inputs, evaluate=equal_damage), \
                    patch.object(result_store, 'DATA_ROOT', Path(directory) / 'data'):
                result = run_task(source, Path(directory) / 'task', search_config=dict(
                    input_interval_ms=200, candidate_limit=64, round_candidate_limit=1, batch_targets=(2,),
                    iterations=2, validation_batches=2))
                saved = read_task(Path(directory) / 'task')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['search']['stop_reason'], 'no_improvement')
            self.assertEqual(result['search']['rounds'], 4)
            self.assertEqual(len(result['search']['chains']), count)
            self.assertEqual([chain['rounds'] for chain in result['search']['chains']],
                             [2, 2])
            self.assertEqual(result['search_result']['dps'], 200.0)
            self.assertEqual(result['search']['no_improvement_round_limit'], count)
            self.assertEqual(saved['search']['no_improvement_round_limit'], count)

    def test_search_skips_exhausted_path_and_stops_only_after_all_paths_exhausted(self):
        import threading
        from test_rule_diagnostics import _observed_evaluate

        starts = [[['death_coil']], [['outbreak']]]
        cancellation = threading.Event()
        diagnostic_calls = []

        def cancel_after_first_path_is_skipped(profile, candidate, folder, **kwargs):
            result = _observed_evaluate(profile, candidate, folder, **kwargs)
            actions = [action['simc_action'] for block in candidate['blocks'] for action in block]
            observations = result['report']['sim']['players'][0]['sim2gse_rule_observations']
            for collection in ('inputs', 'action_observations', 'state_observations'):
                for row in observations[collection]:
                    row['source_step'] = row['input_index'] % len(candidate['blocks'])
            if actions[0] == 'death_coil':
                observations['action_observations'][0].update(attempt=True, success=True)
            # 真正的首路径已消费机会而池空；第二路径的真实插入已启动后才取消。
            if actions == ['death_coil', 'outbreak'] and kwargs.get('rule_observation_request'):
                diagnostic_calls.append(actions)
                cancellation.set()
            return result

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'role.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            with _guided_search_boundary(directory, starts, evaluate=cancel_after_first_path_is_skipped):
                cancelled = run_task(source, Path(directory) / 'task', cancel_event=cancellation,
                    search_config=dict(rule_diagnostics_policy='eager',
                    input_interval_ms=200, candidate_limit=32, round_candidate_limit=1, batch_targets=(2,),
                    iterations=2, validation_batches=2))
                self.assertEqual(cancelled['status'], 'cancelled')
                self.assertTrue(cancelled['search']['chains'][0]['stalled'])
                self.assertEqual(cancelled['search']['rounds'], 0)
                result = resume_task(Path(directory) / 'task')
                saved = read_task(Path(directory) / 'task', include_search_records=True)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['search']['stop_reason'], 'space_stalled')
            self.assertEqual(result['search']['rounds'], 1)
            self.assertEqual([chain['rounds'] for chain in result['search']['chains']], [0, 1])
            self.assertTrue(all(chain['stalled'] for chain in result['search']['chains']))
            self.assertEqual(saved['search']['chains'], result['search']['chains'])
            self.assertEqual(result['search']['no_improvement_round_limit'], 2)
            self.assertEqual(len(diagnostic_calls), 1)
            replayed_key = next(row['key'] for row in result['search']['records']
                                if row['program'] == [['death_coil'], ['outbreak']])
            replayed = next(row for row in saved['search']['records'] if row['key'] == replayed_key)
            self.assertTrue(replayed['rule_diagnostics']['pool']['complete'])
            self.assertIn(replayed['key'], saved['search']['rule_diagnostic_replays'])
            self.assertGreaterEqual(result['elapsed_seconds'], cancelled['elapsed_seconds'])

    def test_multiple_local_chains_use_their_own_observed_feedback(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-local-search-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            names = ('outbreak', 'scourge_strike', 'epidemic', 'death_and_decay')
            starts = [[[name] for name in (*names[index:], *names[:index], 'death_coil')]
                      for index in range(2)]
            with _guided_search_boundary(directory, starts):
                result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=120,
                    input_interval_ms=200,search_budget_seconds=90,candidate_limit=5,round_candidate_limit=2,batch_targets=(2,),
                    validation_batches=2,iterations=2,final_batches=2,final_iterations=2,scenarios=('nominal',)))
                saved = read_task(Path(directory) / 'task', include_search_records=True)
            self.assertEqual(result['search']['candidate_count'],5)
            self.assertTrue(result['search']['partial_round'])
            chains=result['search']['chains']
            records = {row['key']: row for row in saved['search']['records']}
            steps = list(saved['search']['rule_steps'].values())
            self.assertGreaterEqual(sum(chain['rounds']>0 for chain in chains),2)
            for chain in chains:
                if chain['rounds']:
                    selections = [step for step in steps
                                  if step['parent_candidate_key'] in chain['visited']]
                    self.assertTrue(selections)
                    for step in selections:
                        self.assertIn(step['candidate_key'], chain['visited'])
                        parent = records[step['parent_candidate_key']]
                        child = records[step['candidate_key']]
                        self.assertEqual(step['request']['parent_identity'],
                                         parent['rule_diagnostics']['parent_identity'])
                        feedback = step['selection']['feedback']
                        self.assertEqual(feedback['status'], 'learned')
                        self.assertTrue(feedback['evidence'])
                        parent_batches = {row['data_key']: row for row in parent['batches']}
                        child_batches = {row['data_key']: row for row in child['batches']}
                        for evidence in feedback['evidence']:
                            self.assertIn(evidence['parent_batch'], parent_batches)
                            self.assertIn(evidence['candidate_batch'], child_batches)
                            before = parent_batches[evidence['parent_batch']]
                            self.assertEqual(evidence['parent_dps'], before['dps'])
                            self.assertEqual(evidence['parent_samples'], before['samples'])
            self.assertIn(result['search']['stop_reason'],{'candidate_limit','no_improvement','search_deadline','space_stalled'})

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

    def test_search_deadline_terminates_a_hung_native_batch(self):
        import ctypes
        from ctypes import wintypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        runtime._kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        runtime._kernel32.OpenProcess.restype=wintypes.HANDLE
        held=[]
        def hanging_engine(*args):
            batch='batches' in str(args[7])
            if batch:
                args=list(args)
                args[0]=str(Path(sys.executable).resolve())
                args[1]=ctypes.create_unicode_buffer('"'+args[0]+'" -c "import time;time.sleep(10)"')
            success=original(*args)
            if success and batch:
                info=ctypes.cast(args[9],ctypes.POINTER(runtime._PROCESS_INFORMATION)).contents
                held.append(runtime._kernel32.OpenProcess(0x100000,False,info.dwProcessId))
            return success
        with tempfile.TemporaryDirectory(prefix='sim2gse-deadline-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            started=time.monotonic()
            try:
                with _fast_initialization(), patch.object(runtime._kernel32,'CreateProcessW',side_effect=hanging_engine):
                    result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=10,search_budget_seconds=5,
                        candidate_limit=2,batch_targets=(2,),iterations=2,validation_batches=2))
                self.assertTrue(held,'未触发原生批次超时路径')
                self.assertEqual(result['status'],'validation_incomplete')
                self.assertLess(time.monotonic()-started,10)
                for handle in held:self.assertEqual(runtime._kernel32.WaitForSingleObject(handle,0),0)
            finally:
                for handle in held:runtime._kernel32.CloseHandle(handle)


if __name__ == "__main__":
    import unittest

    unittest.main()
