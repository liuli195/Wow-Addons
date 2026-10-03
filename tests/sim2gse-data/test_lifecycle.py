"""仅经共用CLI演练生命周期；所有根与数据是临时合成样例。"""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid


CLI = Path(__file__).resolve().parents[2] / ".agents/skills/sim2gse-data/scripts/simdata.py"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="simdata 合成 lifecycle ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "data root"
        self.config = Path(self.temporary.name) / "machine.json"
        self.policy = dict(schema_version=1, mode="test", root_id=str(uuid.uuid4()),
                           data_root=str(self.root), production_enabled=False,
                           capacity_bytes=4 * 1024 * 1024, retention_days=1,
                           maintenance_interval_hours=1, maintenance_reserve_bytes=65536,
                           archive_part_bytes=65536, metadata_reserve_bytes=131072, lease_seconds=1)
        self.save_config()

    def save_config(self):
        self.config.write_text(json.dumps(self.policy), encoding="utf-8")

    def injected_call(self, setup, command, *arguments, expected=0):
        # 仅在子进程替换操作系统边界，仍调用公开CLI，不读写内部索引。
        code = setup + "\nimport runpy, sys\nsys.argv=sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')"
        result = subprocess.run([sys.executable, "-B", "-c", code, str(CLI), command,
                                 "--config", str(self.config), *arguments], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expected, result.stderr)
        if expected == 77:
            return
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def test_initialization_rejects_insufficient_capacity_without_publishing_root(self):
        self.policy.update(capacity_bytes=8192, maintenance_reserve_bytes=1, metadata_reserve_bytes=1)
        self.save_config()
        plan = self.call("init-root")
        self.call("init-root", "--approve-hash", plan["plan_hash"], expected=2)
        self.assertFalse(self.root.exists())

    def test_initialization_rejects_insufficient_disk_without_publishing_root(self):
        plan = self.call("init-root")
        self.injected_call("import shutil\nshutil.disk_usage=lambda path: type('Usage',(),{'free':0})()",
                           "init-root", "--approve-hash", plan["plan_hash"], expected=2)
        self.assertFalse(self.root.exists())

    def test_releasing_a_reservation_still_requires_physical_metadata_headroom(self):
        self.initialize()
        begun = self.call("begin", "--request-id", "physical-full", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000")
        source = Path(begun["path"]) / "unfinished.json"
        source.write_bytes(b"keep")
        self.injected_call("import shutil\nshutil.disk_usage=lambda path: type('Usage',(),{'free':0})()",
                           "lease", "--run-id", begun["run_id"], "--token", begun["token"], "--action", "release", expected=2)
        self.assertEqual(self.call("status")["reserved_bytes"], 1000)
        self.assertEqual(source.read_bytes(), b"keep")
        self.call("lease", "--run-id", begun["run_id"], "--token", begun["token"], "--action", "release")

    def test_wal_cache_preview_never_creates_or_modifies_source_side_files(self):
        self.initialize()
        source = self.root / "legacy.sqlite3"
        db = sqlite3.connect(source)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE reusable(key TEXT PRIMARY KEY,value TEXT)")
        db.commit()
        db.close()
        def identities():
            return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in self.root.glob("legacy.sqlite3*")}
        before = identities()
        self.call("cache-references", "--database", str(source), expected=2)
        self.assertEqual(identities(), before)
        db = sqlite3.connect(source)
        try:
            db.execute("INSERT INTO reusable VALUES ('active','{}')")
            db.commit()
            before = identities()
            self.call("cache-references", "--database", str(source), expected=2)
            self.assertEqual(identities(), before)
        finally:
            db.close()

    def test_failed_allocation_with_missing_parents_is_recoverable(self):
        self.initialize()
        obstacle = self.root / "runs"
        obstacle.write_bytes(b"synthetic obstacle")
        owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        try:
            self.call("begin", "--request-id", "blocked", "--owner-pid", str(owner.pid), "--reserve-bytes", "1000", expected=2)
        finally:
            owner.communicate(timeout=10)
        obstacle.unlink()
        run_id = str(uuid.uuid5(uuid.UUID(self.policy["root_id"]), "run:blocked"))
        self.assertEqual(self.call("lease", "--run-id", run_id, "--action", "status")["state"], "allocating")
        plan = self.call("lease", "--run-id", run_id, "--action", "recover-preview")
        self.call("lease", "--run-id", run_id, "--action", "recover", "--approve-hash", plan["plan_hash"])
        self.assertEqual(self.call("status")["reserved_bytes"], 0)
        self.call("begin", "--request-id", "after-recovery", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000")

    def test_process_interruption_after_reservation_is_recoverable(self):
        self.initialize()
        owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        setup = "from pathlib import Path\nimport os\noriginal=Path.mkdir\ndef interrupted(path,*args,**kwargs):\n if path.name=='runs': os._exit(77)\n return original(path,*args,**kwargs)\nPath.mkdir=interrupted"
        try:
            self.injected_call(setup, "begin", "--request-id", "interrupted", "--owner-pid", str(owner.pid),
                               "--reserve-bytes", "1000", "--token", "retained", expected=77)
        finally:
            owner.communicate(timeout=10)
        run_id = str(uuid.uuid5(uuid.UUID(self.policy["root_id"]), "run:interrupted"))
        plan = self.call("lease", "--run-id", run_id, "--action", "recover-preview")
        self.call("lease", "--run-id", run_id, "--action", "recover", "--approve-hash", plan["plan_hash"])
        self.assertEqual(self.call("status")["reserved_bytes"], 0)

    def test_release_and_dead_owner_recovery_work_when_inventory_or_quota_is_exceeded(self):
        self.initialize()
        for number, oversized in enumerate((False, True)):
            with self.subTest(oversized=oversized):
                owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
                begun = self.call("begin", "--request-id", f"over-{number}", "--owner-pid", str(owner.pid), "--reserve-bytes", "1000")
                folder = Path(begun["path"])
                if oversized:
                    payload = folder / "large.json"
                    payload.write_bytes(b"x" * self.policy["capacity_bytes"])
                else:
                    for index in range(1001):
                        (folder / f"{index}.json").touch()
                try:
                    self.call("lease", "--run-id", begun["run_id"], "--token", begun["token"], "--action", "release")
                    self.assertEqual(self.call("status")["reserved_bytes"], 0)
                finally:
                    owner.communicate(timeout=10)
                # 只移除测试自建payload，允许下一种根超额情形独立演练。
                for path in folder.glob("*.json"):
                    if path.name != ".run-id.json":
                        path.unlink()
                dead_owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
                second = self.call("begin", "--request-id", f"recover-over-{number}", "--owner-pid", str(dead_owner.pid), "--reserve-bytes", "1000")
                second_folder = Path(second["path"])
                if oversized:
                    (second_folder / "large.json").write_bytes(b"x" * self.policy["capacity_bytes"])
                else:
                    for index in range(1001):
                        (second_folder / f"{index}.json").touch()
                dead_owner.communicate(timeout=10)
                preview = self.call("lease", "--run-id", second["run_id"], "--action", "recover-preview")
                self.call("lease", "--run-id", second["run_id"], "--action", "recover", "--approve-hash", preview["plan_hash"])
                self.assertEqual(self.call("status")["reserved_bytes"], 0)
                self.assertTrue((second_folder / ("large.json" if oversized else "1000.json")).exists())
                for path in second_folder.glob("*.json"):
                    if path.name != ".run-id.json":
                        path.unlink()

    def call(self, command, *arguments, expected=0):
        result = subprocess.run([sys.executable, "-B", str(CLI), command, "--config", str(self.config), *arguments],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def initialize(self):
        import io
        import runpy
        from contextlib import redirect_stderr, redirect_stdout

        main = runpy.run_path(str(CLI))["main"]
        original = sys.argv

        def invoke(*arguments):
            output, error = io.StringIO(), io.StringIO()
            sys.argv = [str(CLI), "init-root", "--config", str(self.config), *arguments]
            with redirect_stdout(output), redirect_stderr(error):
                code = main()
            self.assertEqual(code, 0, error.getvalue())
            return json.loads(output.getvalue())

        try:
            preview = invoke()
            return invoke("--approve-hash", preview["plan_hash"])
        finally:
            sys.argv = original

    def test_test_root_requires_preview_approval_and_is_bound_to_config(self):
        preview = self.call("init-root")
        self.assertFalse(self.root.exists())
        self.assertIn("计划摘要", self.call("init-root", "--approve-hash", "wrong", expected=2)["error"])
        self.assertFalse(self.root.exists())
        initialized = self.call("init-root", "--approve-hash", preview["plan_hash"])
        self.assertEqual(initialized["root_id"], self.policy["root_id"])
        report = self.call("status")
        self.assertEqual(report["root_id"], self.policy["root_id"])
        self.assertEqual(report["registered_artifacts"], 0)
        self.assertFalse(report["production_enabled"])
        self.policy["root_id"] = str(uuid.uuid4())
        self.save_config()
        self.assertIn("绑定", self.call("init-root", "--approve-hash", preview["plan_hash"], expected=2)["error"])

    def test_registration_is_previewed_stable_and_resolves_original_bytes(self):
        self.initialize()
        source = self.root / "native.json"
        source.write_bytes(b"hello")
        preview = self.call("register", "--path", str(source), "--role", "native")
        self.assertEqual(self.call("status")["registered_artifacts"], 0)
        self.assertEqual(preview["sha256"], "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        applied = self.call("register", "--path", str(source), "--role", "native", "--approve-hash", preview["plan_hash"])
        repeated = self.call("register", "--path", str(source), "--role", "native", "--approve-hash", preview["plan_hash"])
        self.assertEqual(applied["artifact_id"], repeated["artifact_id"])
        resolved = self.call("resolve", "--artifact-id", applied["artifact_id"])
        self.assertEqual(resolved["path"], str(source))
        self.assertEqual(source.read_bytes(), b"hello")
        self.assertEqual(self.call("status")["registered_artifacts"], 1)

    def test_begin_finish_reserves_seals_and_resolves_a_new_run(self):
        self.initialize()
        begun = self.call("begin", "--request-id", "synthetic-run", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1024")
        self.assertEqual(self.call("status")["reserved_bytes"], 1024)
        (Path(begun["path"]) / "native.json").write_bytes(b"hello")
        finished = self.call("finish", "--run-id", begun["run_id"], "--token", begun["token"], "--outcome", "failed")
        self.assertEqual(finished["outcome"], "failed")
        self.assertTrue(finished["sealed"])
        self.assertEqual(self.call("status")["reserved_bytes"], 0)
        artifact = self.call("resolve", "--artifact-id", finished["artifact_ids"][0])
        self.assertEqual(Path(artifact["path"]).read_bytes(), b"hello")

    def registered(self, name="native.json", role="native"):
        source = self.root / name
        source.write_bytes(b"hello")
        plan = self.call("register", "--path", str(source), "--role", role)
        return self.call("register", "--path", str(source), "--role", role, "--approve-hash", plan["plan_hash"])["artifact_id"]

    def test_finish_retry_is_idempotent_and_rejects_changed_members(self):
        self.initialize()
        args = ("--request-id", "retry", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1024", "--token", "stable-token")
        begun = self.call("begin", *args)
        self.assertEqual(self.call("begin", *args)["run_id"], begun["run_id"])
        folder = Path(begun["path"])
        (folder / "native.json").write_bytes(b"hello")
        finish = ("--run-id", begun["run_id"], "--token", "stable-token", "--outcome", "success")
        first = self.call("finish", *finish)
        self.assertEqual(self.call("finish", *finish), first)
        (folder / "extra.json").write_bytes(b"extra")
        self.call("finish", *finish, expected=2)
        self.assertEqual(self.call("status")["registered_artifacts"], 1)

    def test_concurrent_reservations_cannot_oversell_capacity(self):
        self.policy["capacity_bytes"] = 1600000
        self.save_config()
        self.initialize()
        children = [subprocess.Popen([sys.executable, "-B", str(CLI), "begin", "--config", str(self.config),
                    "--request-id", str(number), "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000000"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8") for number in range(2)]
        results = [(child, child.communicate(timeout=30)) for child in children]
        winners = [json.loads(output[0]) for child, output in results if child.returncode == 0]
        self.assertEqual(len(winners), 1, results)
        self.assertTrue(all(child.returncode in (0, 2) for child, _ in results))
        self.assertEqual(self.call("status")["reserved_bytes"], 1000000)
        self.call("begin", "--request-id", "no-room", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000000", expected=2)
        winner = winners[0]
        self.call("lease", "--run-id", winner["run_id"], "--token", winner["token"], "--action", "release")
        self.call("begin", "--request-id", "room-again", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000000")

    def test_dead_owner_requires_approved_recovery_without_deleting_payload(self):
        self.initialize()
        owner = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        self.addCleanup(lambda: owner.poll() is None and owner.kill())
        begun = self.call("begin", "--request-id", "dead", "--owner-pid", str(owner.pid), "--reserve-bytes", "1000")
        source = Path(begun["path"]) / "unfinished.json"
        source.write_bytes(b"unfinished")
        owner.communicate(timeout=10)
        preview = self.call("lease", "--run-id", begun["run_id"], "--action", "recover-preview")
        self.call("lease", "--run-id", begun["run_id"], "--action", "recover", "--approve-hash", "wrong", expected=2)
        self.assertEqual(self.call("status")["reserved_bytes"], 1000)
        self.call("lease", "--run-id", begun["run_id"], "--action", "recover", "--approve-hash", preview["plan_hash"])
        self.assertEqual(self.call("status")["reserved_bytes"], 0)
        self.assertEqual(source.read_bytes(), b"unfinished")

    def test_changed_registration_preview_and_oversized_run_are_rejected(self):
        self.initialize()
        source = self.root / "native.json"
        source.write_bytes(b"hello")
        plan = self.call("register", "--path", str(source), "--role", "native")
        source.write_bytes(b"changed")
        self.call("register", "--path", str(source), "--role", "native", "--approve-hash", plan["plan_hash"], expected=2)
        self.assertEqual(self.call("status")["registered_artifacts"], 0)
        begun = self.call("begin", "--request-id", "oversized", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1")
        (Path(begun["path"]) / "native.json").write_bytes(b"oversized")
        self.call("finish", "--run-id", begun["run_id"], "--token", begun["token"], "--outcome", "success", expected=2)
        self.assertEqual(self.call("status")["reserved_bytes"], 1)

    def test_existing_runner_file_is_allowed_but_an_occupied_lock_blocks_writes(self):
        self.initialize()
        artifact = self.registered()
        lock = self.root / ".runner.lock"
        lock.write_bytes(b"0")
        self.assertFalse(self.call("protect", "--artifact-id", artifact)["protected"])
        with lock.open("r+b") as handle:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.assertIn("runner-lock", self.call("protect", "--artifact-id", artifact)["reasons"])
                self.call("register", "--path", str(self.root / "native.json"), "--role", "native", expected=2)
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        self.assertFalse(self.call("protect", "--artifact-id", artifact)["protected"])

    def test_pins_durable_and_unknown_references_block_cache_invalidation(self):
        self.initialize()
        artifact = self.registered()
        self.call("reference", "--artifact-id", artifact, "--owner", "cache:synthetic", "--kind", "cache", "--action", "add")
        self.call("pin", "--artifact-id", artifact, "--label", "acceptance", "--action", "add")
        protection = self.call("protect", "--artifact-id", artifact)
        self.assertIn("pin:acceptance", protection["reasons"])
        self.assertIn("保护", self.call("reference", "--artifact-id", artifact, "--owner", "cache:synthetic", "--action", "invalidate-preview", expected=2)["error"])
        self.call("pin", "--artifact-id", artifact, "--label", "acceptance", "--action", "remove")
        preview = self.call("reference", "--artifact-id", artifact, "--owner", "cache:synthetic", "--action", "invalidate-preview")
        self.assertTrue(preview["may_recompute"])
        self.call("reference", "--artifact-id", artifact, "--owner", "cache:synthetic", "--action", "invalidate", "--approve-hash", preview["plan_hash"])
        self.assertEqual(self.call("protect", "--artifact-id", artifact)["cache_references"], [])
        self.call("reference", "--artifact-id", artifact, "--owner", "analysis:synthetic", "--kind", "durable", "--action", "add")
        self.call("reference", "--artifact-id", artifact, "--owner", "unknown:synthetic", "--kind", "unknown", "--action", "add")
        self.call("reference", "--artifact-id", artifact, "--owner", "cache:again", "--kind", "cache", "--action", "add")
        reasons = self.call("protect", "--artifact-id", artifact)["reasons"]
        self.assertIn("durable:analysis:synthetic", reasons)
        self.assertIn("unknown:unknown:synthetic", reasons)
        self.call("reference", "--artifact-id", artifact, "--owner", "cache:again", "--action", "invalidate-preview", expected=2)

    def test_expired_heartbeat_does_not_clear_a_live_owner_or_reused_pid(self):
        self.initialize()
        begun = self.call("begin", "--request-id", "lease", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1000")
        time.sleep(1.05)
        status = self.call("lease", "--run-id", begun["run_id"], "--action", "status")
        self.assertTrue(status["heartbeat_expired"])
        self.assertEqual(status["owner_state"], "alive")
        self.call("lease", "--run-id", begun["run_id"], "--action", "recover-preview", expected=2)
        mismatch = self.call("begin", "--request-id", "pid-reuse", "--owner-pid", str(os.getpid()),
                             "--owner-start", "stale-birth-identity", "--reserve-bytes", "1000", expected=2)
        self.assertIn("PID", mismatch["error"])
        self.call("lease", "--run-id", begun["run_id"], "--action", "heartbeat", "--token", begun["token"])
        self.call("lease", "--run-id", begun["run_id"], "--action", "release", "--token", begun["token"])
        self.assertEqual(self.call("status")["reserved_bytes"], 0)

    def test_old_cache_adapter_is_read_only_and_preserves_original_native_path(self):
        self.initialize()
        folder = self.root / "legacy" / "batches" / "k"
        folder.mkdir(parents=True)
        native = folder / "native.json"
        native.write_bytes(b"hello")
        preview = self.call("register", "--path", str(native), "--role", "native")
        artifact = self.call("register", "--path", str(native), "--role", "native", "--approve-hash", preview["plan_hash"])["artifact_id"]
        database = self.root / "cache.sqlite3"
        db = sqlite3.connect(database)
        db.execute("CREATE TABLE reusable(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        value = dict(status="success", origin=str(self.root / "legacy"), artifact="batches/k",
                     sha256=preview["sha256"], request={"purpose": "search"}, dps=10, samples=2)
        db.execute("INSERT INTO reusable VALUES (?,?)", ("synthetic-key", json.dumps(value)))
        db.execute("INSERT INTO reusable VALUES (?,?)", ("broken-key", "not-json"))
        db.commit()
        db.close()
        original = database.read_bytes()
        last_used = self.call("protect", "--artifact-id", artifact)["last_used"]
        plan = self.call("cache-references", "--database", str(database))
        self.assertEqual(database.read_bytes(), original)
        self.call("cache-references", "--database", str(database), "--approve-hash", plan["plan_hash"])
        safety = self.call("protect", "--artifact-id", artifact)
        self.assertTrue(safety["protected"])
        self.assertIn("unknown-legacy-references", safety["reasons"])
        self.assertTrue(any(reason.startswith("durable:legacy-path:") for reason in safety["reasons"]))
        self.assertEqual(safety["last_used"], last_used)
        self.assertEqual(database.read_bytes(), original)
        self.assertEqual(native.read_bytes(), b"hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
