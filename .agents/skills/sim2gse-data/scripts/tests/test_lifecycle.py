"""仅经共用CLI演练生命周期；所有根与数据是临时合成样例。"""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid


CLI = Path(__file__).resolve().parents[1] / "simdata.py"


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

    def call(self, command, *arguments, expected=0):
        result = subprocess.run([sys.executable, "-B", str(CLI), command, "--config", str(self.config), *arguments],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def initialize(self):
        preview = self.call("init-root")
        return self.call("init-root", "--approve-hash", preview["plan_hash"])

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
