"""第一票角色读取与导出公开入口的行为检查。"""

from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / 'projects/sim2gse'))
from task import TaskError, run_task, parse_character


REAL_PROFILE = (
    REPOSITORY
    / ".local"
    / "sim2gse"
    / "target-evidence"
    / "task-05"
    / "unholy-20260912-0240.simc"
)

FIXTURE_PROFILE = '''# 可提交的最小真实形状样例\ndeathknight="中文 角色"\nlevel=90\nrace=highmountain_tauren\nregion=cn\nserver=伊利丹\nrole=attack\nspec=unholy\ntalents=CwPAkXBWxkyfx9CbGaHonEAhLBYmxMjZGDz2MzMTziZmZMjBAAAAAAAgZGjZAwyMmZ2MzYMAbmFDDZgZjhGLYADAmHYmZMDwMzwYA\ntrinket1=,id=250245\ntrinket2=,id=250228\n# 背包候选\n# trinket1=,id=251221\n'''


def sample_profile() -> str:
    return FIXTURE_PROFILE + 'main_hand=,id=237846,ilevel=311,enchant_id=6241\n'


class CharacterExportTests(unittest.TestCase):
    def test_native_precombat_button_is_a_nocombat_gse_step(self):
        from codec import export
        from engine import inspect
        from sequence import compiled_program, select

        native = dict(
            actions_protocol=1,
            active_items=[],
            executed_actions=[dict(
                name='heart_strike', signature='heart_strike', player_owned=True,
                background=False, quiet=False, passive=False, type='spell',
                precombat=False, data_id=206930, data_valid=True,
                base_spell_id=206930, gcd_ms=1500,
            )],
            precombat_sequence=[dict(id=195292, name='deaths_caress', queue_failed=False),
                                dict(id=195292, name='deaths_caress', queue_failed=False)],
            precombat_definitions=[dict(
                name='deaths_caress', signature='deaths_caress', player_owned=True,
                background=False, quiet=False, passive=False, type='spell',
                precombat=True, data_id=195292, data_valid=True,
                base_spell_id=195292, gcd_ms=1500,
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            capabilities = inspect(native, Path(directory) / 'capabilities')
            self.assertEqual([a['simc_action'] for a in capabilities['precombat_actions']],
                             ['deaths_caress', 'deaths_caress'])
            candidate = export(select(capabilities, [['heart_strike']]), Path(directory) / 'export',
                               identity=dict(spec_id=250, class_id=6))
            self.assertEqual(candidate['compiled_steps'][0],
                             dict(type='macro', macrotext='/cast [nocombat] deaths_caress'))
            self.assertEqual(candidate['compiled_steps'][1], candidate['compiled_steps'][0])
            self.assertEqual(compiled_program(candidate),
                             [['deaths_caress'], ['deaths_caress'], ['heart_strike']])
            self.assertEqual(candidate['precombat_count'], 2)

    def test_client_target_masks_apply_across_classes_and_mixed_blocks(self):
        from codec import export
        from sequence import compiled_program
        # 独立客户端 SpellTargetRestrictions 正反例；同名天赋版不能误改为脚下。
        cases = [(43265, True), (2120, True), (190356, True), (61882, True),
                 (73920, True), (5740, True), (1254851, False), (204475, False),
                 (206930, False), (2061, False), (26573, False)]
        with tempfile.TemporaryDirectory() as directory:
            for spell_id, is_ground in cases:
                with self.subTest(spell=spell_id):
                    command = dict(kind='spell', spell_id=spell_id, name='spell_'+str(spell_id), simc_action='spell_'+str(spell_id))
                    blocks = [[command], [dict(kind='start_attack', simc_action='auto_attack'), command]]
                    result = export(blocks, Path(directory)/str(spell_id), identity=dict(spec_id=250, class_id=6))
                    first = result['compiled_steps'][0]
                    self.assertEqual(first['type'], 'macro' if is_ground else 'spell')
                    self.assertEqual('[@player]' in result['compiled_steps'][1]['macrotext'], is_ground)
                    self.assertEqual(compiled_program(result), [[command['simc_action']], ['auto_attack',command['simc_action']]])
            for driver, expected in [(43265, True), (206930, False)]:
                item = dict(kind='item', slot=13, driver_spell_id=driver, simc_action='use_item,slot=trinket1')
                result = export([[item]], Path(directory)/('item'+str(driver)), identity=dict(spec_id=250,class_id=6))
                self.assertEqual(result['compiled_steps'][0], dict(type='macro',macrotext='/use [@player] 13') if expected else dict(type='item',item=13))
                self.assertEqual(compiled_program(result), [['use_item,slot=trinket1']])

    def test_public_entry_rejects_output_override_before_writing(self) -> None:
        source = sample_profile() + "\noutput=forbidden.simc\n"
        with tempfile.TemporaryDirectory(prefix="sim2gse-test-") as directory:
            input_path = Path(directory) / "中文 角色.simc"
            input_path.write_text(source, encoding="utf-8")
            with self.assertRaises(TaskError) as raised:
                run_task(input_path, Path(directory) / "task-output", mode="single")
            self.assertIn("output", str(raised.exception))
            self.assertFalse((Path(directory) / "task-output").exists())

    def test_public_entry_preserves_real_character_and_bag_candidates(self) -> None:
        source = sample_profile()
        with tempfile.TemporaryDirectory(prefix="sim2gse-test-") as directory:
            input_path = Path(directory) / "中文 角色.simc"
            output_path = Path(directory) / "task-output"
            input_path.write_text(source, encoding="utf-8")
            result = run_task(input_path, output_path, mode="single")
            self.assertEqual(result['status'], 'offline_ready')
            self.assertTrue((output_path / 'candidate.txt').exists())
            capabilities = result['capabilities']
            self.assertEqual(capabilities['scope'], 'baseline_executed_player_actions')
            self.assertEqual(capabilities['coverage'], 'all_baseline_iterations')
            spell_ids = {a['spell_id'] for a in capabilities['actions'] if a['kind']=='spell'}
            self.assertTrue({42650,1233448,47541,55090} <= spell_ids)
            self.assertTrue(spell_ids.isdisjoint({47528,50977,255654,48743,221562,316239,46585}))
            self.assertEqual([a['simc_action'] for a in capabilities['precombat_actions']], ['raise_dead'])
            self.assertEqual(result['candidate']['compiled_steps'][0],
                             dict(type='macro', macrotext='/cast [nocombat] raise_dead'))
            selected = [row for row in capabilities['sources'] if row['status']=='mapped']
            self.assertTrue(all(row['executions']>0 and row['player_owned'] and
                                not row['background'] and not row['passive'] for row in selected))
            character = result['character']
            self.assertEqual(character.name, "中文 角色")
            self.assertEqual(character.spec, "unholy")
            self.assertEqual(character.equipment["trinket1"].item_id, 250245)
            self.assertEqual(character.equipment["trinket2"].item_id, 250228)
            self.assertIn(251221, {item.item_id for item in character.bag_candidates})
            self.assertTrue(output_path.is_dir())
            self.assertEqual((output_path / "input.simc").read_text(encoding="utf-8"), source)
            self.assertIn(
                '"item_id": 250245',
                (output_path / "profile.json").read_text(encoding="utf-8"),
            )

    def test_public_entry_rejects_multiple_characters_and_bad_values(self) -> None:
        cases = (
            (sample_profile() + "\ndeathknight=\"第二个\"\n", "只能包含一个角色"),
            (sample_profile().replace("race=highmountain_tauren", "race=high mountain"), "race"),
            (sample_profile() + "\ncopy=other-profile\n", "外部引用"),
            (sample_profile() + "\nactions=death_coil\n", "动作列表"),
        )
        for source, expected in cases:
            with self.subTest(source=source[-40:]):
                with tempfile.TemporaryDirectory(prefix="sim2gse-test-") as directory:
                    input_path = Path(directory) / "中文 角色.simc"
                    output_path = Path(directory) / "task-output"
                    input_path.write_text(source, encoding="utf-8")
                    with self.assertRaises(TaskError) as raised:
                        run_task(input_path, output_path, mode="single")
                    self.assertIn(expected, str(raised.exception))
                    self.assertFalse(output_path.exists())

    def test_public_entry_simulates_native_channel_item(self):
        with tempfile.TemporaryDirectory(prefix='序列 饰品 ') as directory:
            source = Path(directory) / '角色.simc'
            source.write_text(sample_profile().replace('trinket1=,id=250245', 'trinket1=,id=270168,ilevel=311'), encoding='utf-8')
            destination = Path(directory) / '任务'
            result = run_task(source, destination, mode="single")
            self.assertTrue((destination / 'candidate.txt').exists())
            self.assertTrue(result['controlled_simulation']['consistent'])
            self.assertIn(270168, {a['item_id'] for a in result['capabilities']['actions'] if a['kind']=='item'})

    def test_public_entry_exports_both_active_items(self):
        with tempfile.TemporaryDirectory(prefix='序列 双主动 ') as directory:
            source = Path(directory) / '角色.simc'
            source.write_text(sample_profile().replace('trinket1=,id=250245', 'trinket1=,id=202610,ilevel=311')
                              .replace('trinket2=,id=250228', 'trinket2=,id=219303,ilevel=311'), encoding='utf-8')
            destination = Path(directory) / '任务'
            result = run_task(source, destination, mode="single")
            self.assertEqual([a['slot'] for a in result['capabilities']['actions'] if a['kind'] == 'item'], [13,14])
            self.assertIn(dict(type='item', item=13), result['candidate']['compiled_steps'])
            self.assertIn(dict(type='macro', macrotext='/use [@player] 14'), result['candidate']['compiled_steps'])


    def test_public_entry_allows_unselected_racial_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / '角色.simc'
            source.write_text(sample_profile().replace('highmountain_tauren', 'undead'), encoding='utf-8')
            destination = Path(directory) / '任务'
            result = run_task(source, destination, mode="single")
            self.assertEqual(result['status'], 'offline_ready')
            self.assertTrue((destination / 'reference').exists())
            self.assertTrue((destination / 'candidate.txt').exists())


if __name__ == "__main__":
    unittest.main()
