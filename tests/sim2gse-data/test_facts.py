"""事实逻辑在进程内验证；来源绑定与快照保留少量真实合成文件检查。"""
import hashlib
import json
import unittest

import test_lifecycle as lifecycle


class FactTests(unittest.TestCase):
    setUp = lifecycle.LifecycleTests.setUp
    save_config = lifecycle.LifecycleTests.save_config
    initialize = lifecycle.LifecycleTests.initialize

    def call(self, command, *arguments, expected=0):
        return lifecycle.LifecycleTests.call_main(self, command, *arguments, expected=expected)

    def source(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        plan = self.call("register", "--path", str(path), "--role", "native")
        return self.call("register", "--path", str(path), "--role", "native", "--approve-hash", plan["plan_hash"])["artifact_id"]

    def batch(self, version="v1", seed=7, fidelity="native", budget=600, **values):
        condition = dict(fields={"talents": "recorded"}, class_name="Death Knight",
                         engine={"controlled": {"version": version}}, options=["max_time=180"],
                         config={"total_budget_seconds": budget}, simulation_config={"target_count": 1},
                         cbor2="recorded-version", rules={"score": "recorded-rule"})
        condition_hash = hashlib.sha256(json.dumps(condition, ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode()).hexdigest()
        row = dict(status="success", dps=100, samples=9, requested_iterations=10,
                   request=dict(condition=condition_hash, program="recorded-program", purpose="search", seed=seed,
                                input_seed=500007, iterations=10, stats="recorded-stats", times=[0, 0.3],
                                trace=False, reset_events=[]), condition_details=condition, fidelity=fidelity)
        row.update(values)
        return row

    def extracted(self, name, document):
        return self.call("extract", "--artifact-id", self.source(name, document))["fact_id"]

    def batch_extracted(self, directory, documents):
        folder = self.root / directory
        folder.mkdir()
        for name, document in documents.items():
            (folder / name).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        plan = self.call("legacy-register", "--directory", str(folder), "--role", "native")
        registered = self.call("legacy-register", "--directory", str(folder), "--role", "native",
                               "--approve-hash", plan["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), len(documents))
        return {item["path"].rsplit("/", 1)[-1]: self.call("extract", "--artifact-id", item["artifact_id"])["fact_id"]
                for item in registered["artifacts"]}

    def test_extract_is_idempotent_retains_missing_and_does_not_touch_last_used(self):
        self.initialize()
        artifact = self.source("batch.json", self.batch())
        before = self.call("protect", "--artifact-id", artifact)["last_used"]
        first = self.call("extract", "--artifact-id", artifact)
        self.assertTrue(first["changed"])
        second = self.call("extract", "--artifact-id", artifact)
        self.assertFalse(second["changed"])
        self.assertEqual(first["fact_id"], second["fact_id"])
        fact = self.call("query")["rows"][0]
        self.assertEqual(fact["samples"], 9)
        self.assertEqual(fact["requested_iterations"], 10)
        self.assertIsNone(fact["observations"]["probabilities"])
        self.assertIsNone(fact["observations"]["action_trace"])
        self.assertIsNone(fact["uncertainty"])
        self.assertEqual(self.call("protect", "--artifact-id", artifact)["last_used"], before)

    def test_failed_incomplete_censored_and_native_uncertainty_are_preserved(self):
        self.initialize()
        for status in ("failed", "incomplete", "budget_exhausted"):
            self.extracted(f"{status}.json", {"status": status, "error": "recorded failure"})
        native = dict(sim={"players": [{"name": "A", "sim2gse_class": "death_knight",
                        "collected_data": {"dps": {"mean": 25, "count": 9, "std_dev": 3},
                                           "fight_length": {"mean": 180}}}]})
        self.extracted("native.json", native)
        rows = self.call("query")["rows"]
        by_status = {row["status"]: row for row in rows}
        for status in ("failed", "incomplete", "budget_exhausted"):
            self.assertIsNone(by_status[status]["dps"])
            self.assertIsNone(by_status[status]["samples"])
        self.assertTrue(by_status["budget_exhausted"]["censored"])
        self.assertEqual(by_status["reported"]["uncertainty"], {"std_dev": 3})
        self.assertEqual(by_status["reported"]["seconds"], 180)

    def test_query_export_are_bounded_and_preserve_rows(self):
        self.initialize()
        for number in range(3):
            self.extracted(f"{number}.json", self.batch(dps=number))
        result = self.call("query", "--limit", "2")
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(self.call("query", "--limit", "2", "--offset", "2")["rows"]), 1)
        self.call("query", "--limit", "1001", expected=2)
        self.call("query", "--offset", "-1", expected=2)
        self.assertEqual(self.call("export", "--limit", "2")["rows"], result["rows"])

    def test_compare_allows_version_axis_but_refuses_or_stratifies_other_changes(self):
        self.initialize()
        left = self.extracted("left.json", self.batch())
        right = self.extracted("right.json", self.batch(version="v2", dps=110))
        args = ("--left", left, "--right", right, "--axis", "condition.engine.controlled.version")
        comparison = self.call("compare", *args)
        self.assertTrue(comparison["comparable"])
        self.assertEqual(comparison["delta_dps"], 10)
        self.assertIsNone(comparison["delta_confidence_interval"])
        changed = self.extracted("changed.json", self.batch(version="v2", seed=8, dps=110))
        args = ("--left", left, "--right", changed, "--axis", "condition.engine.controlled.version")
        self.call("compare", *args, expected=2)
        stratified = self.call("compare", *args, "--stratify", "request.seed")
        self.assertFalse(stratified["comparable"])
        self.assertIsNone(stratified["delta_dps"])
        fidelity = self.extracted("fidelity.json", self.batch(version="v2", fidelity="replay"))
        self.call("compare", "--left", left, "--right", fidelity, "--axis", "condition.engine.controlled.version", expected=2)
        budget = self.extracted("budget.json", self.batch(version="v2", budget=300))
        self.call("compare", "--left", left, "--right", budget, "--axis", "condition.engine.controlled.version", expected=2)
        self.call("compare", "--left", left, "--right", right, expected=2)
        self.call("compare", "--left", left, "--right", right, "--axis", "missing.version", expected=2)

    def test_snapshot_freezes_selection_and_persistently_protects_sources(self):
        self.initialize()
        artifact = self.source("source.json", self.batch())
        fact = self.call("extract", "--artifact-id", artifact)["fact_id"]
        args = ("--fact-id", fact)
        preview = self.call("snapshot", *args)
        self.assertFalse(preview["applied"])
        self.call("snapshot", *args, "--approve-hash", "wrong", expected=2)
        applied = self.call("snapshot", *args, "--approve-hash", preview["plan_hash"])
        self.assertEqual(self.call("snapshot", *args, "--approve-hash", preview["plan_hash"])["snapshot_id"], applied["snapshot_id"])
        frozen = self.call("query", "--snapshot-id", applied["snapshot_id"])
        self.extracted("new.json", self.batch(version="new"))
        self.assertEqual(self.call("query", "--snapshot-id", applied["snapshot_id"]), frozen)
        self.assertEqual(len(self.call("query")["rows"]), 2)
        reasons = self.call("protect", "--artifact-id", artifact)["reasons"]
        self.assertIn("durable:snapshot:" + applied["snapshot_id"], reasons)
        self.assertEqual(frozen["rows"][0]["source"]["sha256"], self.call("resolve", "--artifact-id", artifact, "--inspect")["sha256"])

    def test_native_context_is_hash_bound_and_opaque_conditions_cannot_be_compared(self):
        self.initialize()
        native = {"sim": {"players": [{"name": "A", "collected_data": {"dps": {"mean": 100, "count": 9}}}]}}
        artifact = self.source("native.json", native)
        row = self.batch()
        row["sha256"] = "wrong"
        context = self.source("context.json", row)
        self.call("extract", "--artifact-id", artifact, "--context-artifact-id", context, expected=2)
        row["sha256"] = self.call("resolve", "--artifact-id", artifact, "--inspect")["sha256"]
        context = self.source("correct-context.json", row)
        fact = self.call("extract", "--artifact-id", artifact, "--context-artifact-id", context)["fact_id"]
        self.assertIn("durable:fact:" + fact, self.call("protect", "--artifact-id", context)["reasons"])
        opaque = self.batch(version="v2")
        opaque.pop("condition_details")
        other = self.extracted("opaque.json", opaque)
        self.call("compare", "--left", fact, "--right", other, "--axis", "condition.engine.controlled.version", expected=2)

    def test_changed_sources_nonfinite_numbers_and_bad_condition_binding_are_rejected(self):
        self.initialize()
        artifact = self.source("changed.json", self.batch())
        (self.root / "changed.json").write_text("{}", encoding="utf-8")
        self.call("extract", "--artifact-id", artifact, expected=2)
        bad = self.batch()
        bad["condition_details"]["config"]["total_budget_seconds"] = 1
        self.call("extract", "--artifact-id", self.source("bad-condition.json", bad), expected=2)
        self.call("extract", "--artifact-id", self.source("nan.json", {"status": "success", "dps": float("nan")}), expected=2)

    def test_snapshot_rechecks_source_before_publish_and_bad_context_shapes_are_rejected(self):
        self.initialize()
        artifact = self.source("source.json", self.batch())
        fact = self.call("extract", "--artifact-id", artifact)["fact_id"]
        plan = self.call("snapshot", "--fact-id", fact)
        (self.root / "source.json").write_text("{}", encoding="utf-8")
        self.call("snapshot", "--fact-id", fact, "--approve-hash", plan["plan_hash"], expected=2)
        malformed = self.batch()
        malformed["condition_details"]["config"] = "not-an-object"
        malformed["request"]["condition"] = hashlib.sha256(json.dumps(malformed["condition_details"], ensure_ascii=False,
                                                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.call("extract", "--artifact-id", self.source("bad-shape.json", malformed), expected=2)

    def test_native_context_flags_and_multi_player_metric_are_not_lost(self):
        self.initialize()
        native = {"sim": {"players": [{"name": "A", "collected_data": {"dps": {"mean": 10, "count": 9}}},
                                      {"name": "B", "collected_data": {"dps": {"mean": 20, "count": 9}}}],
                          "statistics": {"raid_dps": {"mean": 30, "count": 9, "mean_std_dev": 0.5}}}}
        artifact = self.source("multi.json", native)
        self.call("extract", "--artifact-id", artifact, expected=2)
        context = self.batch(dps=30, censored=True, incomplete=True)
        context["sha256"] = self.call("resolve", "--artifact-id", artifact, "--inspect")["sha256"]
        metadata = self.source("context.json", context)
        result = self.call("extract", "--artifact-id", artifact, "--context-artifact-id", metadata, "--player-name", "A")
        row = self.call("query")["rows"][0]
        self.assertEqual(row["fact_id"], result["fact_id"])
        self.assertEqual(row["metric"], "raid_dps")
        self.assertEqual(row["dps"], 30)
        self.assertEqual(row["uncertainty"], {"mean_std_dev": 0.5})
        self.assertTrue(row["censored"])
        self.assertTrue(row["incomplete"])

    def test_summary_result_and_unreported_actions_are_preserved_without_inference(self):
        self.initialize()
        fact = self.extracted("result.json", {"status": "completed", "search_result": {"dps": 5, "samples": 3},
                                              "independent_validation_complete": False})
        row = self.call("query")["rows"][0]
        self.assertEqual(row["fact_id"], fact)
        self.assertEqual(row["source_kind"], "search_summary")
        self.assertFalse(row["independent_validation_complete"])
        self.assertIsNone(row["observations"]["probabilities"])
        self.assertIsNone(row["context"]["fidelity"])

    def test_recorded_native_action_sequence_has_a_source_pointer_not_invented_probabilities(self):
        self.initialize()
        document = {"sim": {"players": [{"name": "A", "collected_data": {"dps": {"mean": 10, "count": 2},
                                     "action_sequence": [{"time": 0, "name": "recorded-action"}]}}]}}
        source = self.source("recorded.json", document)
        self.call("extract", "--artifact-id", source)
        observations = self.call("query")["rows"][0]["observations"]
        self.assertEqual(observations["action_sequence"], {"artifact_id": source, "entries": 1,
                                                          "json_pointer": "/sim/players/0/collected_data/action_sequence"})
        self.assertIsNone(observations["probabilities"])

    def production_batch(self, program="death_strike", seed=7, dps=100):
        # 按search.py1270—1325的实际记录结构，不加入condition_details或fidelity。
        return dict(status="success", request=dict(condition="a" * 64,
                    program=dict(version="sim2gse-search-behavior-v1", start_step=1, sequence_reset="end",
                                 clicks=[[program]], castsequences=[]), purpose="search", behavior_identity=program,
                    seed=seed, input_seed=seed + 500000, iterations=10, times=[0.0, 0.3],
                    stats="paired-bootstrap-v1", trace=False, reset_events=[]), dps=dps, samples=9,
                    requested_iterations=10, artifact="batches/recorded-key", origin="recorded-origin",
                    sha256="b" * 64, feedback=None)

    def test_actual_production_rows_can_compare_known_axes_under_same_opaque_condition(self):
        self.initialize()
        left = self.extracted("actual-left.json", self.production_batch())
        right = self.extracted("actual-right.json", self.production_batch(seed=8, dps=110))
        result = self.call("compare", "--left", left, "--right", right, "--axis", "request.seed", "--axis", "request.input_seed")
        self.assertTrue(result["comparable"])
        self.assertEqual(result["delta_dps"], 10)
        self.assertEqual(result["comparison_scope"], "same_opaque_condition")
        self.assertIn("fidelity_label", result["unknown_conditions"])
        self.assertIsNone(result["validation_complete"])
        changed = self.production_batch(seed=8)
        changed["request"]["condition"] = "c" * 64
        other = self.extracted("other-condition.json", changed)
        self.call("compare", "--left", left, "--right", other, "--axis", "request.seed", expected=2)

    def test_search_termination_validation_and_elapsed_survive_export_and_snapshot(self):
        self.initialize()
        document = dict(status="completed", phase="done", elapsed_seconds=599.75, completed_batches=12,
                        search_result={"dps": 100, "samples": 9}, independent_validation_complete=False,
                        search=dict(dataset="search", rounds=4, candidate_count=12, unique_candidates=15,
                                    partial_round=True, stop_reason="search_deadline"))
        fact = self.extracted("deadline-result.json", document)
        row = self.call("query")["rows"][0]
        self.assertTrue(row["censored"])
        self.assertTrue(row["incomplete"])
        self.assertEqual(row["censoring_scope"], "search")
        self.assertIsNone(row["sample_censored"])
        self.assertEqual(row["validation_status"], "incomplete")
        self.assertEqual(row["elapsed_seconds"], 599.75)
        self.assertIsNone(row["fight_length_seconds"])
        self.assertEqual(row["search_summary"], document["search"])
        self.assertEqual(self.call("export")["rows"], [row])
        plan = self.call("snapshot", "--fact-id", fact)
        snapshot = self.call("snapshot", "--fact-id", fact, "--approve-hash", plan["plan_hash"])
        self.assertEqual(self.call("query", "--snapshot-id", snapshot["snapshot_id"])["rows"], [row])
        unfinished = self.extracted("validation-result.json", {"status": "validation_incomplete", "phase": "validation", "elapsed_seconds": 23.5})
        by_id = {item["fact_id"]: item for item in self.call("query")["rows"]}
        self.assertTrue(by_id[unfinished]["incomplete"])
        self.assertEqual(by_id[unfinished]["validation_status"], "incomplete")



    def test_request_types_and_nested_json_boolean_numeric_differences_are_preserved(self):
        self.initialize()
        malformed = self.production_batch()
        malformed["request"]["trace"] = 0
        self.call("extract", "--artifact-id", self.source("bad-trace.json", malformed), expected=2)
        documents = {}
        for number, (left_value, right_value) in enumerate(((False, 0), ([False], [0]), ({"flag": False}, {"flag": 0}))):
            left_document, right_document = self.batch(), self.batch(version="v2")
            left_document["request"]["program"] = {"nested": left_value}
            right_document["request"]["program"] = {"nested": right_value}
            documents[f"type-left-{number}.json"] = left_document
            documents[f"type-right-{number}.json"] = right_document
        facts = self.batch_extracted("type facts", documents)
        for number in range(3):
            left = facts[f"type-left-{number}.json"]
            right = facts[f"type-right-{number}.json"]
            self.call("compare", "--left", left, "--right", right, "--axis", "condition.engine.controlled.version", expected=2)

    def test_adaptive_request_counts_and_effective_samples_are_not_normalized_to512(self):
        self.initialize()
        for requested, effective, batches in ((32, 31, 1), (128, 124, 4), (512, 496, 16)):
            row = self.production_batch()
            row["request"]["iterations"] = requested
            row.update(requested_iterations=requested, samples=effective, completed_batches=batches,
                       elapsed_seconds=1.25 * batches)
            self.extracted(f"adaptive-{requested}.json", row)
        rows = self.call("query")["rows"]
        self.assertEqual({(row["requested_iterations"], row["samples"], row["completed_batches"]) for row in rows},
                         {(32, 31, 1), (128, 124, 4), (512, 496, 16)})
        for row in rows:
            self.assertTrue(row["sample_complete"])
            self.assertIsNone(row["censored"])
            self.assertIsNone(row["fight_length_seconds"])
            self.assertEqual(row["elapsed_seconds"], 1.25 * row["completed_batches"])

    def test_complete_search_summary_is_comparable_only_with_recorded_completion_evidence(self):
        self.initialize()
        def result(version, dps, **changes):
            value = self.batch(version=version, status="completed", search_result={"dps": dps, "samples": 9},
                               search={"partial_round": False, "stop_reason": "no_improvement"},
                               independent_validation_complete=True)
            value.update(changes)
            return value
        variants = [result("v2", 110, independent_validation_complete=False),
                    result("v2", 110, independent_validation_complete=None),
                    result("v2", 110, status="validation_incomplete"),
                    result("v2", 110, search={"partial_round": False, "stop_reason": "search_deadline"}),
                    result("v2", 110, search={"stop_reason": "no_improvement"}),
                    result("v2", 110, search={"partial_round": True, "stop_reason": "no_improvement"})]
        documents = {"complete-left.json": result("v1", 100), "complete-right.json": result("v2", 110)}
        documents.update({f"incomplete-{index}.json": document for index, document in enumerate(variants)})
        facts = self.batch_extracted("completion facts", documents)
        left, right = facts["complete-left.json"], facts["complete-right.json"]
        compared = self.call("compare", "--left", left, "--right", right, "--axis", "condition.engine.controlled.version")
        self.assertTrue(compared["validation_complete"])
        self.assertEqual(compared["sample_complete"], {"left": True, "right": True})
        self.assertTrue(compared["comparable"])
        self.assertEqual(compared["delta_dps"], 10)
        for index, document in enumerate(variants):
            other = facts[f"incomplete-{index}.json"]
            refused = self.call("compare", "--left", left, "--right", other, "--axis", "condition.engine.controlled.version")
            self.assertFalse(refused["comparable"])
            self.assertIsNone(refused["delta_dps"])
            if index == 0:
                self.assertFalse(refused["validation_complete"])
                self.assertEqual(refused["validation_status"], {"left": "complete", "right": "incomplete"})

    def test_real_rule_path_keys_compare_and_escaped_literal_dot_axes_are_distinct(self):
        self.initialize()
        rule_key = "D:\\My Project\\Wow Addons\\projects\\sim2gse\\task.py"
        def document(version, rule_hash="a" * 64, nested=1, literal=2):
            value = self.batch(version=version)
            value["condition_details"]["rules"] = {rule_key: rule_hash, "D:\\My Project\\codec.lua": "b" * 64,
                                                    "D:\\My Project\\compatibility.json": "c" * 64}
            value["condition_details"]["config"].update(x={"y": nested}, **{"x.y": literal})
            value["request"]["condition"] = hashlib.sha256(json.dumps(value["condition_details"], ensure_ascii=False,
                                                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            return value
        facts = self.batch_extracted("rule facts", {"rules-left.json": document("v1"), "rules-right.json": document("v2"),
                                     "literal-right.json": document("v2", literal=3), "nested-right.json": document("v2", nested=999),
                                     "changed-rule.json": document("v2", rule_hash="d" * 64)})
        left, right = facts["rules-left.json"], facts["rules-right.json"]
        self.assertTrue(self.call("compare", "--left", left, "--right", right,
                                 "--axis", "condition.engine.controlled.version")["comparable"])
        literal = facts["literal-right.json"]
        self.call("compare", "--left", left, "--right", literal, "--axis", "condition.engine.controlled.version", expected=2)
        self.assertTrue(self.call("compare", "--left", left, "--right", literal,
                                 "--axis", "condition.engine.controlled.version", "--axis", "condition.config.x%2Ey")["comparable"])
        nested = facts["nested-right.json"]
        self.call("compare", "--left", left, "--right", nested, "--axis", "condition.engine.controlled.version",
                  "--axis", "condition.config.x%2Ey", expected=2)
        changed = facts["changed-rule.json"]
        self.call("compare", "--left", left, "--right", changed, "--axis", "condition.engine.controlled.version", expected=2)
        escaped = "condition.rules.D%3A%5CMy%20Project%5CWow%20Addons%5Cprojects%5Csim2gse%5Ctask%2Epy"
        self.assertTrue(self.call("compare", "--left", left, "--right", changed,
                                 "--axis", "condition.engine.controlled.version", "--axis", escaped)["comparable"])





class FactJsonLogicTests(unittest.TestCase):
    def test_json_byte_bound_and_nonfinite_values_are_checked_in_memory(self):
        import runpy
        namespace = runpy.run_path(str(lifecycle.CLI))
        compact = namespace["compact_json"]
        for maximum in (namespace["FACT_BYTES"], namespace["QUERY_BYTES"]):
            for text in ("x" * (maximum - 2), "汉" * ((maximum - 2) // 3) + "x" * ((maximum - 2) % 3)):
                self.assertEqual(len(compact(text, maximum).encode()), maximum)
                with self.assertRaisesRegex(namespace["DataError"], "固定字节边界"):
                    compact(text + "x", maximum)
        with self.assertRaisesRegex(namespace["DataError"], "非有限"):
            compact(float("nan"), namespace["FACT_BYTES"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
