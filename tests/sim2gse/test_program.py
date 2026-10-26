"""搜索的简单程序经共享编译入口仍产生相同 GSE 序列。"""

from pathlib import Path
import base64
import sys
import unittest
import zlib
from unittest.mock import patch

import cbor2

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from codec import wire_value
from macro_interpreter import (macro_spell_ids, macro_spell_names, map_action, map_macro,
                               parse_castsequence, preflight_macro)  # noqa: E402
from program import compile_program, from_gse_import


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
        with self.assertRaisesRegex(ValueError, "点击间隔.*一致"):
            compile_program(from_gse_import(text, "MISMATCH", 1), Path("unused-output"),
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
        with patch("gse_import.run_command") as run_upstream, \
             self.assertRaisesRegex(ValueError, "3333.*3332.*不能模拟"):
            compile_program(from_gse_import(text, "FUTURE", 1), Path("unused-output"),
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
            with self.subTest(name=name), \
                 self.assertRaisesRegex(ValueError, message):
                compile_program(from_gse_import(text, name, 1), Path("unused-output"),
                                identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                                context=dict(click_ms=300, input_interval_ms=300,
                                             gcd_ms=1500, seed=1))

    def test_expansion_limit_is_checked_before_starting_upstream_compiler(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Loop", "Repeat": "2",
                                                1: {"Type": "Pause", "Clicks": 3000}}])])
        raw = cbor2.dumps(wire_value(["TOO_MANY", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with patch("gse_import.run_command") as run_upstream, \
             self.assertRaisesRegex(ValueError, "展开.*4096"):
            compile_program(from_gse_import(text, "TOO_MANY", 1), Path("unused-output"),
                            identity=dict(class_id=6, spec_id=252), capabilities=dict(actions=[]),
                            context=dict(click_ms=300, input_interval_ms=300,
                                         gcd_ms=1500, seed=1))
        run_upstream.assert_not_called()


    def test_default_scene_rejects_active_petattack_with_its_source_path(self):
        sequence = dict(MetaData=dict(SpecID=252, GSEVersion=3331), Default=1,
                        Versions=[dict(Actions=[{"Type": "Action", "type": "macro",
                                                "macro": "/targetenemy [noharm][dead]\n/cast [mod:shift] 343294\n/petattack [@target,harm,nodead]\n/cast [@player] 43265"}])])
        raw = cbor2.dumps(wire_value(["MACRO", sequence]))
        text = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        capabilities = dict(actions=[dict(kind="spell", spell_id=43265, name="Death and Decay",
                                          simc_action="death_and_decay")])
        with self.assertRaisesRegex(
                ValueError, r"/petattack.*Sequences\[MACRO\]\.Versions\[1\]\.Actions\[1\]"):
            compile_program(from_gse_import(text, "MACRO", 1), Path("unused-output"),
                            identity=dict(class_id=6, spec_id=252), capabilities=capabilities,
                            context=dict(click_ms=300, input_interval_ms=300, gcd_ms=1500, seed=1))

    def test_item_action_rejects_ambiguous_actual_item_id(self):
        ambiguous = [
            dict(kind="item", slot=13, item_id=250245, simc_action="use_item,slot=trinket1"),
            dict(kind="item", slot=14, item_id=250245, simc_action="use_item,slot=trinket2"),
        ]
        with self.assertRaisesRegex(ValueError, "item 250245.*不能映射"):
            map_action("item", "250245", ambiguous, "ITEM_ID v1 1")


    def test_overlong_compiled_macro_rejected_before_lua(self):
        from codec import prepare_block
        command = dict(kind='spell', spell_id=63560, name='dark_transformation',
                       simc_action='dark_transformation')
        with patch('codec.run_command') as compiler, self.assertRaisesRegex(ValueError, '255'):
            prepare_block([command] * 16, {})
        compiler.assert_not_called()
