"""第一票角色读取与导出公开入口的行为检查。"""

from __future__ import annotations

import tempfile
import pytest
import contextlib
import io
import json
import runpy
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_public_commands_reject_retired_data_options(self):
        for entry in ("task.py", "interface.py"):
            command = REPOSITORY / "scripts/dev/sim2gse" / entry
            with self.subTest(entry=entry):
                output = io.StringIO()
                with patch.object(sys, "argv", [str(command), "--help"]), \
                        contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as help_exit:
                    runpy.run_path(str(command), run_name="__main__")
                self.assertEqual(help_exit.exception.code, 0)
                self.assertNotIn("--data-config", output.getvalue())
                self.assertNotIn("--reserve-bytes", output.getvalue())
                error = io.StringIO()
                arguments = [str(command), "--data-config", "retired.json", "--reserve-bytes", "1"]
                if entry == "task.py":
                    arguments += ["--output", "unused-output"]
                with patch.object(sys, "argv", arguments), contextlib.redirect_stderr(error), \
                        self.assertRaises(SystemExit) as rejected:
                    runpy.run_path(str(command), run_name="__main__")
                self.assertEqual(rejected.exception.code, 2)
                self.assertIn("unrecognized arguments", error.getvalue())


    def test_lua_start_callback_counts_failed_process_start(self):
        import codec

        starts = []
        failed = SimpleNamespace(returncode=1, stdout=b"", stderr=b"failed")
        def failed_process(*args, **kwargs):
            kwargs["on_start"]()
            return failed
        with patch.object(Path, 'mkdir'), patch.object(Path, 'write_bytes'), \
                patch.object(Path, 'write_text'), \
                patch.object(codec.tempfile, 'TemporaryDirectory', return_value=contextlib.nullcontext(
                    str(REPOSITORY / '.local/sim2gse/codec/memory-callback'))), \
                patch.object(codec, "run_command", side_effect=failed_process), \
                self.assertRaisesRegex(ValueError, "上游编译校验失败"):
            codec.export([[dict(kind="spell", spell_id=206930, name="heart_strike",
                                      simc_action="heart_strike")]], REPOSITORY / '.local/memory-export',
                         identity=dict(spec_id=250, class_id=6),
                         on_lua_start=lambda: starts.append("started"))
        self.assertEqual(starts, ["started"])

    def test_process_creation_failure_does_not_call_start_callback(self):
        import runtime
        starts = []
        with patch.object(Path, 'mkdir'), \
                patch.object(runtime, '_create_process', side_effect=OSError('create failed')), \
                self.assertRaisesRegex(OSError, 'create failed'):
            runtime.run_command(['missing.exe'], Path('unused'), timeout_seconds=1,
                                on_start=lambda: starts.append('started'))
        self.assertEqual(starts, [])

    @pytest.mark.real
    def test_native_precombat_buttons_and_item_keep_the_complete_nocombat_prefix(self):
        import base64
        import zlib
        import cbor2
        import codec
        from codec import export
        from engine import inspect
        from sequence import compiled_program, select

        native = dict(
            actions_protocol=1, apl_actions_protocol=1, apl_actions=[],
            active_items=[dict(slot='trinket1', id=123, driver_spell_id=206930, name='test_item')],
            executed_actions=[dict(
                name='heart_strike', signature='heart_strike', player_owned=True,
                background=False, quiet=False, passive=False, type='spell',
                precombat=False, data_id=206930, data_valid=True,
                base_spell_id=206930, gcd_ms=1500,
            )],
            precombat_sequence=[dict(id=195292, name='deaths_caress', queue_failed=False),
                                dict(id=195292, name='deaths_caress', queue_failed=False),
                                dict(id=123, name='use_item_test_item', queue_failed=False)],
            precombat_definitions=[dict(
                name='deaths_caress', signature='deaths_caress', player_owned=True,
                background=False, quiet=False, passive=False, type='spell',
                precombat=True, data_id=195292, data_valid=True,
                base_spell_id=195292, gcd_ms=1500,
            ), dict(
                name='use_item_test_item', signature='use_item,slot=trinket1', player_owned=True,
                background=False, quiet=False, passive=False, type='item',
                precombat=True, data_id=123, data_valid=True,
                base_spell_id=123, gcd_ms=0,
            )],
        )
        with tempfile.TemporaryDirectory(prefix='中文路径 ') as directory, \
                patch.object(codec, 'run_command', wraps=codec.run_command) as compiler:
            capabilities = inspect(native, Path(directory) / 'capabilities')
            self.assertEqual([a['simc_action'] for a in capabilities['precombat_actions']],
                             ['deaths_caress', 'deaths_caress', 'use_item,slot=trinket1'])
            candidate = export(select(capabilities, [['heart_strike']]), Path(directory) / 'export',
                               identity=dict(spec_id=250, class_id=6, data_version='12.1.0.69933'))
            self.assertEqual(candidate['compiled_steps'][:3], [
                dict(type='macro', macrotext='/cast [nocombat] deaths_caress'),
                dict(type='macro', macrotext='/cast [nocombat] deaths_caress'),
                dict(type='macro', macrotext='/use [nocombat] 13'),
            ])
            self.assertEqual(compiled_program(candidate),
                             [['deaths_caress'], ['deaths_caress'],
                              ['use_item,slot=trinket1'], ['heart_strike']])
            self.assertEqual(candidate['precombat_count'], 3)
            payload = cbor2.loads(zlib.decompress(base64.b64decode(candidate['text'][6:]), -15))
            self.assertIn('模拟数据 12.1.0.69933', payload[1][b'MetaData'][b'Help'].decode())

        self.assertEqual(compiler.call_count, 1)
        self.assertTrue(all(str(value).isascii()
                            for call in compiler.call_args_list for value in call.args[0][1:]))


    def test_client_target_masks_apply_across_classes_and_mixed_blocks(self):
        import codec
        from sequence import compiled_program

        targeting = json.loads((REPOSITORY / 'projects/sim2gse/compatibility/spell-target-masks.json')
                               .read_text(encoding='utf-8'))
        cases = [(43265, True), (2120, True), (190356, True), (61882, True),
                 (73920, True), (5740, True), (1254851, False), (204475, False),
                 (206930, False), (2061, False), (26573, False)]
        for spell_id, is_ground in cases:
            with self.subTest(target_mask=spell_id):
                self.assertEqual(bool(targeting['target_masks'].get(str(spell_id), 0) & 64), is_ground)
        ground = dict(kind='spell', spell_id=43265, name='spell_43265', simc_action='spell_43265')
        normal = dict(kind='spell', spell_id=206930, name='spell_206930', simc_action='spell_206930')
        attack = dict(kind='start_attack', simc_action='auto_attack')
        item = dict(kind='item', slot=13, driver_spell_id=43265, simc_action='use_item,slot=trinket1')
        steps = [codec.prepare_block(block, targeting['target_masks'])[1]
                 for block in [[ground], [attack, ground], [normal], [attack, normal], [item]]]
        self.assertEqual(steps[0]['type'], 'macro')
        self.assertIn('[@player]', steps[1]['macrotext'])
        self.assertEqual(steps[2]['type'], 'spell')
        self.assertNotIn('[@player]', steps[3]['macrotext'])
        self.assertEqual(steps[4], dict(type='macro', macrotext='/use [@player] 13'))
        self.assertEqual(compiled_program(dict(compiled_steps=steps, blocks=[[ground], [attack, ground], [normal], [attack, normal], [item]])), [
            ['spell_43265'], ['auto_attack', 'spell_43265'],
            ['spell_206930'], ['auto_attack', 'spell_206930'], ['use_item,slot=trinket1'],
        ])

    def test_public_entry_rejects_output_override_before_writing(self) -> None:
        source = sample_profile() + "\noutput=forbidden.simc\n"
        with patch('result_store.ensure_available'), \
                patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'read_bytes', return_value=source.encode()), \
                patch.object(Path, 'mkdir') as mkdir, \
                patch.object(Path, 'write_bytes') as write_bytes, \
                patch.object(Path, 'write_text') as write_text, \
                self.assertRaises(TaskError) as raised:
            run_task(Path('/memory/中文角色.simc'), Path('/memory/task-output'), mode='single')
        self.assertIn('output', str(raised.exception))
        mkdir.assert_not_called()
        write_bytes.assert_not_called()
        write_text.assert_not_called()

    @pytest.mark.real
    def test_public_entry_preserves_real_character_and_bag_candidates(self) -> None:
        source = sample_profile()
        with tempfile.TemporaryDirectory(prefix="sim2gse-test-") as directory:
            input_path = Path(directory) / "中文 角色.simc"
            output_path = Path(directory) / "task-output"
            input_path.write_text(source, encoding="utf-8")
            from test_search import _fast_evaluate
            with patch('sequence.evaluate', side_effect=_fast_evaluate):
                result = run_task(input_path, output_path, mode="single")
            self.assertEqual(result['status'], 'offline_ready')
            from task import read_task
            self.assertEqual(read_task(output_path)['candidate']['text'], result['candidate']['text'])
            capabilities = result['capabilities']
            self.assertEqual(capabilities['scope'], 'default_apl_player_actions')
            self.assertEqual(capabilities['coverage'], 'combat_apl_buttons_with_baseline_forms')
            full_spell_ids = {a['spell_id'] for a in capabilities['actions'] if a['kind']=='spell'}
            self.assertTrue({43265, 207317} <= full_spell_ids)
            spell_ids = {a['spell_id'] for a in capabilities['baseline_actions'] if a['kind']=='spell'}
            self.assertTrue({42650,1233448,47541,55090} <= spell_ids)
            self.assertTrue(spell_ids.isdisjoint({47528,50977,255654,48743,221562,316239,46585}))
            self.assertEqual([a['simc_action'] for a in capabilities['precombat_actions']], ['raise_dead'])
            self.assertEqual(result['candidate']['compiled_steps'][0],
                             dict(type='macro', macrotext='/cast [nocombat] raise_dead'))
            selected = [row for row in capabilities['sources']
                        if row['status']=='mapped' and row['catalogue']=='baseline']
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
            (sample_profile() + "\noutput=forbidden.simc\n", "output"),
            (sample_profile() + "\ndeathknight=\"第二个\"\n", "只能包含一个角色"),
            (sample_profile().replace("race=highmountain_tauren", "race=high mountain"), "race"),
            (sample_profile() + "\ncopy=other-profile\n", "外部引用"),
            (sample_profile() + "\nactions=death_coil\n", "动作列表"),
        )
        for source, expected in cases:
            with self.subTest(source=source[-40:]), self.assertRaises(TaskError) as raised:
                parse_character(source)
            self.assertIn(expected, str(raised.exception))

    @pytest.mark.real
    def test_public_entry_simulates_native_channel_item(self):
        with tempfile.TemporaryDirectory(prefix='序列 饰品 ') as directory:
            source = Path(directory) / '角色.simc'
            text = (sample_profile().replace('highmountain_tauren', 'undead')
                    .replace('trinket1=,id=250245', 'trinket1=,id=270168,ilevel=311'))
            source.write_text(text, encoding='utf-8', newline='')
            destination = Path(directory) / '任务'
            result = run_task(source, destination, mode="single")
            self.assertEqual(result['status'], 'offline_ready')
            self.assertTrue((destination / 'reference').exists())
            from task import read_task
            self.assertEqual(read_task(destination)['candidate']['text'], result['candidate']['text'])
            self.assertTrue(result['controlled_simulation']['consistent'])
            self.assertIn(270168, {a['item_id'] for a in result['capabilities']['actions'] if a['kind']=='item'})

    @pytest.mark.real
    def test_native_catalogue_exports_both_active_items(self):
        from engine import reference, inspect
        from sequence import select
        from program import compile_program, from_action_blocks

        with tempfile.TemporaryDirectory(prefix='序列 双主动 ') as directory:
            folder = Path(directory)
            text = (sample_profile().replace('trinket1=,id=250245', 'trinket1=,id=202610,ilevel=311')
                    .replace('trinket2=,id=250228', 'trinket2=,id=219303,ilevel=311'))
            source = folder / 'input.simc'
            source.write_text(text, encoding='utf-8', newline='')
            native = reference(source, folder / 'reference', parse_character(text), iterations=2)
            capabilities = inspect(native, folder / 'capabilities')
            candidate = compile_program(from_action_blocks(select(capabilities)), folder / 'export',
                                        identity=native['identity'], capabilities=capabilities)
            self.assertEqual([a['slot'] for a in capabilities['actions'] if a['kind'] == 'item'], [13,14])
            self.assertIn(dict(type='item', item=13), candidate['compiled_steps'])
            self.assertIn(dict(type='macro', macrotext='/use [@player] 14'), candidate['compiled_steps'])


if __name__ == "__main__":
    unittest.main()
