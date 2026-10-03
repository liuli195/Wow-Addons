"""原生进程清理的可移植边界回归；真实Windows进程测试仍在test_search。"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "projects" / "sim2gse"))
import runtime


class RuntimeTests(TestCase):
    def test_redirect_cleanup_retries_only_transient_windows_sharing_violation(self):
        for target, failures, winerror, expected_calls in (("stdout", 2, 32, 3), ("stderr", 2, 32, 3),
                                                          ("stdout", 20, 32, 11), ("stdout", 1, 5, 1),
                                                          ("stdout", 1, None, 1)):
            with self.subTest(target=target, failures=failures, winerror=winerror), tempfile.TemporaryDirectory() as directory:
                stdout, stderr = Path(directory) / "stdout.tmp", Path(directory) / "stderr.tmp"
                stdout.write_bytes(b"owned stdout")
                stderr.write_bytes(b"owned stderr")
                events, reservations, attempts = [], [], []
                process = SimpleNamespace(stdout_path=stdout, stderr_path=stderr,
                                          terminate=lambda: events.append("terminate"),
                                          wait=lambda timeout: events.append("wait"),
                                          close=lambda: events.append("close"))
                task_runtime = runtime.TaskRuntime(10)
                task_runtime.reservation = lambda key, allowance: reservations.append((key, allowance))
                original_unlink = Path.unlink
                violation = PermissionError("injected sharing or access failure")
                if winerror is not None:
                    violation.winerror = winerror

                def unlink(path, *args, **kwargs):
                    self.assertEqual(events[-1], "close")
                    if path == (stdout if target == "stdout" else stderr):
                        attempts.append(path)
                        if len(attempts) <= failures:
                            raise violation
                    return original_unlink(path, *args, **kwargs)

                original_budget = runtime.BudgetExceeded("original native budget")
                expected_error = runtime.BudgetExceeded if failures < expected_calls else PermissionError
                with patch.object(runtime, "_create_process", return_value=process), \
                        patch.object(Path, "unlink", unlink), self.assertRaises(expected_error) as raised:
                    runtime.run_command(["simc"], directory, timeout_seconds=5, runtime=task_runtime,
                                        on_start=lambda: (_ for _ in ()).throw(original_budget))
                self.assertEqual(len(attempts), expected_calls)
                self.assertEqual(events, ["terminate", "wait", "close"])
                self.assertIsNone(reservations[-1][1])
                self.assertEqual(reservations[0][0], reservations[-1][0])
                self.assertEqual(task_runtime.budget_seconds, 10)
                self.assertGreaterEqual(task_runtime.elapsed_seconds, (expected_calls - 1) * 0.02)
                if expected_error is runtime.BudgetExceeded:
                    self.assertIs(raised.exception, original_budget)
                    self.assertFalse(stdout.exists())
                    self.assertFalse(stderr.exists())
                else:
                    self.assertIs(raised.exception, violation)
                    self.assertEqual(stdout.read_bytes(), b"owned stdout")
                    self.assertEqual(stderr.read_bytes(), b"owned stderr")
