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
import ast

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

    def batch_sources(self, directory, values):
        folder = self.root / directory
        folder.mkdir()
        for name, value in values.items():
            (folder / name).write_bytes(value)
        plan = self.call("legacy-register", "--directory", str(folder), "--role", "native")
        result = self.call("legacy-register", "--directory", str(folder), "--role", "native", "--approve-hash", plan["plan_hash"])
        self.assertEqual(len(result["artifacts"]), len(values))
        return [item["artifact_id"] for item in result["artifacts"]]

    def restore_archive(self, archived, destination):
        arguments = ("--archive-id", archived["archive_id"], "--destination", str(destination))
        plan = self.call("restore", *arguments)
        return self.call("restore", *arguments, "--approve-hash", plan["plan_hash"])

    def legacy_writer_cli(self):
        # 真实历史writer源码夹具，仅替换隔离CLI副本的版本；不是业务函数mock。
        original = lifecycle.CLI.read_text(encoding="utf-8")
        node = next(node for node in ast.parse(original).body if isinstance(node, ast.FunctionDef) and node.name == "create_archive")
        lines = original.splitlines(keepends=True)
        writer = (Path(__file__).parent / "fixtures/archive_format1_single_member.txt").read_text(encoding="utf-8")
        copied = Path(self.temporary.name) / "legacy skill copy" / "scripts" / "simdata.py"
        copied.parent.mkdir(parents=True)
        copied.write_text("".join(lines[:node.lineno - 1]) + writer + "\n" + "".join(lines[node.end_lineno:]), encoding="utf-8")
        shutil.copytree(lifecycle.CLI.parents[1] / "assets", copied.parents[1] / "assets")
        shutil.copyfile(lifecycle.CLI.parents[1] / "SKILL.md", copied.parents[1] / "SKILL.md")
        return copied

    def legacy_call(self, cli, command, *arguments, setup=None, expected=0):
        original = lifecycle.CLI
        try:
            lifecycle.CLI = cli
            if setup is None:
                return self.call(command, *arguments, expected=expected)
            return self.injected_call(setup, command, *arguments, expected=expected)
        finally:
            lifecycle.CLI = original

    def test_empty_boundary_and_large_sources_keep_original_segment_sizes(self):
        self.initialize()
        self.policy["archive_part_bytes"] = 8
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        values = {"empty.bin": b"", "minus.bin": b"a" * 7, "exact.bin": b"b" * 8,
                  "plus.bin": b"c" * 9, "large.bin": b"d" * 17}
        identities = self.batch_sources("boundary sources", values)
        archived = self.archive(*identities)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        expected = {"empty.bin": [(0, 0)], "minus.bin": [(0, 7)], "exact.bin": [(0, 8)],
                    "plus.bin": [(0, 8), (8, 1)], "large.bin": [(0, 8), (8, 8), (16, 1)]}
        members = [member for part in manifest["parts"] for member in part["members"]]
        self.assertGreater(len(manifest["parts"]), 1)
        self.assertTrue(all(sum(member["size"] for member in part["members"]) <= 8 for part in manifest["parts"]))
        self.assertTrue(all(len(part["members"]) <= 1000 for part in manifest["parts"]))
        for source in manifest["sources"]:
            observed = [(member["offset"], member["size"]) for member in members if member["artifact_id"] == source["id"]]
            self.assertEqual(observed, expected[Path(source["path"]).name])
        self.assertEqual([member["artifact_id"] for member in members],
                         [source["id"] for source in manifest["sources"] for _ in expected[Path(source["path"]).name]])
        restored = self.restore_archive(archived, self.root / "boundary restored")
        self.assertEqual({Path(item["path"]).name: Path(item["path"]).read_bytes() for item in restored["restored"]}, values)

    def test_empty_members_use_a_small_real_batch_and_keep_id_count_guard(self):
        self.initialize()
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        identities = self.batch_sources("empty members", {"empty-%02d.bin" % number: b"" for number in range(8)})
        # 只测1000/1001参数边界，不把内存索引冒充1000文件集成。
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE artifacts(id TEXT PRIMARY KEY)")
            namespace = self._main.__globals__
            with self.assertRaisesRegex(namespace["DataError"], "未知对象ID"):
                namespace["archive_sources"](self.root, db, [str(number) for number in range(1000)])
            for ids in ([str(number) for number in range(1001)], ["duplicate", "duplicate"]):
                with self.assertRaisesRegex(namespace["DataError"], "1至1000个不同"):
                    namespace["archive_sources"](self.root, db, ids)
        archived = self.archive(*identities)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["parts"]), 1)
        self.assertEqual(len(manifest["parts"][0]["members"]), 8)
        self.assertTrue(all(member["size"] == 0 for member in manifest["parts"][0]["members"]))
        preview = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(self.root / "empty restored"))
        self.assertEqual(len(preview["manifest"]["sources"]), 8)
        self.assertTrue(all(member["sha256"] == hashlib.sha256(b"").hexdigest() for member in manifest["parts"][0]["members"]))

    def test_later_member_interruption_retains_completed_and_partial_parts_before_retry(self):
        self.initialize()
        self.policy["archive_part_bytes"] = 4
        self.policy["capacity_bytes"] = 32 * 1024 * 1024
        self.save_config()
        values = {"member-%d.bin" % number: b"ok" for number in range(5)}
        identities = self.batch_sources("interrupted members", values)
        arguments = [argument for identity in identities for argument in ("--artifact-id", identity)]
        plan = self.call("archive", *arguments)
        setup = "import tarfile,os\noriginal=tarfile.TarFile.addfile\ncount=0\ndef fail(self,*args,**kwargs):\n global count\n original(self,*args,**kwargs)\n count+=1\n if count==4: os._exit(77)\ntarfile.TarFile.addfile=fail"
        self.injected_call(setup, "archive", *arguments, "--approve-hash", plan["plan_hash"], expected=77)
        stage = self.root / ".staging" / plan["operation_id"]
        completed = stage / "data" / "part-000000.tar.gz"
        partial = stage / "data" / "part-000001.tar.gz.tmp"
        before = completed.read_bytes(), partial.read_bytes()
        self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "writing")
        self.assertGreater(self.call("status")["operation_reserved_bytes"], 0)
        archived = self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
        retained = list(stage.glob("retained-*"))
        self.assertEqual(len(retained), 1)
        self.assertEqual((retained[0] / completed.name).read_bytes(), before[0])
        self.assertEqual((retained[0] / partial.name).read_bytes(), before[1])
        restored = self.restore_archive(archived, self.root / "retry restored")
        self.assertEqual({Path(item["path"]).name: Path(item["path"]).read_bytes() for item in restored["restored"]}, values)

    def test_shared_part_rejects_a_changed_later_member_digest(self):
        self.initialize()
        identities = self.batch_sources("digest sources", {"left.bin": b"abc", "right.bin": b"def"})
        archived = self.archive(*identities)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["parts"]), 1)
        manifest["parts"][0]["members"][1]["sha256"] = "0" * 64
        _, path = self.source("changed-member-manifest.json", json.dumps(manifest).encode())
        target = self.root / "changed member restored"
        self.call("restore", "--manifest", str(path), "--destination", str(target), expected=2)
        self.assertFalse(target.exists())

    def test_old_single_member_layout_and_all_old_operation_phases_remain_compatible(self):
        self.initialize()
        self.policy["archive_part_bytes"] = 8
        self.save_config()
        cli = self.legacy_writer_cli()
        for phase in ("reserved", "writing", "verified", "published", "sealed"):
            with self.subTest(legacy_phase=phase):
                values = {"old-%d.bin" % number: b"old" for number in range(3)}
                identities = self.batch_sources("old " + phase, values)
                arguments = [argument for identity in identities for argument in ("--artifact-id", identity)]
                plan = self.legacy_call(cli, "archive", *arguments)
                self.legacy_call(cli, "archive", *arguments, "--approve-hash", plan["plan_hash"],
                                 setup=self.crash_on_phase(plan["operation_id"], phase), expected=77)
                private = self.root / ".staging" / plan["operation_id"] / "data"
                published = self.root / plan["destination"]
                prior = {path.name: path.read_bytes() for folder in (private, published) if folder.exists() for path in folder.glob("*.tar.gz")}
                archived = self.call("archive", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(archived["phase"], "sealed")
                for name, content in prior.items():
                    self.assertEqual((published / name).read_bytes(), content)
                manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
                if phase in ("verified", "published", "sealed"):
                    self.assertEqual(len(manifest["parts"]), 3)
                    self.assertTrue(all(len(part["members"]) == 1 for part in manifest["parts"]))
                else:
                    self.assertEqual(len(manifest["parts"]), 2)
                restored = self.restore_archive(archived, self.root / ("old restored " + phase))
                self.assertEqual({Path(item["path"]).name: Path(item["path"]).read_bytes() for item in restored["restored"]}, values)

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

    def test_small_sources_share_a_part_without_changing_original_segments(self):
        self.initialize()
        self.policy["archive_part_bytes"] = 8
        self.save_config()
        identities = [self.source("small-%d.bin" % number, value)[0]
                      for number, value in enumerate((b"abc", b"def"))]
        archived = self.archive(*identities)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["parts"]), 1)
        self.assertEqual([member["artifact_id"] for member in manifest["parts"][0]["members"]], sorted(identities))
        self.assertEqual([member["size"] for member in manifest["parts"][0]["members"]], [3, 3])
        self.assertTrue(all(member["offset"] == 0 for member in manifest["parts"][0]["members"]))
        target = self.root / "small restored"
        plan = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target))
        result = self.call("restore", "--archive-id", archived["archive_id"], "--destination", str(target),
                           "--approve-hash", plan["plan_hash"])
        self.assertEqual({Path(item["path"]).name: Path(item["path"]).read_bytes() for item in result["restored"]},
                         {"small-0.bin": b"abc", "small-1.bin": b"def"})

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
                self.assertEqual(result["operation_id"], plan["operation_id"])
                self.assertEqual(result["phase"], "sealed")
                self.assertEqual(len(result["restored"]), 1)
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
        fixtures = self.root / "hostile fixtures"
        fixtures.mkdir()
        for number, (name, kind) in enumerate(cases):
            package = fixtures / ("hostile-%d.tar.gz" % number)
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = 3 if kind == tarfile.REGTYPE else 0
            member.linkname = "../escape" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
            with gzip.GzipFile(filename=str(package), mode="wb", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as tar:
                    tar.addfile(member, io.BytesIO(b"abc") if member.size else None)
            contents = package.read_bytes()
            manifest = json.loads(json.dumps(original_manifest))
            manifest["parts"] = [dict(path=package.relative_to(self.root).as_posix(), sha256=hashlib.sha256(contents).hexdigest(), size=len(contents),
                                       members=[dict(name=name, artifact_id=identity, offset=0, size=3, sha256=hashlib.sha256(b"abc").hexdigest())])]
            (fixtures / ("hostile-%d.json" % number)).write_text(json.dumps(manifest), encoding="utf-8")
        plan = self.call("legacy-register", "--directory", str(fixtures), "--role", "raw")
        registered = self.call("legacy-register", "--directory", str(fixtures), "--role", "raw", "--approve-hash", plan["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), 14)
        for item in registered["artifacts"]:
            contents = (self.root / item["path"]).read_bytes()
            self.assertEqual(item["size"], len(contents))
            self.assertEqual(item["sha256"], hashlib.sha256(contents).hexdigest())
        for number, (name, kind) in enumerate(cases):
            with self.subTest(name=name, kind=kind):
                path = fixtures / ("hostile-%d.json" % number)
                target = self.root / ("hostile-target-%d" % number)
                self.call("restore", "--manifest", str(path), "--destination", str(target), expected=2)
                self.assertFalse(target.exists())





    def test_restore_package_names_reject_windows_aliases_escape_and_nonfiles(self):
        self.initialize()
        identity, _ = self.source(contents=b"safe original bytes")
        archived = self.archive(identity)
        original = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        directory = self.root / "package-directory"
        directory.mkdir()
        invalid = ("", "/absolute", "//server/share", "C:/drive", "../escape", "a/../b", "a\\b",
                   "a//b", "a/./b", "a:b", "NUL", "COM1.json", "LPT9.txt", "trailing.", "trailing ",
                   "nul\x00byte", directory.name, "missing-package.tar.gz")
        inputs = self.root / "invalid manifests"
        inputs.mkdir()
        for number, relative in enumerate(invalid):
            manifest = json.loads(json.dumps(original))
            manifest["parts"][0]["path"] = relative
            (inputs / ("invalid-package-%d.json" % number)).write_bytes(json.dumps(manifest).encode())
        plan = self.call("legacy-register", "--directory", str(inputs), "--role", "native")
        registered = self.call("legacy-register", "--directory", str(inputs), "--role", "native",
                               "--approve-hash", plan["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), len(invalid))
        for number, relative in enumerate(invalid):
            with self.subTest(relative=relative):
                path = inputs / ("invalid-package-%d.json" % number)
                target = self.root / ("invalid-package-target-%d" % number)
                self.call("restore", "--manifest", str(path), "--destination", str(target), expected=2)
                self.assertFalse(target.exists())

    def test_restore_keeps_fresh_parent_and_leaf_reparse_checks_at_both_boundaries(self):
        self.initialize()
        identity, source = self.source("nested/native.json", b"never follow a changed path")
        archived = self.archive(identity)
        manifest = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        package = self.root / manifest["parts"][0]["path"]
        for scope in ("package", "sealed"):
            for part in ("parent", "leaf"):
                with self.subTest(scope=scope, part=part):
                    target = self.root / ("reparse-" + scope + "-" + part)
                    restored = target / source.relative_to(self.root)
                    checked = package if scope == "package" else restored
                    checkpoint = checked.parent if part == "parent" else checked
                    marker = Path(self.temporary.name) / ("reparse-" + scope + "-" + part + ".json")
                    setup = ("from pathlib import Path\nimport sys,json\noriginal=Path.lstat\n"
                             "class Reparse:\n"
                             " def __init__(self,info): self.info=info; self.st_file_attributes=getattr(info,'st_file_attributes',0)|0x400\n"
                             " def __getattr__(self,name): return getattr(self.info,name)\n"
                             "def measured(path,*args,**kwargs):\n"
                             " info=original(path,*args,**kwargs)\n caller=sys._getframe(1)\n parent=sys._getframe(2)\n"
                             " names=[]\n frame=caller\n while frame is not None:\n  names.append(frame.f_code.co_name); frame=frame.f_back\n"
                             " scope=" + repr(scope) + "\n"
                             " boundary=caller.f_code.co_name=='checked_path' and ((scope=='package' and parent.f_code.co_name=='managed_file' and 'verify_archive' in names) or (scope=='sealed' and parent.f_code.co_name=='seal_job'))\n"
                             " if boundary and str(path)==" + repr(str(checkpoint)) + ":\n"
                             "  Path(" + repr(str(marker)) + ").write_text(json.dumps({'reached':True}))\n  return Reparse(info)\n"
                             " return info\nPath.lstat=measured")
                    arguments = ("--archive-id", archived["archive_id"], "--destination", str(target))
                    if scope == "package":
                        self.injected_call(setup, "restore", *arguments, expected=2)
                        self.assertFalse(target.exists())
                    else:
                        plan = self.call("restore", *arguments)
                        self.injected_call(setup, "restore", *arguments, "--approve-hash", plan["plan_hash"], expected=2)
                        self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "published")
                        self.assertEqual(restored.read_bytes(), source.read_bytes())
                    self.assertTrue(json.loads(marker.read_text())["reached"])
                    self.assertEqual(source.read_bytes(), b"never follow a changed path")

    def test_restore_sealing_rejects_missing_or_directory_leaf_after_publication(self):
        self.initialize()
        identity, source = self.source("nested/native.json", b"sealed original bytes")
        archived = self.archive(identity)
        for kind in ("missing", "directory"):
            with self.subTest(kind=kind):
                target = self.root / ("seal-" + kind)
                restored = target / source.relative_to(self.root)
                arguments = ("--archive-id", archived["archive_id"], "--destination", str(target))
                plan = self.call("restore", *arguments)
                marker = Path(self.temporary.name) / ("seal-" + kind + ".json")
                setup = ("from pathlib import Path\nimport sys\noriginal=Path.lstat\nfired=False\n"
                         "def measured(path,*args,**kwargs):\n global fired\n"
                         " if not fired and sys._getframe(1).f_code.co_name=='checked_path' and sys._getframe(2).f_code.co_name=='seal_job' and str(path)==" + repr(str(restored)) + ":\n"
                         "  fired=True\n  path.unlink()\n"
                         + ("  path.mkdir()\n" if kind == "directory" else "")
                         + "  Path(" + repr(str(marker)) + ").write_text('reached')\n"
                         " return original(path,*args,**kwargs)\nPath.lstat=measured")
                self.injected_call(setup, "restore", *arguments, "--approve-hash", plan["plan_hash"], expected=2)
                self.assertEqual(marker.read_text(), "reached")
                self.assertEqual(self.call("operation", "--operation-id", plan["operation_id"])["phase"], "published")
                self.assertEqual(source.read_bytes(), b"sealed original bytes")

    def test_archive_preview_does_not_decode_unrelated_pending_operation_plans(self):
        self.initialize()
        pending, _ = self.source("pending.json", b"pending bytes")
        preview = self.call("archive", "--artifact-id", pending)
        self.injected_call(self.crash_on_phase(preview["operation_id"], "reserved"), "archive",
                           "--artifact-id", pending, "--approve-hash", preview["plan_hash"], expected=77)
        directory = self.root / "another batch"
        directory.mkdir()
        for number in range(3):
            (directory / ("native-%d.json" % number)).write_bytes(b"{}")
        plan = self.call("legacy-register", "--directory", str(directory), "--role", "native")
        registered = self.call("legacy-register", "--directory", str(directory), "--role", "native",
                               "--approve-hash", plan["plan_hash"])
        arguments = [argument for item in registered["artifacts"]
                     for argument in ("--artifact-id", item["artifact_id"])]
        counter = Path(self.temporary.name) / "operation-decode-count.json"
        setup = ("import json,atexit\nfrom pathlib import Path\noriginal=json.loads\ncount=0\n"
                 "def measured(*args,**kwargs):\n global count\n result=original(*args,**kwargs)\n"
                 " if isinstance(result,dict) and result.get('kind') in ('archive','restore') and 'operation_id' in result: count+=1\n"
                 " return result\njson.loads=measured\natexit.register(lambda: Path(" + repr(str(counter)) + ").write_text(str(count)))")
        result = self.injected_call(setup, "archive", *arguments)
        self.assertEqual(len(result["sources"]), 3)
        self.assertEqual(int(counter.read_text()), 0)
        self.assertEqual(self.call("operation", "--operation-id", preview["operation_id"])["phase"], "reserved")


    def test_approved_archive_rechecks_source_after_acquiring_manager_lock(self):
        self.initialize()
        identity, source = self.source("changed-at-lock.json", b"before lock")
        preview = self.call("archive", "--artifact-id", identity)
        if os.name == "nt":
            setup = ("import msvcrt\nfrom pathlib import Path\noriginal=msvcrt.locking\nfired=False\n"
                     "def locking(handle,mode,size):\n global fired\n result=original(handle,mode,size)\n"
                     " if mode==msvcrt.LK_NBLCK and not fired:\n  fired=True\n  Path(" + repr(str(source)) + ").write_bytes(b'after lock')\n"
                     " return result\nmsvcrt.locking=locking")
        else:
            setup = ("import fcntl\nfrom pathlib import Path\noriginal=fcntl.flock\nfired=False\n"
                     "def locking(handle,mode):\n global fired\n result=original(handle,mode)\n"
                     " if mode & fcntl.LOCK_EX and not fired:\n  fired=True\n  Path(" + repr(str(source)) + ").write_bytes(b'after lock')\n"
                     " return result\nfcntl.flock=locking")
        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", preview["plan_hash"], expected=2)
        self.assertEqual(source.read_bytes(), b"after lock")
        self.assertFalse((self.root / ".archives").exists())
        self.call("operation", "--operation-id", preview["operation_id"], expected=2)

    def test_copy_activity_checks_keep_transitive_run_and_reader_leases(self):
        self.initialize()
        run = self.call("begin", "--request-id", "dependency-run", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1024")
        relative = (Path(run["path"]).relative_to(self.root) / "native.json").as_posix()
        required, _ = self.source("required.json", b"required")
        dependent, _ = self.source(relative, b"dependent")
        self.call("dependency", "--artifact-id", dependent, "--requires", required, "--kind", "durable")
        self.call("archive", "--artifact-id", required, expected=2)
        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")
        reader = self.call("read-lease", "--action", "acquire", "--artifact-id", dependent,
                           "--owner-pid", str(os.getpid()), "--token", "dependent-reader")
        self.call("archive", "--artifact-id", required, expected=2)
        self.call("read-lease", "--action", "release", "--lease-id", reader["lease_id"], "--token", "dependent-reader")
        self.assertTrue(self.call("protect", "--artifact-id", required)["protected"])
        self.assertEqual(len(self.call("archive", "--artifact-id", required)["sources"]), 1)

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

    def test_sqlite_retry_rejects_source_growth_before_creating_payload_image(self):
        self.initialize()
        self.policy["capacity_bytes"] = 3400000
        self.save_config()
        source = self.root / "growing-wal.sqlite3"
        with closing(sqlite3.connect(source)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE entries(payload BLOB)")
            writer.commit()
            arguments = ("--database", str(source), "--request-id", "fixed-payload")
            plan = self.call("backup-sqlite", *arguments)
            self.injected_call(self.crash_on_phase(plan["operation_id"], "reserved"), "backup-sqlite", *arguments,
                               "--approve-hash", plan["plan_hash"], expected=77)
            writer.execute("INSERT INTO entries VALUES (?)", (bytes(1000000),))
            writer.commit()
            self.call("backup-sqlite", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"], expected=2)
            stage = self.root / ".staging" / plan["operation_id"]
            self.assertFalse(list(stage.rglob("image.sqlite3")))
            self.assertFalse((self.root / plan["destination"]).exists())
            self.assertEqual(writer.execute("SELECT length(payload) FROM entries").fetchone()[0], 1000000)
            logical_bytes = self.call("inventory")["logical_bytes"]
            pending_bytes = self.call("status")["operation_reserved_bytes"]
            self.assertLessEqual(logical_bytes + pending_bytes + self.policy["maintenance_reserve_bytes"]
                                 + self.policy["metadata_reserve_bytes"], self.policy["capacity_bytes"])

    def test_long_path_batch_and_large_manifest_preserve_data_on_recovery(self):
        self.initialize()
        self.policy["capacity_bytes"] = 1024 * 1024 * 1024
        self.save_config()
        prefix = "/".join(["nested " + "x" * 180] * 12)
        directory = self.root / prefix
        directory.mkdir(parents=True)
        values = {"native-%03d.json" % number: json.dumps({"sample": number}).encode() for number in range(3)}
        for name, value in values.items():
            (directory / name).write_bytes(value)
        preview = self.call("legacy-register", "--directory", str(directory), "--role", "native")
        registered = self.call("legacy-register", "--directory", str(directory), "--role", "native",
                               "--approve-hash", preview["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), 3)
        identities = [item["artifact_id"] for item in registered["artifacts"]]
        archived = self.archive(*reversed(identities))
        self.assertEqual([item["id"] for item in json.loads(Path(archived["manifest_path"]).read_text())["sources"]], sorted(identities))
        arguments = ("--archive-id", archived["archive_id"], "--destination", str(self.root / "large restore"))
        extended = json.loads(Path(archived["manifest_path"]).read_text(encoding="utf-8"))
        encoded = json.dumps(extended, ensure_ascii=False, separators=(",", ":")).encode()
        extended["metadata_note"] = "x" * (801 * 1024 - len(encoded))
        _, extended_path = self.source("extended-801KiB.json", json.dumps(extended, ensure_ascii=False, separators=(",", ":")).encode())
        measured = self.call("inventory", "--limit", "1000")
        self.assertFalse(measured["truncated"])
        self.policy["capacity_bytes"] = measured["logical_bytes"] + self.policy["maintenance_reserve_bytes"] + self.policy["metadata_reserve_bytes"] + 32768
        self.save_config()
        for rejected in (arguments, ("--manifest", str(extended_path), "--destination", str(self.root / "extended restore"))):
            plan = self.call("restore", *rejected)
            self.assertGreater(plan["metadata_peak_bytes"], len(json.dumps(plan["manifest"]).encode()))
            before = self.call("inventory", "--limit", "1000")["logical_bytes"]
            database_before = hashlib.sha256((self.root / "index.sqlite3").read_bytes()).hexdigest()
            self.assertGreater(plan["reserved_bytes"], 32768)
            self.assertIn("容量", self.call("restore", *rejected, "--approve-hash", plan["plan_hash"], expected=2)["error"])
            self.assertLessEqual(self.call("inventory", "--limit", "1000")["logical_bytes"], before)
            self.assertEqual(hashlib.sha256((self.root / "index.sqlite3").read_bytes()).hexdigest(), database_before)
            self.call("operation", "--operation-id", plan["operation_id"], expected=2)
            self.assertFalse((self.root / ".staging" / plan["operation_id"]).exists())
        self.assertFalse((self.root / "large restore").exists())
        self.policy["capacity_bytes"] = 1024 * 1024 * 1024
        self.save_config()
        for phase in ("verified",):
            with self.subTest(large_phase=phase):
                target = self.root / ("large restore " + phase)
                arguments = ("--archive-id", archived["archive_id"], "--destination", str(target))
                plan = self.call("restore", *arguments)
                self.injected_call(self.crash_on_phase(plan["operation_id"], phase), "restore", *arguments,
                                   "--approve-hash", plan["plan_hash"], expected=77)
                result = self.call("restore", "--operation-id", plan["operation_id"], "--approve-hash", plan["plan_hash"])
                self.assertEqual(result["operation_id"], plan["operation_id"])
                self.assertEqual(result["phase"], "sealed")
                self.assertEqual(len(result["restored"]), 3)
                self.assertEqual({Path(item["path"]).name: Path(item["path"]).read_bytes() for item in result["restored"]}, values)
                # 仅清理本测试新建的Temp恢复副本，让有界盘点逐阶段保持完整。
                self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
                shutil.rmtree(target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
