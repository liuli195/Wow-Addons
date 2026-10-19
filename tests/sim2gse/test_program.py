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
from macro_interpreter import (macro_spell_ids, macro_spell_names, map_action, map_macro,
                               parse_castsequence, preflight_macro)  # noqa: E402
from program import compile_program, from_action_blocks, from_gse_import  # noqa: E402
from sequence import compiled_program  # noqa: E402


class ProgramTests(unittest.TestCase):
    def test_castsequence_parser_keeps_reset_rules_and_rejects_conditions(self):
        source = 'blocks[2]'
        parsed = parse_castsequence(
            '/castsequence reset=12/target/combat/shift/ctrl/alt 77575,47541', source)
        self.assertEqual(parsed['reset'],
                         {'timeout_seconds': 12,
                          'flags': ['target', 'combat', 'shift', 'ctrl', 'alt']})
        self.assertEqual(parsed['members'], ['77575', '47541'])
        with self.assertRaisesRegex(ValueError, '暂不支持宏条件'):
            parse_castsequence('/castsequence [harm] reset=2 77575,47541', source)
        with self.assertRaisesRegex(ValueError, '暂不支持条件分支'):
            parse_castsequence('/castsequence reset=2 77575;47541', source)
        with self.assertRaisesRegex(ValueError, 'reset 不支持'):
            parse_castsequence('/castsequence reset=2.5 77575,47541', source)

    def test_macro_interpreter_maps_raw_text_with_explicit_scene_and_catalogue(self):
        text = "/cast [pet] 77575\n/cast [nopet] 49998\n/cast Epidemic"
        source = "REAL v1 Versions[1].Actions[1].macro"
        actions = [
            dict(kind="spell", spell_id=77575, name="Outbreak", simc_action="outbreak"),
            dict(kind="spell", spell_id=49998, name="Epidemic", simc_action="epidemic"),
        ]

        preflight_macro(text, source)
        with self.assertRaisesRegex(ValueError, "宏条件不能确定.*nochanneling"):
            preflight_macro("/cast [nochanneling] 49998", source)
        self.assertEqual(map_macro(text, source,
                                   dict(pet_ready=True, enemy_target_ready=True), actions),
                         ["outbreak", "epidemic"])
        self.assertEqual(map_action("item", "13", [
            dict(kind="item", slot=13, item_id=250245,
                 simc_action="use_item,slot=trinket1"),
        ], source), ["use_item,slot=trinket1"])
        self.assertEqual(macro_spell_ids(text), [49998, 77575])
        self.assertEqual(macro_spell_names(text), ["Epidemic"])

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
                                                 "stdout": b"STEP\t1\tspell\t77575\t\t31\t465554555245\t1\nPASS\t1\n",
                                                 "stderr": b""})()
        with tempfile.TemporaryDirectory() as directory, \
             patch("gse_import.run_command", return_value=upstream_result) as run_upstream, \
             self.assertRaisesRegex(ValueError, "3333.*3332.*不能模拟"):
            compile_program(from_gse_import(text, "FUTURE", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()

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

    def test_random_loop_repeat_maps_actual_upstream_order_across_seeds(self):
        actions = [
            dict(kind="spell", spell_id=77575, name="Outbreak", simc_action="outbreak"),
            dict(kind="spell", spell_id=49998, name="Death Coil", simc_action="death_coil"),
            dict(kind="spell", spell_id=55090, name="Scourge Strike", simc_action="scourge_strike"),
            dict(kind="spell", spell_id=43265, name="Death and Decay", simc_action="death_and_decay"),
        ]
        loop = {"Type": "Loop", "Repeat": "2", "StepFunction": "Random",
                1: {"Type": "Action", "type": "spell", "spell": 77575},
                2: {"Type": "Repeat", "Interval": 2, "type": "spell", "spell": 49998},
                3: {"Type": "Action", "type": "spell", "spell": 55090},
                4: {"Type": "Action", "type": "spell", "spell": 43265}}
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[loop])])
        raw = cbor2.dumps(wire_value(["RANDOM_SOURCE", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        by_path = {"1.1": "outbreak", "1.2": "death_coil",
                   "1.3": "scourge_strike", "1.4": "death_and_decay"}
        observed_orders = set()
        for seed in (1, 2):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as directory:
                candidate = compile_program(from_gse_import(text, "RANDOM_SOURCE", 1), Path(directory),
                                            identity=dict(class_id=6, spec_id=252),
                                            capabilities=dict(actions=actions),
                                            context=dict(click_ms=300, input_interval_ms=300,
                                                         gcd_ms=1500, seed=seed))
                steps = candidate["compiled_steps"]
                clicks = candidate["compiled_program"]["clicks"]
                observed_orders.add(tuple(step["source_path"] for step in steps))
                self.assertEqual(len(steps), len(clicks))
                self.assertTrue({"1.1", "1.2", "1.3", "1.4"} <=
                                {step["source_path"] for step in steps})
                for step, click in zip(steps, clicks):
                    self.assertEqual(click["source"]["sequence"], "RANDOM_SOURCE")
                    self.assertEqual(click["source"]["version"], 1)
                    self.assertEqual(click["source"]["path"], step["source_path"])
                    self.assertEqual(click["commands"], [by_path[step["source_path"]]])
        self.assertGreater(len(observed_orders), 1)

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

    def test_default_scene_rejects_active_petattack_with_its_source_path(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                "macro": "/targetenemy [noharm][dead]\n/cast [mod:shift] 343294\n/petattack [@target,harm,nodead]\n/cast [@player] 43265"}])])
        raw = cbor2.dumps(wire_value(["MACRO", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=43265, name="Death and Decay",
                                          simc_action="death_and_decay")])
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
                ValueError, r"/petattack.*Sequences\[MACRO\]\.Versions\[1\]\.Actions\[1\]"):
            compile_program(from_gse_import(text, "MACRO", 1), Path(directory),
                            identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))

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


    def test_overlong_compiled_macro_rejected_before_lua(self):
        command = dict(kind='spell', spell_id=63560, name='dark_transformation',
                       simc_action='dark_transformation')
        with tempfile.TemporaryDirectory() as directory, patch('codec.run_command') as compiler:
            with self.assertRaisesRegex(ValueError, '255'):
                export([[command] * 16], Path(directory) / 'export',
                       identity=dict(class_id=6, spec_id=252))
        compiler.assert_not_called()
