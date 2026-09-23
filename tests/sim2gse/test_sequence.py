"""第二票：同一公开任务入口的序列模拟行为检查。"""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest
import json
import copy
from collections import Counter
from dataclasses import replace
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from task import run_task, TaskError, parse_character
from engine import run, reference, inspect
from codec import export
from sequence import compiled_program, evaluate, select
from test_character_export import sample_profile


class SequenceSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='sim2gse-sequence-shared-')
        cls.prepared = cls.prepare(sample_profile(), Path(cls.directory.name) / 'default')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def prepare(text, root):
        root.mkdir(parents=True, exist_ok=True)
        source = root / 'input.simc'
        source.write_text(text, encoding='utf-8')
        character = parse_character(text)
        native = reference(source, root / 'reference', character)
        character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        return source, character, native, inspect(native, root / 'capabilities')

    def candidate(self, prepared, program):
        source, character, native, capabilities = prepared
        folder = Path(tempfile.mkdtemp(prefix='candidate-', dir=self.directory.name))
        return export(select(capabilities, program), folder, identity=native['identity']), source, character

    def task(self, program, *, phase_ms=0, iterations=3):
        candidate, source, character = self.candidate(self.prepared, program)
        folder = Path(tempfile.mkdtemp(prefix='controlled-', dir=self.directory.name))
        controlled = evaluate(source, candidate, folder, character=character,
                              iterations=iterations, input_times=list(range(phase_ms, 180000, 300)))
        return {'candidate': candidate, 'character': character,
                'controlled_simulation': controlled}

    def task_entry(self, program):
        destination = Path(tempfile.mkdtemp(prefix='entry-', dir=self.directory.name)) / 'task'
        with patch('engine.reference', return_value=self.prepared[2]), \
                patch('engine.inspect', return_value=self.prepared[3]):
            return run_task(self.prepared[0], destination, program=program, mode='single')

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

    def test_real_timeline_preserves_first_precombat_gcd(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['outbreak']])
            simulation = evaluate(source, candidate, Path(directory) / 'precombat-gcd',
                                  character=character, iterations=2,
                                  input_times=[0, 214, 844, 1052])
            executed = [e for e in simulation['trace']
                        if e['event'] == 'native_execute' and e['action'] == 'outbreak']
            self.assertFalse(any(e['ms'] == 214 for e in executed))
            self.assertTrue(any(e['ms'] >= 1270 and e['origin'] == 4 for e in executed), executed)

    def test_failed_steps_and_queue_replacement(self):
        result = self.task([['outbreak'], ['death_coil'], ['scourge_strike']])
        events = result['controlled_simulation']['trace']
        self.assertTrue(any(e['event'] == 'not_ready' and e['action'] == 'death_coil' and e['ms'] == 600 for e in events))
        self.assertFalse(any(e['event'] == 'native_execute' and e['action'] == 'scourge_strike' and e['ms'] == 600 for e in events))
        self.assertTrue(any(e['event'] == 'queue_commit' for e in events))
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
            candidate, source, character = self.candidate(self.prepared, [['putrefy']])
            simulation = evaluate(source, candidate, Path(directory) / 'queue-window',
                                  character=character, iterations=2,
                                  input_times=[0, 300, 1200, 1500, 2900, 3000, 31100, 31200])
            events = [e for e in simulation['trace'] if e['action'] == 'putrefy']
            self.assertTrue(any(e['event'] == 'queue' and e['ms'] == 31200
                                and e['cooldown_ms'] == 301 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['ms'] >= 31501
                                and e['origin'] == 8 for e in events))

    def test_pending_queue_can_be_replaced_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['scourge_strike'], ['putrefy']])
            simulation = evaluate(source, candidate, Path(directory) / 'queue-replace',
                                  character=character, iterations=2,
                                  input_times=[0, 1050, 1120, 1445])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'replace' and e['action'] == 'putrefy'
                                and e['origin'] == 2 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_commit' and e['action'] == 'scourge_strike'
                                and e['origin'] == 3 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_locked' and e['action'] == 'putrefy'
                                and e['origin'] == 4 for e in events), events)

    def test_tc_queue_rejects_early_request_and_replaces_pending_request(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['outbreak'], ['scourge_strike'], ['putrefy'], ['outbreak']])
            simulation = evaluate(source, candidate, Path(directory) / 'tc-queue',
                                  character=character, iterations=1,
                                  input_times=[0, 100, 500, 1050, 1100, 1200],
                                  mode='tc')
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'tc_reject' and e['action'] == 'scourge_strike'
                                and e['origin'] == 3 for e in events), events)
            self.assertTrue(any(e['event'] == 'tc_replace' and e['action'] == 'putrefy'
                                and e['origin'] == 4 for e in events), events)
            self.assertTrue(any(e['event'] == 'tc_execute_attempt' and e['action'] == 'outbreak'
                                and e['origin'] == 5 and e['ms'] > 1100 for e in events), events)
            self.assertFalse(any(e['event'] == 'queue_commit' for e in events), events)

    def test_tc_pending_waits_for_default_server_update_check(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['outbreak'], ['scourge_strike'], ['putrefy'], ['outbreak']])
            simulation = evaluate(source, candidate, Path(directory) / 'tc-update',
                                  character=character, iterations=1,
                                  input_times=[0, 100, 500, 1050, 1100, 1200, 1445],
                                  mode='tc')
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'tc_replace' and e['origin'] == 5
                                and e['ms'] == 1445 for e in events), events)
            self.assertFalse(any(e['event'] == 'native_execute' and e['origin'] == 5
                                 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 7
                                for e in events), events)

    def test_tc_queue_checks_resource_at_execution_not_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['death_coil'], ['outbreak']])
            simulation = evaluate(source, candidate, Path(directory) / 'tc-resource',
                                  character=character, iterations=1,
                                  input_times=[0, 1500, 1600],
                                  mode='tc')
            events = [e for e in simulation['trace'] if e['action'] == 'death_coil' and e['origin'] == 2]
            self.assertTrue(any(e['event'] == 'tc_queue' for e in events), events)
            self.assertTrue(any(e['event'] == 'tc_execute_attempt' for e in events), events)
            self.assertTrue(any(e['event'] == 'dispatch_failed' for e in events), events)

    def test_tc_queue_checks_skill_cooldown_at_execution_not_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['army_of_the_dead']])
            simulation = evaluate(source, candidate, Path(directory) / 'tc-cooldown',
                                  character=character, iterations=1,
                                  input_times=[0, 1500, 2900, 3000], mode='tc')
            events = [e for e in simulation['trace'] if e['action'] == 'army_of_the_dead']
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 2 for e in events), events)
            final = [e for e in events if e['origin'] == 4]
            self.assertTrue(any(e['event'] == 'tc_queue' and e['cooldown_ms'] > 0 for e in final), events)
            self.assertTrue(any(e['event'] == 'tc_execute_attempt' for e in final), events)
            self.assertTrue(any(e['event'] == 'dispatch_failed' for e in final), events)

    def test_tc_mode_rejects_observed_combat_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['outbreak']])
            for feedback in (dict(gcd_states=[(0, 1270)]),
                             dict(failed_actions=[None]),
                             dict(failure_events=[])):
                with self.subTest(feedback=feedback), self.assertRaisesRegex(ValueError, '只接受按键时刻'):
                    evaluate(source, candidate, Path(directory) / 'tc-feedback',
                             character=character, iterations=1, input_times=[0],
                             mode='tc', **feedback)

    def test_precombat_cast_blocks_early_combat_action(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = self.prepare(
                (REPOSITORY / 'tests/sim2gse/fixtures/devourer.simc').read_text(encoding='utf-8'),
                Path(directory) / 'prepared')
            candidate, source, character = self.candidate(prepared, [['consume']])
            simulation = evaluate(source, candidate, Path(directory) / 'precombat-cast',
                                  character=character, iterations=2,
                                  input_times=[0, 100, 1400])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'precombat_cast' for e in events), events)
            self.assertFalse(any(e['event'] == 'native_execute' and e['action'] == 'consume'
                                 and e['ms'] < 1479 for e in events), events)

    def test_queue_locks_before_gcd_ready_and_executes_at_native_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['scourge_strike'], ['putrefy'], ['soul_reaper'], ['scourge_strike']])
            simulation = evaluate(source, candidate, Path(directory) / 'queue-commit',
                                  character=character, iterations=2,
                                  input_times=[0, 1450, 2500, 2800, 2850, 3800, 3850])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_commit' and e['action'] == 'putrefy'
                                and e['origin'] == 3 for e in events), events)
            self.assertFalse(any(e['event'] == 'replace' and e['action'] == 'putrefy'
                                 and e['origin'] == 3 for e in events))
            self.assertTrue(any(e['event'] == 'queue_locked' and e['action'] == 'soul_reaper'
                                and e['origin'] == 4 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_locked' and e['action'] == 'scourge_strike'
                                and e['origin'] == 5 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['action'] == 'putrefy'
                                and e['origin'] == 3 and e['ms'] >= 2892 for e in events), events)
            self.assertTrue(any(e['event'] == 'outside_window' and e['action'] == 'scourge_strike'
                                and e['origin'] == 7 and e['ms'] == 3850 for e in events), events)

    def test_repeated_queue_commits_do_not_accumulate_clock_lead(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['scourge_strike']])
            simulation = evaluate(source, candidate, Path(directory) / 'clock-lead',
                                  character=character, iterations=2,
                                  input_times=list(range(0, 9000, 70)))
            commits = [e for e in simulation['trace'] if e['event'] == 'queue_commit'
                       and e['gcd'] > e['ms']]
            self.assertGreaterEqual(len(commits), 3)
            self.assertLessEqual(max(e['gcd'] - e['ms'] for e in commits), 150)

    def test_observed_gcd_transition_commits_previous_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-feedback',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270],
                gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                            (1270, 1200), (1270, 1200)])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['action'] == 'putrefy'
                                and e['origin'] == 2 and e['ms'] == 1120 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_locked' and e['action'] == 'soul_reaper'
                                and e['origin'] == 3 and e['ms'] == 1120 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_confirm' and e['action'] == 'putrefy'
                                and e['origin'] == 2 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['action'] == 'putrefy'
                                and e['origin'] == 2 and 1442 <= e['ms'] < 1460 for e in events), events)

    def test_observed_gcd_transition_rolls_back_when_snapshot_reverts(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-feedback-rollback',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270, 1500, 1700],
                gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                            (1270, 1200), (0, 1270), (1500, 1200),
                            (1700, 1200)])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['action'] == 'putrefy'
                                and e['origin'] == 2 and e['ms'] == 1120 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_rollback' and e['action'] == 'putrefy'
                                and e['origin'] == 2 and e['ms'] == 1270 for e in events), events)
            self.assertFalse(any(e['event'] == 'native_execute' and e['action'] == 'putrefy'
                                 and e['origin'] == 2 for e in events), events)

    def test_empty_gcd_snapshot_does_not_lock_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-feedback-empty',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270, 1340, 1410],
                gcd_states=[(0, 1270), (0, 1270), (0, 0),
                            (0, 0), (1270, 1200), (1270, 1200), (1270, 1200)])
            events = simulation['trace']
            self.assertFalse(any(e['event'] == 'queue_tentative' and e['ms'] in (1120, 1200)
                                 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['action'] == 'putrefy'
                                and e['origin'] == 2 and e['ms'] == 1270 for e in events), events)

    def test_empty_gcd_snapshot_keeps_last_known_cooldown_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-feedback-empty-ready',
                character=character, iterations=2,
                input_times=[0, 300, 600, 1050, 1120, 1200, 1270, 1340],
                gcd_states=[(0, 1270), (0, 0), (0, 0),
                            (0, 1270), (1270, 1200), (1270, 1200),
                            (1270, 1200), (1270, 1200)])
            events = simulation['trace']
            self.assertFalse(any(e['event'] == 'queue' and e['ms'] in (300, 600)
                                 for e in events), events)

    def test_transient_gcd_reversion_rolls_back_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-feedback-late-reversion',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1500],
                gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                            (1270, 1200), (0, 1270)])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_rollback' and e['origin'] == 2
                                for e in events), events)
            self.assertFalse(any(e['event'] == 'native_execute' and e['origin'] == 2
                                 for e in events), events)

    def test_same_gcd_start_with_updated_duration_keeps_tentative_action(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'gcd-duration-update',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270, 1500],
                gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                            (1270, 750), (1270, 750), (1270, 750)])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['origin'] == 2
                                for e in events), events)
            self.assertFalse(any(e['event'] == 'queue_rollback' and e['origin'] == 2
                                 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 2
                                for e in events), events)

    def test_failure_feedback_is_not_visible_before_its_event_time(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            kwargs = dict(character=character, iterations=2,
                          input_times=[0, 1050, 1120, 1200, 1270, 1500],
                          gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                                      (1270, 1200), (1270, 1200), (1270, 1200)])
            baseline = evaluate(source, candidate, Path(directory) / 'without-failure', **kwargs)
            with_failure = evaluate(
                source, candidate, Path(directory) / 'timed-failure',
                failure_events=[(1300, 2, 'putrefy')], **kwargs)
            self.assertEqual(with_failure['failure_events'], [(1300, 2, 'putrefy')])
            prefix = lambda result: [(e['ms'], e['event'], e['origin'], e['action'])
                                     for e in result['trace'] if e['ms'] < 1300]
            self.assertEqual(prefix(baseline), prefix(with_failure))
            events = with_failure['trace']
            self.assertTrue(any(e['event'] == 'observed_failed' and e['ms'] == 1300
                                and e['origin'] == 2 for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_rollback' and e['origin'] == 2
                                for e in events), events)
            self.assertFalse(any(e['event'] == 'native_execute' and e['origin'] == 2
                                 for e in events), events)

    def test_failure_at_click_timestamp_follows_that_click(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['putrefy'], ['auto_attack']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'same-timestamp-failure',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1270, 1500],
                gcd_states=[(0, 1270)] * 3 + [(1270, 1200)] * 2,
                failure_events=[(1050, 2, 'putrefy')])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue' and e['origin'] == 2
                                and e['ms'] == 1050 for e in events), events)
            self.assertTrue(any(e['event'] == 'observed_failed' and e['origin'] == 2
                                and e['action'] == 'putrefy' and e['ms'] == 1050
                                for e in events), events)
            queued = next(i for i, e in enumerate(events) if e['event'] == 'queue'
                          and e['origin'] == 2)
            failed = next(i for i, e in enumerate(events) if e['event'] == 'observed_failed'
                          and e['origin'] == 2 and e['action'] == 'putrefy')
            self.assertLess(queued, failed)

    def test_timed_feedback_mode_does_not_depend_on_future_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['dark_transformation']])
            kwargs = dict(character=character, iterations=2,
                          input_times=[0, 1500, 1600, 9000])
            no_failures = evaluate(source, candidate, Path(directory) / 'no-failures',
                                   failure_events=[], **kwargs)
            distant_failure = evaluate(source, candidate, Path(directory) / 'distant-failure',
                                       failure_events=[(9000, 4, 'dark_transformation')], **kwargs)
            prefix = lambda result: [(e['ms'], e['event'], e['origin'], e['action'])
                                     for e in result['trace'] if e['ms'] < 9000]
            self.assertEqual(prefix(no_failures), prefix(distant_failure))

    def test_unrelated_failure_with_same_origin_is_not_late_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'unrelated-failure',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270, 1500],
                gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                            (1270, 1200), (1270, 1200), (1270, 1200)],
                failure_events=[(1500, 2, 'soul_reaper')])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 2
                                and e['action'] == 'putrefy' for e in events), events)
            self.assertFalse(any(e['event'] == 'late_negative_feedback' for e in events), events)

    def test_executed_identity_survives_next_gcd_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper']])
            output = Path(directory) / 'late-failure-after-next-gcd'
            with self.assertRaisesRegex(ValueError, '已执行后收到否定反馈'):
                evaluate(
                    source, candidate, output,
                    character=character, iterations=2,
                    input_times=[0, 1050, 1120, 1200, 1270, 1500, 2500],
                    gcd_states=[(0, 1270), (0, 1270), (1270, 1200),
                                (1270, 1200), (1270, 1200), (1270, 1200),
                                (2500, 1200)],
                    failure_events=[(3000, 2, 'putrefy')])
            events = [line.split('S2GSE\t', 1)[1].split('\t')
                      for line in (output / 'native.txt').read_text(encoding='utf-8').splitlines()
                      if 'S2GSE\t' in line]
            self.assertTrue(any(e[1] == 'native_execute' and e[2] == '2'
                                and e[4] == 'putrefy' for e in events))
            self.assertTrue(any(e[1] == 'input' and e[0] == '2500' for e in events))
            self.assertTrue(any(e[1] == 'late_negative_feedback' and e[0] == '3000'
                                and e[2] == '2' for e in events))

    def test_immediate_failure_cancels_deferred_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['dark_transformation'], ['outbreak']])
            for failure_at in (1501, 1502):
                with self.subTest(failure_at=failure_at):
                    simulation = evaluate(
                        source, candidate, Path(directory) / f'immediate-rejection-{failure_at}',
                        character=character, iterations=2,
                        input_times=[0, 1500, 1600],
                        failure_events=[(failure_at, 2, 'dark_transformation')])
                    events = simulation['trace']
                    self.assertTrue(any(e['event'] == 'observed_failed' and e['ms'] == failure_at
                                        and e['origin'] == 2 for e in events), events)
                    self.assertFalse(any(e['event'] == 'native_execute' and e['origin'] == 2
                                         for e in events), events)
                    self.assertFalse(any(e['event'] == 'late_negative_feedback' for e in events), events)

    def test_long_delayed_failure_is_not_hidden_by_execution_grace(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['dark_transformation']])
            output = Path(directory) / 'late-rejection'
            with self.assertRaisesRegex(ValueError, '已执行后收到否定反馈'):
                evaluate(source, candidate, output, character=character, iterations=2,
                         input_times=[0, 1500],
                         failure_events=[(1550, 2, 'dark_transformation')])
            events = [line.split('S2GSE\t', 1)[1].split('\t')
                      for line in (output / 'native.txt').read_text(encoding='utf-8').splitlines()
                      if 'S2GSE\t' in line]
            self.assertTrue(any(e[1] == 'native_execute' and e[2] == '2'
                                and int(e[0]) < 1550 for e in events))
            self.assertTrue(any(e[1] == 'late_negative_feedback' and e[2] == '2'
                                and e[0] == '1550' for e in events))

    def test_failed_replacements_restore_earlier_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['soul_reaper'], ['putrefy']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'failed-replacements',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1200, 1270, 1340, 1410, 1500],
                gcd_states=[(0, 1270), (0, 1270), (0, 1270), (0, 1270),
                            (1270, 1200), (1270, 1200), (1270, 1200), (1270, 1200)],
                failure_events=[(1250, 3, 'soul_reaper'), (1250, 4, 'putrefy')])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['origin'] == 2
                                for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 2
                                for e in events), events)

    def test_failed_tentative_winner_promotes_earlier_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['putrefy']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'failed-tentative-winner',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1270, 1340, 1410, 1500],
                gcd_states=[(0, 1270), (0, 1270), (0, 1270),
                            (1270, 1200), (1270, 1200), (1270, 1200), (1270, 1200)],
                failure_events=[(1300, 3, 'putrefy')])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'queue_restore' and e['origin'] == 2
                                for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['origin'] == 2
                                for e in events), events)

    def test_matching_failure_feedback_does_not_replace_pending_action(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(
                self.prepared, [['putrefy'], ['putrefy']])
            simulation = evaluate(
                source, candidate, Path(directory) / 'failed-feedback',
                character=character, iterations=2,
                input_times=[0, 1050, 1120, 1270, 1340, 1410],
                gcd_states=[(0, 1270), (0, 1270), (0, 1270),
                            (1270, 1200), (1270, 1200), (1270, 1200)],
                failed_actions=[None, None, 'putrefy', None, None, None])
            events = simulation['trace']
            self.assertTrue(any(e['event'] == 'observed_failed' and e['origin'] == 3
                                for e in events), events)
            self.assertTrue(any(e['event'] == 'queue_tentative' and e['origin'] == 2
                                and e['ms'] == 1270 for e in events), events)
            self.assertFalse(any(e['event'] == 'queue_tentative' and e['origin'] == 3
                                 for e in events), events)

    def test_press_during_cast_queues_the_ready_button_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = self.prepare(
                (REPOSITORY / 'tests/sim2gse/fixtures/devourer.simc').read_text(encoding='utf-8'),
                Path(directory) / 'prepared')
            candidate, source, character = self.candidate(prepared, [['consume']])
            simulation = evaluate(source, candidate, Path(directory) / 'cast-window',
                                  character=character, iterations=2,
                                  input_times=[0, 100, 200, 300, 400, 1400])
            events = [e for e in simulation['trace'] if e['action'] in ('devour', 'consume')]
            self.assertTrue(any(e['event'] == 'not_ready' and e['action'] == 'devour'
                                and e['ms'] == 1400 for e in events))
            self.assertTrue(any(e['event'] == 'queue' and e['action'] == 'consume'
                                and e['ms'] == 1400 and e['origin'] == 6 for e in events), events)
            self.assertTrue(any(e['event'] == 'native_execute' and e['action'] == 'consume'
                                and e['ms'] >= 2959 and e['origin'] == 6 for e in events), events)

    def test_same_block_item_order(self):
        first_actions = []
        text = sample_profile().replace('trinket1=,id=250245', 'trinket1=,id=202610,ilevel=311')
        text = text.replace('trinket2=,id=250228', 'trinket2=,id=219303,ilevel=311')
        prepared = self.prepare(text, Path(tempfile.mkdtemp(prefix='items-', dir=self.directory.name)))
        for slots in [('trinket1',), ('trinket1', 'trinket2'), ('trinket2', 'trinket1')]:
            program = [[*[f'use_item,slot={s}' for s in slots], 'outbreak']]
            candidate, source, character = self.candidate(prepared, program)
            controlled = evaluate(source, candidate,
                                  Path(tempfile.mkdtemp(prefix='items-controlled-', dir=self.directory.name)),
                                  character=character, iterations=2)
            result = {'candidate': candidate, 'controlled_simulation': controlled}
            self.assertEqual(result['controlled_simulation']['blocks'], [['raise_dead'], *program])
            self.assertEqual(result['controlled_simulation']['native_blocks'], [[], *program])
            events = result['controlled_simulation']['trace']
            first_press = [e['action'] for e in events if e['event'] == 'native_execute' and e['ms'] == 300]
            self.assertTrue(first_press[0].startswith('use_item_'))
            self.assertTrue(any(e['event'] == 'native_execute' and e['action'] == 'outbreak'
                                and e['ms'] >= 1500 for e in events))
            first_actions.append(first_press[0])
        self.assertEqual(first_actions[0], first_actions[1])
        self.assertNotEqual(first_actions[1], first_actions[2])

    def test_phase_reset_and_replay(self):
        program = [['outbreak'], ['scourge_strike']]
        first = self.task(program, phase_ms=150, iterations=100)['controlled_simulation']
        second = self.task(program, phase_ms=150, iterations=100)['controlled_simulation']
        inputs = [e for e in first['trace'] if e['event'] == 'input']
        self.assertEqual(inputs[0]['ms'], 150)
        self.assertTrue(all(e['step'] == 0 and e['ms'] == 150 for e in inputs if e['origin'] == 1))
        self.assertEqual(first['trace'], second['trace'])
        self.assertEqual(first['report']['sim']['players'], second['report']['sim']['players'])
        self.assertEqual(first['summary']['samples'], 99)

    def test_disabled_controller_matches_original(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, source, character = self.candidate(self.prepared, [['outbreak']])
            run(source, Path(directory) / 'disabled', 'controlled')
            original = json.loads((Path(self.directory.name) / 'default/reference/native.json').read_text(encoding='utf-8'))
            disabled = json.loads((Path(directory) / 'disabled/native.json').read_text(encoding='utf-8'))
            self.assertEqual(original['sim']['players'], disabled['sim']['players'])
            altered = copy.deepcopy(candidate)
            altered['compiled_steps'][altered['precombat_count']]['spell'] = 999999
            with self.assertRaises((ValueError, KeyError)):
                compiled_program(altered)
            with self.assertRaisesRegex(ValueError, '原版引擎不兼容'):
                evaluate(source, candidate, Path(directory) / 'wrong', character=character, mode='baseline')

    def test_two_gcd_commands_rejected_at_task_entry(self):
        with self.assertRaisesRegex(TaskError, '同块多个公共冷却'):
            self.task_entry([['outbreak', 'scourge_strike']])

    def test_overlong_compiled_macro_rejected(self):
        with self.assertRaisesRegex(TaskError, '255'):
            self.task_entry([['dark_transformation'] * 16])


if __name__ == "__main__":
    unittest.main()
