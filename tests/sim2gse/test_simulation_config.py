"""Sim2GSE 本地模拟目标配置的公开接口检查。"""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest
import json
import sqlite3
import hashlib
import importlib.util
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request, urlopen


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from simulation_config import (  # noqa: E402
    DEFAULT_CONFIG,
    config_for,
    engine_options,
    load_config,
)


def _fast_search_config() -> dict:
    return {
        "total_budget_seconds": 30,
        "search_budget_seconds": 10,
        "candidate_limit": 2,
        "round_candidate_limit": 1,
        "batch_targets": (2,),
        "validation_batches": 1,
        "final_batches": 1,
        "iterations": 2,
        "final_iterations": 2,
        "scenarios": ("nominal",),
        "max_processes": 1,
    }


def _read_state(destination: Path) -> bytes:
    database = sqlite3.connect(destination / "task.sqlite3")
    try:
        return database.execute("SELECT value FROM state").fetchone()[0].encode("utf-8")
    finally:
        database.close()


class SimulationConfigTests(unittest.TestCase):
    def test_missing_config_uses_documented_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(Path(directory) / "missing.toml")

        self.assertEqual(config, DEFAULT_CONFIG)
        self.assertEqual(
            engine_options(config),
            [
                "enemy=Damage_Dummy",
                "level=90",
                "armor_coefficient=4531.03",
                "desired_targets=1",
            ],
        )

    def test_partial_config_inherits_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                '[simulation]\ntarget_name = "Raid_Boss"\ntarget_count = 3\n'
                'enable_omnium_talents = true\n',
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config["target_name"], "Raid_Boss")
        self.assertEqual(config["target_count"], 3)
        self.assertTrue(config["enable_omnium_talents"])
        self.assertEqual(config["target_level"], DEFAULT_CONFIG["target_level"])
        self.assertEqual(config["armor_coefficient"], DEFAULT_CONFIG["armor_coefficient"])

    def test_invalid_config_is_rejected(self) -> None:
        cases = (
            '[simulation]\ntarget_name = "not safe-name"\n',
            "[simulation]\ntarget_level = 0\n",
            "[simulation]\ntarget_count = 0\n",
            "[simulation]\narmor_coefficient = -1\n",
            "[simulation]\nunknown = true\n",
        )
        for text in cases:
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "config.toml"
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_config(path)

    def test_config_for_returns_a_valid_copy(self) -> None:
        config = config_for({"target_count": 2})

        self.assertEqual(config["target_count"], 2)
        self.assertEqual(config["target_name"], DEFAULT_CONFIG["target_name"])
        self.assertEqual(config_for()["target_count"], DEFAULT_CONFIG["target_count"])

    def test_task_entry_removes_only_valid_omnium_line_when_disabled(self) -> None:
        from task import run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        value = "136822:1/136819:1/136817:1"
        source_text = (sample_profile()
                       .replace('deathknight="中文 角色"',
                                'deathknight="omnium_talents=inside-name"')
                       + f"omnium_talents={value}\n"
                       + "# omnium_talents=comment\n")
        original = source_text.encode("utf-8")
        expected_effective = (source_text
                              .replace(f"omnium_talents={value}\n", "")
                              .encode("utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_bytes(original)
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=config_for({"enable_omnium_talents": False}))

            self.assertEqual((destination / "input.original.simc").read_bytes(), original)
            self.assertEqual((destination / "input.simc").read_bytes(), expected_effective)
            profile = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["identity"]["name"], "omnium_talents=inside-name")
            self.assertEqual(profile["fields"]["omnium_talents"], value)
            self.assertEqual(profile["input_original_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(profile["input_effective_sha256"], hashlib.sha256(expected_effective).hexdigest())
            state = json.loads(_read_state(destination))
            self.assertEqual(state["input_original_sha256"], profile["input_original_sha256"])
            self.assertEqual(state["input_effective_sha256"], profile["input_effective_sha256"])

    def test_task_entry_preserves_omnium_line_when_enabled(self) -> None:
        from task import run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        source_text = sample_profile() + "omnium_talents=136822:1/136819:1\n"
        original = source_text.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_bytes(original)
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=config_for({"enable_omnium_talents": True}))

            self.assertEqual((destination / "input.original.simc").read_bytes(), original)
            self.assertEqual((destination / "input.simc").read_bytes(), original)

    def test_omnium_switch_change_rejects_resume_before_simc_start(self) -> None:
        import task
        from task import TaskError, resume_task, run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        source_text = sample_profile() + "omnium_talents=136822:1/136819:1\n"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(source_text, encoding="utf-8")
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=config_for({"enable_omnium_talents": False}))

            with patch.object(task, "run_task", side_effect=AssertionError("SimC must not start")) as rerun:
                with self.assertRaisesRegex(TaskError, "恢复模拟配置"):
                    resume_task(destination,
                                simulation_config=config_for({"enable_omnium_talents": True}))
            rerun.assert_not_called()

    def test_baseline_and_controlled_engines_share_target_options(self) -> None:
        import engine

        config = config_for({
            "target_name": "Raid_Boss",
            "target_level": 91,
            "armor_coefficient": 5000,
            "target_count": 3,
        })
        commands = []

        def run_command(command, folder, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"", elapsed_seconds=0)

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "role.simc"
            profile.write_text("mage=test\nlevel=90\nspec=frost\n", encoding="utf-8")
            with patch.object(engine, "identity", return_value=(Path("simc.exe"), {})), \
                    patch.object(engine, "run_command", side_effect=run_command):
                engine.run(profile, Path(directory) / "baseline", "baseline", simulation_config=config)
                engine.run(profile, Path(directory) / "controlled", "controlled", simulation_config=config)

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
                "options": {"dbc": {"Live": {"build_level": 69587}, "version_used": "Live"}},
            }
        }

        simulation = config_for({"target_count": 2})
        engine.check_report(report, character, 100, simulation_config=simulation)
        with self.assertRaises(TypeError):
            engine.check_report(report, character, 100, target_count=2)

    def test_controlled_sequence_passes_the_effective_config_to_the_engine(self) -> None:
        import sequence

        config = config_for({"target_name": "Raid_Boss", "target_count": 2})
        observed = []
        report = {
            "sim": {
                "players": [{}, {}],
                "targets": [{}, {}],
                "statistics": {"raid_dps": {"mean": 100.0, "count": 1}},
            }
        }

        def fake_run(profile, folder, mode, options, *, runtime=None, simulation_config=None):
            observed.append(simulation_config)
            Path(folder, "native.pending.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            return "S2GBLOCK\t0\t0\toutbreak\n"

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "role.simc"
            profile.write_text("mage=test\nlevel=90\nspec=frost\n", encoding="utf-8")
            candidate = {
                "blocks": [[{"kind": "spell", "simc_action": "outbreak", "spell_id": 1,
                              "name": "outbreak"}]],
                "compiled_steps": [{"type": "spell", "spell": 1}],
                "precombat_count": 0,
            }
            with patch.object(sequence, "run", side_effect=fake_run), \
                    patch.object(sequence, "check_report", return_value={"dps": 100.0, "samples": 1}):
                sequence.evaluate(profile, candidate, Path(directory) / "run",
                                  character=SimpleNamespace(), trace=False,
                                  simulation_config=config)

        self.assertEqual(observed, [config])

    def test_task_records_effective_config_and_rejects_changed_resume(self) -> None:
        from task import TaskError, resume_task, run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        simulation = config_for({"target_name": "Raid_Boss", "target_count": 2})
        search = _fast_search_config()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                run_task(source, destination, search_config=search, simulation_config=simulation)

                state = json.loads(_read_state(destination))
                self.assertEqual(state["simulation_config"], simulation)
                profile = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    profile["input_original_sha256"],
                    hashlib.sha256(
                        (destination / "input.original.simc").read_bytes()
                    ).hexdigest(),
                )
                self.assertEqual(
                    profile["input_effective_sha256"],
                    hashlib.sha256(
                        (destination / "input.simc").read_bytes()
                    ).hexdigest(),
                )
                self.assertEqual(state["input_original_sha256"], profile["input_original_sha256"])
                self.assertEqual(state["input_effective_sha256"], profile["input_effective_sha256"])
                with self.assertRaisesRegex(TaskError, "恢复模拟配置"):
                    resume_task(destination,
                                simulation_config=dict(simulation, target_count=3))

    def test_same_custom_config_can_resume(self) -> None:
        from task import resume_task, run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        simulation = config_for({"target_name": "Raid_Boss", "target_count": 2})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=simulation)
                resumed = resume_task(destination, simulation_config=simulation)

        self.assertEqual(resumed["simulation_config"], simulation)

    def test_tampering_either_input_copy_rejects_without_state_or_result_change(self) -> None:
        from task import TaskError, resume_task, run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        simulation = config_for({"target_name": "Raid_Boss", "target_count": 2})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=simulation)
                state_before = _read_state(destination)
                result_before = (destination / "result.json").read_bytes()
                for name in ("input.original.simc", "input.simc"):
                    path = destination / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n# tampered\n")
                    try:
                        with self.assertRaisesRegex(TaskError, "输入"):
                            resume_task(destination, simulation_config=simulation)
                        self.assertEqual(_read_state(destination), state_before)
                        self.assertEqual((destination / "result.json").read_bytes(), result_before)
                    finally:
                        path.write_bytes(original)

    def test_tampered_input_is_rejected_before_task_store_construction(self) -> None:
        import search
        from task import TaskError, resume_task, run_task
        from test_character_export import sample_profile
        from test_search import _fast_search_boundary

        simulation = config_for({"target_name": "Raid_Boss", "target_count": 2})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                run_task(source, destination, search_config=_fast_search_config(),
                         simulation_config=simulation)
                before = {
                    name: path.read_bytes()
                    for name in ("profile.json", "result.json", "task.sqlite3")
                    if (path := destination / name).exists()
                }
                for name in ("input.original.simc", "input.simc"):
                    path = destination / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n# tampered\n")
                    try:
                        with patch.object(search, "TaskStore",
                                          side_effect=AssertionError("TaskStore must not open")) as store:
                            with self.assertRaisesRegex(TaskError, "输入"):
                                resume_task(destination, simulation_config=simulation)
                        store.assert_not_called()
                        self.assertEqual(
                            {name: (destination / name).read_bytes() for name in before},
                            before,
                        )
                    finally:
                        path.write_bytes(original)

    def test_http_task_entry_passes_the_startup_snapshot(self) -> None:
        import interface

        simulation = config_for({"target_name": "Raid_Boss", "target_count": 2})
        from test_character_export import sample_profile

        with tempfile.TemporaryDirectory() as directory:
            server = interface.create_server(
                Path(directory) / "output",
                port=0,
                task_options={"simulation_config": simulation},
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = json.dumps({"profile": sample_profile()}).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/tasks",
                    data=payload,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with patch.object(interface, "start_task",
                                  return_value=SimpleNamespace(done=True, error=None)) as start:
                    with urlopen(request, timeout=3) as response:
                        self.assertEqual(response.status, 202)
                    self.assertEqual(start.call_args.kwargs["simulation_config"], simulation)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_command_line_task_entry_loads_config_for_new_and_resume(self) -> None:
        import task

        simulation = config_for({"target_name": "Raid_Boss"})
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "role.simc"
            output_path = Path(directory) / "task"
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
        config = config_for({"target_name": "Raid_Boss"})
        with patch.object(module, "load_config", return_value=config), \
                patch.object(module, "serve") as serve, \
                patch.object(sys, "argv", [str(script), "--port", "0"]):
            self.assertEqual(module.main(), 0)

        serve.assert_called_once_with(
            REPOSITORY / ".local/sim2gse/ui-tasks",
            host="127.0.0.1",
            port=0,
            task_options={"simulation_config": config},
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
