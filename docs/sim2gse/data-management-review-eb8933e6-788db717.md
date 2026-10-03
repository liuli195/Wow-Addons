# eb8933e6至788db717只读审查原文

固定范围：eb8933e6e2808c5f3c478dd433bc69d3c99bf9b1..788db71710d5340265e469c90d7f24f6c339cd43。以下只采集git对象原文与测试断言摘要，不作审查结论。

展示说明：diff围栏中纯空白的上下文行展示为空行，满足仓库空白检查；其余Git对象代码原文保持。此展示文件不作为git apply补丁，精确diff可用文中固定范围的git diff命令复现。

## Runtime完整差异

```diff
diff --git a/.agents/skills/sim2gse-data/scripts/simdata.py b/.agents/skills/sim2gse-data/scripts/simdata.py
index cb6bb96d..fc616582 100644
--- a/.agents/skills/sim2gse-data/scripts/simdata.py
+++ b/.agents/skills/sim2gse-data/scripts/simdata.py
@@ -717,31 +717,34 @@ def finish_run(root, policy, args):
     return dict(run_id=args.run_id, sealed=True, outcome=args.outcome, artifact_ids=artifact_ids)


-def protection(root, db, artifact_id, *, own_job=None):
+def protection(root, db, artifact_id, *, own_job=None, activity_only=False):
     artifact = artifact_row(db, artifact_id)
     reasons = []
-    if artifact["role"] in PROTECTED_ROLES:
-        reasons.append("protected-role:" + artifact["role"])
-    if {part.casefold() for part in Path(artifact["path"]).parts} & PROTECTED_DIRECTORIES:
-        reasons.append("protected-evidence-path")
-    reasons.extend("pin:" + row[0] for row in db.execute("SELECT label FROM pins WHERE artifact_id=? ORDER BY label", (artifact_id,)))
+    if not activity_only:
+        if artifact["role"] in PROTECTED_ROLES:
+            reasons.append("protected-role:" + artifact["role"])
+        if {part.casefold() for part in Path(artifact["path"]).parts} & PROTECTED_DIRECTORIES:
+            reasons.append("protected-evidence-path")
+        reasons.extend("pin:" + row[0] for row in db.execute("SELECT label FROM pins WHERE artifact_id=? ORDER BY label", (artifact_id,)))
     references = [dict(row) for row in db.execute("SELECT * FROM refs WHERE target=? ORDER BY owner", (artifact_id,))]
-    reasons.extend(row["kind"] + ":" + row["owner"] for row in references if row["kind"] != "cache")
-    reasons.extend(dependency_protection(root, db, artifact_id, own_job=own_job))
-    if db.execute("SELECT count(*) FROM unknown_refs").fetchone()[0]:
-        reasons.append("unknown-legacy-references")
-    if has_table(db, "jobs"):
-        for job in db.execute("SELECT * FROM jobs WHERE phase NOT IN ('sealed','abandoned')"):
-            plan = json.loads(job["plan"])
-            if any(source["id"] == artifact_id for source in plan.get("sources", plan.get("manifest", {}).get("sources", []))):
-                reasons.append("operation:" + job["id"])
-    if has_table(db, "safety_jobs"):
-        for job in db.execute("SELECT * FROM safety_jobs WHERE phase NOT IN ('sealed','abandoned')"):
-            if job["id"] == own_job:
-                continue
-            safety_plan = json.loads(job["plan"])
-            if any(source["id"] == artifact_id for source in safety_plan.get("sources", safety_plan.get("items", []))):
-                reasons.append("operation:" + job["id"])
+    if not activity_only:
+        reasons.extend(row["kind"] + ":" + row["owner"] for row in references if row["kind"] != "cache")
+    reasons.extend(dependency_protection(root, db, artifact_id, own_job=own_job, activity_only=activity_only))
+    if not activity_only:
+        if db.execute("SELECT count(*) FROM unknown_refs").fetchone()[0]:
+            reasons.append("unknown-legacy-references")
+        if has_table(db, "jobs"):
+            for job in db.execute("SELECT * FROM jobs WHERE phase NOT IN ('sealed','abandoned')"):
+                plan = json.loads(job["plan"])
+                if any(source["id"] == artifact_id for source in plan.get("sources", plan.get("manifest", {}).get("sources", []))):
+                    reasons.append("operation:" + job["id"])
+        if has_table(db, "safety_jobs"):
+            for job in db.execute("SELECT * FROM safety_jobs WHERE phase NOT IN ('sealed','abandoned')"):
+                if job["id"] == own_job:
+                    continue
+                safety_plan = json.loads(job["plan"])
+                if any(source["id"] == artifact_id for source in safety_plan.get("sources", safety_plan.get("items", []))):
+                    reasons.append("operation:" + job["id"])
     if has_table(db, "readers"):
         reasons.extend("read-lease:" + row["id"] + ":" + lease_state(row)
                        for row in db.execute("SELECT * FROM readers WHERE artifact_id=? AND state='active'", (artifact_id,)))
@@ -1461,30 +1464,30 @@ def manage_operation(root, policy, args):
         return dict(preview, applied=True)


-def artifact_image(root, row):
-    with closing(open_index(root)) as db:
-        _, source, manifest = read_location(root, db, row)
+def artifact_image(root, db, row):
+    _, source, manifest = read_location(root, db, row)
     if not row["sealed"]:
         raise DataError("封口文件身份或摘要不匹配")
     return dict(id=row["id"], path=row["path"], role=row["role"], schema_version=row["schema_version"], **manifest)


 def idle_image(root, db, row):
-    if any(reason.startswith(("lease:", "read-lease:", "runner-lock")) for reason in protection(root, db, row["id"])["reasons"]):
+    if any(reason.startswith(("lease:", "read-lease:", "runner-lock")) for reason in protection(root, db, row["id"], activity_only=True)["reasons"]):
         raise DataError("活动租约或文件锁阻止读取生命周期输入")
-    return artifact_image(root, row)
+    return artifact_image(root, db, row)


 def archive_sources(root, db, ids):
     if not ids or len(ids) > 1000 or len(set(ids)) != len(ids):
         raise DataError("归档须列出1至1000个不同的登记ID")
     sources = []
+    index_paths(root)
     for artifact_id in sorted(ids):
         row = artifact_row(db, artifact_id)
-        reasons = protection(root, db, artifact_id)["reasons"]
+        reasons = protection(root, db, artifact_id, activity_only=True)["reasons"]
         if any(reason.startswith(("lease:", "read-lease:", "runner-lock")) for reason in reasons):
             raise DataError("活动租约或文件锁阻止归档")
-        sources.append(artifact_image(root, row))
+        sources.append(artifact_image(root, db, row))
     return sources


@@ -1549,13 +1552,13 @@ def quarantine_retry(root, stage, db, operation_id):
     os.replace(data, destination)


-def create_archive(root, plan, data):
+def create_archive(root, db, plan, data):
     manifest = dict(format=1, root_id=plan["root_id"], archive_id=plan["operation_id"], sources=plan["sources"], parts=[])
     part_size = plan["part_bytes"]
     number = 0
+    index_paths(root)
     for source in plan["sources"]:
-        with closing(open_index(root)) as location_db:
-            source_root, path, current_image = read_location(root, location_db, artifact_row(location_db, source["id"]))
+        source_root, path, current_image = read_location(root, db, artifact_row(db, source["id"]))
         if current_image != {key: source[key] for key in ("sha256", "size", "identity")}:
             raise DataError("归档读取位置或身份改变")
         with runner_locks(source_root, path), path.open("rb") as handle:
@@ -1926,14 +1929,14 @@ def seal_job(root, db, plan):

 def lifecycle_execute(root, policy, args):
     root_marker(root, policy)
-    with closing(open_index(root)) as reader:
-        plan = lifecycle_plan(root, policy, reader, args)
-    preview = dict(plan, plan_hash=digest(plan), applied=False)
     if args.approve_hash is None:
-        return preview
-    if args.approve_hash != digest(plan) or plan["policy_hash"] != digest(policy):
-        raise DataError("操作须批准当前清单及配置摘要")
+        with closing(open_index(root)) as reader:
+            plan = lifecycle_plan(root, policy, reader, args)
+        return dict(plan, plan_hash=digest(plan), applied=False)
     with write_index(root, policy) as db:
+        plan = lifecycle_plan(root, policy, db, args)
+        if args.approve_hash != digest(plan) or plan["policy_hash"] != digest(policy):
+            raise DataError("操作须批准当前清单及配置摘要")
         job = db.execute("SELECT * FROM jobs WHERE id=?", (plan["operation_id"],)).fetchone() if has_table(db, "jobs") else None
         if job and job["phase"] == "sealed":
             check_product(db, plan["operation_id"], owned_path(root, plan["destination"]))
@@ -1941,9 +1944,6 @@ def lifecycle_execute(root, policy, args):
         if job and job["phase"] == "abandoned":
             raise DataError("已放弃操作不能恢复，须新请求")
         if not job:
-            current = lifecycle_plan(root, policy, db, args)
-            if current != plan:
-                raise DataError("计划在批准后发生变化")
             check_budget(root, db, policy, plan["reserved_bytes"])
             lifecycle_tables(db)
             db.execute("INSERT INTO jobs(id,kind,phase,plan,reserved_bytes) VALUES (?,?,?,?,?)", (plan["operation_id"], plan["kind"], "reserved", compact_json(plan, QUERY_BYTES), plan["reserved_bytes"]))
@@ -1978,7 +1978,7 @@ def lifecycle_execute(root, policy, args):
                 if plan["kind"] == "archive":
                     if archive_sources(root, db, [source["id"] for source in plan["sources"]]) != plan["sources"]:
                         raise DataError("归档来源已变化")
-                    manifest = create_archive(root, plan, data)
+                    manifest = create_archive(root, db, plan, data)
                     verify_archive(root, manifest, package_root=data)
                 elif plan["kind"] == "restore":
                     for part in plan["manifest"]["parts"]:
@@ -2008,7 +2008,7 @@ def lifecycle_execute(root, policy, args):
         return operation_result(root, db, job_row(db, plan["operation_id"]))


-def dependency_protection(root, db, artifact_id, *, own_job=None):
+def dependency_protection(root, db, artifact_id, *, own_job=None, activity_only=False):
     pending, seen, reasons = [artifact_id], set(), []
     while pending:
         current = pending.pop()
@@ -2023,7 +2023,7 @@ def dependency_protection(root, db, artifact_id, *, own_job=None):
             continue
         refs = db.execute("SELECT owner,kind FROM refs WHERE target=?", (current,)).fetchall()
         if current != artifact_id:
-            if (row["role"] in PROTECTED_ROLES or {part.casefold() for part in Path(row["path"]).parts} & PROTECTED_DIRECTORIES or
+            if not activity_only and (row["role"] in PROTECTED_ROLES or {part.casefold() for part in Path(row["path"]).parts} & PROTECTED_DIRECTORIES or
                     db.execute("SELECT 1 FROM pins WHERE artifact_id=?", (current,)).fetchone() or any(ref["kind"] != "cache" for ref in refs)):
                 reasons.append("persistent-dependency:" + current)
             if has_table(db, "readers") and db.execute("SELECT 1 FROM readers WHERE artifact_id=? AND state='active'", (current,)).fetchone():
@@ -2035,7 +2035,7 @@ def dependency_protection(root, db, artifact_id, *, own_job=None):
                     pass
             except DataError:
                 reasons.append("runner-lock:dependency:" + current)
-            for table in ("jobs", "safety_jobs"):
+            for table in (() if activity_only else ("jobs", "safety_jobs")):
                 if has_table(db, table):
                     for job in db.execute("SELECT * FROM " + table + " WHERE phase NOT IN ('sealed','abandoned')"):
                         if table == "safety_jobs" and job["id"] == own_job:
@@ -2368,7 +2368,7 @@ def safety_source(root, db, identity, *, destructive=False, own_job=None):
         raise DataError("持久/未知引用、活动租约、锁或尚未批准失效的加速缓存阻止隔离/删除")
     if any(value.startswith(("lease:", "read-lease:", "runner-lock", "operation:")) for value in reasons):
         raise DataError("活动操作、租约或锁阻止位置变更")
-    image = artifact_image(root, row)
+    image = artifact_image(root, db, row)
     if destructive:
         original = managed_file(root, str(root / row["path"]))
         image = dict(id=row["id"], path=row["path"], role=row["role"], schema_version=row["schema_version"],
```

## 五项新增公开CLI测试

- test_batch_archive_preview_reuses_its_index_connection：4/12来源计划含全部来源，连接数不随来源增加。

- test_archive_preview_does_not_decode_unrelated_pending_operation_plans：3来源完整预览；不解码无关操作计划；原reserved操作状态保留。

- test_approved_restore_reads_its_plan_once_under_the_write_lock：封口成功、原字节恢复；完整清单解码一次。

- test_approved_archive_rechecks_source_after_acquiring_manager_lock：OS取锁后改变原件则拒绝，无归档发布和操作登记。

- test_copy_activity_checks_keep_transitive_run_and_reader_leases：消费者运行/读者租约阻止复制，解除后持久保护仍为true但可预览复制。

```diff
diff --git a/tests/sim2gse-data/test_archive.py b/tests/sim2gse-data/test_archive.py
index f7fac2c5..251e9fe3 100644
--- a/tests/sim2gse-data/test_archive.py
+++ b/tests/sim2gse-data/test_archive.py
@@ -287,6 +287,105 @@ class ArchiveTests(unittest.TestCase):
             observed.append(json.loads(counter.read_text()))
         self.assertLessEqual(observed[1] - observed[0], 8 * (12 - 4), observed)

+    def test_batch_archive_preview_reuses_its_index_connection(self):
+        self.initialize()
+        counts = []
+        for size in (4, 12):
+            directory = self.root / ("batch-%d" % size)
+            directory.mkdir()
+            for number in range(size):
+                (directory / ("native-%d.json" % number)).write_bytes(b"{}")
+            preview = self.call("legacy-register", "--directory", str(directory), "--role", "native")
+            registered = self.call("legacy-register", "--directory", str(directory), "--role", "native",
+                                   "--approve-hash", preview["plan_hash"])
+            arguments = [argument for item in registered["artifacts"]
+                         for argument in ("--artifact-id", item["artifact_id"])]
+            counter = Path(self.temporary.name) / ("connect-count-%d.json" % size)
+            setup = ("import sqlite3,atexit,json\nfrom pathlib import Path\noriginal=sqlite3.connect\ncount=0\n"
+                     "def measured(*args,**kwargs):\n global count\n count+=1\n return original(*args,**kwargs)\n"
+                     "sqlite3.connect=measured\natexit.register(lambda: Path(" + repr(str(counter)) + ").write_text(json.dumps(count)))")
+            archived = self.injected_call(setup, "archive", *arguments)
+            self.assertEqual(len(archived["sources"]), size)
+            counts.append(json.loads(counter.read_text()))
+        self.assertLessEqual(counts[1], counts[0], counts)
+
+    def test_archive_preview_does_not_decode_unrelated_pending_operation_plans(self):
+        self.initialize()
+        pending, _ = self.source("pending.json", b"pending bytes")
+        preview = self.call("archive", "--artifact-id", pending)
+        self.injected_call(self.crash_on_phase(preview["operation_id"], "reserved"), "archive",
+                           "--artifact-id", pending, "--approve-hash", preview["plan_hash"], expected=77)
+        directory = self.root / "another batch"
+        directory.mkdir()
+        for number in range(3):
+            (directory / ("native-%d.json" % number)).write_bytes(b"{}")
+        plan = self.call("legacy-register", "--directory", str(directory), "--role", "native")
+        registered = self.call("legacy-register", "--directory", str(directory), "--role", "native",
+                               "--approve-hash", plan["plan_hash"])
+        arguments = [argument for item in registered["artifacts"]
+                     for argument in ("--artifact-id", item["artifact_id"])]
+        counter = Path(self.temporary.name) / "operation-decode-count.json"
+        setup = ("import json,atexit\nfrom pathlib import Path\noriginal=json.loads\ncount=0\n"
+                 "def measured(*args,**kwargs):\n global count\n result=original(*args,**kwargs)\n"
+                 " if isinstance(result,dict) and result.get('kind') in ('archive','restore') and 'operation_id' in result: count+=1\n"
+                 " return result\njson.loads=measured\natexit.register(lambda: Path(" + repr(str(counter)) + ").write_text(str(count)))")
+        result = self.injected_call(setup, "archive", *arguments)
+        self.assertEqual(len(result["sources"]), 3)
+        self.assertEqual(int(counter.read_text()), 0)
+        self.assertEqual(self.call("operation", "--operation-id", preview["operation_id"])["phase"], "reserved")
+
+    def test_approved_restore_reads_its_plan_once_under_the_write_lock(self):
+        self.initialize()
+        identity, source = self.source("approved.json", b"checked original")
+        archived = self.archive(identity)
+        destination = self.root / "single plan restore"
+        arguments = ("--archive-id", archived["archive_id"], "--destination", str(destination))
+        preview = self.call("restore", *arguments)
+        counter = Path(self.temporary.name) / "restore-plan-count.json"
+        setup = ("import json,atexit\nfrom pathlib import Path\noriginal=json.loads\ncount=0\n"
+                 "def measured(*args,**kwargs):\n global count\n result=original(*args,**kwargs)\n"
+                 " if isinstance(result,dict) and result.get('format')==1 and 'archive_id' in result: count+=1\n"
+                 " return result\njson.loads=measured\natexit.register(lambda: Path(" + repr(str(counter)) + ").write_text(str(count)))")
+        result = self.injected_call(setup, "restore", *arguments, "--approve-hash", preview["plan_hash"])
+        self.assertEqual(result["phase"], "sealed")
+        self.assertEqual(Path(result["restored"][0]["path"]).read_bytes(), source.read_bytes())
+        self.assertEqual(int(counter.read_text()), 1)
+
+    def test_approved_archive_rechecks_source_after_acquiring_manager_lock(self):
+        self.initialize()
+        identity, source = self.source("changed-at-lock.json", b"before lock")
+        preview = self.call("archive", "--artifact-id", identity)
+        if os.name == "nt":
+            setup = ("import msvcrt\nfrom pathlib import Path\noriginal=msvcrt.locking\nfired=False\n"
+                     "def locking(handle,mode,size):\n global fired\n result=original(handle,mode,size)\n"
+                     " if mode==msvcrt.LK_NBLCK and not fired:\n  fired=True\n  Path(" + repr(str(source)) + ").write_bytes(b'after lock')\n"
+                     " return result\nmsvcrt.locking=locking")
+        else:
+            setup = ("import fcntl\nfrom pathlib import Path\noriginal=fcntl.flock\nfired=False\n"
+                     "def locking(handle,mode):\n global fired\n result=original(handle,mode)\n"
+                     " if mode & fcntl.LOCK_EX and not fired:\n  fired=True\n  Path(" + repr(str(source)) + ").write_bytes(b'after lock')\n"
+                     " return result\nfcntl.flock=locking")
+        self.injected_call(setup, "archive", "--artifact-id", identity, "--approve-hash", preview["plan_hash"], expected=2)
+        self.assertEqual(source.read_bytes(), b"after lock")
+        self.assertFalse((self.root / ".archives").exists())
+        self.call("operation", "--operation-id", preview["operation_id"], expected=2)
+
+    def test_copy_activity_checks_keep_transitive_run_and_reader_leases(self):
+        self.initialize()
+        run = self.call("begin", "--request-id", "dependency-run", "--owner-pid", str(os.getpid()), "--reserve-bytes", "1024")
+        relative = (Path(run["path"]).relative_to(self.root) / "native.json").as_posix()
+        required, _ = self.source("required.json", b"required")
+        dependent, _ = self.source(relative, b"dependent")
+        self.call("dependency", "--artifact-id", dependent, "--requires", required, "--kind", "durable")
+        self.call("archive", "--artifact-id", required, expected=2)
+        self.call("lease", "--run-id", run["run_id"], "--token", run["token"], "--action", "release")
+        reader = self.call("read-lease", "--action", "acquire", "--artifact-id", dependent,
+                           "--owner-pid", str(os.getpid()), "--token", "dependent-reader")
+        self.call("archive", "--artifact-id", required, expected=2)
+        self.call("read-lease", "--action", "release", "--lease-id", reader["lease_id"], "--token", "dependent-reader")
+        self.assertTrue(self.call("protect", "--artifact-id", required)["protected"])
+        self.assertEqual(len(self.call("archive", "--artifact-id", required)["sources"]), 1)
+
     def test_every_persistent_sqlite_backup_phase_is_recoverable(self):
         self.initialize()
         source = self.root / "phase.sqlite3"
```

## 生命周期执行前（原文）

```python
@contextmanager
def write_index(root, policy):
    write_guard(root, policy)
    with byte_lock(root / ".manager.lock", create=True):
        db = open_index(root, writable=True)
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0] != policy["root_id"]:
                raise DataError("索引身份绑定不符")
            yield db
            db.commit()
        finally:
            db.close()

def lifecycle_execute(root, policy, args):
    root_marker(root, policy)
    with closing(open_index(root)) as reader:
        plan = lifecycle_plan(root, policy, reader, args)
    preview = dict(plan, plan_hash=digest(plan), applied=False)
    if args.approve_hash is None:
        return preview
    if args.approve_hash != digest(plan) or plan["policy_hash"] != digest(policy):
        raise DataError("操作须批准当前清单及配置摘要")
    with write_index(root, policy) as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (plan["operation_id"],)).fetchone() if has_table(db, "jobs") else None
        if job and job["phase"] == "sealed":
            check_product(db, plan["operation_id"], owned_path(root, plan["destination"]))
            return operation_result(root, db, job_row(db, plan["operation_id"]))
        if job and job["phase"] == "abandoned":
            raise DataError("已放弃操作不能恢复，须新请求")
        if not job:
            current = lifecycle_plan(root, policy, db, args)
            if current != plan:
                raise DataError("计划在批准后发生变化")
            check_budget(root, db, policy, plan["reserved_bytes"])
            lifecycle_tables(db)
            db.execute("INSERT INTO jobs(id,kind,phase,plan,reserved_bytes) VALUES (?,?,?,?,?)", (plan["operation_id"], plan["kind"], "reserved", compact_json(plan, QUERY_BYTES), plan["reserved_bytes"]))
            if plan["kind"] == "backup-sqlite":
                source = checked_path(root / plan["source"])
                image = file_manifest(source, allow_sqlite=True)
                source_id = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "artifact:" + os.path.normcase(plan["source"])))
                existing_source = db.execute("SELECT * FROM artifacts WHERE path=?", (plan["source"],)).fetchone()
                if existing_source and existing_source["role"] not in ("sqlite-source", "sqlite-backup"):
                    raise DataError("SQLite源与已登记角色冲突")
                if not existing_source:
                    db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (source_id, plan["source"], "sqlite-source", image["sha256"], image["size"], json.dumps(image["identity"]), 1, 0, time.time()))
            phase_commit(db, plan["operation_id"], "reserved")
        elif "metadata_phase_bytes" not in plan:
            raise DataError("旧未封口操作缺少元数据峰值预留，须显式放弃后重新预览")
        destination = owned_path(root, plan["destination"])
        stage = private_stage(root, plan)
        data = stage / "data"
        job = job_row(db, plan["operation_id"])
        if destination.exists():
            if job["phase"] not in ("verified", "published"):
                raise DataError("目的路径已存在，拒绝覆盖")
        else:
            if job["phase"] != "verified":
                quarantine_retry(root, stage, db, plan["operation_id"])
                check_budget(root, db, policy)
                retained = inventory(stage, 1000)
                if retained["truncated"] or retained["logical_bytes"] + plan["product_bound"] + 65536 > plan["payload_reserved_bytes"]:
                    raise DataError("保留的中断产品已耗尽本操作预留；须预览放弃后重新配置，不能偷偷删除")
                data.mkdir()
                phase_commit(db, plan["operation_id"], "writing")
                if plan["kind"] == "archive":
                    if archive_sources(root, db, [source["id"] for source in plan["sources"]]) != plan["sources"]:
                        raise DataError("归档来源已变化")
                    manifest = create_archive(root, plan, data)
                    verify_archive(root, manifest, package_root=data)
                elif plan["kind"] == "restore":
                    for part in plan["manifest"]["parts"]:
                        registered = db.execute("SELECT * FROM artifacts WHERE path=?", (part["path"],)).fetchone()
                        if registered is None or idle_image(root, db, registered)["sha256"] != part["sha256"]:
                            raise DataError("恢复分包身份与登记不一致")
                    verify_archive(root, plan["manifest"], data)
                else:
                    source = owned_path(root, plan["source"])
                    if any(source.is_relative_to(root / run["path"]) for run in db.execute("SELECT path FROM runs WHERE state IN ('allocating','running')")):
                        raise DataError("活动运行租约阻止SQLite备份重试")
                    backup_image(root, plan, data)
                product = product_manifest(data)
                if len(compact_json(product, QUERY_BYTES).encode("utf-8")) > plan["product_metadata_bound_bytes"]:
                    raise DataError("产品清单编码超过已批准元数据上界")
                if sum(item["size"] for item in product) > plan["product_bound"]:
                    raise DataError("产品增长超过批准的字节上限")
                db.execute("UPDATE jobs SET product=? WHERE id=?", (compact_json(product, QUERY_BYTES), plan["operation_id"]))
                phase_commit(db, plan["operation_id"], "verified")
            check_product(db, plan["operation_id"], data)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.stat().st_dev != data.stat().st_dev:
                raise DataError("发布不允许跨卷原子移动；须使用迁移入口")
            os.replace(data, destination)
        phase_commit(db, plan["operation_id"], "published")
        seal_job(root, db, plan)
        return operation_result(root, db, job_row(db, plan["operation_id"]))
```

## 生命周期执行后（原文）

```python
@contextmanager
def write_index(root, policy):
    write_guard(root, policy)
    with byte_lock(root / ".manager.lock", create=True):
        db = open_index(root, writable=True)
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0] != policy["root_id"]:
                raise DataError("索引身份绑定不符")
            yield db
            db.commit()
        finally:
            db.close()

def lifecycle_execute(root, policy, args):
    root_marker(root, policy)
    if args.approve_hash is None:
        with closing(open_index(root)) as reader:
            plan = lifecycle_plan(root, policy, reader, args)
        return dict(plan, plan_hash=digest(plan), applied=False)
    with write_index(root, policy) as db:
        plan = lifecycle_plan(root, policy, db, args)
        if args.approve_hash != digest(plan) or plan["policy_hash"] != digest(policy):
            raise DataError("操作须批准当前清单及配置摘要")
        job = db.execute("SELECT * FROM jobs WHERE id=?", (plan["operation_id"],)).fetchone() if has_table(db, "jobs") else None
        if job and job["phase"] == "sealed":
            check_product(db, plan["operation_id"], owned_path(root, plan["destination"]))
            return operation_result(root, db, job_row(db, plan["operation_id"]))
        if job and job["phase"] == "abandoned":
            raise DataError("已放弃操作不能恢复，须新请求")
        if not job:
            check_budget(root, db, policy, plan["reserved_bytes"])
            lifecycle_tables(db)
            db.execute("INSERT INTO jobs(id,kind,phase,plan,reserved_bytes) VALUES (?,?,?,?,?)", (plan["operation_id"], plan["kind"], "reserved", compact_json(plan, QUERY_BYTES), plan["reserved_bytes"]))
            if plan["kind"] == "backup-sqlite":
                source = checked_path(root / plan["source"])
                image = file_manifest(source, allow_sqlite=True)
                source_id = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "artifact:" + os.path.normcase(plan["source"])))
                existing_source = db.execute("SELECT * FROM artifacts WHERE path=?", (plan["source"],)).fetchone()
                if existing_source and existing_source["role"] not in ("sqlite-source", "sqlite-backup"):
                    raise DataError("SQLite源与已登记角色冲突")
                if not existing_source:
                    db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (source_id, plan["source"], "sqlite-source", image["sha256"], image["size"], json.dumps(image["identity"]), 1, 0, time.time()))
            phase_commit(db, plan["operation_id"], "reserved")
        elif "metadata_phase_bytes" not in plan:
            raise DataError("旧未封口操作缺少元数据峰值预留，须显式放弃后重新预览")
        destination = owned_path(root, plan["destination"])
        stage = private_stage(root, plan)
        data = stage / "data"
        job = job_row(db, plan["operation_id"])
        if destination.exists():
            if job["phase"] not in ("verified", "published"):
                raise DataError("目的路径已存在，拒绝覆盖")
        else:
            if job["phase"] != "verified":
                quarantine_retry(root, stage, db, plan["operation_id"])
                check_budget(root, db, policy)
                retained = inventory(stage, 1000)
                if retained["truncated"] or retained["logical_bytes"] + plan["product_bound"] + 65536 > plan["payload_reserved_bytes"]:
                    raise DataError("保留的中断产品已耗尽本操作预留；须预览放弃后重新配置，不能偷偷删除")
                data.mkdir()
                phase_commit(db, plan["operation_id"], "writing")
                if plan["kind"] == "archive":
                    if archive_sources(root, db, [source["id"] for source in plan["sources"]]) != plan["sources"]:
                        raise DataError("归档来源已变化")
                    manifest = create_archive(root, db, plan, data)
                    verify_archive(root, manifest, package_root=data)
                elif plan["kind"] == "restore":
                    for part in plan["manifest"]["parts"]:
                        registered = db.execute("SELECT * FROM artifacts WHERE path=?", (part["path"],)).fetchone()
                        if registered is None or idle_image(root, db, registered)["sha256"] != part["sha256"]:
                            raise DataError("恢复分包身份与登记不一致")
                    verify_archive(root, plan["manifest"], data)
                else:
                    source = owned_path(root, plan["source"])
                    if any(source.is_relative_to(root / run["path"]) for run in db.execute("SELECT path FROM runs WHERE state IN ('allocating','running')")):
                        raise DataError("活动运行租约阻止SQLite备份重试")
                    backup_image(root, plan, data)
                product = product_manifest(data)
                if len(compact_json(product, QUERY_BYTES).encode("utf-8")) > plan["product_metadata_bound_bytes"]:
                    raise DataError("产品清单编码超过已批准元数据上界")
                if sum(item["size"] for item in product) > plan["product_bound"]:
                    raise DataError("产品增长超过批准的字节上限")
                db.execute("UPDATE jobs SET product=? WHERE id=?", (compact_json(product, QUERY_BYTES), plan["operation_id"]))
                phase_commit(db, plan["operation_id"], "verified")
            check_product(db, plan["operation_id"], data)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.stat().st_dev != data.stat().st_dev:
                raise DataError("发布不允许跨卷原子移动；须使用迁移入口")
            os.replace(data, destination)
        phase_commit(db, plan["operation_id"], "published")
        seal_job(root, db, plan)
        return operation_result(root, db, job_row(db, plan["operation_id"]))
```

## 原06容量同观察时点及745小时拒绝（788db717原文）

### inventory

```python
def inventory(root, limit, *, run_db=None):
    files = logical_bytes = visited = 0
    active_payload_credit = 0
    # 深度优先流式遍历；目录项和正文不整树物化。None只供完整预算核算。
    initial = root.stat()
    pending = [(root, (initial.st_dev, initial.st_ino), os.scandir(root), None)]
    try:
        while pending:
            folder, identity, entries, active_run = pending[-1]
            try:
                entry = next(entries)
            except StopIteration:
                current = checked_path(folder).stat()
                if (current.st_dev, current.st_ino) != identity:
                    raise DataError("盘点目录身份变化，拒绝不完整核算")
                if active_run is not None and folder == active_run[0]:
                    active_payload_credit += min(active_run[1], active_run[2])
                entries.close()
                pending.pop()
                continue
            else:
                visited += 1
                if limit is not None and visited > limit:
                    return dict(files=files, logical_bytes=logical_bytes, truncated=True)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise DataError("数据根内含链接或重解析点")
                if stat.S_ISDIR(info.st_mode):
                    folder = checked_path(entry.path)
                    if len(pending) >= 128:
                        raise DataError("目录深度超过128，拒绝不完整盘点")
                    current = folder.stat()
                    selected_run = active_run
                    if run_db is not None and folder.is_relative_to(root / "runs"):
                        run = run_db.execute("SELECT * FROM runs WHERE path=? AND state IN ('allocating','running')",
                                             (folder.relative_to(root).as_posix(),)).fetchone()
                        if run is not None:
                            if run_folder(root, run) != folder:
                                raise DataError("运行盘点路径身份不符")
                            selected_run = [folder, run["reserved_bytes"], 0]  # 路径、批准载荷、本次已计量载荷
                    pending.append((folder, (current.st_dev, current.st_ino), os.scandir(folder), selected_run))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    logical_bytes += info.st_size
                    if active_run is not None and not (folder == active_run[0] and entry.name in (".run-id.json", ".runner.lock")):
                        active_run[2] += info.st_size
                else:
                    raise DataError("盘点发现非普通文件，拒绝忽略未知对象")
    finally:
        for _, _, entries, _ in pending:
            entries.close()
    result = dict(files=files, logical_bytes=logical_bytes, truncated=False)
    if run_db is not None:
        result["active_payload_credit"] = active_payload_credit
    return result
```

### check_budget

```python
def check_budget(root, db, policy, growth=0, *, physical_growth=None, finishing_run_id=None):
    # 同一写锁内每次完整流式核算，不复用分页游标或陈旧缓存；未知字节也计入。
    for run in db.execute("SELECT * FROM runs WHERE state IN ('allocating','running')"):
        run_folder(root, run)
    reserved = db.execute("SELECT coalesce(sum(reserved_bytes),0) FROM runs WHERE state IN ('allocating','running')").fetchone()[0]
    measured = domain_inventory(root, db, observe_runs=True)
    if measured["truncated"]:
        raise DataError("容量盘点未完整，拒绝新增长；不能忽略未知文件")
    # 只抵扣本次总量已经计入的同一stat字节；producer不持管理锁，后续扫描会漏账。
    remaining = reserved - measured["active_payload_credit"]
    root_remaining = physical_future(root, db, root.stat().st_dev, finishing_run_id=finishing_run_id)
    remaining += job_remaining(root, db) + safety_remaining(db)
    reserve = policy["maintenance_reserve_bytes"] + policy["metadata_reserve_bytes"]
    if measured["logical_bytes"] + remaining + growth + reserve > policy["capacity_bytes"]:
        raise DataError("容量不足：原件、索引/WAL、活动预留和维护空间必须共存")
    if shutil.disk_usage(root).free < root_remaining + (growth if physical_growth is None else physical_growth) + reserve:
        raise DataError("所在卷可用空间不足，拒绝增长且不自动清理")
    return dict(logical_bytes=measured["logical_bytes"], remaining_reserved_bytes=remaining,
                maintenance_reserve_bytes=policy["maintenance_reserve_bytes"], metadata_reserve_bytes=policy["metadata_reserve_bytes"])
```

### finish_run

```python
def finish_run(root, policy, args):
    with write_index(root, policy) as db:
        run = run_row(db, args.run_id)
        authorize_run(run, args.token)
        folder = checked_path(root / run["path"])
        if inventory(folder, 1000)["truncated"]:
            raise DataError("运行超过有界封口范围，不能假称完整")
        manifests = []
        for path in sorted(folder.rglob("*")):
            checked_path(path)
            if path.is_file() and path.name not in (".runner.lock", ".run-id.json"):
                with runner_locks(root, path):
                    manifests.append((path, file_manifest(path)))
        if run["state"] != "sealed" and sum(manifest["size"] for _, manifest in manifests) > run["reserved_bytes"]:
            raise DataError("实际产物超过预留，保持未封口和保护状态")
        check_budget(root, db, policy, finishing_run_id=run["id"])
        if run["state"] == "sealed":
            registered = {row[0] for row in db.execute("SELECT artifact_id FROM run_artifacts WHERE run_id=?", (args.run_id,))}
            observed = {str(uuid.uuid5(uuid.UUID(policy["root_id"]), "artifact:" + os.path.normcase(path.relative_to(root).as_posix()))) for path, _ in manifests}
            if registered != observed:
                raise DataError("封口后成员清单已变化，不能改写")
        artifact_ids = []
        for path, manifest in manifests:
            relative = path.relative_to(root).as_posix()
            artifact_id = str(uuid.uuid5(uuid.UUID(policy["root_id"]), "artifact:" + os.path.normcase(relative)))
            old = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if old and (old["sha256"] != manifest["sha256"] or old["identity"] != json.dumps(manifest["identity"])):
                raise DataError("封口后产物已变化，不能覆盖")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (artifact_id, relative, "native", manifest["sha256"],
                       manifest["size"], json.dumps(manifest["identity"]), 1, 1, time.time()))
            db.execute("INSERT OR IGNORE INTO run_artifacts VALUES (?,?)", (args.run_id, artifact_id))
            artifact_ids.append(artifact_id)
        if run["state"] == "sealed" and run["outcome"] != args.outcome:
            raise DataError("封口结果状态不同，不能改写")
        db.execute("UPDATE runs SET state='sealed',reserved_bytes=0,outcome=?,last_used=? WHERE id=?", (args.outcome, time.time(), args.run_id))
        db.execute("UPDATE operations SET phase='sealed' WHERE id=?", (args.run_id,))
    return dict(run_id=args.run_id, sealed=True, outcome=args.outcome, artifact_ids=artifact_ids)
```

### domain_inventory

```python
def domain_inventory(root, db, *, observe_runs=False):
    measured = inventory(root, None, run_db=db if observe_runs else None)
    if has_table(db, "volumes"):
        for row in db.execute("SELECT id FROM volumes ORDER BY id"):
            other = inventory(volume_root(root, db, row["id"]), None)
            measured["logical_bytes"] += other["logical_bytes"]
            measured["truncated"] = measured["truncated"] or other["truncated"]
    return measured
```

### physical_future

```python
def physical_future(root, db, device, *, finishing_run_id=None):
    """按OS卷合并承诺；锁内迁移可抵扣，锁外producer保守保留完整物理预留。"""
    primary = root.stat().st_dev == device
    future = 0
    if primary:
        # 活动producer可不持管理锁写/截断载荷；disk_usage与目录stat不能组成同一快照。
        # 物理准入保守保留其整个批准载荷直到finish/release，不用另一时点的文件抵扣。
        future = job_remaining(root, db) + db.execute("SELECT coalesce(sum(reserved_bytes),0) FROM runs WHERE state IN ('allocating','running') AND id != ?",
                                                   (finishing_run_id or "",)).fetchone()[0]
    if has_table(db, "safety_jobs"):
        for job in db.execute("SELECT * FROM safety_jobs WHERE phase NOT IN ('sealed','abandoned')"):
            plan = json.loads(job["plan"])
            if job["kind"] != "migration":
                if primary:
                    future += job["reserved_bytes"]
                continue
            target = volume_root(root, db, plan["volume_id"])
            if target.stat().st_dev == device:
                materialized = migration_materialized(root, db, job)
                progress = json.loads(job["progress"])
                unwritten = sum(item["size"] for item in plan["sources"] if item["id"] not in progress)
                # verified/published只验证及改名，绝不重新写载荷。writing重试须保留旧部分件，
                # 因此未完成来源还至少需要一次完整复制，不能用部分/保留件抵扣这次复制。
                if job["phase"] not in ("verified", "published"):
                    future += max(unwritten, plan["payload_reserved_bytes"] - materialized)
            if primary:
                future += plan["metadata_reserved_bytes"]
    return future
```

### schedule_preview

```python
def schedule_preview(root, policy, args):
    if not args.config or not args.python:
        raise DataError("计划任务预览须明确技能外机器配置和已有Python绝对路径")
    executable = checked_path(args.python)
    if not Path(args.python).is_absolute() or not executable.is_file():
        raise DataError("Python须为已有可执行文件绝对路径")
    unresolved = [key for key in ("root_id", "capacity_bytes", "retention_days", "maintenance_interval_hours",
                                 "maintenance_reserve_bytes", "archive_part_bytes", "metadata_reserve_bytes", "lease_seconds") if policy[key] is None]
    if not args.start_at:
        unresolved.append("start_at")
    if unresolved:
        return dict(installed=False, enabled=False, xml=None, unresolved=unresolved, production_enabled=policy["production_enabled"])
    if policy["maintenance_interval_hours"] > 744:
        raise DataError("Windows重复间隔最多31天（744小时），拒绝生成无效任务；不会截断用户策略")
    try:
        start = datetime.fromisoformat(args.start_at)
    except ValueError as error:
        raise DataError("start-at须为含时区的ISO8601时间") from error
    if start.tzinfo is None:
        raise DataError("start-at须显式包含时区偏移")
    task = ET.Element("Task", version="1.4", xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task")
    trigger = ET.SubElement(ET.SubElement(task, "Triggers"), "TimeTrigger")
    ET.SubElement(trigger, "StartBoundary").text = start.isoformat()
    ET.SubElement(trigger, "Enabled").text = "false"
    ET.SubElement(ET.SubElement(trigger, "Repetition"), "Interval").text = f"PT{policy['maintenance_interval_hours']}H"
    principals = ET.SubElement(task, "Principals")
    principal = ET.SubElement(principals, "Principal", id="Author")
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "LeastPrivilege"
    settings = ET.SubElement(task, "Settings")
    ET.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    ET.SubElement(settings, "Enabled").text = "false"
    action = ET.SubElement(ET.SubElement(task, "Actions", Context="Author"), "Exec")
    ET.SubElement(action, "Command").text = str(executable)
    ET.SubElement(action, "Arguments").text = subprocess.list2cmdline([str(SKILL_ROOT / "scripts/simdata.py"), "maintenance", "--config", str(checked_path(args.config)), "--task", "status"])
    ET.SubElement(action, "WorkingDirectory").text = str(SKILL_ROOT)
    return dict(installed=False, enabled=False, unresolved=[], xml=ET.tostring(task, encoding="unicode"),
                action="maintenance status", production_enabled=policy["production_enabled"],
                instruction="仅生成配置，不安装或启用；定期入口只报告状态，数据变更另需具体计划批准")
```

## 原大清单五阶段完整测试结构（Git对象原文）

eb8933e6与788db717该方法逐字符相同：True。

```python
    def test_large_legal_restore_plan_is_admitted_before_any_metadata_write(self):
        self.initialize()
        self.policy["capacity_bytes"] = 1024 * 1024 * 1024
        self.save_config()
        prefix = "/".join(["nested " + "x" * 180] * 12)
        directory = self.root / prefix
        directory.mkdir(parents=True)
        for number in range(220):
            (directory / ("native-%03d.json" % number)).write_bytes(b"{}")
        preview = self.call("legacy-register", "--directory", str(directory), "--role", "native")
        registered = self.call("legacy-register", "--directory", str(directory), "--role", "native",
                               "--approve-hash", preview["plan_hash"])
        self.assertEqual(len(registered["artifacts"]), 220)
        identities = [item["artifact_id"] for item in registered["artifacts"]]
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
```

## 结构事实及实测范围

同一方法只初始化一次根及索引、登记一次220来源、生成一次archive ID；容量拒绝后重置合成容量。五个phase各自使用新target和由公开plan生成的operation ID，先在该操作的对应commit阶段中断，再按同一operation ID和plan hash恢复封口，校验220字节副本。每次只删除本次合成target；索引、历史操作/locations及staging仍在同一根中供后续阶段使用。它并非把同一个operation依次在五阶段中断，也不能据此认定独立根拆分完全等价。这里仅描述代码结构，不作拆分审查结论。

每阶段完整独立耗时尚未测得。先前45秒临时诊断在最终一次计划修复前：首reserved预览2.579秒、注入中断6.072秒、恢复0.891秒后预算截止，未完成；writing/verified/published/sealed未取得有效完成时间。截止后约1毫秒尝试不是阶段测量且该包装已停用。最终788db717同口径8次CLI诊断只有一次完整无中断restore，30.949秒，不代表五阶段完整时间。不得给出缺失阶段的伪造数值。

## 仓库现有pytest并行登记（788db717配置读取）

```json
{
  "maxParallel": 3,
  "fullBudgetSeconds": 60,
  "checks": [
    {
      "id": "verify.sim2gse",
      "pr": false,
      "command": ".venv\\Scripts\\python.exe -m pytest -q tests/sim2gse --dist=worksteal",
      "checkParallel": true,
      "pytestXdistWorkers": 8,
      "paths": [
        "projects/sim2gse/**",
        "scripts/dev/sim2gse/**",
        ".build-and-verify/config.json",
        "tests/sim2gse/**",
        "scripts/dev/requirements.txt",
        "package.json",
        "package-lock.json"
      ],
      "inputs": [
        "projects/sim2gse/**",
        "scripts/dev/sim2gse/**",
        ".build-and-verify/config.json",
        ".tools/sim2gse/product/baseline/engine/simc.exe",
        ".tools/sim2gse/product/controlled/engine/simc.exe",
        ".local/sim2gse/build/baseline/build.json",
        ".local/sim2gse/build/controlled/build.json",
        ".tools/sim2gse-research/gse-f225d4c/**",
        "tests/sim2gse/**",
        "scripts/dev/requirements.txt",
        "package.json",
        "package-lock.json"
      ],
      "timeoutSeconds": 600
    },
    {
      "id": "verify.sim2gse-data",
      "command": ".venv\\Scripts\\python.exe -B -m pytest -q tests/sim2gse-data --dist=worksteal",
      "checkParallel": true,
      "pytestXdistWorkers": 8,
      "paths": [
        ".agents/skills/sim2gse-data/**",
        "tests/sim2gse-data/**",
        ".build-and-verify/config.json",
        "tests/README.md"
      ],
      "inputs": [
        ".agents/skills/sim2gse-data/**",
        "tests/sim2gse-data/**",
        ".build-and-verify/config.json"
      ],
      "timeoutSeconds": 60
    }
  ]
}
```
