"""票06最高公开CLI；大根、任务及维护仅在临时合成根验证。"""
import os
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest
import stat
from types import SimpleNamespace
from unittest.mock import patch
import test_lifecycle as lifecycle


class MaintenanceTests(unittest.TestCase):
    setUp = lifecycle.LifecycleTests.setUp
    save_config = lifecycle.LifecycleTests.save_config
    call = lifecycle.LifecycleTests.call
    initialize = lifecycle.LifecycleTests.initialize
    injected_call = lifecycle.LifecycleTests.injected_call

    def test_verified_finisher_releases_only_its_own_future_physical_payload(self):
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        self.initialize()
        other = self.call("begin", "--request-id", "other-producer", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(1024 * 1024))
        own = self.call("begin", "--request-id", "finisher", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(3 * 1024 * 1024))
        (Path(own["path"]) / "native.json").write_bytes(b"x" * (3 * 1024 * 1024))
        args = ("--run-id", own["run_id"], "--token", own["token"], "--outcome", "success")
        self.injected_call("import shutil\nshutil.disk_usage=lambda p:type('Usage',(),{'free':1048576})()", "finish", *args, expected=2)
        result = self.injected_call("import shutil\nshutil.disk_usage=lambda p:type('Usage',(),{'free':2097152})()", "finish", *args)
        self.assertTrue(result["sealed"])
        self.assertEqual(self.call("status")["reserved_bytes"], 1024 * 1024)
        self.call("lease", "--run-id", other["run_id"], "--token", other["token"], "--action", "release")

    def test_producer_growth_between_inventory_and_reservation_credit_cannot_oversell(self):
        self.initialize()
        run = self.call("begin", "--request-id", "producer", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(3 * 1024 * 1024))
        folder = self.root / "unknown between scans"
        folder.mkdir()
        for number in range(3):
            (folder / str(number)).write_bytes(b"x")
        self.call("begin", "--request-id", "competing", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(2 * 1024 * 1024), expected=2)
        setup = ("import os\nfrom pathlib import Path\noriginal=os.scandir\n"
                 "class ProducerBoundary:\n"
                 " def __init__(self,p): self.p=Path(p); self.inner=original(p)\n"
                 " def __iter__(self): return iter(self.inner)\n"
                 " def __next__(self): return next(self.inner)\n"
                 " def __enter__(self): return self\n"
                 " def __exit__(self,*a): self.close()\n"
                 " def close(self):\n  self.inner.close()\n"
                 "  if self.p==Path(" + repr(str(self.root)) + "):\n"
                 "   Path(" + repr(str(Path(run["path"]) / "producer.bin")) + ").write_bytes(b'x'*(3*1024*1024))\n"
                 "os.scandir=ProducerBoundary\n")
        refused = self.injected_call(setup, "begin", "--request-id", "competing", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(2 * 1024 * 1024), expected=2)
        self.assertIn("容量不足", refused["error"])
        self.assertEqual((Path(run["path"]) / "producer.bin").stat().st_size, 3 * 1024 * 1024)
        small = self.call("begin", "--request-id", "same-scan-credit", "--owner-pid", str(os.getpid()), "--reserve-bytes", "131072")
        self.call("lease", "--run-id", small["run_id"], "--token", small["token"], "--action", "release")
        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")

    def test_physical_free_cannot_credit_a_producer_truncated_after_payload_scan(self):
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        self.initialize()
        run = self.call("begin", "--request-id", "physical-producer", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(3 * 1024 * 1024))
        payload = Path(run["path"]) / "producer.bin"
        payload.write_bytes(b"x" * (3 * 1024 * 1024))
        marker = Path(self.temporary.name) / "producer-truncated.json"
        setup = ("import shutil,json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
                 "def usage(path):\n p=Path(" + repr(str(payload)) + ")\n"
                 " if p.exists():\n"
                 "  before=p.stat().st_size\n  p.unlink()\n"
                 "  Path(" + repr(str(marker)) + ").write_text(json.dumps({'before':before,'after':0}))\n"
                 " return SimpleNamespace(free=4*1024*1024-(p.stat().st_size if p.exists() else 0))\nshutil.disk_usage=usage\n")
        refused = self.injected_call(setup, "begin", "--request-id", "physical-competitor", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(2 * 1024 * 1024), expected=2)
        self.assertFalse(payload.exists(), "producer truncation must actually occur")
        self.assertEqual(json.loads(marker.read_text()), {"before": 3 * 1024 * 1024, "after": 0})
        self.assertIn("可用空间不足", refused["error"])
        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")

    def test_unknown_link_blocks_growth_and_cursor_errors_are_structured(self):
        self.initialize()
        folder = self.root / "synthetic extras"
        folder.mkdir()
        for number in range(3):
            (folder / str(number)).write_bytes(b"x")
        link = folder / "outside link"
        if os.name == "nt":
            import subprocess
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.root.parent)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(lambda: os.rmdir(link))
        else:
            link.symlink_to(self.root.parent, target_is_directory=True)
        self.call("begin", "--request-id", "linked", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1", expected=2)
        self.call("inventory", "--incremental", "--cursor", "broken", expected=2)
        self.call("maintenance", "--task", "archive", "--plan", str(self.config), expected=2)
        self.call("schedule-preview", "--python", sys.executable, "--start-at", "2026-10-03T08:00:00", expected=2)

    def test_incremental_inventory_finishes_without_hash_or_business_use(self):
        self.initialize()
        folder = self.root / "incremental"
        folder.mkdir()
        for number in range(7):
            (folder / f"{number:04d}").write_bytes(b"xx")
        setup = "from pathlib import Path\nPath.open_original=Path.open\ndef guarded(self,*a,**k):\n if self.parent.name=='incremental': raise RuntimeError('must not hash')\n return self.open_original(*a,**k)\nPath.open=guarded\n"
        cursor = None
        pages = 0
        while True:
            arguments = ["--incremental", "--limit", "2"]
            if cursor:
                arguments += ["--cursor", cursor]
            report = self.injected_call(setup, "inventory", *arguments)
            self.assertLessEqual(report["batch_visited"], 2)
            self.assertFalse(report["last_used_updated"])
            pages += 1
            if not report["truncated"]:
                break
            cursor = report["next_cursor"]
        self.assertGreater(pages, 3)
        self.assertGreaterEqual(report["files"], 7)
        self.assertGreaterEqual(report["logical_bytes"], 14)
        self.assertIsNone(report["next_cursor"])
        cursor = self.call("inventory", "--incremental", "--limit", "2")["next_cursor"]
        (self.root / "changed").write_bytes(b"new")
        self.call("inventory", "--incremental", "--cursor", cursor, expected=2)

    def test_unknown_root_counts_all_bytes_before_growth(self):
        self.initialize()
        folder = self.root / "unknown synthetic"
        folder.mkdir()
        for number in range(3):
            (folder / str(number)).write_bytes(b"x" * 131072)
        self.policy["capacity_bytes"] = 512 * 1024
        self.save_config()
        rejected = self.call("begin", "--request-id", "full", "--owner-pid", str(os.getpid()), "--reserve-bytes", "10", expected=2)
        self.assertIn("容量不足", rejected["error"])
        self.policy["capacity_bytes"] = 8 * 1024 * 1024
        self.save_config()
        run = self.call("begin", "--request-id", "large", "--owner-pid", str(os.getpid()), "--reserve-bytes", "10")
        self.assertEqual(run["reserved_bytes"], 10)
        self.call("lease", "--run-id", run["run_id"], "--action", "release", "--token", run["token"])
        self.assertEqual((folder / "2").read_bytes(), b"x" * 131072)


class MaintenanceLogicTests(unittest.TestCase):
    """纯逻辑不建根；真实数据链由安全测试保留。"""
    call = lifecycle.LifecycleTests.call_main

    def setUp(self):
        import runpy
        self._main = runpy.run_path(str(lifecycle.CLI))["main"]
        self.module = self._main.__globals__
        self.config = Path(lifecycle.CLI.anchor) / "synthetic machine.json"
        self.root = Path(lifecycle.CLI.anchor) / "synthetic root"

    def test_inventory_consumes_one_bounded_stream_and_closes_it(self):
        for limit, count, truncated in ((None, 9, False), (2, 2, True)):
            live = peak = 0
            class Entry:
                def __init__(self):
                    nonlocal live, peak
                    live += 1
                    peak = max(peak, live)
                def __del__(self):
                    nonlocal live
                    live -= 1
                def stat(self, **kwargs):
                    return SimpleNamespace(st_mode=stat.S_IFREG, st_size=1024)
            class Stream:
                number = 0
                closed = False
                iterated = False
                def __iter__(self):
                    if self.iterated:
                        raise AssertionError("directory stream iterated twice")
                    self.iterated = True
                    return self
                def __length_hint__(self):
                    raise AssertionError("directory stream must not be materialized")
                def __next__(self):
                    if self.closed:
                        raise AssertionError("closed directory stream reused")
                    if self.number == 9:
                        raise StopIteration
                    self.number += 1
                    return Entry()
                def close(self):
                    self.closed = True
            stream = Stream()
            root = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1, st_ino=2))
            with self.subTest(limit=limit), patch.object(self.module["os"], "scandir", return_value=stream), patch.dict(self.module, checked_path=lambda path: path):
                observed = self.module["inventory"](root, limit)
            self.assertEqual(observed, dict(files=count, logical_bytes=count * 1024, truncated=truncated))
            self.assertEqual(stream.number, 9 if limit is None else 3)
            self.assertTrue(stream.closed)
            self.assertLessEqual(peak, 2)
            self.assertEqual(live, 0)

    def test_maintenance_dispatch_preserves_exact_approval_arguments(self):
        def handler(root, policy, args):
            return vars(args)
        handlers = dict(load_policy=lambda config: {"data_root": None}, checked_path=lambda value, **kwargs: Path(value),
                        lifecycle_execute=handler, quarantine=handler, purge=handler,
                        maintenance_status=lambda *args: {"automatic_cleanup": False})
        with patch.dict(self.module, handlers), patch.object(Path, "is_dir", return_value=True):
            for task, options, preserved in (
                    ("archive", ("--artifact-id", "a", "--approve-hash", "approved"), {"artifact_id": ["a"], "approve_hash": "approved"}),
                    ("quarantine", ("--artifact-id", "a", "--operation-id", "operation", "--approve-hash", "approved"), {"artifact_id": ["a"], "operation_id": "operation", "approve_hash": "approved"}),
                    ("purge", ("--plan", "saved.json", "--approve-hash", "approved", "--confirm-item", "a:hash"), {"plan": "saved.json", "approve_hash": "approved", "confirm_item": ["a:hash"]}),
                    ("restore", ("--archive-id", "archive", "--destination", "target", "--approve-hash", "approved"), {"archive_id": "archive", "destination": "target", "approve_hash": "approved"})):
                with self.subTest(task=task):
                    result = self.call("maintenance", "--root", str(self.root), "--task", task, *options)
                    self.assertEqual(result["command"], task)
                    for key, value in preserved.items():
                        self.assertEqual(result[key], value)
                    self.call("maintenance", "--root", str(self.root), "--task", task, "--database", "unexpected", expected=2)
            self.assertFalse(self.call("maintenance", "--root", str(self.root))["automatic_cleanup"])

    def test_schedule_xml_is_disabled_bounded_and_preserves_unset_policy(self):
        policy = dict.fromkeys(("data_root", "root_id", "capacity_bytes", "retention_days", "maintenance_interval_hours",
                                "maintenance_reserve_bytes", "archive_part_bytes", "metadata_reserve_bytes", "lease_seconds"), 1)
        policy["production_enabled"] = False
        args = SimpleNamespace(config=str(self.config), python=sys.executable, start_at="2026-10-03T08:00:00+08:00")
        with patch.dict(self.module, checked_path=lambda value: Path(value)), patch.object(Path, "is_file", return_value=True):
            preview = self.module["schedule_preview"](self.root, policy, args)
            self.assertFalse(preview["installed"])
            self.assertFalse(preview["enabled"])
            document = ET.fromstring(preview["xml"])
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            self.assertEqual(document.find("t:Settings/t:Enabled", ns).text, "false")
            self.assertEqual(document.find("t:Triggers/t:TimeTrigger/t:Enabled", ns).text, "false")
            self.assertEqual(document.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text, "PT1H")
            arguments = document.find("t:Actions/t:Exec/t:Arguments", ns).text
            self.assertIn('maintenance --config "' + str(self.config) + '"', arguments)
            self.assertNotIn("approve", arguments)
            policy["maintenance_interval_hours"] = 744
            self.assertIn("PT744H", self.module["schedule_preview"](None, policy, args)["xml"])
            policy["maintenance_interval_hours"] = 745
            with self.assertRaisesRegex(self.module["DataError"], "744"):
                self.module["schedule_preview"](None, policy, args)
            self.assertEqual(policy["maintenance_interval_hours"], 745)
            policy.update(data_root=None, maintenance_interval_hours=None)
            args.start_at = None
            before = policy.copy()
            unresolved = self.module["schedule_preview"](None, policy, args)
            self.assertIsNone(unresolved["xml"])
            self.assertEqual(unresolved["unresolved"], ["data_root", "maintenance_interval_hours", "start_at"])
            self.assertEqual(policy, before)
            policy.update(data_root=1, maintenance_interval_hours=1)
            args.start_at = "2026-10-03T08:00:00"
            with self.assertRaisesRegex(self.module["DataError"], "时区"):
                self.module["schedule_preview"](None, policy, args)


if __name__ == "__main__":
    unittest.main()
