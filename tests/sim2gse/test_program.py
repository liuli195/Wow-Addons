"""搜索的简单程序经共享编译入口仍产生相同 GSE 序列。"""

from pathlib import Path
import base64
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

import cbor2

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from codec import export, wire_value  # noqa: E402
from gse_import import _map_step, decode_import, import_action_spell_ids  # noqa: E402
from program import compile_program, from_action_blocks, from_gse_import  # noqa: E402
from sequence import compiled_program  # noqa: E402


class ProgramTests(unittest.TestCase):
    def test_import_action_spell_ids_include_embedded_repeat_and_macro_actions(self):
        program = dict(nodes=[
            dict(kind="Action", commands=[dict(type="spell", argument=316239)]),
            dict(kind="Repeat", action=dict(kind="Action", commands=[
                dict(type="spell", argument="1247378")])),
            dict(kind="Embed", body=[dict(kind="Action", commands=[
                dict(type="macro", text="/cast [@target,harm] 43265\n/use 13")])]),
        ])
        self.assertEqual(import_action_spell_ids(program), [43265, 316239, 1247378])

    def test_upstream_compiles_direct_sequence_object_shell(self):
        sequence = dict(MetaData=dict(Name="DIRECT_SEQUENCE", SpecID=252, GSEVersion=3331),
                        Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "spell", "spell": 77575}])])
        raw = cbor2.dumps(wire_value(sequence))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "DIRECT_SEQUENCE", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["outbreak"]])

    def test_compile_rejects_click_rate_different_from_simulation_input_interval(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Pause", "MS": "GCD"}])])
        raw = cbor2.dumps(wire_value(["MISMATCH", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "点击间隔.*一致"):
            compile_program(from_gse_import(text, "MISMATCH", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=400,
                                         gcd_ms=1500, seed=1))

    def test_import_rejects_gse_version_newer_than_locked_upstream_before_compiling(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3333), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "spell", "spell": 77575}])])
        raw = cbor2.dumps(wire_value(["FUTURE", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        upstream_result = type("Process", (), {"returncode": 0,
                                                 "stdout": b"STEP\t1\tspell\t77575\t\t1\nPASS\t1\n",
                                                 "stderr": b""})()
        with tempfile.TemporaryDirectory() as directory, \
             patch("gse_import.run_command", return_value=upstream_result) as run_upstream, \
             self.assertRaisesRegex(ValueError, "3333.*3332.*不能模拟"):
            compile_program(from_gse_import(text, "FUTURE", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()

    def test_import_rejects_invalid_pause_duration_with_clear_error(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Pause", "MS": {"bad": 1}}])])
        raw = cbor2.dumps(wire_value(["INVALID_PAUSE", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "GSE Pause 时长无效"):
            compile_program(from_gse_import(text, "INVALID_PAUSE", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))

    def test_if_boolean_literals_with_equals_compile_the_selected_branch(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "If", "Variable": "=true",
                                                1: [{"Type": "Action", "type": "spell", "spell": 77575}],
                                                2: [{"Type": "Action", "type": "spell", "spell": 999999}] }])])
        raw = cbor2.dumps(wire_value(["IF_TRUE", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "IF_TRUE", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["outbreak"]])

    def test_if_false_literal_selects_only_the_false_branch(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "If", "Variable": "=false",
                                                1: [{"Type": "Action", "type": "spell", "spell": 999999}],
                                                2: [{"Type": "Action", "type": "spell", "spell": 77575}] }])])
        raw = cbor2.dumps(wire_value(["IF_FALSE", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "IF_FALSE", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["outbreak"]])

    def test_embed_missing_and_cycle_errors_include_source_path(self):
        missing = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                       Versions=[dict(Actions=[{"Type": "Embed", "Sequence": "ABSENT"}])])
        cycle_a = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                       Versions=[dict(Actions=[{"Type": "Embed", "Sequence": "B"}])])
        cycle_b = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                       Versions=[dict(Actions=[{"Type": "Embed", "Sequence": "A"}])])
        cases = [
            (["MISSING", missing], "Embed 引用缺失：ABSENT.*Actions\\[1\\]"),
            ({"type": "COLLECTION", "payload": {"Sequences": {"A": cycle_a, "B": cycle_b}}},
             "Embed 循环引用：A.*Actions\\[1\\]"),
        ]
        for payload, message in cases:
            raw = cbor2.dumps(wire_value(payload))
            text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
            name = "MISSING" if isinstance(payload, list) else "A"
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, \
                 self.assertRaisesRegex(ValueError, message):
                compile_program(from_gse_import(text, name, 1), Path(directory),
                                identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                                context=dict(click_ms=300, input_interval_ms=300,
                                             gcd_ms=1500, seed=1))

    def test_expansion_limit_is_checked_before_starting_upstream_compiler(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Loop", "Repeat": "2",
                                                1: {"Type": "Pause", "Clicks": 3000}}])])
        raw = cbor2.dumps(wire_value(["TOO_MANY", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        fake = type("Process", (), {"returncode": 0, "stdout": b"PASS\t1\n", "stderr": b""})()
        with tempfile.TemporaryDirectory() as directory, \
             patch("gse_import.run_command", return_value=fake) as run_upstream, \
             self.assertRaisesRegex(ValueError, "展开.*4096"):
            compile_program(from_gse_import(text, "TOO_MANY", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=300,
                                         gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()

    def test_loop_step_functions_follow_fixed_upstream_order(self):
        actions = [
            dict(kind="spell", spell_id=77575, name="Outbreak", simc_action="outbreak"),
            dict(kind="spell", spell_id=49998, name="Death Coil", simc_action="death_coil"),
        ]
        expected = {
            "Sequential": [["outbreak"], ["death_coil"]],
            "Priority": [["outbreak"], ["outbreak"], ["death_coil"]],
            "ReversePriority": [["outbreak"], ["death_coil"], ["outbreak"]],
        }
        for step_function in ("Sequential", "Priority", "ReversePriority", "Random"):
            sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                            Versions=[dict(Actions=[{"Type": "Loop", "Repeat": "1",
                                                    "StepFunction": step_function,
                                                    1: {"Type": "Action", "type": "spell", "spell": 77575},
                                                    2: {"Type": "Action", "type": "spell", "spell": 49998}}])])
            raw = cbor2.dumps(wire_value(["STEP_FUNCTION", sequence]))
            text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
            with self.subTest(step_function=step_function), tempfile.TemporaryDirectory() as directory:
                candidate = compile_program(from_gse_import(text, "STEP_FUNCTION", 1), Path(directory),
                                            identity=dict(class_id=6, spec_id=252),
                                            capabilities=dict(actions=actions),
                                            context=dict(click_ms=300, input_interval_ms=300,
                                                         gcd_ms=1500, seed=1))
                loop = candidate["program"]["nodes"][0]
                self.assertEqual(loop["step_function"], step_function)
                compiled = compiled_program(candidate)
                if step_function == "Random":
                    self.assertEqual(sorted(compiled), sorted([["outbreak"], ["death_coil"]]))
                else:
                    self.assertEqual(compiled, expected[step_function])

    def test_priority_loop_growth_is_limited_before_upstream(self):
        loop = {"Type": "Loop", "Repeat": "1", "StepFunction": "Priority"}
        for index in range(1, 92):
            loop[index] = {"Type": "Action", "type": "spell", "spell": 77575}
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[loop])])
        raw = cbor2.dumps(wire_value(["PRIORITY_LIMIT", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with tempfile.TemporaryDirectory() as directory, \
             patch("gse_import.run_command") as run_upstream, \
             self.assertRaisesRegex(ValueError, "展开.*4096"):
            compile_program(from_gse_import(text, "PRIORITY_LIMIT", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=300,
                                         gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()

    def test_repeat_sparse_insert_positions_match_fixed_upstream(self):
        actions = [{"Type": "Action", "type": "spell", "spell": 77575},
                   {"Type": "Repeat", "Interval": 8, "type": "spell", "spell": 77575},
                   {"Type": "Loop", "Repeat": "2",
                    **{index: {"Type": "Action", "type": "spell", "spell": 77575}
                       for index in range(1, 6)}}]
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=actions)])
        raw = cbor2.dumps(wire_value(["SPARSE_REPEAT", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "SPARSE_REPEAT", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252),
                                        capabilities=dict(actions=[dict(
                                            kind="spell", spell_id=77575, name="Outbreak",
                                            simc_action="outbreak")]),
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        self.assertEqual([step["source_path"] for step in candidate["compiled_steps"]],
                         ["1", "2", "3.1", "3.2", "3.3", "3.4", "3.5",
                          "3.1", "3.2", "3.3", "2", "3.4", "3.5"])
        self.assertEqual(compiled_program(candidate), [["outbreak"]] * 13)

    def test_upstream_compiles_six_control_blocks_in_one_collection(self):
        def sequence(actions):
            return dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=actions)])
        payload = dict(type="COLLECTION", payload=dict(Sequences={
            "MAIN": sequence([
                {"Type": "Action", "type": "spell", "spell": 77575},
                {"Type": "Repeat", "type": "spell", "spell": 77575, "Interval": 2},
                {"Type": "Loop", "Repeat": "2",
                 1: {"Type": "Action", "type": "spell", "spell": 77575},
                 2: {"Type": "Pause", "Clicks": 2}},
                {"Type": "If", "Variable": "true",
                 1: [{"Type": "Action", "type": "spell", "spell": 77575}],
                 2: [{"Type": "Pause", "Clicks": 2}]},
                {"Type": "Embed", "Sequence": "CHILD"},
            ]),
            "CHILD": sequence([{"Type": "Action", "type": "spell", "spell": 77575}]),
        }, Variables={}, Macros={}))
        raw = cbor2.dumps(wire_value(payload))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        cap = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                 simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "MAIN", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=cap,
                                        context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        def node_kinds(nodes):
            found = []
            for node in nodes:
                found.append(node["kind"])
                found.extend(node_kinds(node.get("body", [])))
                found.extend(node_kinds(node.get("then", [])))
                found.extend(node_kinds(node.get("else_branch", [])))
                if node.get("action"):
                    found.extend(node_kinds([node["action"]]))
            return found

        self.assertTrue({"Action", "Loop", "Repeat", "Pause", "If", "Embed"}
                        <= set(node_kinds(candidate["program"]["nodes"])))
        self.assertEqual([node["commands"] if node["kind"] == "Action" else []
                          for node in candidate["compiled_program"]["clicks"]], compiled_program(candidate))
        self.assertEqual(len(candidate["compiled_program"]["clicks"]), 14)
        self.assertTrue(all(node["source"]["path"] for node in candidate["compiled_program"]["clicks"]))
        self.assertEqual(candidate["compiled_program"]["clicks"][0]["source"]["sequence"], "MAIN")
        self.assertEqual(candidate["compiled_program"]["clicks"][12]["source"]["sequence"], "CHILD")
        self.assertEqual([bool(block) for block in compiled_program(candidate)],
                         [True, True, True, False, True, False, True, True,
                          False, False, True, True, True, True])
        self.assertEqual(len(candidate["source_paths"]), 14)

    def test_default_scene_skips_modifier_cast_and_uses_targeted_macro(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                "macro": "/targetenemy [noharm][dead]\n/cast [mod:shift] 343294\n/petattack [@target,harm,nodead]\n/cast [@player] 43265"}])])
        raw = cbor2.dumps(wire_value(["MACRO", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=43265, name="Death and Decay",
                                          simc_action="death_and_decay")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "MACRO", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["death_and_decay"]])
        self.assertTrue(candidate["compile_context"]["pet_ready"])
        self.assertTrue(candidate["compile_context"]["enemy_target_ready"])
        self.assertEqual(candidate["compile_context"]["scene"],
                         "no_modifiers_enemy_target_ready_pet_ready")

    def test_targetenemy_noharm_dead_is_a_noop_only_with_ready_enemy_target(self):
        exact = dict(type="macro", macrotext="/targetenemy [noharm][dead]")
        self.assertEqual(_map_step(exact, [], "Versions[1].Actions[1]", enemy_target_ready=True), [])
        with self.assertRaisesRegex(ValueError, "敌方目标状态"):
            _map_step(exact, [], "Versions[1].Actions[1]", enemy_target_ready=False)
        for line in ("/targetenemy", "/targetenemy [noharm]", "/targetenemy [dead,noharm]"):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "targetenemy"):
                _map_step(dict(type="macro", macrotext=line), [], "Versions[1].Actions[1]",
                          enemy_target_ready=True)

    def test_pet_attack_requires_explicit_not_ready_scene_when_pet_is_absent(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                "macro": "/petattack\n/cast 77575"}])])
        raw = cbor2.dumps(wire_value(["PET_NOT_READY", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "宠物状态"):
            compile_program(from_gse_import(text, "PET_NOT_READY", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500,
                                         seed=1, pet_ready=False))

    def test_embed_uses_child_default_version_and_source_position(self):
        child = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=2,
                     Versions=[dict(Actions=[{"Type": "Action", "type": "spell", "spell": 77575}]),
                                dict(Actions=[{"Type": "Action", "type": "spell", "spell": 49998}])])
        main = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                    Versions=[dict(Actions=[{"Type": "Embed", "Sequence": "CHILD"}])])
        raw = cbor2.dumps(wire_value({"type": "COLLECTION", "payload": {
            "Sequences": {"MAIN": main, "CHILD": child}, "Variables": {}, "Macros": {},
        }}))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[
            dict(kind="spell", spell_id=77575, name="Outbreak", simc_action="outbreak"),
            dict(kind="spell", spell_id=49998, name="Death Coil", simc_action="death_coil"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "MAIN", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        embed = candidate["program"]["nodes"][0]
        self.assertEqual(embed["kind"], "Embed")
        self.assertEqual(embed["version"], 2)
        self.assertEqual(embed["body"][0]["source"]["version"], 2)
        self.assertEqual(candidate["compiled_program"]["clicks"][0]["source"]["sequence"], "CHILD")
        self.assertEqual(candidate["compiled_program"]["clicks"][0]["source"]["version"], 2)
        self.assertEqual(compiled_program(candidate), [["death_coil"]])

    def test_imported_loop_and_pause_keep_empty_clicks(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[
                            {"Type": "Loop", "Repeat": "2", 1: {"Type": "Action", "type": "spell", "spell": 77575},
                             2: {"Type": "Pause", "Clicks": 2}},
                        ])])
        raw = cbor2.dumps(wire_value(["IMPORTED", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "IMPORTED", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["outbreak"], [], [], ["outbreak"], [], []])
        self.assertEqual(len(candidate["source_paths"]), 6)

    def test_embed_rejects_child_gse_version_newer_than_lock_before_upstream(self):
        main = dict(MetaData=dict(SpecID=252, GSEVersion=3332), Default=1,
                    Versions=[dict(Actions=[{"Type": "Embed", "Sequence": "CHILD"}])])
        child = dict(MetaData=dict(SpecID=252, GSEVersion=3333), Default=1,
                     Versions=[dict(Actions=[{"Type": "Action", "type": "spell", "spell": 77575}])])
        raw = cbor2.dumps(wire_value({"type": "COLLECTION", "payload": {
            "Sequences": {"MAIN": main, "CHILD": child}, "Variables": {}, "Macros": {},
        }}))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with tempfile.TemporaryDirectory() as directory, \
             patch("gse_import.run_command") as run_upstream, \
             self.assertRaisesRegex(ValueError, "CHILD.*3333.*3332.*不能模拟"):
            compile_program(from_gse_import(text, "MAIN", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()

    def test_disabled_nodes_are_skipped_like_locked_upstream(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[
                            {"Type": "UnknownFutureBlock", "Disabled": True,
                             "formula": "=GSE.V.NotAvailable()"},
                            {"Type": "Action", "type": "spell", "spell": 77575},
                        ])])
        raw = cbor2.dumps(wire_value(["DISABLED", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        program = from_gse_import(text, "DISABLED", 1)
        self.assertEqual([node["kind"] for node in program["nodes"]], ["Action"])
        capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                          simc_action="outbreak")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(program, Path(directory), identity=dict(class_id=6, spec_id=252),
                                        capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["outbreak"]])

    def test_macro_pet_and_harm_conditions_use_explicit_compile_context(self):
        cases = [
            ("[pet]", True, True, [["outbreak"], ["outbreak"]]),
            ("[pet]", False, True, [[], ["outbreak"]]),
            ("[nopet]", True, True, [[], ["outbreak"]]),
            ("[nopet]", False, True, [["outbreak"], ["outbreak"]]),
            ("[harm]", True, True, [["outbreak"], ["outbreak"]]),
            ("[harm]", True, False, [[], ["outbreak"]]),
        ]
        for condition, pet_ready, enemy_target_ready, expected in cases:
            with self.subTest(condition=condition, pet_ready=pet_ready,
                              enemy_target_ready=enemy_target_ready):
                sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                                Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                        "macro": f"/cast {condition} 77575"},
                                                        {"Type": "Action", "type": "spell", "spell": 77575}])])
                raw = cbor2.dumps(wire_value(["CONDITIONS", sequence]))
                text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
                capabilities = dict(actions=[dict(kind="spell", spell_id=77575, name="Outbreak",
                                                  simc_action="outbreak")])
                with tempfile.TemporaryDirectory() as directory:
                    candidate = compile_program(from_gse_import(text, "CONDITIONS", 1), Path(directory),
                                                identity=dict(class_id=6, spec_id=252),
                                                capabilities=capabilities,
                                                context=dict(click_ms=300, input_interval_ms=300,
                                                             gcd_ms=1500, seed=1, pet_ready=pet_ready,
                                                             enemy_target_ready=enemy_target_ready))
                self.assertEqual(compiled_program(candidate), expected)

    def test_item_action_maps_only_by_unique_actual_item_id(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "item",
                                                "item": 250245}])])
        raw = cbor2.dumps(wire_value(["ITEM_ID", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[], import_actions=[dict(kind="item", slot=13, item_id=250245,
                                                              simc_action="use_item,slot=trinket1")])
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "ITEM_ID", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["use_item,slot=trinket1"]])

        ambiguous = dict(actions=[], import_actions=[
            dict(kind="item", slot=13, item_id=250245, simc_action="use_item,slot=trinket1"),
            dict(kind="item", slot=14, item_id=250245, simc_action="use_item,slot=trinket2"),
        ])
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "item 250245.*不能映射"):
            compile_program(from_gse_import(text, "ITEM_ID", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=ambiguous,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))

    def test_spell_alias_and_baseline_row_resolve_to_one_native_action(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                "macro": "/cast festering_strike"}])])
        raw = cbor2.dumps(wire_value(["SPELL_ALIAS", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        action = dict(kind="spell", spell_id=85948, name="festering_strike",
                      simc_action="festering_strike")
        alias = dict(kind="spell", spell_id=316239, native_spell_id=85948,
                     name="festering_strike", simc_action="festering_strike",
                     data_valid=True, available=True, background=False, passive=False, quiet=False)
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "SPELL_ALIAS", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252),
                                        capabilities=dict(actions=[action], import_actions=[action, alias]),
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        self.assertEqual(compiled_program(candidate), [["festering_strike"]])

    def test_repeat_and_embed_same_path_keep_full_source_identity(self):
        main = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                    Versions=[dict(Actions=[
                        {"Type": "Repeat", "Interval": 1, "type": "spell", "spell": 70001},
                        {"Type": "Action", "type": "spell", "spell": 70002},
                        {"Type": "Action", "type": "spell", "spell": 70003},
                        {"Type": "Embed", "Sequence": "CHILD"},
                    ])])
        child = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                     Versions=[dict(Actions=[{"Type": "Action", "type": "spell", "spell": 70004}])])
        raw = cbor2.dumps(wire_value({"type": "COLLECTION", "payload": {
            "Sequences": {"MAIN": main, "CHILD": child}, "Variables": {}, "Macros": {},
        }}))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        actions = [dict(kind="spell", spell_id=spell_id, name=f"spell_{spell_id}",
                        simc_action=f"spell_{spell_id}") for spell_id in (70001, 70002, 70003, 70004)]
        with tempfile.TemporaryDirectory() as directory:
            candidate = compile_program(from_gse_import(text, "MAIN", 1), Path(directory),
                                        identity=dict(class_id=6, spec_id=252),
                                        capabilities=dict(actions=actions),
                                        context=dict(click_ms=300, input_interval_ms=300,
                                                     gcd_ms=1500, seed=1))
        clicks = candidate["compiled_program"]["clicks"]
        expected = [
            ("MAIN", 1, "1"), ("MAIN", 1, "2"), ("MAIN", 1, "1"),
            ("MAIN", 1, "3"), ("MAIN", 1, "1"), ("CHILD", 1, "1"),
        ]
        self.assertEqual([(click["source"].get("sequence"), click["source"].get("version"),
                           click["source"]["path"]) for click in clicks], expected)
        self.assertEqual([click["commands"] for click in clicks],
                         [["spell_70001"], ["spell_70002"], ["spell_70001"],
                          ["spell_70003"], ["spell_70001"], ["spell_70004"]])

    def test_search_program_keeps_export_and_compiled_order(self):
        blocks = [[dict(kind="spell", spell_id=77575, name="Outbreak", simc_action="outbreak")]]
        identity = dict(class_id=6, spec_id=252)
        program = from_action_blocks(blocks)
        self.assertEqual(program["nodes"][0]["kind"], "Action")
        self.assertEqual(program["nodes"][0]["commands"], blocks[0])
        self.assertEqual(program["nodes"][0]["source"]["path"], "blocks[0]")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = export(blocks, root / "old", identity=identity)
            new = compile_program(program, root / "new", identity=identity)
        self.assertEqual(new["text"], old["text"])
        self.assertEqual(new["compiled_steps"], old["compiled_steps"])
        self.assertEqual(new["blocks"], old["blocks"])
        self.assertEqual([node["commands"] if node["kind"] == "Action" else []
                          for node in new["compiled_program"]["clicks"]], compiled_program(new))
        self.assertEqual(new["compiled_program"]["clicks"][0]["source"]["path"], "blocks[0]")
