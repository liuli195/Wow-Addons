"""归档、恢复及SQLite备份的公开CLI回归；仅隔离合成数据。"""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import os
import gzip
import io
import tarfile
import shutil
import unittest

import test_lifecycle as lifecycle


class ArchiveTests(unittest.TestCase):
    setUp = lifecycle.LifecycleTests.setUp
    save_config = lifecycle.LifecycleTests.save_config
    call = lifecycle.LifecycleTests.call
    initialize = lifecycle.LifecycleTests.initialize
    injected_call = lifecycle.LifecycleTests.injected_call

    def source(self, name="native.bin", contents=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents if contents is not None else bytes(range(256)) * 301)
        plan = self.call("register", "--path", str(path), "--role", "native")
        result = self.call("register", "--path", str(path), "--role", "native", "--approve-hash", plan["plan_hash"])
        return result["artifact_id"], path

    def archive(self, *ids):
        arguments = [argument for identity in ids for argument in ("--artifact-id", identity)]
        plan = self.call("archive", *arguments)
        return self.call("archive", *arguments, "--approve-hash", plan["plan_hash"])

    def test_streamed_parts_restore_original_bytes_without_touching_business_last_used(self):
        self.initialize()
        identity, source = self.source("输入 空格/native.bin")
        last_used = self.call("protect", "--artifact-id", identity)["last_used"]
        plan = self.call("archive", "--artifact-id", identity)
        self.assertFalse((self.root / ".archives").exists())
        result = self.call("archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"])
        self.assertEqual(result["archive_id"], plan["operation_id"])
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["parts"]), 2)
        destination = self.root / "restored tree"
        preview = self.call("restore", "--archive-id", result["archive_id"], "--destination", str(destination))
        restored = self.call("restore", "--archive-id", result["archive_id"], "--destination", str(destination),
                             "--approve-hash", preview["plan_hash"])
        self.assertEqual(Path(restored["restored"][0]["path"]).read_bytes(), source.read_bytes())
        self.assertEqual(self.call("protect", "--artifact-id", identity)["last_used"], last_used)
        self.assertEqual(self.call("operation", "--operation-id", result["operation_id"])["phase"], "sealed")
        self.assertEqual(self.call("status")["operation_reserved_bytes"], 0)
        source.unlink()  # 仅删除本测试创建的合成原件，演练恢复位置解析。
        self.assertEqual(Path(self.call("resolve", "--artifact-id", identity, "--inspect")["path"]).read_bytes(),
                         bytes(range(256)) * 301)

    def test_restore_rejects_corruption_and_existing_destination(self):
        self.initialize()
        identity, source = self.source()
        result = self.archive(identity)
        destination = self.root / "existing"
        destination.mkdir()
        (destination / "user.txt").write_bytes(b"keep")
        self.call("restore", "--archive-id", result["archive_id"], "--destination", str(destination), expected=2)
        self.assertEqual((destination / "user.txt").read_bytes(), b"keep")
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        part = self.root / manifest["parts"][0]["path"]
        part.write_bytes(part.read_bytes()[:-8])
        target = self.root / "not-published"
        self.call("restore", "--archive-id", result["archive_id"], "--destination", str(target), expected=2)
        self.assertFalse(target.exists())
        self.assertEqual(source.read_bytes(), bytes(range(256)) * 301)

    def test_archive_capacity_and_active_run_fail_before_publishing(self):
        self.initialize()
        identity, _ = self.source()
        self.policy["capacity_bytes"] = 400000
        self.save_config()
        plan = self.call("archive", "--artifact-id", identity)
        self.call("archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=2)
        self.assertFalse((self.root / ".archives").exists())
        self.assertFalse((self.root / ".staging").exists())

    def test_sqlite_backup_keeps_committed_wal_rows_and_archives_its_original_image(self):
        self.initialize()
        source = self.root / "legacy.sqlite3"
        db = sqlite3.connect(source)
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records(value INTEGER)")
        db.executemany("INSERT INTO records VALUES (?)", [(1,), (2,), (3,)])
        db.commit()
        db.execute("INSERT INTO records VALUES (4)")  # 未提交，不得进入一致映像。
        before = source.read_bytes()
        args = ("--database", str(source), "--request-id", "wal-copy")
        plan = self.call("backup-sqlite", *args)
        result = self.call("backup-sqlite", *args, "--approve-hash", plan["plan_hash"])
        self.assertEqual(source.read_bytes(), before)
        image = Path(result["path"])
        with closing(sqlite3.connect(image.as_uri() + "?mode=ro", uri=True)) as copied:
            self.assertEqual(copied.execute("SELECT value FROM records ORDER BY value").fetchall(), [(1,), (2,), (3,)])
        self.assertEqual(image.read_bytes()[18:20], b"\x01\x01")
        self.assertEqual(self.call("backup-sqlite", *args, "--approve-hash", plan["plan_hash"])["artifact_id"], result["artifact_id"])
        self.assertEqual(self.call("resolve", "--artifact-id", result["artifact_id"], "--inspect")["sha256"], hashlib.sha256(image.read_bytes()).hexdigest())
        archived = self.archive(result["artifact_id"])
        target = self.root / "restored database"
        preview = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target))
        restored = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target), "--approve-hash", preview["plan_hash"])
        self.assertEqual(Path(restored["restored"][0]["path"]).read_bytes(), image.read_bytes())

    def test_archive_restart_after_partial_write_retains_bytes_and_reservation(self):
        self.initialize()
        identity, source = self.source()
        plan = self.call("archive", "--artifact-id", identity)
        setup = "import tarfile,os\noriginal=tarfile.TarFile.addfile\ndef fail(self,*a,**k):\n original(self,*a,**k)\n os._exit(77)\ntarfile.TarFile.addfile=fail\n"
        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=77)
        self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "writing")
        self.assertGreater(self.call("status")["operation_reserved_bytes"], 0)
        result = self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
        self.assertEqual(result["phase"], "sealed")
        self.assertTrue(list((self.root / ".staging" / plan["operation_id"]).glob("retained-*")))
        self.assertEqual(source.read_bytes(), bytes(range(256)) * 301)
        self.assertEqual(self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])["archive_id"], result["archive_id"])

    def test_restart_after_publish_checks_identity_before_sealing(self):
        self.initialize()
        identity, _ = self.source()
        plan = self.call("archive", "--artifact-id", identity)
        setup = "import os\noriginal=os.replace\ndef fail(a,b,*args,**kw):\n result=original(a,b,*args,**kw)\n if '.archives' in str(b): os._exit(77)\n return result\nos.replace=fail\n"
        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=77)
        self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "verified")
        result = self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
        self.assertEqual(result["phase"], "sealed")
        restored_path = self.root / "restore interrupted"
        preview = self.call("restore", "--archive-id", result["archive_id"], "--destination", str(restored_path))
        setup = "import os\noriginal=os.replace\ndef fail(a,b,*args,**kw):\n result=original(a,b,*args,**kw)\n if 'restore interrupted' in str(b): os._exit(77)\n return result\nos.replace=fail\n"
        self.injected_call(setup, "restore", "--archive-id", result["archive_id"], "--destination", str(restored_path), "--approve-hash", preview["plan_hash"], expected=77)
        restored = self.call("restore", "--operation-id", preview["operation_id"], "--approve-hash", preview["plan_hash"])
        self.assertEqual(Path(restored["restored"][0]["path"]).read_bytes(), bytes(range(256)) * 301)

    def test_disk_full_leaves_originals_and_no_publish(self):
        self.initialize()
        identity, source = self.source()
        plan = self.call("archive", "--artifact-id", identity)
        setup = "import shutil\nfrom collections import namedtuple\nshutil.disk_usage=lambda path:namedtuple('usage','total used free')(100,100,0)\n"
        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=2)
        self.assertFalse((self.root / ".staging").exists())
        self.assertEqual(source.read_bytes(), bytes(range(256)) * 301)

    def test_abandon_is_explicit_and_does_not_delete_partial_products(self):
        self.initialize()
        identity, _ = self.source()
        plan = self.call("archive", "--artifact-id", identity)
        setup = "import tarfile,os\noriginal=tarfile.TarFile.addfile\ndef fail(self,*a,**k):\n original(self,*a,**k)\n os._exit(77)\ntarfile.TarFile.addfile=fail\n"
        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", plan["plan_hash"], expected=77)
        files = list((self.root / ".staging").rglob("*.tmp"))
        preview = self.call("operation", "--operation-id", plan["operation_id"], "--action", "abandon-preview")
        self.call("operation", "--operation-id", plan["operation_id"], "--action", "abandon", "--approve-hash", "wrong", expected=2)
        self.call("operation", "--operation-id", plan["operation_id"], "--action", "abandon", "--approve-hash", preview["approval_hash"])
        self.assertEqual(self.call("status")["operation_reserved_bytes"], 0)
        self.assertTrue(all(path.exists() for path in files))

    def test_sqlite_index_backup_is_consistent_and_normal_registration_rejects_sqlite(self):
        self.initialize()
        self.source(contents=b"index snapshot")
        source = self.root / "index.sqlite3"
        preview = self.call("backup-sqlite", "--database", str(source), "--request-id", "metadata-index")
        result = self.call("backup-sqlite", "--database", str(source), "--request-id", "metadata-index", "--approve-hash", preview["plan_hash"])
        with closing(sqlite3.connect(Path(result["path"]).as_uri() + "?mode=ro", uri=True)) as db:
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0], self.policy["root_id"])
        self.call("register", "--path", result["path"], expected=2)

    def crash_on_phase(self, operation_id, phase):
        return ("import sqlite3,os\noriginal=sqlite3.connect\n"
                "class CrashConnection(sqlite3.Connection):\n"
                " def commit(self):\n  super().commit()\n"
                "  try:\n   row=self.execute(\"SELECT phase FROM jobs WHERE id=?\",(" + repr(operation_id) + ",)).fetchone()\n"
                "  except sqlite3.OperationalError: return\n"
                "  if row and row[0]==" + repr(phase) + ": os._exit(77)\n"
                "def connect(*a,**k):\n k['factory']=CrashConnection\n return original(*a,**k)\nsqlite3.connect=connect\n")

    def test_every_persistent_archive_phase_is_recoverable_and_idempotent(self):
        self.initialize()
        for phase in ("reserved", "writing", "verified", "published", "sealed"):
            with self.subTest(phase=phase):
                identity, source = self.source("phase-" + phase + ".bin", b"bytes for " + phase.encode())
                plan = self.call("archive", "--artifact-id", identity)
                self.injected_call(self.crash_on_phase(plan["operation_id"], phase), "archive", "--artifact-id", identity,
                                   "--approve-hash", plan["plan_hash"], expected=77)
                self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], phase)
                result = self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(result["phase"], "sealed")
                self.assertEqual(self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"]), result)
                self.assertEqual(source.read_bytes(), b"bytes for " + phase.encode())

    def test_every_persistent_restore_phase_is_recoverable(self):
        self.initialize()
        identity, source = self.source(contents=b"restore stages")
        archived = self.archive(identity)
        for phase in ("reserved", "writing", "verified", "published", "sealed"):
            with self.subTest(phase=phase):
                target = self.root / ("restore-" + phase)
                plan = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target))
                self.injected_call(self.crash_on_phase(plan["operation_id"], phase), "restore", "--archive-id", archived["archive_id"],
                                   "--destination", str(target), "--approve-hash", plan["plan_hash"], expected=77)
                result = self.call("restore", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(Path(result["restored"][0]["path"]).read_bytes(), source.read_bytes())

    def test_restore_refuses_parent_escape_and_managed_directory(self):
        self.initialize()
        identity, _ = self.source(contents=b"paths")
        archived = self.archive(identity)
        for path in (self.root / ".." / "escaped", self.root / ".staging" / "bad", self.root / "NUL"):
            self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(path), expected=2)

    def test_active_run_and_occupied_runner_lock_block_archive(self):
        self.initialize()
        run = self.call("begin", "--request-id", "active-source", "--owner-pid", str(os.getpid()), "--reserve-bytes", "131072", "--token", "synthetic-owner")
        identity, _ = self.source((Path(run["path"]).relative_to(self.root) / "native.bin").as_posix(), b"active")
        self.call("archive", "--artifact-id", identity, expected=2)
        identity, source = self.source("locked/native.bin", b"locked")
        lock = source.parent / ".runner.lock"
        lock.write_bytes(b"x")
        with lock.open("r+b") as handle:
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                self.call("archive", "--artifact-id", identity, expected=2)
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def test_registered_hostile_tar_members_are_rejected_before_destination_creation(self):
        self.initialize()
        identity, _ = self.source(contents=b"abc")
        archived = self.archive(identity)
        original_manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        cases = [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("C:/drive", tarfile.REGTYPE),
                 ("NUL", tarfile.REGTYPE), ("safe", tarfile.SYMTYPE), ("safe", tarfile.LNKTYPE), ("safe", tarfile.XHDTYPE)]
        for number, (name, kind) in enumerate(cases):
            with self.subTest(name=name, kind=kind):
                package = self.root / ("hostile-%d.tar.gz" % number)
                member = tarfile.TarInfo(name)
                member.type = kind
                member.size = 3 if kind == tarfile.REGTYPE else 0
                member.linkname = "../escape" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
                with gzip.GzipFile(filename=str(package), mode="wb", mtime=0) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as tar:
                        tar.addfile(member, io.BytesIO(b"abc") if member.size else None)
                plan = self.call("register", "--path", str(package), "--role", "raw")
                self.call("register", "--path", str(package), "--role", "raw", "--approve-hash", plan["plan_hash"])
                manifest = json.loads(json.dumps(original_manifest))
                manifest["parts"] = [dict(path=package.relative_to(self.root).as_posix(), sha256=plan["sha256"], size=plan["size"],
                                           members=[dict(name=name, artifact_id=identity, offset=0, size=3, sha256=hashlib.sha256(b"abc").hexdigest())])]
                path = self.root / ("hostile-%d.json" % number)
                path.write_text(json.dumps(manifest), encoding="utf-8")
                registration = self.call("register", "--path", str(path), "--role", "raw")
                self.call("register", "--path", str(path), "--role", "raw", "--approve-hash", registration["plan_hash"])
                target = self.root / ("hostile-target-%d" % number)
                self.call("restore", "--manifest", str(path), "--destination", str(target), expected=2)
                self.assertFalse(target.exists())

    def test_long_windows_paths_restore_without_materializing_absolute_tar_members(self):
        self.initialize()
        relative = "/".join(["long " + "x" * 70] * 4) + "/native.bin"
        identity, source = self.source(relative, b"long path original")
        archived = self.archive(identity)
        target = self.root / "long restored"
        plan = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target))
        result = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target), "--approve-hash", plan["plan_hash"])
        self.assertEqual(Path(result["restored"][0]["path"]).read_bytes(), source.read_bytes())

    def test_every_persistent_sqlite_backup_phase_is_recoverable(self):
        self.initialize()
        source = self.root / "phase.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.execute("CREATE TABLE test(value TEXT)")
            db.execute("INSERT INTO test VALUES ('committed')")
            db.commit()
        for phase in ("reserved", "writing", "verified", "published", "sealed"):
            with self.subTest(phase=phase):
                arguments = ("--database", str(source), "--request-id", "backup-phase-" + phase)
                plan = self.call("backup-sqlite", *arguments)
                self.injected_call(self.crash_on_phase(plan["operation_id"], phase), "backup-sqlite", *arguments,
                                   "--approve-hash", plan["plan_hash"], expected=77)
                result = self.call("backup-sqlite", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                with closing(sqlite3.connect(Path(result["path"]).as_uri() + "?mode=ro", uri=True)) as db:
                    self.assertEqual(db.execute("SELECT value FROM test").fetchone()[0], "committed")

    def test_interrupted_operation_reservation_blocks_competing_growth(self):
        self.initialize()
        identity, _ = self.source()
        self.policy["capacity_bytes"] = 4 * 1024 * 1024
        self.save_config()
        plan = self.call("archive", "--artifact-id", identity)
        self.injected_call(self.crash_on_phase(plan["operation_id"], "reserved"), "archive", "--artifact-id", identity,
                           "--approve-hash", plan["plan_hash"], expected=77)
        self.call("begin", "--request-id", "competing-growth", "--owner-pid", str(os.getpid()), "--reserve-bytes", "2000000", expected=2)
        self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "reserved")

    def test_registered_decompression_bomb_and_changed_verified_product_are_rejected(self):
        self.initialize()
        identity, _ = self.source(contents=b"abc")
        archived = self.archive(identity)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        name = manifest["parts"][0]["members"][0]["name"]
        header = tarfile.TarInfo(name)
        header.size = 3
        package = self.root / "zero-bomb.tar.gz"
        with gzip.GzipFile(filename=str(package), mode="wb", mtime=0) as stream:
            stream.write(header.tobuf(format=tarfile.USTAR_FORMAT) + b"abc" + bytes(509))
            for _ in range(128):
                stream.write(bytes(1024))
        registration = self.call("register", "--path", str(package), "--role", "raw")
        self.call("register", "--path", str(package), "--role", "raw", "--approve-hash", registration["plan_hash"])
        manifest["parts"][0].update(path=package.relative_to(self.root).as_posix(), size=registration["size"], sha256=registration["sha256"])
        manifest_path = self.root / "zero-bomb.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        plan = self.call("register", "--path", str(manifest_path), "--role", "raw")
        self.call("register", "--path", str(manifest_path), "--role", "raw", "--approve-hash", plan["plan_hash"])
        self.call("restore", "--manifest", str(manifest_path), "--destination", str(self.root / "bomb-target"), expected=2)
        self.assertFalse((self.root / "bomb-target").exists())
        identity, _ = self.source("changed.bin", b"immutable")
        preview = self.call("archive", "--artifact-id", identity)
        self.injected_call(self.crash_on_phase(preview["operation_id"], "verified"), "archive", "--artifact-id", identity,
                           "--approve-hash", preview["plan_hash"], expected=77)
        path = next((self.root / ".staging" / preview["operation_id"] / "data").glob("*.tar.gz"))
        path.write_bytes(b"changed product")
        self.call("archive", "--operation-id", preview["operation_id"], "--approve-hash", preview["plan_hash"], expected=2)
        self.assertFalse((self.root / preview["destination"]).exists())

    def test_restore_rejects_an_externally_registered_package_with_active_lease(self):
        self.initialize()
        identity, _ = self.source(contents=b"leased package")
        archived = self.archive(identity)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        run = self.call("begin", "--request-id", "external-packages", "--owner-pid", str(os.getpid()), "--reserve-bytes", "131072")
        relative = (Path(run["path"]).relative_to(self.root) / "part.tar.gz").as_posix()
        _, package = self.source(relative, (self.root / manifest["parts"][0]["path"]).read_bytes())
        manifest["parts"][0]["path"] = relative
        _, manifest_path = self.source("leased-manifest.json", json.dumps(manifest).encode())
        target = self.root / "leased-restore"
        self.call("restore", "--manifest", str(manifest_path), "--destination", str(target), expected=2)
        self.assertFalse(target.exists())

    def test_resolve_tries_missing_locations_but_never_skips_a_suspicious_copy(self):
        self.initialize()
        identity, original = self.source(contents=b"multiple copies")
        archived = self.archive(identity)
        copies = []
        for directory in ("a", "b"):
            arguments = ("--archive-id", archived["archive_id"], "--destination", str(self.root / directory))
            plan = self.call("restore", *arguments)
            result = self.call("restore", *arguments, "--approve-hash", plan["plan_hash"])
            copies.append(Path(result["restored"][0]["path"]))
        original.write_bytes(b"changed primary")
        self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)
        original.unlink()
        copies[0].write_bytes(b"changed first copy")
        self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)
        copies[0].unlink()
        self.assertEqual(self.call("resolve", "--artifact-id", identity, "--inspect")["path"], str(copies[1]))
        copies[1].write_bytes(b"tampered")
        self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)
        copies[1].unlink()
        self.call("resolve", "--artifact-id", identity, "--inspect", expected=2)

    def test_large_legal_restore_plan_is_admitted_before_any_metadata_write(self):
        self.initialize()
        self.policy["capacity_bytes"] = 1024 * 1024 * 1024
        self.save_config()
        prefix = "/".join(["nested " + "x" * 180] * 12)
        identities = [self.source(prefix + "/native-%03d.json" % number, b"{}")[0] for number in range(220)]
        archived = self.archive(*identities)
        arguments = ("--archive-id", archived["archive_id"], "--destination", str(self.root / "large restore"))
        extended = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        encoded = json.dumps(extended, ensure_ascii=False, separators=(",", ":")).encode()
        extended["metadata_note"] = "x" * (801 * 1024 - len(encoded))
        _, extended_path = self.source("extended-801KiB.json", json.dumps(extended, ensure_ascii=False, separators=(",", ":")).encode())
        measured = self.call("inventory", "--limit", "1000")
        self.assertFalse(measured["truncated"])
        self.policy["capacity_bytes"] = measured["logical_bytes"] + self.policy["maintenance_reserve_bytes"] + self.policy["metadata_reserve_bytes"] + 600000
        self.save_config()
        for rejected in (arguments, ("--manifest", str(extended_path), "--destination", str(self.root / "extended restore"))):
            plan = self.call("restore", *rejected)
            self.assertGreater(plan["metadata_peak_bytes"], len(json.dumps(plan["manifest"]).encode()))
            before = self.call("inventory", "--limit", "1000")["logical_bytes"]
            database_before = hashlib.sha256((self.root / "index.sqlite3").read_bytes()).hexdigest()
            self.call("restore", *rejected, "--approve-hash", plan["plan_hash"], expected=2)
            self.assertLessEqual(self.call("inventory", "--limit", "1000")["logical_bytes"], before)
            self.assertEqual(hashlib.sha256((self.root / "index.sqlite3").read_bytes()).hexdigest(), database_before)
            self.call("operation", "--operation-id", plan["operation_id"], expected=2)
            self.assertFalse((self.root / ".staging" / plan["operation_id"]).exists())
        self.assertFalse((self.root / "large restore").exists())
        self.policy["capacity_bytes"] = 1024 * 1024 * 1024
        self.save_config()
        for phase in ("reserved", "writing", "verified", "published", "sealed"):
            with self.subTest(large_phase=phase):
                target = self.root / ("large restore " + phase)
                arguments = ("--archive-id", archived["archive_id"], "--destination", str(target))
                plan = self.call("restore", *arguments)
                self.injected_call(self.crash_on_phase(plan["operation_id"], phase), "restore", *arguments,
                                   "--approve-hash", plan["plan_hash"], expected=77)
                result = self.call("restore", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(result["phase"], "sealed")
                self.assertEqual(len(result["restored"]), 220)
                self.assertTrue(all(Path(item["path"]).read_bytes() == b"{}" for item in result["restored"]))
                # 仅清理本测试新建的Temp恢复副本，让有界盘点逐阶段保持完整。
                self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
                shutil.rmtree(target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
