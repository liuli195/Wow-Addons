"""第三票：通过同一任务入口驱动搜索、复测与结果隔离。"""

from __future__ import annotations

import tempfile
import time
import shutil
import hashlib
from contextlib import contextmanager, nullcontext
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
from task import cancel_task, read_task, resume_task, run_task, start_task, TaskError
from search import initial_programs, mutate


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
                    simulation_config=None):
    return dict(dps=100.0, metric="dps", personal_dps=100.0, samples=max(1, iterations-1), seconds=180,
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
        "sim2gse_spec_id": character.spec_id or 252, "race": character.race,
        "talents": character.fields["talents"], "sim2gse_resource": "runic_power",
        "collected_data": {"dps": {"mean": score, "count": samples}, "fight_length": {"mean": 180},
                           "resource_overflowed": {"runic_power": {"mean": 0}}},
    }
    return {"sim": {"players": [player], "targets": [{}],
                    "statistics": {"raid_dps": {"mean": score, "count": samples}},
                    "options": {"dbc": {"Live": {"build_level": 69587, "version_used": "Live"}}}}}


def _fast_evaluate(profile, candidate, folder, *, character, iterations=100,
                   seed=20260912, trace=True, mode="controlled", input_times=None,
                   runtime=None, score_offset=0, simulation_config=None, reset_events=None,
                   on_native_start=None):
    """构造稳定报告，保留 search.optimize 的选择、缓存和发布逻辑。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if on_native_start is not None:
        on_native_start()
    input_times = list(range(0, 180000, 300)) if input_times is None else list(input_times)
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
    """跳过与状态、缓存和进程故障断言无关的原生初始化。"""
    import codec
    import engine

    def compiler(command, *args, **kwargs):
        if kwargs.get("on_start") is not None:
            kwargs["on_start"]()
        output = b"CHECKSUM\ttest\n" if command[-1] == "checksum" else b"PASS\ttest\n"
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


class SearchAndValidationTests(TestCase):
    def test_parent_diagnostic_maps_loop_wait_and_repeated_castsequence_member(self):
        from search import _parent_positions

        cases = [
            ([["outbreak"], dict(kind="Loop", count=2, blocks=[["death_coil"], ["scourge_strike"]])],
             3, None, {"segment": 1, "loop_block": 0}),
            ([["outbreak"], dict(kind="WaitClicks", clicks=2), ["death_coil"]],
             3, None, {"segment": 2}),
            ([["outbreak"], dict(kind="CastSequence", members=["death_coil", "death_coil"], reset=None)],
             1, 1, {"segment": 1, "member": 1}),
        ]
        for parent, step, member, expected in cases:
            with self.subTest(position=expected):
                positions = _parent_positions(parent, _fast_capabilities(), [
                    dict(click_position=step, action_position=member),
                ])
                self.assertEqual(positions[0]["source_position"], expected)

    def test_finite_replacement_options_are_not_repeated_for_the_same_parent(self):
        import random
        from search import program_key

        excluded = set()
        parent = [["outbreak"]]
        for _ in range(4):
            child = mutate(parent, _fast_capabilities(), random.Random(6), excluded_programs=excluded)
            self.assertNotEqual(child, parent)
            self.assertNotIn(program_key(child), excluded)
            excluded.add(program_key(child))
        self.assertEqual(mutate(parent, _fast_capabilities(), random.Random(6), excluded_programs=excluded), parent)

    def test_position_feedback_proposes_changes_without_removing_failed_skill(self):
        import random

        parent = [["outbreak"], ["death_coil"], ["scourge_strike"]]
        feedback = dict(positions=[dict(unresolved_inputs=1, source_position={"segment": 1},
                                       ambiguous=False)])
        repairs = []
        for seed in range(100):
            observation = {}
            child = mutate(parent, _fast_capabilities(), random.Random(seed),
                           feedback=feedback, observation=observation)
            position = observation.get("modification_position") or {}
            if position.get("repair"):
                repairs.append(child)
                self.assertNotEqual(child, parent)
                self.assertIn(["death_coil"], child)
                self.assertEqual(parent, [["outbreak"], ["death_coil"], ["scourge_strike"]])
        self.assertGreater(len(repairs), 0)

    def test_search_diagnostic_locates_failed_parent_position_once_per_input(self):
        from search import _parent_positions, _position_observations

        parent = [["outbreak"], ["death_coil"]]
        candidate = {
            "blocks": [[action] for action in _fast_capabilities()["actions"][:2]],
            "compiled_steps": [dict(type="spell", spell=1001), dict(type="spell", spell=1002)],
        }
        first = dict(ms=0, event="input", battle=1, origin=1, step=0, action="-", signature="-")
        second = dict(ms=300, event="input", battle=1, origin=2, step=1, action="-", signature="-")
        failed = dict(ms=300, event="not_ready", battle=1, origin=2, step=1,
                      action="death_coil", signature="death_coil")
        positions = _parent_positions(parent, _fast_capabilities(), _position_observations(
            candidate, "candidate", [first, second, dict(second), failed, dict(failed),
                                      dict(failed, event="queue"), dict(failed, event="queue_confirm")]))
        failed = next(row for row in positions if row["click_position"] == 1)
        self.assertEqual(failed["source_position"], {"segment": 1})
        self.assertEqual(failed["turns"], 1)
        self.assertEqual(failed["queued"], 1)
        self.assertEqual(failed["failures"], {"not_ready": 1})
        self.assertEqual(failed["unresolved_inputs"], 1)

    def test_replacement_mutation_changes_action_without_creating_two_gcd_actions(self):
        import random
        from program import canonicalize_search_program

        parent = [["outbreak", "use_item,slot=trinket1"]]
        checked = 0
        for seed in range(200):
            observation = {}
            child = mutate(parent, _fast_capabilities(), random.Random(seed), observation=observation)
            if observation["sampled_mutation"] != "replace":
                continue
            checked += 1
            self.assertNotEqual(child, parent)
            canonicalize_search_program(child, _fast_capabilities())
        self.assertGreater(checked, 0)

    def test_new_loop_never_wraps_existing_loop_or_castsequence(self):
        import random
        from program import canonicalize_search_program

        parent = [["outbreak"], dict(kind="CastSequence", members=["death_coil", "scourge_strike"], reset=None),
                  ["dark_transformation"]]
        checked = 0
        for seed in range(200):
            observation = {}
            child = mutate(parent, _fast_capabilities(), random.Random(seed), observation=observation)
            if observation["sampled_mutation"] == "loop":
                checked += 1
                canonicalize_search_program(child, _fast_capabilities())
        self.assertGreater(checked, 0)

    def test_cancelled_task_does_not_compile_pending_unscored_candidates(self):
        import search
        import sequence
        import threading

        with tempfile.TemporaryDirectory(prefix="sim2gse-lazy-compile-") as directory:
            cancellation = threading.Event()
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            generated = iter([[["death_coil"]], [["scourge_strike"]],
                              [["dark_transformation"]]] * 160)

            def evaluate(profile, candidate, folder, **kwargs):
                result = _fast_evaluate(profile, candidate, folder, **kwargs)
                if len(candidate["blocks"]) == 1 and candidate["blocks"][0][0]["simc_action"] == "death_coil":
                    cancellation.set()
                return result

            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=4, round_candidate_limit=3, batch_targets=(2,),
                          iterations=2, validation_batches=1, final_batches=1,
                          final_iterations=2, scenarios=("nominal",), max_processes=1,
                          diagnostic_logging=True, diagnostics="full", random_seed=41)
            with _fast_search_boundary(), \
                    patch.object(search, "initial_programs", return_value=[[["outbreak"]]]), \
                    patch.object(search, "mutate", side_effect=lambda *args, **kwargs: next(generated)), \
                    patch.object(sequence, "evaluate", side_effect=evaluate):
                result = run_task(source, destination, search_config=config, cancel_event=cancellation)
            diagnostics = json.loads((destination / "diagnostics.json").read_text())
            self.assertEqual(result["status"], "cancelled")
            self.assertLessEqual(diagnostics["candidate_compilations"],
                                 len(result["search"]["records"]) + 1)

    def test_repeated_actions_without_trace_position_are_reported_as_ambiguous(self):
        from search import _position_observations

        action = dict(kind="spell", spell_id=1001, simc_action="outbreak", name="outbreak")
        candidate = {
            "blocks": [[action, action]],
            "compiled_steps": [dict(type="macro",
                                     macrotext="/cast outbreak\n/cast outbreak")],
        }
        rows = _position_observations(candidate, "candidate", [
            dict(event="input", step=0),
            dict(event="native_execute", step=0, action="outbreak", signature="outbreak"),
            dict(event="native_execute", step=0, action="outbreak", signature="outbreak"),
        ])

        ambiguous = [row for row in rows if row.get("ambiguous")]
        self.assertEqual(len(ambiguous), 1)
        self.assertIsNone(ambiguous[0]["action_position"])
        self.assertEqual(ambiguous[0]["ambiguity_reason"], "trace_missing_action_position")
        self.assertEqual(ambiguous[0]["successes"], 2)
        self.assertEqual(ambiguous[0]["turns"], 0)
        self.assertTrue(all(row["successes"] == 0 for row in rows
                            if row["action_position"] in (0, 1)))

    def test_processing_counts_a_dispatch_once_when_native_execution_follows(self):
        from search import _position_observations

        candidate = {
            "blocks": [[dict(kind="spell", spell_id=1001, simc_action="outbreak",
                              name="outbreak")]],
            "compiled_steps": [dict(type="spell", spell=1001)],
        }
        rows = _position_observations(candidate, "candidate", [
            dict(event="input", step=0),
            dict(event="dispatch", step=0, action="outbreak", signature="outbreak"),
            dict(event="native_execute", step=0, action="outbreak", signature="outbreak"),
        ])

        self.assertEqual(rows[0]["processing"], 1)
        self.assertEqual(rows[0]["successes"], 1)

    def test_search_cutoff_assigns_outcomes_to_every_unscored_candidate(self):
        import search
        import sequence
        from runtime import BudgetExceeded

        calls = 0

        def stop_on_second_batch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise BudgetExceeded("test search cutoff")
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-pending-outcomes-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=4, round_candidate_limit=1,
                          no_improvement_rounds=5, batch_targets=(2,), iterations=2,
                          validation_batches=2, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=11,
                          diagnostic_logging=True, search_observability="full")
            with _fast_initialization(), \
                    patch.object(sequence, "evaluate", side_effect=stop_on_second_batch), \
                    patch.object(search, "initial_programs",
                                 return_value=[[['outbreak']], [['death_coil']]]):
                result = run_task(source, root / "task", search_config=config)

        observation = result["search"]["observability"]
        outcomes = [row.get("outcome") for row in observation["details"]]
        self.assertCountEqual(outcomes, ["scored", "budget_not_scored"])
        self.assertEqual(sum(observation["summary"]["outcomes"].values()),
                         observation["summary"]["initial_candidates"] +
                         observation["summary"]["mutation_attempts"])

    def test_full_observability_is_locked_during_heartbeat_and_survives_resume(self):
        import threading
        import search
        import sequence
        from runtime import TaskRuntime

        stores = []

        def guard(value, lock):
            if isinstance(value, dict):
                return LockedDict(value, lock)
            if isinstance(value, list):
                return LockedList(value, lock)
            return value

        class LockedDict(dict):
            def __init__(self, value, lock):
                self.lock = lock
                dict.__init__(self, ((key, guard(item, lock)) for key, item in value.items()))

            def __setitem__(self, key, value):
                if not self.lock._is_owned():
                    raise AssertionError("search observability write did not hold TaskStore.lock")
                dict.__setitem__(self, key, guard(value, self.lock))

            def setdefault(self, key, default=None):
                if key in self:
                    return self[key]
                self[key] = default
                return self[key]

        class LockedList(list):
            def __init__(self, value, lock):
                self.lock = lock
                list.__init__(self, (guard(item, lock) for item in value))

            def append(self, value):
                if not self.lock._is_owned():
                    raise AssertionError("search observability append did not hold TaskStore.lock")
                list.append(self, value)

        class LockedStore(search.TaskStore):
            def __init__(self, destination):
                super().__init__(destination)
                self.heartbeat_publishes = 0
                if "search_observability" in self.state:
                    self.state["search_observability"] = guard(
                        self.state["search_observability"], self.lock)
                stores.append(self)

            def publish(self):
                if threading.current_thread() is not threading.main_thread():
                    self.heartbeat_publishes += 1
                return super().publish()

        original_observability = search._new_search_observability

        def locked_observability(mode):
            return guard(original_observability(mode), stores[-1].lock)

        runtime = TaskRuntime(60)
        calls = 0

        def cancel_after_first(*args, **kwargs):
            nonlocal calls
            result = _fast_evaluate(*args, **kwargs)
            calls += 1
            if calls == 1:
                threading.Event().wait(0.6)
                runtime.cancel()
            return result

        with tempfile.TemporaryDirectory(prefix="sim2gse-observability-resume-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            destination = root / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37,
                          diagnostic_logging=True, search_observability="full")
            with _fast_initialization(), \
                    patch.object(search, "TaskStore", LockedStore), \
                    patch.object(search, "_new_search_observability",
                                 side_effect=locked_observability), \
                    patch.object(search, "initial_programs",
                                 return_value=[[['outbreak']], [['death_coil']]]), \
                    patch.object(sequence, "evaluate", side_effect=cancel_after_first):
                stopped = run_task(source, destination, search_config=config, _runtime=runtime)
                resumed = run_task(source, destination, search_config=config, resume=True,
                                   _runtime=TaskRuntime(60))

        self.assertEqual(stopped["status"], "cancelled")
        self.assertTrue(any(store.heartbeat_publishes for store in stores))
        stopped_details = stopped["search"]["observability"]["details"]
        resumed_details = resumed["search"]["observability"]["details"]
        self.assertEqual([row["event_id"] for row in stopped_details],
                         [row["event_id"] for row in resumed_details])
        self.assertCountEqual([row["outcome"] for row in resumed_details],
                              ["scored", "cancelled_not_scored"])

    def test_budget_exhausted_resume_keeps_previously_collected_observability(self):
        import sqlite3
        import search

        with tempfile.TemporaryDirectory(prefix="sim2gse-observability-budget-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            destination = root / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=1, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37,
                          diagnostic_logging=True, search_observability="full")
            with _fast_search_boundary(), patch.object(
                    search, "initial_programs", return_value=[[['outbreak']]]):
                completed = run_task(source, destination, search_config=config)

            database = sqlite3.connect(destination / "task.sqlite3")
            try:
                state = json.loads(database.execute(
                    "SELECT value FROM state WHERE id=1").fetchone()[0])
                state["elapsed_seconds"] = config["total_budget_seconds"]
                state["status"] = "interrupted"
                database.execute("UPDATE state SET value=? WHERE id=1",
                                 (json.dumps(state, ensure_ascii=False),))
                database.commit()
            finally:
                database.close()

            with _fast_initialization():
                resumed = resume_task(destination, search_config=config)

        self.assertEqual(resumed["status"], "validation_incomplete")
        self.assertEqual(resumed["search_observability"]["details"],
                         completed["search"]["observability"]["details"])

    def test_local_and_second_global_comparisons_both_record_positions(self):
        import search

        with tempfile.TemporaryDirectory(prefix="sim2gse-global-position-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=4, round_candidate_limit=1,
                          no_improvement_rounds=5, batch_targets=(2,), iterations=2,
                          validation_batches=2, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=11,
                          diagnostic_logging=True, search_observability="full")
            with _fast_search_boundary(), patch.object(
                    search, "initial_programs",
                    return_value=[[['use_item,slot=trinket1']], [['death_coil']]]):
                result = run_task(source, root / "task", search_config=config)

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

    def test_position_observation_uses_main_budget_and_propagates_cancel(self):
        import search
        import sequence
        from runtime import TaskCancelled, TaskRuntime

        runtime = TaskRuntime(60)
        observed_runtimes = []

        def cancel_observation(*args, **kwargs):
            observed_runtimes.append(kwargs["runtime"])
            if "observability" in str(args[2]):
                raise TaskCancelled("cancel during position observation")
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-observation-budget-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37,
                          diagnostic_logging=True, search_observability="full")
            with _fast_initialization(), \
                    patch.object(sequence, "evaluate", side_effect=cancel_observation), \
                    patch.object(search, "initial_programs",
                                 return_value=[[['outbreak']], [['death_coil']]]):
                result = run_task(source, root / "task", search_config=config,
                                  _runtime=runtime)

        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(result["search"]["observability"]["summary"]
                        ["position_observation_incomplete"])
        self.assertTrue(observed_runtimes)
        self.assertTrue(all(item is runtime for item in observed_runtimes))

    def test_promotion_timeout_keeps_pending_position_observation_visible(self):
        import search
        import sequence
        from runtime import BudgetExceeded, TaskRuntime

        runtime = TaskRuntime(60)
        scores = iter((1.0, 2.0, 3.0, 4.0))

        def stop_during_promotion(*args, **kwargs):
            if kwargs.get("trace") and runtime.remaining_seconds <= 0:
                raise BudgetExceeded("no time left for position observation")
            if 100000 <= kwargs["seed"] < 200000 and not kwargs.get("trace"):
                runtime.used_seconds = runtime.budget_seconds
                raise BudgetExceeded("test promotion timeout")
            return _fast_evaluate(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-promotion-timeout-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=4, round_candidate_limit=1,
                          no_improvement_rounds=5, batch_targets=(2,), iterations=2,
                          validation_batches=2, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=11,
                          diagnostic_logging=True, search_observability="full")
            with _fast_search_boundary(), \
                    patch.object(sequence, "evaluate", side_effect=stop_during_promotion), \
                    patch.object(search, "_score", side_effect=lambda rows: next(scores)), \
                    patch.object(search, "initial_programs",
                                 return_value=[[['use_item,slot=trinket1']], [['death_coil']]]):
                result = run_task(source, root / "task", search_config=config,
                                  _runtime=runtime)

        observation = result["search"]["observability"]
        checked = [row for row in observation["details"]
                   if row["global_promotion"]["checked"]]
        self.assertTrue(checked)
        self.assertTrue(observation["summary"]["position_observation_incomplete"])
        self.assertTrue(any("position_summary" not in row for row in checked))

    def test_replacement_recording_preserves_the_existing_random_draw_order(self):
        import random

        from search import mutate

        capabilities = _fast_capabilities()
        observed_rng = random.Random(6)
        observation = {}
        observed = mutate([["outbreak"]], capabilities, observed_rng,
                          observation=observation)

        plain_rng = random.Random(6)
        plain = mutate([["outbreak"]], capabilities, plain_rng)

        self.assertEqual(observed, [["death_coil"]])
        self.assertEqual(observed, plain)
        self.assertEqual(observed_rng.getstate(), plain_rng.getstate())
        self.assertEqual(observation["sampled_mutation"], "replace")
        self.assertEqual(observation["actual_mutation"], "replace")
        self.assertEqual(observation["modification_position"], {"segment": 0, "action": 0})

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
            output = b"CHECKSUM\ttest\n" if command[-1] == "checksum" else b"PASS\ttest\n"
            return SimpleNamespace(returncode=0, stdout=output, stderr=b"")

        def evaluate(profile, candidate, folder, **kwargs):
            clicks = candidate["compiled_program"]["clicks"]
            plan = [click.get("commands", []) for click in clicks]
            evaluated.append((kwargs.get("seed"), plan))
            return _fast_evaluate(profile, candidate, folder, **kwargs)

        with tempfile.TemporaryDirectory(prefix="sim2gse-canonical-task-") as directory:
            source = Path(directory) / "角色.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37)
            with _fast_search_boundary(), \
                    patch.object(search, "initial_programs", return_value=equivalent_programs), \
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
        self.assertEqual(matching_compiles, ["checksum", "compile"])

    def test_run_task_does_not_save_full_state_for_batch_counters(self):
        import search

        saves = []
        original = search.TaskStore

        class CountingTaskStore(original):
            def save(self):
                saves.append(self.state.get("batch_requests", 0))
                return super().save()

        with tempfile.TemporaryDirectory(prefix="sim2gse-save-count-") as directory:
            source = Path(directory) / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=1, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37)
            with _fast_search_boundary(), \
                    patch.object(search, "TaskStore", CountingTaskStore), \
                    patch.object(search, "initial_programs", return_value=[[['outbreak']]]):
                result = run_task(source, Path(directory) / "task", search_config=config)

        self.assertLessEqual(len(saves), result["completed_batches"] * 2 + 9,
                             (len(saves), result["completed_batches"]))
        self.assertNotIn("diagnostics", result["search"])

    def test_summary_diagnostics_report_cost_without_detailed_events(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-summary-diagnostics-") as directory:
            source = Path(directory) / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=1, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37,
                          diagnostic_logging=True, diagnostics="summary")
            with _fast_search_boundary():
                result = run_task(source, Path(directory) / "task", search_config=config)
            persisted = json.loads((Path(directory) / "task" / "diagnostics.json").read_text())

        diagnostics = result["search"]["diagnostics"]
        self.assertEqual(diagnostics["mode"], "summary")
        self.assertGreater(diagnostics["task_state_writes"], 0)
        self.assertGreater(diagnostics["candidate_compilations"], 0)
        self.assertNotIn("events", diagnostics)
        self.assertGreaterEqual(persisted["task_state_writes"], diagnostics["task_state_writes"])
        self.assertEqual(persisted["lua_compiler_starts"],
                         persisted["candidate_compilations"] * 2)

        with tempfile.TemporaryDirectory(prefix="sim2gse-full-diagnostics-") as directory:
            source = Path(directory) / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                full = run_task(source, Path(directory) / "task",
                                search_config=dict(config, diagnostics="full"))
        self.assertTrue(full["search"]["diagnostics"]["events"])

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
                with _fast_search_boundary(), patch.object(
                        search, "initial_programs", return_value=[[['outbreak']]]):
                    result = run_task(source, destination, search_config=options)
                database = sqlite3.connect(destination / "task.sqlite3")
                try:
                    state = json.loads(database.execute(
                        "SELECT value FROM state WHERE id=1").fetchone()[0])
                finally:
                    database.close()
                return result, state.get("rng"), state.get("condition")

            baseline, baseline_rng, baseline_condition = run("off")
            summarized, summary_rng, summary_condition = run("summary", "summary")
            observed, observed_rng, observed_condition = run("full", "full")

        self.assertNotIn("observability", baseline["search"])
        self.assertEqual(summarized["search"]["observability"]["mode"], "summary")
        self.assertNotIn("details", summarized["search"]["observability"])
        self.assertEqual(baseline["selected_candidate_key"], observed["selected_candidate_key"])
        self.assertEqual(baseline_rng, observed_rng)
        self.assertEqual(baseline_rng, summary_rng)
        self.assertEqual(baseline_condition, observed_condition)
        self.assertEqual(baseline_condition, summary_condition)

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
        self.assertEqual(score_snapshot(baseline), score_snapshot(summarized))

    def test_observability_time_is_returned_to_total_budget_after_search(self):
        import search
        from runtime import TaskRuntime

        runtime = TaskRuntime(60)
        with tempfile.TemporaryDirectory(prefix="sim2gse-observation-time-") as directory:
            root = Path(directory)
            source = root / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, random_seed=37,
                          diagnostic_logging=True, search_observability="full")
            with _fast_search_boundary(), patch.object(
                    search, "initial_programs", return_value=[[['outbreak']]]):
                result = run_task(source, root / "task", search_config=config,
                                  _runtime=runtime)

        recorded = sum(result["search"]["observability"]["summary"]
                       ["phase_seconds"].values())
        self.assertGreater(recorded, 0)
        self.assertLessEqual(runtime.remaining_seconds, runtime.budget_seconds)

    def test_search_artifacts_and_requests_use_the_canonical_behavior_identity(self):
        import search

        with tempfile.TemporaryDirectory(prefix="sim2gse-identity-trace-") as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1)
            with _fast_search_boundary(), patch.object(
                    search, "initial_programs",
                    return_value=[[['outbreak']], [['death_coil']]]):
                result = run_task(source, destination, search_config=config)

            record_keys = {record["key"] for record in result["search"]["records"]}
            export_keys = {path.name for path in (destination / "exports").iterdir()}
            self.assertEqual(export_keys, record_keys)
            self.assertIn(result["locked_candidate_key"], record_keys)
            for record in result["search"]["records"]:
                for row in record["batches"]:
                    self.assertEqual(row["request"]["behavior_identity"], record["key"])

    def test_search_reports_requests_cache_hits_and_native_batch_starts_separately(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-cache-counters-") as directory:
            source = Path(directory) / "role.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=60, search_budget_seconds=30,
                          candidate_limit=2, batch_targets=(2,), iterations=2,
                          validation_batches=1, final_batches=1, final_iterations=2,
                          scenarios=("nominal",), max_processes=1, diagnostic_logging=True)
            with _fast_search_boundary():
                first = run_task(source, Path(directory) / "first", search_config=config)
                second = run_task(source, Path(directory) / "second", search_config=config)

        self.assertEqual(first["search"]["batch_cache_hits"], 0)
        self.assertEqual(first["search"]["batch_requests"],
                         first["search"]["native_batch_starts"])
        self.assertGreater(second["search"]["batch_cache_hits"], 0)
        self.assertEqual(second["search"]["batch_requests"],
                         second["search"]["batch_cache_hits"]
                         + second["search"]["native_batch_starts"])

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
                state = json.loads(database.execute(
                    "SELECT value FROM state WHERE id=1").fetchone()[0])
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
                    patch.object(search, "initial_programs",
                                 return_value=[[['outbreak']], [['death_coil']]]), \
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
        self.assertEqual(loop["form"]["clicks"],
                         [["outbreak"], ["use_item,slot=trinket1"]])
        self.assertEqual(loop["form"]["version"], "sim2gse-search-behavior-v1")
        self.assertEqual(loop["program"]["nodes"][0]["kind"], "Loop")
        self.assertNotEqual(loop["program"]["nodes"][0]["source"],
                            expanded["program"]["nodes"][0]["source"])

    def test_canonical_identity_merges_adjacent_wait_clicks(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        adjacent = canonicalize_search_program(
            [dict(kind="WaitClicks", clicks=2), dict(kind="WaitClicks", clicks=3), ["outbreak"]],
            capabilities,
        )
        combined = canonicalize_search_program(
            [dict(kind="WaitClicks", clicks=5), ["outbreak"]], capabilities
        )

        self.assertEqual(adjacent["identity"], combined["identity"])
        self.assertEqual(adjacent["form"]["clicks"],
                         [[], [], [], [], [], ["outbreak"]])

    def test_canonical_identity_keeps_action_order_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        forward = canonicalize_search_program([["outbreak"], ["death_coil"]], capabilities)
        reversed_actions = canonicalize_search_program([["death_coil"], ["outbreak"]], capabilities)

        self.assertNotEqual(forward["identity"], reversed_actions["identity"])

    def test_canonical_identity_keeps_action_count_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        twice = canonicalize_search_program([["outbreak"], ["outbreak"]], capabilities)
        three_times = canonicalize_search_program(
            [["outbreak"], ["outbreak"], ["outbreak"]], capabilities
        )

        self.assertNotEqual(twice["identity"], three_times["identity"])

    def test_canonical_identity_keeps_action_block_boundaries_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        item = "use_item,slot=trinket1"
        one_block = canonicalize_search_program([["outbreak", item]], capabilities)
        two_blocks = canonicalize_search_program([["outbreak"], [item]], capabilities)

        self.assertNotEqual(one_block["identity"], two_blocks["identity"])

    def test_canonical_identity_keeps_castsequence_members_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        first = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"], reset=None)],
            capabilities,
        )
        second = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "scourge_strike"], reset=None)],
            capabilities,
        )

        self.assertNotEqual(first["identity"], second["identity"])

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

    def test_canonical_form_declares_start_and_sequence_reset_rules(self):
        from program import canonicalize_search_program

        result = canonicalize_search_program([["outbreak"]], _fast_capabilities())

        self.assertEqual(result["form"]["start_step"], 1)
        self.assertEqual(result["form"]["sequence_reset"], "end")

    def test_canonical_identity_treats_castsequence_reset_flags_as_a_set(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        target_combat = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3, "flags": ["target", "combat"]})],
            capabilities,
        )
        combat_target = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3,
                         "flags": ["combat", "target", "combat"]})],
            capabilities,
        )

        self.assertEqual(target_combat["identity"], combat_target["identity"])
        self.assertEqual(target_combat["form"]["castsequences"][0]["reset"]["flags"],
                         ["combat", "target"])

    def test_canonical_identity_accepts_an_active_trinket_as_its_only_action(self):
        from program import canonicalize_search_program

        result = canonicalize_search_program([["use_item,slot=trinket1"]], _fast_capabilities())

        self.assertEqual(result["form"]["clicks"], [["use_item,slot=trinket1"]])
        self.assertEqual(result["form"]["castsequences"], [])

    def test_canonical_identity_rejects_only_empty_clicks_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"blocks\[0\].*空点击"):
            canonicalize_search_program([dict(kind="WaitClicks", clicks=2)], _fast_capabilities())

    def test_canonical_identity_rejects_invalid_wait_click_counts_with_location(self):
        from program import canonicalize_search_program

        for clicks in (1, 4097):
            with self.subTest(clicks=clicks), self.assertRaisesRegex(
                    ValueError, r"segments\[0\].*WaitClicks"):
                canonicalize_search_program(
                    [dict(kind="WaitClicks", clicks=clicks), ["outbreak"]], _fast_capabilities()
                )

    def test_canonical_identity_rejects_empty_loop_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"segments\[0\]\.blocks\[0\].*Loop"):
            canonicalize_search_program(
                [dict(kind="Loop", count=2, blocks=[[]])], _fast_capabilities()
            )

    def test_canonical_identity_rejects_unmapped_action_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"segments\[0\].*当前角色不支持"):
            canonicalize_search_program([["not_a_character_action"]], _fast_capabilities())

    def test_canonical_identity_rejects_expansion_over_4096_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"blocks\[0\].*4096"):
            canonicalize_search_program(
                [dict(kind="Loop", count=4096,
                      blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
                _fast_capabilities(),
            )

    def test_search_can_vary_castsequence_timeout_without_event_variants(self):
        from search import program_key

        class TimeoutChoice:
            @staticmethod
            def choice(values):
                if 'castsequence_reset' in values:
                    assert 'castsequence_reset_flag' not in values
                    return 'castsequence_reset'
                if 2 in values:
                    return 2
                for value in values:
                    if isinstance(value, dict) and value.get('timeout_seconds') == 2:
                        return value
                return values[0]

        original = [dict(kind='CastSequence', members=['outbreak', 'death_coil'], reset=None)]
        changed = mutate(original, _fast_capabilities(), TimeoutChoice())
        self.assertEqual(changed[0]['reset'], {'timeout_seconds': 2, 'flags': []})
        self.assertIsNone(original[0]['reset'])
        self.assertNotEqual(program_key(changed), program_key(original))

    def test_search_can_vary_observable_castsequence_reset_flag(self):
        class FlagChoice:
            @staticmethod
            def choice(values):
                if 'castsequence_reset_flag' in values:
                    return 'castsequence_reset_flag'
                if 'target' in values:
                    return 'target'
                return values[0]

        original = [dict(kind='CastSequence', members=['outbreak', 'death_coil'], reset=None)]
        changed = mutate(original, _fast_capabilities(), FlagChoice(), reset_flags=('target',))
        self.assertEqual(changed[0]['reset'], {'timeout_seconds': None, 'flags': ['target']})

    def test_search_reset_events_require_observable_scenario(self):
        from search import config_for

        configured = config_for({'scenarios': ('nominal',),
                                 'reset_events': ((3000, 'target'), (6000, 'shift'))})
        self.assertEqual(configured['reset_events'], ((3000, 'target'), (6000, 'shift')))
        with self.assertRaisesRegex(ValueError, '修饰键'):
            config_for({'scenarios': ('nominal',), 'reset_events': ((6001, 'shift'),)})
        with self.assertRaisesRegex(ValueError, '修饰键'):
            config_for({'reset_events': ((6000, 'shift'),)})
        with self.assertRaisesRegex(ValueError, '诊断模式'):
            config_for({'diagnostics': 'verbose'})

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
        reference = dict(action_sequence=[
            dict(name="outbreak"), dict(name="death_coil"), dict(name="outbreak"),
            dict(name="scourge_strike", queue_failed=True), dict(name="unknown_action"),
        ])
        expected = [
            [["outbreak"], ["death_coil"], ["scourge_strike"]],
            [["outbreak"], ["outbreak"], ["death_coil"]],
            [["outbreak"], ["death_coil"], ["outbreak"], ["death_coil"]],
            [["scourge_strike"], ["death_coil"], ["outbreak"]],
        ]

        self.assertEqual(initial_programs(capabilities, reference, seed=20260912), expected)
        from search import input_times
        first = input_times("jitter", seed=20260912)
        self.assertEqual(first, input_times("jitter", seed=20260912))
        self.assertNotEqual(first, input_times("jitter", seed=20260913))

    def test_loop_repeat_count_is_part_of_candidate_identity(self):
        from search import program_key

        body = [["outbreak"], ["death_coil"]]
        twice = [dict(kind="Loop", count=2, blocks=body)]
        three_times = [dict(kind="Loop", count=3, blocks=body)]
        self.assertNotEqual(program_key(twice), program_key(three_times))

    def test_low_success_action_inside_loop_drops_its_top_level_candidate(self):
        class FeedbackRng:
            def __init__(self):
                self.choice_count = 0

            def choice(self, values):
                self.choice_count += 1
                return "swap" if self.choice_count == 1 else values[0]

            def random(self):
                return 0

            def sample(self, population, count):
                return [0, 2]

        program = [
            ["outbreak"],
            dict(kind="Loop", count=2, blocks=[["death_coil"], ["wasted_action"]]),
            ["scourge_strike"],
        ]
        capabilities = dict(actions=[dict(simc_action=name) for name in (
            "outbreak", "death_coil", "wasted_action", "scourge_strike")])
        feedback = dict(attempts={"wasted_action": 3}, successes={"wasted_action": 0})

        result = mutate(program, capabilities, FeedbackRng(), feedback=feedback)

        self.assertEqual(result, [["outbreak"], ["scourge_strike"]])

    def test_report_version_gate_accepts_historical_and_current_build(self):
        """历史报告在其对应版本上有效，升级不得把它们踢掉。"""
        import engine

        def character():
            equipment = {"head": SimpleNamespace(raw=",id=1")}
            return SimpleNamespace(name="角色", class_name="death_knight", level=90, race="scourge",
                                   spec_id=252, fields={"talents": "talents"}, equipment=equipment)

        def report(build_level, version_used="Live"):
            player = {"name": "角色", "sim2gse_class": "death_knight", "level": 90,
                      "sim2gse_spec_id": 252, "race": "scourge", "talents": "talents",
                      "sim2gse_resource": "runic_power", "sim2gse_class_id": 6,
                      "sim2gse_spec": "unholy", "role": "attack",
                      "gear": {"head": {"encoded_item": ",id=1"}},
                      "collected_data": {"dps": {"mean": 100.0, "count": 99},
                                         "fight_length": {"mean": 180}}}
            return {"sim": {"players": [player], "targets": [{}],
                            "statistics": {"raid_dps": {"mean": 100.0, "count": 99}},
                            "options": {"dbc": {"Live": {"build_level": build_level},
                                                "version_used": version_used}}}}

        for build in (69587, 69814):
            engine.check_report(report(build), character(), 100)
        # 校验强度不变：清单外的版本照旧拒绝。
        for build in (69999, 0):
            with self.assertRaises(ValueError):
                engine.check_report(report(build), character(), 100)
        with self.assertRaises(ValueError):
            engine.check_report(report(69814, "Ptr"), character(), 100)

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
            self.assertEqual(result["selected_candidate_key"], result["locked_candidate_key"])
            self.assertEqual((destination / "candidate.txt").read_text(encoding="ascii"), result["candidate"]["text"])
            self.assertNotEqual(result["search"]["dataset"], result["validation"]["dataset"])
            self.assertNotEqual(result["validation"]["dataset"], result["final"]["dataset"])

            search_seeds={row['request']['seed'] for record in result['search']['records'] for row in record['batches']}
            validation_seeds={row['request']['seed'] for record in result['validation']['records'] for row in record['candidate']+record['control']}
            final_seeds={row['request']['seed'] for scenario in result['final']['scenarios'].values() for row in scenario['candidate']+scenario['seed']}
            self.assertTrue(search_seeds and validation_seeds)
            self.assertFalse(final_seeds)
            self.assertFalse(search_seeds & validation_seeds or search_seeds & final_seeds or validation_seeds & final_seeds)

    def test_reference_start_keeps_executed_active_items(self):
        starts = initial_programs(_fast_capabilities(), dict(action_sequence=[
            dict(name="use_item,slot=trinket1", queue_failed=False),
        ]))
        self.assertEqual(starts[1], [["use_item,slot=trinket1"]])

    def test_search_winner_is_not_replaced_by_a_final_comparison(self):
        import search
        from unittest.mock import patch
        summarize_pairs = search.summarize_pairs

        def reject_final_gain(candidate, seed):
            comparison = summarize_pairs(candidate, seed)
            if len(candidate) == 1:
                comparison["status"] = "not_proven_better"
            return comparison

        with tempfile.TemporaryDirectory(prefix="sim2gse-no-gain-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary(), \
                    patch.object(search, "DEFAULT_SCENARIOS", ("nominal",)), \
                    patch.dict(search.DEFAULT_CONFIG, final_batches=1, final_iterations=2), \
                    patch.object(search, "summarize_pairs", side_effect=reject_final_gain):
                result = run_task(source, destination, search_config={
                    "total_budget_seconds": 60,
                    "search_budget_seconds": 30,
                    "candidate_limit": 4,
                    "batch_targets": (2,),
                    "validation_batches": 2,
                    "final_batches": 1,
                    "iterations": 2,
                    "final_iterations": 2,
                    "scenarios": ("nominal",),
                    "max_processes": 1,
                })

            seed_key = result["search"]["records"][0]["key"]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["improvement"], "search_result")
            self.assertNotEqual(result["locked_candidate_key"], seed_key)
            self.assertEqual(result["selected_candidate_key"], result["locked_candidate_key"])
            self.assertEqual((destination / "candidate.txt").read_text(encoding="ascii"), result["candidate"]["text"])

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
                    while observed.get("completed_batches", 0) == 0 and time.monotonic() < deadline:
                        time.sleep(0.01)
                        observed = read_task(destination)
                    self.assertEqual(observed.get("phase"), "search")
                    self.assertGreater(observed.get("completed_batches", 0), 0)
                    with self.assertRaisesRegex(TaskError, "正在运行"):
                        resume_task(destination)
                    cancel_task(handle)
                finally:
                    if not handle.done:
                        cancel_task(handle)
                    handle.join(5)
                self.assertTrue(handle.done)
                cancelled = read_task(destination)
                self.assertEqual(cancelled["status"], "cancelled")
                resumed = run_task(destination/"input.simc",destination,resume=True)
            self.assertEqual(resumed['search']['records'][0]['key'], cancelled['search']['records'][0]['key'])
            self.assertGreater(resumed["elapsed_seconds"], cancelled["elapsed_seconds"])
            self.assertGreaterEqual(resumed["completed_batches"], cancelled["completed_batches"])
            for name in ("batch_requests", "batch_cache_hits", "native_batch_starts",
                         "canonicalized_duplicates"):
                self.assertIn(name, cancelled["search"])
                self.assertGreaterEqual(resumed["search"][name], cancelled["search"][name])
            self.assertFalse(resumed["independent_validation_complete"])
            self.assertEqual(resumed["final"]["scenarios"], {})

    def test_corrupt_success_report_is_recomputed_and_changed_config_rejected(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-cache-") as directory:
            source = Path(directory)/'role.simc'
            destination = Path(directory)/'task'
            source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=120,search_budget_seconds=90,candidate_limit=2,
                        batch_targets=(2,),validation_batches=2,final_batches=2,
                        iterations=2,final_iterations=2,scenarios=('nominal',),max_processes=1)
            with _fast_search_boundary():
                first=run_task(source,destination,search_config=config)
                row=first['search']['records'][0]['batches'][0]
                report=destination/row['artifact']/'native.json'
                data=json.loads(report.read_text(encoding='utf-8'))
                data['sim']['players'][0]['collected_data']['dps']['mean']=1
                report.write_text(json.dumps(data),encoding='utf-8')
                resumed=run_task(source,Path(directory)/'second',search_config=config)
                self.assertGreater(resumed['search']['records'][0]['batches'][0]['dps'],1)
                self.assertFalse(resumed['search']['records'][0]['batches'][0].get('cached',False))
                with self.assertRaises(TaskError):
                    resume_task(destination,search_config=dict(config,max_processes=2))
                self.assertFalse(resumed['independent_validation_complete'])

    def test_old_rule_checkpoint_is_rejected_without_overwriting_its_result(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory(prefix='sim2gse-old-rules-') as directory:
            source = Path(directory) / 'role.simc'
            destination = Path(directory) / 'task'
            source.write_text(sample_profile(), encoding='utf-8')
            with _fast_search_boundary():
                run_task(source, destination, search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2))
                before = read_task(destination)
                with closing(sqlite3.connect(destination / 'task.sqlite3')) as database:
                    state = json.loads(database.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
                    state.pop('rules')
                    database.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(state),))
                    database.commit()
                with self.assertRaisesRegex(TaskError, '版本或编译规则已变化'):
                    resume_task(destination)
                self.assertEqual(read_task(destination), before)

    def test_task_hard_exit_preserves_checkpoint_and_cleans_owned_engine(self):
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
                return [child for child,_,name in processes if child in descendants and name=='simc.exe']
            finally:
                kernel.CloseHandle(snapshot)
        with tempfile.TemporaryDirectory(prefix='sim2gse-crash-') as directory:
            source=Path(directory)/'role.simc';destination=Path(directory)/'task'
            source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=60,search_budget_seconds=30,candidate_limit=20,
                        batch_targets=(2,),validation_batches=1,final_batches=2,iterations=2,
                        final_iterations=32,max_processes=2)
            code="import sys,json;sys.path.insert(0,sys.argv[1]);from task import run_task;run_task(sys.argv[2],sys.argv[3],search_config=json.loads(sys.argv[4]))"
            process=subprocess.Popen([sys.executable,'-c',code,str(REPOSITORY/'projects/sim2gse'),str(source),str(destination),json.dumps(config)])
            held=None
            try:
                deadline=time.monotonic()+45
                state={}
                while time.monotonic()<deadline and process.poll() is None:
                    try: state=read_task(destination)
                    except TaskError: pass
                    if state.get('phase') == 'search':
                        for pid in children(process.pid):
                            held=kernel.OpenProcess(0x100000,False,pid)
                            if held: break
                    if held: break
                    time.sleep(0.02)
                self.assertIsNotNone(held,'没有观察到真实引擎进程')
                process.kill();process.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(held,2000),0,'任务退出后仍有所属模拟进程')
                before=state['elapsed_seconds']
                resumed=resume_task(destination)
                self.assertGreaterEqual(resumed['elapsed_seconds'],before)
                self.assertGreaterEqual(resumed['completed_batches'], state['completed_batches'])
            finally:
                if held:kernel.CloseHandle(held)
                if process.poll() is None:process.kill();process.wait(timeout=5)

    def test_search_budget_rejects_values_outside_contract(self):
        from search import config_for

        for value in (601, float("nan"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config_for({"total_budget_seconds": value})

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

    def test_same_conditions_reuse_search_without_final_samples(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-cache-reuse-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=120,search_budget_seconds=90,candidate_limit=2,batch_targets=(2,),
                        validation_batches=2,final_batches=2,iterations=2,final_iterations=2,
                        scenarios=('nominal',),max_processes=1,
                        reset_events=((4500, 'target'),))
            with _fast_search_boundary():
                first=run_task(source,Path(directory)/'first',search_config=config)
                source.write_text(sample_profile()+'\n# display note\n',encoding='utf-8')
                second=run_task(source,Path(directory)/'second',search_config=config)
                changed_events=dict(config, reset_events=((6000, 'target'),))
                third=run_task(source,Path(directory)/'third',search_config=changed_events)
            self.assertTrue(second['search']['records'][0]['batches'][0].get('cached'))
            self.assertFalse(third['search']['records'][0]['batches'][0].get('cached'))
            self.assertEqual(first['final']['scenarios'], {})
            self.assertEqual(second['final']['scenarios'], {})

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

    def test_multiple_local_chains_use_their_own_observed_feedback(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-local-search-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            with _fast_search_boundary():
                result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=120,
                    search_budget_seconds=90,candidate_limit=19,round_candidate_limit=4,batch_targets=(2,),
                    validation_batches=2,iterations=2,final_batches=2,final_iterations=2,scenarios=('nominal',)))
            self.assertEqual(result['search']['candidate_count'],19)
            self.assertTrue(result['search']['partial_round'])
            chains=result['search']['chains']
            self.assertGreaterEqual(sum(chain['rounds']>0 for chain in chains),2)
            for chain in chains:
                if chain['rounds']:
                    self.assertTrue(chain['feedback']['attempts'])
                    self.assertIn(chain['feedback_source'],chain['visited'])
            self.assertIn(result['search']['stop_reason'],{'candidate_limit','no_improvement','search_deadline','space_stalled'})

    def test_malformed_shared_cache_record_is_ignored(self):
        import sqlite3
        with tempfile.TemporaryDirectory(prefix='sim2gse-malformed-cache-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=120,search_budget_seconds=90,candidate_limit=2,batch_targets=(2,),
                        validation_batches=2,final_batches=2,iterations=2,final_iterations=2,scenarios=('nominal',))
            with _fast_search_boundary():
                run_task(source,Path(directory)/'first',search_config=config)
                with sqlite3.connect(Path(directory)/'cache.sqlite3') as database:
                    database.execute("UPDATE reusable SET value='broken-json'")
                database.close()
                result=run_task(source,Path(directory)/'second',search_config=config)
            self.assertTrue(result['candidate']['text'].startswith('!GSE3!'))
            self.assertFalse(result['search']['records'][0]['batches'][0].get('cached',False))

    def test_busy_and_dispatch_failure_are_counted_as_attempts(self):
        from search import feedback_from_trace

        feedback = feedback_from_trace([
            dict(event="busy", battle=1, origin=1, action="feedback_probe"),
            dict(event="dispatch_failed", battle=1, origin=2, action="feedback_probe"),
        ])
        self.assertEqual(feedback["attempts"], {"feedback_probe": 2})

    def test_crash_allowance_exhaustion_is_published_once(self):
        import sqlite3,json
        with tempfile.TemporaryDirectory(prefix='sim2gse-exhaustion-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            destination=Path(directory)/'task'
            with _fast_search_boundary():
                run_task(source,destination,search_config=dict(total_budget_seconds=10,search_budget_seconds=3,
                    candidate_limit=2,batch_targets=(2,),iterations=2,validation_batches=2,final_batches=1,
                    final_iterations=2,scenarios=('nominal',)))
            database=sqlite3.connect(destination/'task.sqlite3')
            try:
                state=json.loads(database.execute('SELECT value FROM state').fetchone()[0])
                state.update(status='running',phase='final',elapsed_seconds=9,inflight={'batch':dict(start=9,allowance=1)})
                database.execute('UPDATE state SET value=?',(json.dumps(state),));database.commit()
            finally:database.close()
            (destination/'progress.json').write_text(json.dumps(dict(status='running',phase='final',elapsed_seconds=9)))
            with _fast_initialization():
                resumed=resume_task(destination)
            self.assertEqual(resumed['status'],'validation_incomplete')
            self.assertEqual(resumed['elapsed_seconds'],10)
            self.assertEqual(read_task(destination)['status'],'validation_incomplete')
            with _fast_initialization():
                self.assertEqual(resume_task(destination)['elapsed_seconds'],10)

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

    def test_native_start_callback_failure_still_cleans_the_created_process(self):
        import runtime

        class Process:
            def __init__(self, folder):
                self.stdout_path = Path(folder) / "stdout.tmp"
                self.stderr_path = Path(folder) / "stderr.tmp"
                self.stdout_path.write_bytes(b"")
                self.stderr_path.write_bytes(b"")
                self.terminated = False
                self.closed = False

            def terminate(self):
                self.terminated = True

            def wait(self, _timeout):
                return 0

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory(prefix="sim2gse-start-callback-") as directory:
            process = Process(directory)
            reservations = []
            task_runtime = runtime.TaskRuntime(10)
            task_runtime.reservation = lambda key, allowance: reservations.append((key, allowance))
            with patch.object(runtime, "_create_process", return_value=process), \
                    self.assertRaisesRegex(OSError, "counter write failed"):
                runtime.run_command(["simc"], directory, timeout_seconds=5,
                                    runtime=task_runtime,
                                    on_start=lambda: (_ for _ in ()).throw(
                                        OSError("counter write failed")))

            self.assertTrue(process.terminated)
            self.assertTrue(process.closed)
            self.assertIsNone(reservations[-1][1])
            self.assertFalse(process.stdout_path.exists())
            self.assertFalse(process.stderr_path.exists())

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
