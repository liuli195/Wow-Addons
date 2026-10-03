"""票05公开CLI；每个根和字节均由本测试创建。"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import subprocess
import sys
import time
import unittest

import test_lifecycle as lifecycle


class SafetyTests(unittest.TestCase):
    save_config = lifecycle.LifecycleTests.save_config
    call = lifecycle.LifecycleTests.call
    initialize = lifecycle.LifecycleTests.initialize
    injected_call = lifecycle.LifecycleTests.injected_call

    def setUp(self):
        lifecycle.LifecycleTests.setUp(self)
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()

    def source(self, name="native.json", contents=b'{"test":"synthetic"}'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        plan = self.call("register", "--path", str(path), "--role", "native")
        result = self.call("register", "--path", str(path), "--role", "native", "--approve-hash", plan["plan_hash"])
        return result["artifact_id"], path

    def crash_on_phase(self, operation_id, phase):
        return ("import sqlite3,os\noriginal=sqlite3.connect\n"
                "class CrashConnection(sqlite3.Connection):\n"
                " def commit(self):\n  super().commit()\n"
                "  try:\n   row=self.execute(\"SELECT phase FROM safety_jobs WHERE id=?\",(" + repr(operation_id) + ",)).fetchone()\n"
                "  except sqlite3.OperationalError: return\n"
                "  if row and row[0]==" + repr(phase) + ": os._exit(77)\n"
                "def connect(*a,**k):\n k['factory']=CrashConnection\n return original(*a,**k)\nsqlite3.connect=connect\n")

    def test_migration_post_publish_crash_is_replayable(self):
        self.initialize()
        # 只保留真实发布后、日志提交前的恢复；阶段提交逻辑另用内存数据库验证。
        identity, source = self.source("native.json")
        destination = self.root / "target rename"
        args = ("--artifact-id", identity, "--destination", str(destination))
        plan = self.call("migration", *args)
        self.assertFalse(destination.exists())
        setup = "import os\noriginal=os.replace\ndef replace(a,b,*args,**kwargs):\n original(a,b,*args,**kwargs)\n if 'target rename' in str(b): os._exit(77)\nos.replace=replace\n"
        self.injected_call(setup, "migration", *args, "--approve-hash", plan["plan_hash"], expected=77)
        recovered = self.call("migration", *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
        self.assertEqual(recovered["operation_id"], plan["operation_id"])
        self.assertEqual(recovered["phase"], "sealed")
        self.assertTrue(source.exists())
        self.assertEqual(Path(recovered["copies"][0]["path"]).read_bytes(), source.read_bytes())
        resolved = self.call("resolve", "--artifact-id", identity, "--inspect")
        self.assertEqual(resolved["artifact_id"], identity)
        self.assertEqual(resolved["path"], recovered["copies"][0]["path"])
        self.assertEqual(self.call("migration", *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"]), recovered)

    def test_quarantine_and_recovery_post_move_crash_are_replayable(self):
        self.initialize()
        identity, source = self.source("quarantine recovery/native.json")
        args = ("--artifact-id", identity)
        setup = ("import os\noriginal=os.fdopen\nclass ClosingCrash:\n"
                 " def __init__(self,h): self.h=h\n"
                 " def __getattr__(self,n): return getattr(self.h,n)\n"
                 " def __enter__(self): return self\n"
                 " def __exit__(self,*a):\n  self.h.close()\n  os._exit(77)\n"
                 "def fdopen(*a,**k): return ClosingCrash(original(*a,**k))\nos.fdopen=fdopen\n")
        for command in ("quarantine", "recover-quarantine"):
            with self.subTest(command=command):
                plan = self.call(command, *args)
                self.injected_call(setup, command, *args, "--approve-hash", plan["plan_hash"], expected=77)
                result = self.call(command, *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(result["operation_id"], plan["operation_id"])
                self.assertEqual(result["phase"], "sealed")
                self.assertFalse(result["space_released"])
                self.assertEqual(result["items"][0]["artifact_id"], identity)
                self.assertEqual(Path(result["items"][0]["path"]).read_bytes(), b'{"test":"synthetic"}')
                if command == "quarantine":
                    self.assertFalse(source.exists())
                    self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)
                else:
                    self.assertEqual(source.read_bytes(), b'{"test":"synthetic"}')
                    self.assertEqual(self.call("resolve", "--artifact-id", identity, "--inspect")["artifact_id"], identity)
                self.assertEqual(self.call(command, *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"]), result)

    def test_managed_volume_migration_copies_across_actual_volume_and_preserves_origin(self):
        self.initialize()
        identity, source = self.source()
        synthetic = lifecycle.CLI.parents[4] / ".local" / ("simdata-synthetic-" + self.policy["root_id"])
        target = synthetic / "managed volume with spaces"
        target.mkdir(parents=True)
        def cleanup():
            resolved = synthetic.resolve(strict=True)
            self.assertEqual(resolved.parent, (lifecycle.CLI.parents[4] / ".local").resolve())
            self.assertEqual(resolved.name, "simdata-synthetic-" + self.policy["root_id"])
            shutil.rmtree(resolved)
        self.addCleanup(cleanup)
        self.assertNotEqual(source.stat().st_dev, target.stat().st_dev)
        preview = self.call("volume-register", "--path", str(target))
        volume = self.call("volume-register", "--path", str(target), "--approve-hash", preview["plan_hash"])
        args = ("--artifact-id", identity, "--volume-id", volume["marker"]["volume_id"], "--destination", str(target / "published data"))
        plan = self.call("migration", *args)
        copied = self.call("migration", *args, "--approve-hash", plan["plan_hash"])
        self.assertTrue(source.exists())
        self.assertEqual(self.call("resolve", "--artifact-id", identity, "--inspect")["path"], copied["copies"][0]["path"])
        isolation = self.call("quarantine", "--artifact-id", identity)
        self.call("quarantine", "--artifact-id", identity, "--approve-hash", isolation["plan_hash"])
        resolved = self.call("resolve", "--artifact-id", identity, "--inspect")
        self.assertEqual(Path(resolved["path"]).read_bytes(), b'{"test":"synthetic"}')
        archived = self.call("archive", "--artifact-id", identity)
        self.call("archive", "--artifact-id", identity, "--approve-hash", archived["plan_hash"])

    def test_reader_lease_blocks_lifecycle_even_with_an_expired_heartbeat(self):
        self.initialize()
        identity, source = self.source()
        lease = self.call("read-lease", "--action", "acquire", "--artifact-id", identity,
                          "--owner-pid", str(os.getpid()), "--token", "synthetic-reader")
        self.assertEqual(Path(lease["path"]).read_bytes(), source.read_bytes())
        self.call("archive", "--artifact-id", identity, expected=2)
        status = self.injected_call("import time\ntime.time=lambda:4000000000\n", "read-lease",
                                    "--action", "status", "--lease-id", lease["lease_id"])
        self.assertTrue(status["heartbeat_expired"])
        self.assertEqual(status["owner_state"], "alive")
        self.call("read-lease", "--action", "release", "--lease-id", lease["lease_id"], "--token", "wrong", expected=2)
        self.call("read-lease", "--action", "release", "--lease-id", lease["lease_id"], "--token", "synthetic-reader")
        self.call("archive", "--artifact-id", identity)

    def test_legacy_registration_is_stable_and_keeps_unknown_consumers_protected(self):
        self.initialize()
        directory = self.root / "legacy samples"
        directory.mkdir()
        source = directory / "native.json"
        source.write_bytes(b'{"dps":10}')
        args = ("--directory", str(directory), "--role", "native")
        plan = self.call("legacy-register", *args)
        self.assertEqual(self.call("status")["registered_artifacts"], 0)
        registered = self.call("legacy-register", *args, "--approve-hash", plan["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), 1)
        identity = registered["artifacts"][0]["artifact_id"]
        self.assertEqual(self.call("resolve", "--artifact-id", identity, "--inspect")["path"], str(source))
        self.assertTrue(self.call("protect", "--artifact-id", identity)["protected"])
        again = self.call("legacy-register", *args, "--approve-hash", plan["plan_hash"])
        self.assertEqual(again["artifacts"], registered["artifacts"])

    def test_persistent_dependency_protects_a_transitive_cache_and_rejects_cycles(self):
        self.initialize()
        a, _ = self.source("a.json")
        b, _ = self.source("b.json")
        c, _ = self.source("c.json")
        self.call("dependency", "--artifact-id", a, "--requires", b, "--kind", "durable")
        self.call("dependency", "--artifact-id", b, "--requires", c, "--kind", "cache")
        self.assertTrue(self.call("protect", "--artifact-id", c)["protected"])
        self.call("reference", "--artifact-id", c, "--owner", "artifact:" + b, "--action", "invalidate-preview", expected=2)
        self.call("dependency", "--artifact-id", c, "--requires", a, "--kind", "cache", expected=2)
        self.call("reference", "--artifact-id", a, "--owner", "artifact:" + c, "--kind", "cache", "--action", "add", expected=2)
        protected, _ = self.source("Captures/ancestor.json")
        leaf, _ = self.source("dependent-cache.json")
        self.call("dependency", "--artifact-id", protected, "--requires", leaf, "--kind", "cache")
        self.assertTrue(self.call("protect", "--artifact-id", leaf)["protected"])
        self.call("quarantine", "--artifact-id", leaf, expected=2)

    def test_purge_requires_saved_current_plan_and_every_item_confirmation(self):
        self.initialize()
        identity, source = self.source()
        isolation = self.call("quarantine", "--artifact-id", identity)
        isolated = self.call("quarantine", "--artifact-id", identity, "--approve-hash", isolation["plan_hash"])
        path = Path(isolated["items"][0]["path"])
        preview = self.call("purge", "--artifact-id", identity, "--valid-seconds", "300")
        saved = self.root.parent / "explicit purge approval.json"
        saved.write_text(json.dumps(preview), encoding="utf-8")
        args = ("--plan", str(saved), "--approve-hash", preview["plan_hash"])
        self.call("purge", *args, expected=2)
        self.assertTrue(path.exists())
        self.call("purge", *args, "--confirm-item", identity + ":wrong", expected=2)
        confirmation = identity + ":" + preview["items"][0]["confirmation_hash"]
        expired = self.injected_call("import time\ntime.time=lambda:4000000000\n", "purge", *args, "--confirm-item", confirmation, expected=2)
        self.assertTrue(path.exists())
        deleted = self.call("purge", *args, "--confirm-item", confirmation)
        self.assertFalse(path.exists())
        self.assertEqual(deleted["purged"], [identity])
        self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)
        self.call("recover-quarantine", "--artifact-id", identity, expected=2)
        self.assertEqual(self.call("purge", *args, "--confirm-item", confirmation)["purged"], [identity])

    def isolated_plan(self, ids, name="purge plan.json"):
        arguments = tuple(value for identity in ids for value in ("--artifact-id", identity))
        isolation = self.call("quarantine", *arguments)
        isolated = self.call("quarantine", *arguments, "--approve-hash", isolation["plan_hash"])
        preview = self.call("purge", *arguments, "--valid-seconds", "300")
        saved = self.root.parent / name
        saved.write_text(json.dumps(preview), encoding="utf-8")
        execution = ("--plan", str(saved), "--approve-hash", preview["plan_hash"])
        confirmations = tuple(value for item in preview["items"] for value in ("--confirm-item", item["id"] + ":" + item["confirmation_hash"]))
        return preview, isolated, execution + confirmations

    def test_purge_validates_every_file_before_any_deletion_and_keeps_tombstone_ids(self):
        self.initialize()
        ids = [self.source(name)[0] for name in ("first.json", "second.json")]
        preview, isolated, args = self.isolated_plan(ids)
        paths = [Path(item["path"]) for item in isolated["items"]]
        self.call("pin", "--artifact-id", preview["items"][-1]["id"], "--label", "synthetic evidence", "--action", "add")
        self.call("purge", *args, expected=2)
        self.assertTrue(all(path.exists() for path in paths))
        self.call("pin", "--artifact-id", preview["items"][-1]["id"], "--label", "synthetic evidence", "--action", "remove")
        result = self.call("purge", *args)
        self.assertEqual(set(result["purged"]), set(ids))
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(self.call("status")["registered_artifacts"], 2)

    def test_purge_delete_before_commit_is_replayable(self):
        self.initialize()
        identity, _ = self.source("native.json")
        plan, isolated, args = self.isolated_plan([identity])
        # OS关闭排他句柄后崩溃；不是内部索引写入，也不增加测试专用产品开关。
        setup = ("import os\noriginal=os.fdopen\nclass ClosingCrash:\n"
                 " def __init__(self,h): self.h=h\n"
                 " def __getattr__(self,n): return getattr(self.h,n)\n"
                 " def __enter__(self): return self\n"
                 " def __exit__(self,*a):\n  self.h.close()\n  os._exit(77)\n"
                 "def fdopen(*a,**k): return ClosingCrash(original(*a,**k))\nos.fdopen=fdopen\n")
        self.injected_call(setup, "purge", *args, expected=77)
        recovered = self.call("purge", *args)
        self.assertEqual(recovered["operation_id"], plan["operation_id"])
        self.assertEqual(recovered["phase"], "sealed")
        self.assertEqual(recovered["purged"], [identity])
        self.assertFalse(Path(isolated["items"][0]["path"]).exists())
        self.assertEqual(self.call("purge", *args), recovered)

    def test_changed_plan_content_cache_references_and_disk_full_refuse_safely(self):
        self.initialize()
        identity, source = self.source()
        self.call("reference", "--action", "add", "--artifact-id", identity, "--owner", "synthetic accelerator", "--kind", "cache")
        self.call("quarantine", "--artifact-id", identity, expected=2)
        invalidate = self.call("reference", "--action", "invalidate-preview", "--artifact-id", identity, "--owner", "synthetic accelerator")
        self.call("reference", "--action", "invalidate", "--artifact-id", identity, "--owner", "synthetic accelerator", "--approve-hash", invalidate["plan_hash"])
        args = ("--artifact-id", identity, "--destination", str(self.root / "no space target"))
        preview = self.call("migration", *args)
        self.injected_call("import shutil\nfrom collections import namedtuple\nshutil.disk_usage=lambda path:namedtuple('usage','total used free')(100,100,0)\n", "migration", *args,
                           "--approve-hash", preview["plan_hash"], expected=2)
        self.assertFalse((self.root / "no space target").exists())
        self.assertTrue(source.exists())
        preview, isolated, purge_args = self.isolated_plan([identity])
        isolated_path = Path(isolated["items"][0]["path"])
        isolated_path.write_bytes(b"modified isolated copy")
        self.call("purge", *purge_args, expected=2)
        self.assertEqual(isolated_path.read_bytes(), b"modified isolated copy")

    def test_reader_death_requires_explicit_recovery_not_only_heartbeat_expiry(self):
        self.initialize()
        identity, _ = self.source()
        owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        try:
            lease = self.call("read-lease", "--action", "acquire", "--artifact-id", identity, "--owner-pid", str(owner.pid))
        finally:
            owner.communicate(timeout=10)
        self.call("migration", "--artifact-id", identity, "--destination", str(self.root / "dead reader target"), expected=2)
        preview = self.call("read-lease", "--action", "recover-preview", "--lease-id", lease["lease_id"])
        self.assertEqual(preview["owner_state"], "dead")
        self.call("read-lease", "--action", "recover", "--lease-id", lease["lease_id"], "--approve-hash", "wrong", expected=2)
        self.call("read-lease", "--action", "recover", "--lease-id", lease["lease_id"], "--approve-hash", preview["plan_hash"])
        self.call("migration", "--artifact-id", identity, "--destination", str(self.root / "dead reader target"))

    def test_quarantine_handle_keeps_spaces_unicode_long_paths_and_no_overwrite(self):
        self.initialize()
        name = ("空格 😀 " + "x" * 95 + "/") * 2 + "native.json"
        identity, original = self.source(name)
        expected = original.read_bytes()
        plan = self.call("quarantine", "--artifact-id", identity)
        result = self.call("quarantine", "--artifact-id", identity, "--approve-hash", plan["plan_hash"])
        self.assertEqual(Path(result["items"][0]["path"]).name, "native.json")
        recovery = self.call("recover-quarantine", "--artifact-id", identity)
        original.write_bytes(b"new user data must never be overwritten")
        self.call("recover-quarantine", "--artifact-id", identity, "--approve-hash", recovery["plan_hash"], expected=2)
        self.assertEqual(original.read_bytes(), b"new user data must never be overwritten")
        original.unlink()  # 仅删除本测试刚创建的冲突合成文件。
        self.call("recover-quarantine", "--artifact-id", identity, "--approve-hash", recovery["plan_hash"])
        self.assertEqual(original.read_bytes(), expected)

    def test_quarantine_existing_file_handle_refuses_then_exact_job_retries(self):
        self.initialize()
        identity, original = self.source()
        plan = self.call("quarantine", "--artifact-id", identity)
        with original.open("rb"):
            self.call("quarantine", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=2)
            self.assertTrue(original.exists())
        result = self.call("quarantine", "--artifact-id", identity, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
        self.assertEqual(Path(result["items"][0]["path"]).read_bytes(), b'{"test":"synthetic"}')

    def test_migration_preview_does_not_authorize_new_junction_or_outside_root(self):
        self.initialize()
        identity, source = self.source()
        outside = self.root.parent / "outside protected synthetic data"
        outside.mkdir()
        sentinel = outside / "keep.json"
        sentinel.write_bytes(b"protected external synthetic evidence")
        self.call("migration", "--artifact-id", identity, "--destination", str(outside / "out"), expected=2)
        parent = self.root / "future destination parent"
        args = ("--artifact-id", identity, "--destination", str(parent / "new data"))
        plan = self.call("migration", *args)
        environment = dict(os.environ, SIMDATA_TEST_LINK=str(parent), SIMDATA_TEST_TARGET=str(outside))
        result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command",
                                 "New-Item -ItemType Junction -Path $env:SIMDATA_TEST_LINK -Target $env:SIMDATA_TEST_TARGET -ErrorAction Stop | Out-Null"],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.call("migration", *args, "--approve-hash", plan["plan_hash"], expected=2)
        self.assertEqual(sentinel.read_bytes(), b"protected external synthetic evidence")
        self.assertFalse((outside / "new data").exists())
        self.assertTrue(source.exists())
        parent.rmdir()  # Windows Junction只移除入口，外部合成目录及哨兵继续保留。
        unknown_stage = self.root / ".staging" / plan["operation_id"]
        unknown_stage.mkdir(parents=True)
        unknown = unknown_stage / "unknown-user-data.json"
        unknown.write_bytes(b"unknown staging contents must stay untouched")
        self.call("migration", *args, "--approve-hash", plan["plan_hash"], expected=2)
        self.assertEqual(unknown.read_bytes(), b"unknown staging contents must stay untouched")
        self.assertTrue(source.exists())

    def test_abandon_migration_retains_bytes_and_releases_only_unspent_reservation(self):
        self.initialize()
        identity, original = self.source()
        args = ("--artifact-id", identity, "--destination", str(self.root / "abandoned target"))
        plan = self.call("migration", *args)
        self.injected_call(self.crash_on_phase(plan["operation_id"], "verified"), "migration", *args, "--approve-hash", plan["plan_hash"], expected=77)
        retained = list((self.root / ".staging").rglob("native.json"))
        self.assertEqual(len(retained), 1)
        self.assertGreater(self.call("status")["operation_reserved_bytes"], 0)
        preview = self.call("safety-operation", "--operation-id", plan["operation_id"], "--action", "abandon-preview")
        self.call("safety-operation", "--operation-id", plan["operation_id"], "--action", "abandon", "--approve-hash", preview["approval_hash"])
        self.assertEqual(self.call("status")["operation_reserved_bytes"], 0)
        self.assertTrue(retained[0].exists())
        self.assertTrue(original.exists())
        self.call("migration", *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"], expected=2)

    def test_reader_pid_reuse_is_distinct_from_alive_and_needs_approved_recovery(self):
        self.initialize()
        identity, _ = self.source()
        lease = self.call("read-lease", "--action", "acquire", "--artifact-id", identity, "--owner-pid", str(os.getpid()))
        # 在操作系统出生时间读取边界模拟同PID新进程；不直接写索引或调用产品私有函数。
        setup = ("import ctypes\noriginal=ctypes.WinDLL\n"
                 "def library(*a,**k):\n dll=original(*a,**k)\n actual=dll.GetProcessTimes\n"
                 " def times(handle,created,*rest):\n  actual.argtypes=times.argtypes\n"
                 "  result=actual(handle,created,*rest)\n  created._obj.dwLowDateTime ^= 1\n  return result\n"
                 " dll.GetProcessTimes=times\n return dll\nctypes.WinDLL=library\n")
        preview = self.injected_call(setup, "read-lease", "--action", "recover-preview", "--lease-id", lease["lease_id"])
        self.assertEqual(preview["owner_state"], "pid-reused")
        self.injected_call(setup, "read-lease", "--action", "release", "--lease-id", lease["lease_id"], "--token", lease["token"], expected=2)
        self.injected_call(setup, "read-lease", "--action", "recover", "--lease-id", lease["lease_id"], "--approve-hash", preview["plan_hash"])
        self.call("quarantine", "--artifact-id", identity)

    def test_archive_quarantine_purge_restore_chain_preserves_original_sha_and_id(self):
        self.initialize()
        identity, original = self.source("archive source/native.json", bytes(range(256)) * 101)
        raw = original.read_bytes()
        archive_plan = self.call("archive", "--artifact-id", identity)
        archive = self.call("archive", "--artifact-id", identity, "--approve-hash", archive_plan["plan_hash"])
        purge_plan, isolated, args = self.isolated_plan([identity])
        self.call("purge", *args)
        self.assertFalse(original.exists())
        self.assertFalse(Path(isolated["items"][0]["path"]).exists())
        destination = self.root / "restore after original deletion"
        restore_plan = self.call("restore", "--archive-id", archive["archive_id"], "--destination", str(destination))
        restored = self.call("restore", "--archive-id", archive["archive_id"], "--destination", str(destination), "--approve-hash", restore_plan["plan_hash"])
        self.assertEqual(Path(restored["restored"][0]["path"]).read_bytes(), raw)
        resolved = self.call("resolve", "--artifact-id", identity, "--inspect")
        self.assertEqual(resolved["artifact_id"], identity)
        self.assertEqual(resolved["sha256"], hashlib.sha256(raw).hexdigest())

    def test_quarantine_locks_destination_directory_against_swap_at_os_move_boundary(self):
        self.initialize()
        identity, original = self.source()
        plan = self.call("quarantine", "--artifact-id", identity)
        directory = self.root / ".quarantine" / plan["operation_id"]
        outside = self.root.parent / "displaced synthetic directory"
        observed = self.root.parent / "boundary lock observation.txt"
        setup = ("import ctypes,os\nfrom pathlib import Path\noriginal=ctypes.WinDLL\n"
                 "def library(*a,**k):\n dll=original(*a,**k)\n actual=dll.SetFileInformationByHandle\n"
                 " def information(handle,kind,data,size):\n  actual.argtypes=information.argtypes\n  actual.restype=information.restype\n"
                 "  if kind==3:\n   try: os.replace(" + repr(str(directory)) + "," + repr(str(outside)) + ")\n"
                 "   except PermissionError: Path(" + repr(str(observed)) + ").write_text('blocked')\n"
                 "   else: raise OSError('destination directory was not locked')\n"
                 "  return actual(handle,kind,data,size)\n dll.SetFileInformationByHandle=information\n return dll\nctypes.WinDLL=library\n")
        result = self.injected_call(setup, "quarantine", "--artifact-id", identity, "--approve-hash", plan["plan_hash"])
        self.assertEqual(observed.read_text(), "blocked")
        self.assertFalse(outside.exists())
        self.assertEqual(Path(result["items"][0]["path"]).read_bytes(), b'{"test":"synthetic"}')

    def test_expired_interrupted_purge_requires_new_bound_plan_and_item_approval(self):
        self.initialize()
        for phase in ("reserved", "published"):
            with self.subTest(phase=phase):
                ids = [self.source(phase + str(number) + ".json")[0] for number in range(2)]
                plan, isolated, execution = self.isolated_plan(ids, phase + " old approval.json")
                confirmations = tuple(value for item in plan["items"] for value in ("--confirm-item", item["id"] + ":" + item["confirmation_hash"]))
                self.assertEqual(plan["expires"] - plan["created"], 300)
                before_expiry = "import time\ntime.time=lambda:" + repr(plan["expires"] - 1) + "\n"
                after_expiry = "import time\ntime.time=lambda:" + repr(plan["expires"] + 1) + "\n"
                self.injected_call(before_expiry + self.crash_on_phase(plan["operation_id"], phase), "purge", *execution, expected=77)
                expired = self.injected_call(after_expiry, "purge", *execution, expected=2)
                self.assertIn("过期", expired["error"])
                renewed = self.injected_call(after_expiry, "purge", "--renew-operation", plan["operation_id"], "--valid-seconds", "300")
                self.assertEqual(renewed["created"], plan["expires"] + 1)
                self.assertEqual(renewed["expires"] - renewed["created"], 300)
                self.assertEqual(renewed["operation_id"], plan["operation_id"])
                self.assertNotEqual(renewed["plan_hash"], plan["plan_hash"])
                if phase == "published":
                    self.assertEqual(len(renewed["completed_ids"]), 1)
                new_saved = self.root.parent / (phase + " renewed approval.json")
                new_saved.write_text(json.dumps(renewed), encoding="utf-8")
                new_args = ("--plan", str(new_saved), "--approve-hash", renewed["plan_hash"])
                self.injected_call(after_expiry, "purge", *new_args, expected=2)
                self.injected_call(after_expiry, "purge", *new_args, *confirmations, expected=2)
                new_confirmations = tuple(value for item in renewed["items"] for value in ("--confirm-item", item["id"] + ":" + item["confirmation_hash"]))
                remaining = next(item["id"] for item in renewed["items"] if item["id"] not in renewed["completed_ids"])
                self.injected_call(after_expiry, "pin", "--artifact-id", remaining, "--action", "add", "--label", "new persistent evidence")
                self.injected_call(after_expiry, "purge", "--renew-operation", plan["operation_id"], "--valid-seconds", "300", expected=2)
                self.injected_call(after_expiry, "purge", *new_args, *new_confirmations, expected=2)
                self.injected_call(after_expiry, "pin", "--artifact-id", remaining, "--action", "remove", "--label", "new persistent evidence")
                if renewed["completed_ids"]:
                    deleted_path = Path(next(item["path"] for item in isolated["items"] if item["artifact_id"] in renewed["completed_ids"]))
                    deleted_path.write_bytes(b"new file must never be deleted")
                    self.injected_call(after_expiry, "purge", "--renew-operation", plan["operation_id"], "--valid-seconds", "300", expected=2)
                    self.injected_call(after_expiry, "purge", *new_args, *new_confirmations, expected=2)
                    self.assertEqual(deleted_path.read_bytes(), b"new file must never be deleted")
                    deleted_path.unlink()  # 仅移除本测试刚创建的冲突合成文件。
                result = self.injected_call(after_expiry, "purge", *new_args, *new_confirmations)
                self.assertEqual(set(result["purged"]), set(ids))
                expired = self.injected_call(after_expiry, "purge", *execution, expected=2)
                self.assertIn("过期", expired["error"])

    def test_batch_migration_internal_dependencies_do_not_block_own_job(self):
        self.initialize()
        for kind in ("cache", "durable"):
            a, _ = self.source(kind + " a.json")
            b, _ = self.source(kind + " b.json")
            self.call("dependency", "--artifact-id", a, "--requires", b, "--kind", kind)
            if kind == "cache":
                ancestor, _ = self.source("other-job-ancestor.json")
                self.call("dependency", "--artifact-id", ancestor, "--requires", a, "--kind", "cache")
            args = ("--artifact-id", a, "--artifact-id", b, "--destination", str(self.root / (kind + " batch")))
            plan = self.call("migration", *args)
            if kind == "cache":
                self.injected_call(self.crash_on_phase(plan["operation_id"], "reserved"), "migration", *args, "--approve-hash", plan["plan_hash"], expected=77)
                archive_args = ("--artifact-id", ancestor)
                archive = self.call("archive", *archive_args)
                setup = self.crash_on_phase(archive["operation_id"], "reserved").replace("FROM safety_jobs", "FROM jobs")
                self.injected_call(setup, "archive", *archive_args, "--approve-hash", archive["plan_hash"], expected=77)
                self.call("migration", *args, "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"], expected=2)
                abandon = self.call("operation", "--operation-id", archive["operation_id"], "--action", "abandon-preview")
                self.call("operation", "--operation-id", archive["operation_id"], "--action", "abandon", "--approve-hash", abandon["approval_hash"])
                args += ("--operation-id", plan["operation_id"])
            result = self.call("migration", *args, "--approve-hash", plan["plan_hash"])
            self.assertEqual(len(result["copies"]), 2)

    def test_pending_migrations_share_physical_volume_reservation(self):
        self.initialize()
        self.policy["capacity_bytes"] = 256 * 1024 * 1024
        self.save_config()
        volumes = []
        for name in ("registered target one", "registered target two"):
            target = self.root.parent / name
            target.mkdir()
            preview = self.call("volume-register", "--path", str(target))
            registered = self.call("volume-register", "--path", str(target), "--approve-hash", preview["plan_hash"])
            volumes.append((target, registered["marker"]["volume_id"]))
        ids = [self.source("payload" + str(i) + ".bin", b"x" * (8 * 1024 * 1024))[0] for i in range(2)]
        plans = []
        arguments = []
        for index in range(2):
            target, volume_id = volumes[index]
            args = ("--artifact-id", ids[index], "--volume-id", volume_id, "--destination", str(target / "published"))
            arguments.append(args)
            plans.append(self.call("migration", *args))
        target_paths = [str(value[0]) for value in volumes]
        setup = ("import shutil\nfrom pathlib import Path\nfrom collections import namedtuple\noriginal_usage=shutil.disk_usage\n"
                 "def usage(path):\n p=Path(path)\n"
                 " if any(p.is_relative_to(Path(value)) for value in " + repr(target_paths) + "):\n"
                 "  materialized=sum(file.stat().st_size for value in " + repr(target_paths) + " for file in Path(value).rglob('*') if file.is_file())\n"
                 "  return namedtuple('usage','total used free')(100000000,60000000+materialized,40000000-materialized)\n"
                 " return original_usage(path)\nshutil.disk_usage=usage\n")
        self.injected_call(setup + self.crash_on_phase(plans[0]["operation_id"], "reserved"), "migration", *arguments[0], "--approve-hash", plans[0]["plan_hash"], expected=77)
        self.injected_call(setup + self.crash_on_phase(plans[1]["operation_id"], "reserved"), "migration", *arguments[1], "--approve-hash", plans[1]["plan_hash"], expected=2)
        abandon = self.call("safety-operation", "--operation-id", plans[0]["operation_id"], "--action", "abandon-preview")
        self.call("safety-operation", "--operation-id", plans[0]["operation_id"], "--action", "abandon", "--approve-hash", abandon["approval_hash"])
        self.injected_call(setup, "migration", *arguments[1], "--approve-hash", plans[1]["plan_hash"])
        first_target, first_volume = volumes[0]
        verified_args = ("--artifact-id", ids[0], "--volume-id", first_volume, "--destination", str(first_target / "verified payload"))
        verified = self.call("migration", *verified_args)
        self.injected_call(setup + self.crash_on_phase(verified["operation_id"], "verified"), "migration", *verified_args, "--approve-hash", verified["plan_hash"], expected=77)
        small, _ = self.source("small.bin", b"y" * (1024 * 1024))
        target, volume_id = volumes[1]
        small_args = ("--artifact-id", small, "--volume-id", volume_id, "--destination", str(target / "materialisation credit"))
        small_plan = self.call("migration", *small_args)
        self.injected_call(setup, "migration", *small_args, "--approve-hash", small_plan["plan_hash"])
        self.injected_call(setup, "migration", *verified_args, "--operation-id", verified["operation_id"], "--approve-hash", verified["plan_hash"])
        self.assertEqual(self.call("status")["operation_reserved_bytes"], 0)
        medium, _ = self.source("medium.bin", b"z" * (3 * 1024 * 1024))
        medium_args = ("--artifact-id", medium, "--volume-id", first_volume, "--destination", str(first_target / "after completion"))
        medium_plan = self.call("migration", *medium_args)
        self.injected_call(setup, "migration", *medium_args, "--approve-hash", medium_plan["plan_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
