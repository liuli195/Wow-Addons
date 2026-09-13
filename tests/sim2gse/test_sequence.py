"""第二票：同一公开任务入口的序列模拟行为检查。"""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest
import json
import copy
from collections import Counter

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from task import run_task, TaskError
from engine import run
from sequence import compiled_program, evaluate
from test_character_export import sample_profile


class SequenceSimulationTests(unittest.TestCase):
    def task(self, program, *, items=False, phase_ms=0):
        with tempfile.TemporaryDirectory(prefix='序列验证 ') as directory:
            source = Path(directory) / '角色.simc'
            text = sample_profile()
            if items:
                text = text.replace('trinket1=,id=250245', 'trinket1=,id=202610,ilevel=311')
                text = text.replace('trinket2=,id=250228', 'trinket2=,id=219303,ilevel=311')
            source.write_text(text, encoding='utf-8')
            return run_task(source, Path(directory) / '任务', program=program, phase_ms=phase_ms, mode='single')

    def test_public_entry_simulates_selected_single_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sim2gse-sequence ") as directory:
            source = Path(directory) / "中文 角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")

            result = run_task(source, destination, program=[["outbreak"]], mode='single')

            simulation = result["controlled_simulation"]
            self.assertEqual(simulation["blocks"], [["raise_dead"], ["outbreak"]])
            self.assertEqual(simulation["native_blocks"], [[], ["outbreak"]])
            self.assertTrue(simulation["consistent"])
            self.assertTrue(simulation["trace"])
            self.assertGreater(simulation["report"]["sim"]["players"][0]["collected_data"]["dps"]["mean"], 0)

    def test_single_evaluation_uses_interval_and_validates_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            result = run_task(source, Path(directory)/'valid', mode='single', program=[['outbreak']],
                              phase_ms=179, search_config={'input_interval_ms':180})
            simulation = result['controlled_simulation']
            self.assertEqual(simulation['input_times'], list(range(179,180000,180)))
            self.assertTrue(simulation['consistent'])
            with self.assertRaisesRegex(TaskError, '0 至 179'):
                run_task(source, Path(directory)/'invalid', mode='single', phase_ms=180,
                         search_config={'input_interval_ms':180})

    def test_failed_steps_and_queue_replacement(self):
        result = self.task([['outbreak'], ['death_coil'], ['scourge_strike']])
        events = result['controlled_simulation']['trace']
        self.assertTrue(any(e['event'] == 'not_ready' and e['action'] == 'death_coil' and e['ms'] == 600 for e in events))
        self.assertFalse(any(e['event'] == 'native_execute' and e['action'] == 'scourge_strike' and e['ms'] == 600 for e in events))
        self.assertTrue(any(e['event'] == 'replace' for e in events))
        self.assertTrue(all(e['cooldown_ms'] <= 0 for e in events if e['event'] == 'dispatch'))
        executed = [e for e in events if e['event'] == 'native_execute']
        dispatched = [e for e in events if e['event'] == 'dispatch']
        self.assertTrue(all(e['origin'] > 0 and e['step'] == (e['origin'] - 1) % 4
                            for e in dispatched + executed))
        self.assertEqual(Counter((e['battle'], e['origin'], e['signature'], e['ms']) for e in executed),
                         Counter((d['battle'], d['origin'], d['signature'], d['ms']) for d in dispatched))
        retained = self.task([['outbreak'], ['outbreak'], ['outbreak'], ['outbreak'], ['death_coil'], ['outbreak']])
        events = retained['controlled_simulation']['trace']
        queued = [e for e in events if e['event'] == 'queue']
        dispatched = [e for e in events if e['event'] == 'dispatch']
        failed_times = sorted({e['ms'] for e in events if e['event'] == 'not_ready'})
        self.assertTrue(any(q['origin'] == d['origin'] and any(q['ms'] < t < d['ms'] for t in failed_times)
                            for q in queued for d in dispatched))

    def test_cooldown_ending_inside_queue_window_executes_from_that_press(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            result = run_task(source, Path(directory) / 'task', mode='single',
                              program=[['putrefy']])
            simulation = evaluate(source, result['candidate'], Path(directory) / 'queue-window',
                                  character=result['character'], iterations=2,
                                  input_times=[0, 300, 1200, 1500, 29700, 30000])
            events = [e for e in simulation['trace'] if e['action'] == 'putrefy']
            self.assertTrue(any(e['event'] == 'queue' and e['ms'] == 30000
                                and e['cooldown_ms'] == 301 for e in events))
            self.assertTrue(any(e['event'] == 'native_execute' and e['ms'] == 30302
                                and e['origin'] == 6 for e in events))

    def test_press_during_cast_queues_the_ready_button_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.simc'
            source.write_text((REPOSITORY / 'tests/sim2gse/fixtures/devourer.simc').read_text(encoding='utf-8'),
                              encoding='utf-8')
            result = run_task(source, Path(directory) / 'task', mode='single', program=[['consume']])
            simulation = evaluate(source, result['candidate'], Path(directory) / 'cast-window',
                                  character=result['character'], iterations=2,
                                  input_times=[0, 100, 200, 300, 400, 1400])
            events = [e for e in simulation['trace'] if e['action'] in ('devour', 'consume')]
            self.assertTrue(any(e['event'] == 'not_ready' and e['action'] == 'devour'
                                and e['ms'] == 1400 for e in events))
            self.assertTrue(any(e['event'] == 'queue' and e['action'] == 'consume'
                                and e['ms'] == 1400 and e['origin'] == 6 for e in events))
            self.assertTrue(any(e['event'] == 'native_execute' and e['action'] == 'consume'
                                and e['ms'] == 3159 and e['origin'] == 6 for e in events))

    def test_same_block_item_order(self):
        first_actions = []
        for slots in [('trinket1',), ('trinket1', 'trinket2'), ('trinket2', 'trinket1')]:
            program = [[*[f'use_item,slot={s}' for s in slots], 'outbreak']]
            result = self.task(program, items=True)
            self.assertEqual(result['controlled_simulation']['blocks'], [['raise_dead'], *program])
            self.assertEqual(result['controlled_simulation']['native_blocks'], [[], *program])
            events = result['controlled_simulation']['trace']
            first_press = [e['action'] for e in events if e['event'] == 'native_execute' and e['ms'] == 300]
            self.assertTrue(first_press[0].startswith('use_item_'))
            self.assertEqual(first_press[1], 'outbreak')
            first_actions.append(first_press[0])
        self.assertEqual(first_actions[0], first_actions[1])
        self.assertNotEqual(first_actions[1], first_actions[2])

    def test_phase_reset_and_replay(self):
        program = [['outbreak'], ['scourge_strike']]
        first = self.task(program, phase_ms=150)['controlled_simulation']
        second = self.task(program, phase_ms=150)['controlled_simulation']
        inputs = [e for e in first['trace'] if e['event'] == 'input']
        self.assertEqual(inputs[0]['ms'], 150)
        self.assertTrue(all(e['step'] == 0 and e['ms'] == 150 for e in inputs if e['origin'] == 1))
        self.assertEqual(first['trace'], second['trace'])
        self.assertEqual(first['report']['sim']['players'], second['report']['sim']['players'])
        self.assertEqual(first['summary']['samples'], 99)

    def test_disabled_controller_matches_original(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.simc'
            source.write_text(sample_profile(), encoding='utf-8')
            result = run_task(source, Path(directory) / 'task', program=[['outbreak']], mode='single')
            run(source, Path(directory) / 'disabled', 'controlled')
            original = json.loads((Path(directory) / 'task/reference/native.json').read_text(encoding='utf-8'))
            disabled = json.loads((Path(directory) / 'disabled/native.json').read_text(encoding='utf-8'))
            self.assertEqual(original['sim']['players'], disabled['sim']['players'])
            altered = copy.deepcopy(result['candidate'])
            altered['compiled_steps'][altered['precombat_count']]['spell'] = 999999
            with self.assertRaises((ValueError, KeyError)):
                compiled_program(altered)
            with self.assertRaisesRegex(ValueError, '原版引擎不兼容'):
                evaluate(source, result['candidate'], Path(directory) / 'wrong', character=result['character'], mode='baseline')

    def test_two_gcd_commands_rejected_at_task_entry(self):
        with self.assertRaisesRegex(TaskError, '同块多个公共冷却'):
            self.task([['outbreak', 'scourge_strike']])

    def test_overlong_compiled_macro_rejected(self):
        with self.assertRaisesRegex(TaskError, '255'):
            self.task([['dark_transformation'] * 16])


if __name__ == "__main__":
    unittest.main()
