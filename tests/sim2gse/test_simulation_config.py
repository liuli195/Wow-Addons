"""Sim2GSE 本地模拟目标配置的公开接口检查。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest
import json
import hashlib
import importlib.util
import threading
from types import SimpleNamespace
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from simulation_config import (  # noqa: E402
    DEFAULT_CONFIG,
    config_for,
    engine_options,
    load_config,
    load_training_config,
)


class SimulationConfigTests(unittest.TestCase):
    def test_training_section_is_independent_validated_and_bounded(self):
        path = BytesIO()
        expected = dict(max_processes=5, max_trainings=4, coarse_iterations=32,
            retest_batches=3, retest_iterations=128, stagnation_generations=2, top_k=8,
            tournament_size=3, crossover_probability=.8, mutation_probability=.8)
        self.assertEqual(load_training_config(BytesIO(path.getvalue())), expected)
        path = BytesIO(('[training]\nmax_trainings=10\nmax_processes=2').encode("utf-8"))
        self.assertEqual(load_training_config(BytesIO(path.getvalue())), dict(expected, max_processes=2, max_trainings=10))
        for outer, inner in ((11, 1), (10, 3)):
            with self.subTest(outer=outer, inner=inner):
                with self.assertRaises(ValueError):
                    load_training_config(BytesIO(path.getvalue()), max_trainings=outer, max_processes=inner)
        for value in (1, 16):
            path = BytesIO(('[simulation]\ntarget_count=5\n[training]\nmax_trainings=1\nmax_processes=' + str(value)).encode("utf-8"))
            self.assertEqual(load_config(BytesIO(path.getvalue()))['target_count'], 5)
            self.assertEqual(load_training_config(BytesIO(path.getvalue())), dict(expected, max_processes=value, max_trainings=1))
        for option in ('max_processes=0', 'max_processes=17', 'max_processes=true',
                       'max_processes=2.5', 'max_processes="4"', 'unknown=2',
                       'top_k=3', 'top_k=true', 'tournament_size=0', 'coarse_iterations=0',
                       'retest_batches=0', 'retest_iterations=true', 'stagnation_generations=0',
                       'crossover_probability=nan', 'mutation_probability=inf',
                       'mutation_probability=-0.1', 'crossover_probability=1.1'):
            path = BytesIO(('[training]\n' + option).encode("utf-8"))
            with self.subTest(option=option):
                self.assertEqual(load_config(BytesIO(path.getvalue())), DEFAULT_CONFIG)
                with self.assertRaises(ValueError):
                    load_training_config(BytesIO(path.getvalue()))

    def test_missing_config_uses_documented_defaults(self) -> None:
        with patch.object(Path, 'exists', return_value=False), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('missing config must not be read')):
            config = load_config(Path('missing.toml'))
        self.assertEqual(config, DEFAULT_CONFIG)
        self.assertTrue(config['enable_omnium_talents'])
        self.assertEqual(engine_options(config), ['desired_targets=1'])

    def test_partial_config_inherits_defaults(self) -> None:
        path = BytesIO(('[simulation]\ntarget_count = 3\n'
            'enable_omnium_talents = true\n').encode("utf-8"))

        config = load_config(BytesIO(path.getvalue()))

        self.assertEqual(config["target_count"], 3)
        self.assertTrue(config["enable_omnium_talents"])

    def test_invalid_config_is_rejected(self) -> None:
        cases = (
            "[simulation]\ntarget_count = 0\n",
            "[simulation]\nunknown = true\n",
        )
        for text in cases:
            with self.subTest(text=text):
                path = BytesIO()
                path = BytesIO((text).encode("utf-8"))
                with self.assertRaises(ValueError):
                    load_config(BytesIO(path.getvalue()))

    def test_config_for_returns_a_valid_copy(self) -> None:
        config = config_for({"target_count": 2})

        self.assertEqual(config["target_count"], 2)
        self.assertTrue(config["enable_omnium_talents"])
        self.assertEqual(config_for()["target_count"], DEFAULT_CONFIG["target_count"])


    def test_baseline_and_controlled_engines_share_target_options(self) -> None:
        import engine

        config = config_for({
            "target_count": 3,
        })
        commands = []

        def run_command(command, folder, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"", elapsed_seconds=0)

        profile = Path("unused-task") / "role.simc"
        with patch.object(Path, "mkdir"), patch.object(engine, "identity", return_value=(Path("simc.exe"), {})), \
                patch.object(engine, "run_command", side_effect=run_command):
            engine.run(profile, Path("unused-task") / "baseline", "baseline", simulation_config=config)
            engine.run(profile, Path("unused-task") / "controlled", "controlled", simulation_config=config)

        options = engine_options(config)
        target_prefixes = ("enemy=", "level=", "armor_coefficient=", "desired_targets=")
        self.assertEqual(
            [[arg for arg in command if arg.startswith(target_prefixes)] for command in commands],
            [options, options],
        )

    def test_report_target_count_can_follow_the_effective_config(self) -> None:
        import engine

        character = SimpleNamespace(
            name="角色",
            class_name="death_knight",
            level=90,
            race="scourge",
            spec_id=None,
            fields={"talents": "talents"},
            equipment={},
        )
        player = {
            "name": "角色",
            "sim2gse_class": "death_knight",
            "sim2gse_class_id": 6,
            "level": 90,
            "sim2gse_spec_id": 252,
            "sim2gse_spec": "unholy",
            "race": "scourge",
            "role": "attack",
            "sim2gse_resource": "runic_power",
            "talents": "talents",
            "collected_data": {"dps": {"mean": 100.0, "count": 99},
                               "fight_length": {"mean": 180}},
        }
        report = {
            "sim": {
                "players": [player],
                "targets": [{}, {}],
                "statistics": {"raid_dps": {"mean": 100.0, "count": 99}},
                "options": {"dbc": {"Live": {"build_level": 69587, "wow_version": "12.1.0.69587"}, "version_used": "Live"}},
            }
        }

        simulation = config_for({"target_count": 2})
        engine.check_report(report, character, 100, simulation_config=simulation)
        with self.assertRaises(TypeError):
            engine.check_report(report, character, 100, target_count=2)

    def test_controlled_sequence_passes_the_effective_config_to_the_engine(self) -> None:
        import sequence
        config = config_for({'target_count': 2})
        report = {'sim': {'players': [dict(name='test', sim2gse_class='mage', sim2gse_skipped_commands=[]),
                                      {'name': 'other'}], 'targets': [{}, {}],
                          'statistics': {'raid_dps': {'mean': 100.0, 'count': 1}}}}
        candidate = dict(blocks=[[dict(kind='spell', simc_action='outbreak', spell_id=1, name='outbreak')]],
                         compiled_steps=[dict(type='spell', spell=1)], precombat_count=0)
        with patch.object(sequence, 'run', return_value='S2GBLOCK\t0\t0\toutbreak\n') as run, \
                patch.object(sequence, 'check_report', return_value={'dps': 100.0, 'samples': 1}), \
                patch.object(Path, 'mkdir'), patch.object(Path, 'write_text'), \
                patch.object(Path, 'read_text', side_effect=['mage=test\nlevel=90\nspec=frost\n', json.dumps(report)]), \
                patch.object(sequence, 'replace_file'):
            sequence.evaluate(Path('role.simc'), candidate, Path('unused-run'),
                              character=SimpleNamespace(name='test', class_name='mage'), trace=False,
                              simulation_config=config)
        self.assertEqual(run.call_args.kwargs['simulation_config'], config)


    def test_tampered_input_is_rejected_before_task_store_construction(self) -> None:
        from contextlib import nullcontext
        import result_store
        import search
        import seed_activity
        import task

        destination = Path('/memory/tampered-input').resolve()
        original = b'original character\n'
        effective = b'effective character\n'
        profile = json.dumps(dict(input_original_sha256=hashlib.sha256(original).hexdigest(),
                                  input_effective_sha256=hashlib.sha256(effective).hexdigest()))
        for name, message in (("input.original.simc", "原始输入副本已变化"),
                              ("input.simc", "任务输入副本已变化")):
            with self.subTest(input=name):
                inputs = {destination / 'input.original.simc': original,
                          destination / 'input.simc': effective}
                inputs[destination / name] += b'# tampered\n'
                with patch.object(result_store, 'ensure_available'), \
                        patch.object(task, '_read_resume_checkpoint', return_value=dict(
                            formal_search_version=1, config=search.config_for())), \
                        patch.object(seed_activity, 'foreground_search', nullcontext), \
                        patch.object(task, '_task_lease', lambda *args: nullcontext()), \
                        patch.object(Path, 'read_text', autospec=True,
                                     side_effect=lambda path, **kwargs: {destination / 'profile.json': profile}[path]), \
                        patch.object(Path, 'read_bytes', autospec=True,
                                     side_effect=lambda path: inputs[path]), \
                        patch.object(search, 'TaskStore', side_effect=AssertionError('TaskStore must not open')) as store:
                    with self.assertRaisesRegex(task.TaskError, message):
                        task.resume_task(destination, search_timeline=False)
                    store.assert_not_called()


    def test_http_target_selection_keeps_startup_options_isolated(self) -> None:
        import interface
        from test_character_export import sample_profile
        from unittest.mock import Mock
        simulation = config_for({'target_count': 2, 'enable_omnium_talents': False})
        server = SimpleNamespace(task_options={'simulation_config': simulation},
            task_paths=Mock(return_value=(Path('input.simc'), Path('task'))),
            tasks_lock=threading.RLock(), tasks={})
        for selection in ({'target_count': 5}, {}, {'target_count': 1}):
            with self.subTest(selection=selection):
                payload = json.dumps({'profile': sample_profile(), **selection}).encode('utf-8')
                handler = object.__new__(interface.InterfaceHandler)
                handler.server = server
                handler.path = '/api/tasks'
                handler.headers = {'Host': 'localhost', 'Content-Length': str(len(payload))}
                handler.rfile = BytesIO(payload)
                handler.wfile = BytesIO()
                handler.request_version = 'HTTP/1.1'
                handler.requestline = 'POST /api/tasks HTTP/1.1'
                with patch.object(interface, 'start_task',
                                  return_value=SimpleNamespace(done=True, error=None)) as start, \
                        patch.object(Path, 'write_text'):
                    handler.do_POST()
                self.assertIn(b'202 Accepted', handler.wfile.getvalue())
                self.assertEqual(start.call_args.kwargs['simulation_config'],
                                 dict(simulation, target_count=selection.get('target_count', 1)))
                self.assertEqual(server.task_options['simulation_config'], simulation)
                self.assertEqual(simulation['target_count'], 2)

    def test_command_line_task_entry_loads_config_for_new_and_resume(self) -> None:
        import task

        simulation = config_for({"enable_omnium_talents": False})
        input_path = Path("unused-task") / "role.simc"
        output_path = Path("unused-task") / "task"
        with patch.object(task, "load_config", return_value=simulation), \
                patch.object(task, "run_task", return_value={"status": "completed"}) as run, \
                patch.object(sys, "argv", ["sim2gse-task", str(input_path), "--output", str(output_path)]):
            self.assertEqual(task.main(), 0)
        self.assertEqual(run.call_args.kwargs["simulation_config"], simulation)

        with patch.object(task, "load_config", return_value=simulation), \
                patch.object(task, "resume_task", return_value={"status": "completed"}) as resume, \
                patch.object(sys, "argv", ["sim2gse-task", "--resume", "--output", str(output_path)]):
            self.assertEqual(task.main(), 0)
        self.assertEqual(resume.call_args.kwargs["simulation_config"], simulation)

    def test_command_line_service_reads_config_once_at_startup(self) -> None:
        script = REPOSITORY / "scripts" / "dev" / "sim2gse" / "interface.py"
        spec = importlib.util.spec_from_file_location("sim2gse_service_entry", script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        config = config_for({"enable_omnium_talents": False})
        with patch.object(module, "load_config", return_value=config) as load, \
                patch.object(module, "serve") as serve, \
                patch.object(sys, "argv", [str(script), "--port", "0"]):
            self.assertEqual(module.main(), 0)

        load.assert_called_once_with()
        serve.assert_called_once_with(
            REPOSITORY / ".local/sim2gse/ui-tasks",
            host="127.0.0.1",
            port=0,
            task_options={"simulation_config": config,
                          "search_config": dict(diagnostic_logging=False, diagnostics="summary",
                                                search_observability="full", search_timeline=False)},
        )

    def test_invalid_service_config_stops_before_starting_server(self) -> None:
        script = REPOSITORY / "scripts" / "dev" / "sim2gse" / "interface.py"
        spec = importlib.util.spec_from_file_location("sim2gse_service_invalid", script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with patch.object(module, "load_config", side_effect=ValueError("配置无效")), \
                patch.object(module, "serve") as serve, \
                patch.object(sys, "argv", [str(script), "--port", "0"]):
            self.assertEqual(module.main(), 2)
        serve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
