"""通过产品 CLI 与 HTTP 入口验证受管任务；只用临时合成数据。"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from unittest.mock import patch
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA_CLI = ROOT / ".agents/skills/sim2gse-data/scripts/simdata.py"
sys.path.insert(0, str(ROOT / "projects/sim2gse"))
sys.path.insert(0, str(ROOT / "tests/sim2gse"))

# 云端诊断仅替换 Windows 锁的 OS 边界，不改变生产入口的平台支持。
if os.name != "nt":
    import fcntl
    def locking(fd, mode, size):
        fcntl.lockf(fd, fcntl.LOCK_UN if mode == 0 else fcntl.LOCK_EX | fcntl.LOCK_NB, size)
    sys.modules["msvcrt"] = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=0, locking=locking)
try:
    import task
    import codec
    import search
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
finally:
    if os.name != "nt":
        sys.modules.pop("msvcrt", None)


class ManagedTaskTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="managed-product-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.root = self.directory / "data"
        self.config = self.directory / "data.json"
        policy = json.loads((DATA_CLI.parents[1] / "assets/config.default.json").read_text())
        policy.update(mode="test", root_id=str(uuid.uuid4()), data_root=str(self.root),
                      lease_seconds=30, archive_part_bytes=1048576)
        self.config.write_text(json.dumps(policy), encoding="utf-8")
        plan = self.data("init-root")
        self.data("init-root", "--approve-hash", plan["plan_hash"])
        self.source = self.directory / "role.simc"
        self.source.write_text(sample_profile(), encoding="utf-8")
        self.destination = self.root / "original-output" / "task"

    def data(self, *arguments):
        result = subprocess.run([sys.executable, "-B", str(DATA_CLI), *arguments,
                                 "--config", str(self.config)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def cli(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["task.py", *map(str, arguments)]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            try:
                code = task.main()
            except SystemExit as raised:
                code = raised.code
        return code, output.getvalue(), error.getvalue()

    @contextlib.contextmanager
    def producer(self):
        read = Path.read_bytes
        target = ROOT / "projects/sim2gse/compatibility/spell-target-masks.json"
        def native_fixture(path):
            data = read(path)
            # 兼容锁记录 Windows 检出字节；云端仅模拟该既有文件的行尾。
            return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") if path == target and os.name != "nt" else data
        config = dict(total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
                      batch_targets=(2,), iterations=2, validation_batches=1, final_batches=1,
                      final_iterations=2, scenarios=("nominal",), max_processes=1, random_seed=37)
        with _fast_search_boundary(), patch.dict(search.DEFAULT_CONFIG, config), \
                patch.object(codec, "LUA", Path(sys.executable)), \
                patch.object(Path, "read_bytes", native_fixture):
            yield

    def test_cli_rejects_missing_task_reservation_before_creating_output(self):
        code, _, error = self.cli(self.source, "--output", self.destination,
                                  "--data-config", self.config)
        self.assertEqual(code, 2)
        self.assertIn("预留", error)
        self.assertFalse(self.destination.exists())

    def test_cli_does_not_fall_back_or_allocate_when_admission_fails(self):
        for arguments in ((), ("--data-config", self.config, "--reserve-bytes", 2**63 - 1)):
            with self.subTest(arguments=arguments):
                code, _, error = self.cli(self.source, "--output", self.destination, *arguments)
                self.assertEqual(code, 2, error)
                self.assertFalse(self.destination.exists())

    def test_explicitly_disabled_policy_preserves_unmanaged_cli(self):
        disabled = self.directory / "disabled.json"
        disabled.write_bytes((DATA_CLI.parents[1] / "assets/config.default.json").read_bytes())
        destination = self.directory / "unmanaged"
        with self.producer():
            code, output, error = self.cli(self.source, "--output", destination, "--data-config", disabled)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["status"], "completed")
        self.assertNotIn("data_management", json.loads(output))
        self.assertFalse((destination / ".run-id.json").exists())

    def test_cli_admits_original_output_path_in_the_shared_manager(self):
        with self.producer():
            code, output, error = self.cli(self.source, "--output", self.destination,
                                           "--data-config", self.config, "--reserve-bytes", 16777216)
        self.assertEqual(code, 0, error)
        report = json.loads(output)
        self.assertEqual(report["status"], "completed")
        run = self.data("lease", "--action", "status", "--run-id", report["data_management"]["run_id"])
        self.assertEqual(run["state"], "sealed")
        self.assertEqual(run["reserved_bytes"], 0)
        self.assertEqual(len(report["data_management"]["sqlite_backups"]), 2)
        for backup in report["data_management"]["sqlite_backups"]:
            restored = self.data("resolve", "--inspect", "--artifact-id", backup["artifact_id"])
            self.assertTrue(Path(restored["path"]).is_file())
        self.assertEqual(Path(run["path"]), self.destination)
        self.assertEqual((self.destination / "input.original.simc").read_bytes(), self.source.read_bytes())
        self.assertFalse((self.root / "runs").exists())

    def test_http_task_is_admitted_before_saving_pasted_input(self):
        self.http_task()

    def test_http_reports_failed_receipt_write_instead_of_running_forever(self):
        self.http_task(fail_receipt=True)

    def http_task(self, *, fail_receipt=False):
        from interface import create_server
        write = Path.write_text
        def receipt_write(path, text, *args, **kwargs):
            if fail_receipt and path.name == '.simdata-run.json.tmp' and '"state": "finishing"' in text:
                raise OSError('synthetic full receipt disk')
            return write(path, text, *args, **kwargs)
        output = self.root / "ui"
        server = create_server(output, task_options={"data_config": self.config,
                                                     "reserve_bytes": 16777216})
        self.addCleanup(server.server_close)
        self.assertFalse(output.exists())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.producer(), patch.object(Path, 'write_text', receipt_write):
                address = f"http://127.0.0.1:{server.server_port}"
                request = Request(address + "/api/tasks", data=json.dumps({"profile": sample_profile()}).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    created = json.load(response)
                for _ in range(100):
                    with urlopen(address + "/api/tasks/" + created["task_id"], timeout=5) as response:
                        state = json.load(response)
                    if state["status"] not in ("starting", "running"):
                        break
                    time.sleep(0.02)
                self.assertEqual(state["status"], "failed" if fail_receipt else "completed", state)
                if not fail_receipt:
                    run = self.data("lease", "--action", "status", "--run-id", state["data_management"]["run_id"])
                    self.assertEqual(Path(run["path"]), output / "tasks" / created["task_id"])
                self.assertFalse((output / "inputs").exists())
        finally:
            server.shutdown()
            thread.join(5)

    def test_cli_resumes_cancelled_managed_task_with_the_original_reservation(self):
        import engine
        from runtime import TaskCancelled
        arguments = ("--output", self.destination, "--data-config", self.config, "--reserve-bytes", 16777216)
        with self.producer(), patch.object(engine, "reference", side_effect=TaskCancelled("合成取消")):
            code, output, error = self.cli(self.source, *arguments)
        self.assertEqual(code, 0, error)
        cancelled = json.loads(output)
        self.assertEqual(cancelled["status"], "cancelled")
        before = self.data("lease", "--action", "status", "--run-id", cancelled["data_management"]["run_id"])
        self.assertEqual(before["reserved_bytes"], 16777216)
        with self.producer():
            code, output, error = self.cli("--resume", *arguments)
        self.assertEqual(code, 0, error)
        resumed = json.loads(output)
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["data_management"]["run_id"], before["run_id"])

    def test_snapshot_failure_keeps_reservation_and_resume_only_finishes_data(self):
        original = subprocess.run
        setup = ("import sqlite3,runpy,sys\nconnect=sqlite3.connect\n"
                 "def denied(path,*a,**k):\n"
                 " if str(path).endswith('/image.sqlite3') or str(path).endswith('\\\\image.sqlite3'):\n"
                 "  raise sqlite3.OperationalError('synthetic snapshot destination denied')\n"
                 " return connect(path,*a,**k)\n"
                 "sqlite3.connect=denied\nsys.argv=sys.argv[1:]\nrunpy.run_path(sys.argv[0],run_name='__main__')")
        def process(command, **kwargs):
            if len(command) > 3 and command[2] == str(DATA_CLI) and command[3] == 'finish' and '--prepare' not in command:
                command = [sys.executable, '-B', '-c', setup, *command[2:]]
            return original(command, **kwargs)
        arguments = ("--output", self.destination, "--data-config", self.config, "--reserve-bytes", 16777216)
        with self.producer(), patch.object(subprocess, "run", side_effect=process):
            code, _, error = self.cli(self.source, *arguments)
        self.assertEqual(code, 2)
        self.assertIn("一致性备份未完成", error)
        state = task.read_task(self.destination)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["data_management"]["state"], "finishing")
        lease = self.data("lease", "--action", "status", "--run-id", state["data_management"]["run_id"])
        self.assertEqual(lease["reserved_bytes"], 16777216)
        import engine
        with self.producer(), patch.object(engine, "reference", side_effect=AssertionError("不得重跑已完成模拟")):
            code, output, error = self.cli("--resume", *arguments)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["data_management"]["state"], "sealed")
        self.assertEqual(self.data("status")["reserved_bytes"], 0)
        self.assertEqual((self.destination / "input.original.simc").read_bytes(), self.source.read_bytes())

    def test_prepare_failure_is_visible_and_resume_does_not_repeat_simulation(self):
        original = subprocess.run
        setup = ("import shutil,runpy,sys\n"
                 "shutil.disk_usage=lambda path: type('Usage',(),{'free':0})()\n"
                 "sys.argv=sys.argv[1:]\nrunpy.run_path(sys.argv[0],run_name='__main__')")
        def process(command, **kwargs):
            if len(command) > 3 and command[2] == str(DATA_CLI) and '--prepare' in command:
                command = [sys.executable, '-B', '-c', setup, *command[2:]]
            return original(command, **kwargs)
        arguments = ("--output", self.destination, "--data-config", self.config, "--reserve-bytes", 16777216)
        with self.producer(), patch.object(subprocess, "run", side_effect=process):
            code, _, error = self.cli(self.source, *arguments)
        self.assertEqual(code, 2, error)
        state = task.read_task(self.destination)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['business_status'], 'completed')
        self.assertEqual(self.data('status')['reserved_bytes'], 16777216)
        import engine
        with self.producer(), patch.object(engine, "reference", side_effect=AssertionError("不得重跑已完成模拟")):
            code, output, error = self.cli("--resume", *arguments)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)['data_management']['state'], 'sealed')
        self.assertEqual(self.data('status')['reserved_bytes'], 0)

    def test_resume_recovers_receipt_after_manager_has_already_sealed(self):
        write = Path.write_text
        def disk_failure(path, text, *arguments, **options):
            if path.name == '.simdata-run.json.tmp' and '"state": "sealed"' in text:
                raise OSError('synthetic receipt publish failure')
            return write(path, text, *arguments, **options)
        arguments = ("--output", self.destination, "--data-config", self.config, "--reserve-bytes", 16777216)
        with self.producer(), patch.object(Path, "write_text", disk_failure):
            code, _, _ = self.cli(self.source, *arguments)
        self.assertEqual(code, 2)
        state = task.read_task(self.destination)
        lease = self.data("lease", "--action", "status", "--run-id", state["data_management"]["run_id"])
        self.assertEqual(lease["state"], "sealed")
        self.assertEqual(lease["reserved_bytes"], 0)
        with self.producer():
            code, output, error = self.cli("--resume", *arguments)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["data_management"]["state"], "sealed")


if __name__ == "__main__":
    unittest.main()
