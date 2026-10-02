"""票06最高公开CLI；大根、任务及维护仅在临时合成根验证。"""
import os
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest
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
        for number in range(1100):
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
        setup = ("import os,shutil\nfrom pathlib import Path\nfrom types import SimpleNamespace\noriginal=os.scandir\nclosed=0\n"
                 "class ResizeBoundary:\n"
                 " def __init__(self,p): self.p=Path(p); self.inner=original(p)\n"
                 " def __iter__(self): return iter(self.inner)\n"
                 " def __next__(self): return next(self.inner)\n"
                 " def __enter__(self): return self\n"
                 " def __exit__(self,*a): self.close()\n"
                 " def close(self):\n  global closed\n  self.inner.close()\n"
                 "  if self.p==Path(" + repr(run["path"]) + "):\n"
                 "   closed+=1\n"
                 "   if closed==3: Path(" + repr(str(payload)) + ").unlink()\n"
                 "os.scandir=ResizeBoundary\n"
                 "def usage(path):\n p=Path(" + repr(str(payload)) + ")\n return SimpleNamespace(free=4*1024*1024-(p.stat().st_size if p.exists() else 0))\nshutil.disk_usage=usage\n")
        refused = self.injected_call(setup, "begin", "--request-id", "physical-competitor", "--owner-pid", str(os.getpid()), "--reserve-bytes", str(2 * 1024 * 1024), expected=2)
        self.assertIn("可用空间不足", refused["error"])
        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")

    def test_schedule_interval_744_is_valid_and_745_is_refused_without_policy_change(self):
        self.initialize()
        self.policy["maintenance_interval_hours"] = 744
        self.save_config()
        valid = self.call("schedule-preview", "--python", sys.executable, "--start-at", "2026-10-03T08:00:00+08:00")
        self.assertIn("PT744H", valid["xml"])
        self.assertFalse(valid["installed"])
        if os.name == "nt":
            import subprocess
            checked = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; $service=New-Object -ComObject Schedule.Service; $service.Connect(); $task=$service.NewTask(0); $task.XmlText=$env:SIMDATA_PREVIEW_XML"],
                                     env=dict(os.environ, SIMDATA_PREVIEW_XML=valid["xml"]), capture_output=True, timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
        self.policy["maintenance_interval_hours"] = 745
        self.save_config()
        refused = self.call("schedule-preview", "--python", sys.executable, "--start-at", "2026-10-03T08:00:00+08:00", expected=2)
        self.assertIn("744", refused["error"])
        self.assertEqual(json.loads(self.config.read_text())["maintenance_interval_hours"], 745)

    def test_560000_streamed_unknown_files_are_counted_without_tree_materialization(self):
        self.initialize()
        folder = self.root / "virtual synthetic scale"
        folder.mkdir()
        # OS目录边界生成56万条合成元数据；不扫描真实历史、不创建56万文件。
        setup = ("import os,stat,tracemalloc\nfrom types import SimpleNamespace\noriginal=os.scandir\ntracemalloc.start()\n"
                 "class Stream:\n"
                 " def __init__(self): self.number=0\n"
                 " def __iter__(self): return self\n"
                 " def __next__(self):\n"
                 "  if self.number>=560000: raise StopIteration\n"
                 "  self.number+=1\n"
                 "  return SimpleNamespace(stat=lambda **k:SimpleNamespace(st_mode=stat.S_IFREG,st_size=1024))\n"
                 " def close(self):\n  if tracemalloc.get_traced_memory()[1]>32*1024*1024: raise RuntimeError('stream memory exceeded')\n"
                 " def __enter__(self): return self\n"
                 " def __exit__(self,*a): self.close()\n"
                 "os.scandir=lambda path: Stream() if str(path).endswith('virtual synthetic scale') else original(path)\n")
        self.policy["capacity_bytes"] = 500 * 1024 * 1024
        self.save_config()
        refused = self.injected_call(setup, "begin", "--request-id", "scale-refused", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1", expected=2)
        self.assertIn("容量不足", refused["error"])
        self.policy["capacity_bytes"] = 600 * 1024 * 1024
        self.save_config()
        observed = self.injected_call(setup, "inventory", "--complete")
        self.assertGreaterEqual(observed["files"], 560000)
        self.assertGreaterEqual(observed["logical_bytes"], 573440000)
        self.assertFalse(observed["truncated"])
        run = self.injected_call(setup, "begin", "--request-id", "scale-admitted", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1")
        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")

    def test_unknown_link_beyond_old_limit_blocks_growth_and_cursor_errors_are_structured(self):
        self.initialize()
        folder = self.root / "synthetic extras"
        folder.mkdir()
        for number in range(1100):
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

    def test_schedule_preview_is_disabled_read_only_and_unset_is_not_invented(self):
        self.initialize()
        before = sorted(path.name for path in self.root.iterdir())
        preview = self.call("schedule-preview", "--python", sys.executable, "--start-at", "2026-10-03T08:00:00+08:00")
        self.assertFalse(preview["installed"])
        self.assertFalse(preview["enabled"])
        document = ET.fromstring(preview["xml"])
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(document.find("t:Settings/t:Enabled", ns).text, "false")
        self.assertEqual(document.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text, "PT1H")
        arguments = document.find("t:Actions/t:Exec/t:Arguments", ns).text
        self.assertIn('maintenance --config "' + str(self.config) + '"', arguments)
        self.assertNotIn("approve", arguments)
        if os.name == "nt":
            import subprocess
            environment = dict(os.environ, SIMDATA_PREVIEW_XML=preview["xml"])
            checked = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                      "$ErrorActionPreference='Stop'; $service=New-Object -ComObject Schedule.Service; $service.Connect(); $task=$service.NewTask(0); $task.XmlText=$env:SIMDATA_PREVIEW_XML"],
                                     env=environment, capture_output=True, timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))
        self.policy.update(mode="production", retention_days=None, maintenance_interval_hours=None)
        self.save_config()
        unset = self.call("schedule-preview", "--python", sys.executable)
        self.assertIn("maintenance_interval_hours", unset["unresolved"])
        self.assertIsNone(unset["xml"])
        self.call("maintenance", "--task", "archive", "--artifact-id", "anything", expected=2)

    def test_maintenance_uses_exact_archive_quarantine_purge_restore_approvals(self):
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        self.initialize()
        path = self.root / "synthetic.json"
        path.write_bytes(b'{"synthetic":true}')
        register = self.call("register", "--path", str(path), "--role", "native")
        identity = self.call("register", "--path", str(path), "--role", "native", "--approve-hash", register["plan_hash"])["artifact_id"]
        plan = self.call("maintenance", "--task", "archive", "--artifact-id", identity)
        self.assertTrue(path.exists())
        archive = self.call("maintenance", "--task", "archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"])
        isolated = self.call("maintenance", "--task", "quarantine", "--artifact-id", identity)
        self.call("maintenance", "--task", "quarantine", "--artifact-id", identity, "--approve-hash", isolated["plan_hash"])
        purge = self.call("maintenance", "--task", "purge", "--artifact-id", identity, "--valid-seconds", "60")
        saved = self.root.parent / "specific purge.json"
        saved.write_text(json.dumps(purge), encoding="utf-8")
        self.call("maintenance", "--task", "purge", "--plan", str(saved), "--approve-hash", purge["plan_hash"], expected=2)
        self.call("maintenance", "--task", "purge", "--plan", str(saved), "--approve-hash", purge["plan_hash"], "--confirm-item", identity + ":" + purge["items"][0]["confirmation_hash"])
        restored = self.call("maintenance", "--task", "restore", "--archive-id", archive["archive_id"], "--destination", str(self.root / "restore"))
        self.call("maintenance", "--task", "restore", "--archive-id", archive["archive_id"], "--destination", str(self.root / "restore"), "--approve-hash", restored["plan_hash"])
        self.assertEqual(Path(self.call("resolve", "--artifact-id", identity, "--inspect")["path"]).read_bytes(), b'{"synthetic":true}')
        self.assertFalse(self.call("maintenance")["automatic_cleanup"])

    def test_incremental_inventory_finishes_without_hash_or_business_use(self):
        self.initialize()
        folder = self.root / "incremental"
        folder.mkdir()
        for number in range(1205):
            (folder / f"{number:04d}").write_bytes(b"xx")
        setup = "from pathlib import Path\nPath.open_original=Path.open\ndef guarded(self,*a,**k):\n if self.parent.name=='incremental': raise RuntimeError('must not hash')\n return self.open_original(*a,**k)\nPath.open=guarded\n"
        cursor = None
        pages = 0
        while True:
            arguments = ["--incremental", "--limit", "200"]
            if cursor:
                arguments += ["--cursor", cursor]
            report = self.injected_call(setup, "inventory", *arguments)
            self.assertLessEqual(report["batch_visited"], 200)
            self.assertFalse(report["last_used_updated"])
            pages += 1
            if not report["truncated"]:
                break
            cursor = report["next_cursor"]
        self.assertGreater(pages, 6)
        self.assertGreaterEqual(report["files"], 1205)
        self.assertGreaterEqual(report["logical_bytes"], 2410)
        self.assertIsNone(report["next_cursor"])
        cursor = self.call("inventory", "--incremental", "--limit", "2")["next_cursor"]
        (self.root / "changed").write_bytes(b"new")
        self.call("inventory", "--incremental", "--cursor", cursor, expected=2)

    def test_large_unknown_root_counts_all_bytes_before_growth(self):
        self.initialize()
        folder = self.root / "unknown synthetic"
        folder.mkdir()
        for number in range(2400):
            (folder / str(number)).write_bytes(b"x" * 1024)
        self.policy["capacity_bytes"] = 2 * 1024 * 1024
        self.save_config()
        rejected = self.call("begin", "--request-id", "full", "--owner-pid", str(os.getpid()), "--reserve-bytes", "10", expected=2)
        self.assertIn("容量不足", rejected["error"])
        self.policy["capacity_bytes"] = 8 * 1024 * 1024
        self.save_config()
        run = self.call("begin", "--request-id", "large", "--owner-pid", str(os.getpid()), "--reserve-bytes", "10")
        self.call("lease", "--run-id", run["run_id"], "--action", "release", "--token", run["token"])
        self.assertEqual((folder / "2399").read_bytes(), b"x" * 1024)


if __name__ == "__main__":
    unittest.main()
