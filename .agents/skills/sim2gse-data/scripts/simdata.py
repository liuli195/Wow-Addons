"""Sim2GSE 数据生命周期的共用命令行入口；仅使用标准库。"""
import argparse
import base64
import gzip
from datetime import datetime
from contextlib import contextmanager, ExitStack, closing
import hashlib
import heapq
import hmac
import json
import math
import os
from pathlib import Path
import shutil
import secrets
import sqlite3
import stat
import subprocess
import sys
import tempfile
import tarfile
import time
import uuid
import zlib
import xml.etree.ElementTree as ET
from urllib.parse import quote


SKILL_ROOT = Path(__file__).resolve().parents[1]
# 固定初始化DDL的保守峰值：主库、写事务/WAL、SHM和根标记；不是用户容量建议。
INITIALIZATION_PEAK_BYTES = 256 * 1024
PROTECTED_ROLES = {"input", "evidence", "model", "analysis", "unknown", "sqlite-source"}
PROTECTED_DIRECTORIES = {"captures", "live-evidence", "archive", "phase2-product-20261001-02", "duration-curve-20261001-01", "start-origin-analysis-20261001"}


class DataError(ValueError):
    pass


def checked_path(path, *, missing_leaf=False):
    """先检查原路径各层，再解析，避免把联接越界隐藏在 resolve 中。"""
    if "\x00" in os.fspath(path):
        raise DataError("路径含NUL字符，不能作为文件系统路径")
    if ".." in os.fspath(path).replace("\\", "/").split("/"):
        raise DataError("路径含上级路径组件，不能在规范化时隐藏链接")
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if missing_leaf and component == path:
                return path.resolve()
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise DataError("数据路径含链接或重解析点")
    return path.resolve(strict=True)


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


def inventory_page(root, limit, cursor):
    """只读续扫。游标是观察进度，不作为容量、身份或删除批准证据。"""
    def frame(folder):
        info = checked_path(folder).stat()
        return dict(path=folder.relative_to(root).as_posix(), after="",
                    identity=[info.st_dev, info.st_ino, info.st_mtime_ns])
    state = dict(root=str(root), stack=[frame(root)], files=0, logical_bytes=0)
    if cursor:
        if len(cursor) > 65536:
            raise DataError("盘点游标超过64KiB")
        try:
            state = json.loads(base64.b64decode(cursor, validate=True))
        except (ValueError, UnicodeError) as error:
            raise DataError("盘点游标格式错误") from error
        if not isinstance(state, dict) or state.get("root") != str(root) or not isinstance(state.get("stack"), list):
            raise DataError("盘点游标根不匹配")
        if len(state["stack"]) > 128 or any(type(state.get(k)) is not int or state[k] < 0 for k in ("files", "logical_bytes")):
            raise DataError("盘点游标计数/深度错误")
    def validate(current):
        if not isinstance(current, dict) or not isinstance(current.get("path"), str) or not isinstance(current.get("after"), str):
            raise DataError("盘点游标目录格式错误")
        relative = Path(current["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise DataError("盘点游标越界")
        folder = checked_path(root / relative)
        if not folder.is_relative_to(root) or not folder.is_dir():
            raise DataError("盘点游标目录越界")
        info = folder.stat()
        if [info.st_dev, info.st_ino, info.st_mtime_ns] != current.get("identity"):
            raise DataError("续扫目录身份/内容变化，须重新盘点")
        return folder
    for current in state["stack"]:
        validate(current)
    visited = enumerated = 0
    while state["stack"] and visited < limit:
        current = state["stack"][-1]
        folder = validate(current)
        available = limit - visited
        with os.scandir(folder) as entries:
            def names():
                nonlocal enumerated
                for entry in entries:
                    enumerated += 1
                    if entry.name > current["after"]:
                        yield entry.name
            selected = heapq.nsmallest(available + 1, names())
        if not selected:
            state["stack"].pop()
            continue
        descended = False
        for name in selected[:available]:
            path = checked_path(folder / name)
            info = path.stat()
            visited += 1
            current["after"] = name
            if stat.S_ISDIR(info.st_mode):
                if len(state["stack"]) >= 128:
                    raise DataError("目录深度超过128")
                state["stack"].append(frame(path))
                descended = True
                break
            if not stat.S_ISREG(info.st_mode):
                raise DataError("盘点发现非普通文件")
            state["files"] += 1
            state["logical_bytes"] += info.st_size
        if not descended and len(selected) <= available:
            state["stack"].pop()
    token = base64.b64encode(json.dumps(state, ensure_ascii=False).encode()).decode() if state["stack"] else None
    if token and len(token) > 65536:
        raise DataError("盘点游标超过64KiB，目录须分根盘点")
    return dict(files=state["files"], logical_bytes=state["logical_bytes"], truncated=bool(token),
                next_cursor=token, batch_visited=visited, enumerated_names=enumerated,
                consistency="live_observation_not_snapshot", budget_evidence=False)


def load_policy(config):
    policy = json.loads((SKILL_ROOT / "assets/config.default.json").read_text(encoding="utf-8"))
    if config:
        if not Path(config).is_absolute():
            raise DataError("配置须使用绝对路径，不能依赖当前工作目录")
        supplied = json.loads(checked_path(config).read_text(encoding="utf-8"))
        if not isinstance(supplied, dict) or set(supplied) - set(policy):
            raise DataError("配置须为对象且不能含未知字段")
        policy.update(supplied)
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise DataError("不支持的配置版本")
    if type(policy["production_enabled"]) is not bool:
        raise DataError("production_enabled须为布尔值")
    if policy["mode"] not in ("production", "test"):
        raise DataError("mode须为production或test")
    if policy["mode"] == "test" and policy["production_enabled"]:
        raise DataError("测试配置不能启用生产")
    if policy["root_id"] is not None:
        try:
            policy["root_id"] = str(uuid.UUID(policy["root_id"]))
        except (ValueError, TypeError, AttributeError) as error:
            raise DataError("root_id须为UUID或未设置") from error
    if policy["data_root"] is not None and (
            not isinstance(policy["data_root"], str) or not Path(policy["data_root"]).is_absolute()):
        raise DataError("data_root须为未设置或绝对目录路径")
    for key in ("capacity_bytes", "retention_days", "maintenance_interval_hours",
                "maintenance_reserve_bytes", "archive_part_bytes", "metadata_reserve_bytes", "lease_seconds"):
        value = policy[key]
        if value is not None and (type(value) is not int or value <= 0):
            raise DataError(f"{key}须为未设置或正整数")
    return policy


def require_write_policy(policy):
    if policy["mode"] == "production" and not policy["production_enabled"]:
        raise DataError("生产管理未启用；只读操作仍可使用")
    required = ("capacity_bytes", "retention_days", "maintenance_interval_hours",
                "maintenance_reserve_bytes", "archive_part_bytes", "metadata_reserve_bytes", "lease_seconds")
    if any(policy[key] is None for key in required):
        raise DataError("生产策略未完整配置；须先商量容量、保留、频率及维护空间")
    if policy["maintenance_reserve_bytes"] >= policy["capacity_bytes"]:
        raise DataError("维护预留须小于容量")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def root_marker(root, policy):
    marker = json.loads(checked_path(root / ".simdata-root.json").read_text(encoding="utf-8"))
    if not isinstance(marker, dict) or marker.get("root") != str(root):
        raise DataError("数据根标记绑定不符")
    if policy["root_id"] is not None and marker.get("root_id") != policy["root_id"]:
        raise DataError("配置与数据根身份绑定不符")
    if marker.get("mode") == "test" and not root.is_relative_to(checked_path(tempfile.gettempdir())):
        raise DataError("测试根必须位于系统临时目录，不能迁用真实数据根")
    return marker


def index_paths(root):
    for name in ("index.sqlite3", "index.sqlite3-wal", "index.sqlite3-shm", "index.sqlite3-journal"):
        path = root / name
        if os.path.lexists(path) and not checked_path(path).is_file():
            raise DataError("索引及SQLite侧文件须为普通文件")


def open_index(root, *, writable=False):
    index_paths(root)
    path = root / "index.sqlite3"
    db = sqlite3.connect(str(path) if writable else path.as_uri() + "?mode=ro", uri=not writable, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL" if writable else "PRAGMA query_only=ON")
    return db


def init_root(root, policy, approval):
    require_write_policy(policy)
    if policy["data_root"] is None or policy["root_id"] is None:
        raise DataError("初始化须明确配置数据根及root_id")
    marker_path = root / ".simdata-root.json"
    if policy["mode"] == "test":
        if not root.is_relative_to(checked_path(tempfile.gettempdir())):
            raise DataError("测试初始化仅允许系统临时目录内的新隔离根")
        if root.exists() and not os.path.lexists(marker_path):
            raise DataError("测试初始化拒绝既有目录；不能用测试模式接管已有数据")
    elif not root.is_dir():
        raise DataError("生产初始化只允许明确配置的既有目录")
    if os.path.lexists(marker_path):
        marker = root_marker(root, policy)
        if marker["mode"] != policy["mode"]:
            raise DataError("配置与数据根模式绑定不符")
    elif os.path.lexists(root / "index.sqlite3"):
        raise DataError("既有未登记索引受保护，不能覆盖")
    plan_hash = digest(dict(action="init-root", root=str(root), policy=policy))
    if approval is None:
        return dict(plan_hash=plan_hash, root=str(root), root_id=policy["root_id"], applied=False)
    if approval != plan_hash:
        raise DataError("初始化计划摘要不符，须批准当前预览")
    measured = inventory(root, None) if root.exists() else dict(logical_bytes=0, truncated=False)
    if measured["truncated"]:
        raise DataError("初始化容量盘点不完整，拒绝发布索引")
    peak = INITIALIZATION_PEAK_BYTES + policy["maintenance_reserve_bytes"] + policy["metadata_reserve_bytes"]
    if measured["logical_bytes"] + peak > policy["capacity_bytes"]:
        raise DataError("初始化容量不足：须容纳索引/WAL峰值及维护、元数据余量")
    if shutil.disk_usage(root if root.exists() else checked_path(root.parent)).free < peak:
        raise DataError("初始化所在卷空间不足，不创建根标记或索引")
    if not root.exists():
        root.mkdir()
    if not os.path.lexists(marker_path):
        with marker_path.open("x", encoding="utf-8") as output:
            json.dump(dict(root=str(root), root_id=policy["root_id"], mode=policy["mode"]), output)
    db = open_index(root, writable=True)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, role TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL, identity TEXT NOT NULL, schema_version INTEGER NOT NULL, sealed INTEGER NOT NULL, last_used REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, kind TEXT NOT NULL, phase TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, path TEXT UNIQUE NOT NULL, state TEXT NOT NULL, owner_pid INTEGER NOT NULL, owner_start TEXT NOT NULL, token_hash TEXT NOT NULL, expires REAL NOT NULL, reserved_bytes INTEGER NOT NULL, last_used REAL NOT NULL, outcome TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS run_artifacts (run_id TEXT NOT NULL REFERENCES runs(id), artifact_id TEXT NOT NULL REFERENCES artifacts(id), PRIMARY KEY(run_id,artifact_id))")
            db.execute("CREATE TABLE IF NOT EXISTS pins (artifact_id TEXT NOT NULL REFERENCES artifacts(id), label TEXT NOT NULL, PRIMARY KEY(artifact_id,label))")
            db.execute("CREATE TABLE IF NOT EXISTS refs (owner TEXT NOT NULL, target TEXT NOT NULL REFERENCES artifacts(id), kind TEXT NOT NULL, PRIMARY KEY(owner,target))")
            db.execute("CREATE TABLE IF NOT EXISTS unknown_refs (source TEXT PRIMARY KEY, reason TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('root_id', ?)", (policy["root_id"],))
            if db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0] != policy["root_id"]:
                raise DataError("索引与数据根身份绑定不符")
    finally:
        db.close()
    return dict(plan_hash=plan_hash, root_id=policy["root_id"], applied=True)


def index_status(root, policy):
    marker = root_marker(root, policy)
    db = open_index(root)
    try:
        if db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0] != marker["root_id"]:
            raise DataError("索引与数据根身份绑定不符")
        return dict(root_id=marker["root_id"], root_mode=marker["mode"],
                    registered_artifacts=db.execute("SELECT count(*) FROM artifacts").fetchone()[0],
                    operation_reserved_bytes=job_remaining(root, db) + safety_remaining(db),
                    reserved_bytes=db.execute("SELECT coalesce(sum(reserved_bytes),0) FROM runs WHERE state IN ('allocating','running')").fetchone()[0])
    finally:
        db.close()


def write_guard(root, policy):
    require_write_policy(policy)
    if policy["data_root"] is None or policy["root_id"] is None:
        raise DataError("写入须明确配置数据根身份")
    marker = root_marker(root, policy)
    if marker["mode"] != policy["mode"]:
        raise DataError("写入模式与数据根绑定不符")
    index_paths(root)


@contextmanager
def byte_lock(path, *, create=False):
    if os.path.lexists(path):
        checked_path(path)
    else:
        checked_path(path.parent)
    with path.open("a+b" if create else "r+b") as handle:
        opened, current = os.fstat(handle.fileno()), path.lstat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise DataError("锁文件身份已变化")
        checked_path(path)
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DataError("活动文件锁或无法安全锁定，操作被阻止") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


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


def managed_file(root, path):
    if not Path(path).is_absolute():
        raise DataError("对象路径须为绝对路径")
    source = checked_path(path)
    if not source.is_relative_to(root) or not source.is_file():
        raise DataError("对象须为数据根内普通文件，不能越界")
    relative = source.relative_to(root).as_posix()
    if relative in (".simdata-root.json", ".manager.lock") or relative.startswith(("index.sqlite3", ".staging/", ".quarantine/")) or source.name == ".runner.lock":
        raise DataError("管理索引、侧文件和锁文件不能登记为原始数据")
    return source


@contextmanager
def runner_locks(root, source):
    with ExitStack() as stack:
        if source.parent.is_relative_to(root):
            for parent in (source.parent, *source.parent.parents):
                lock = parent / ".runner.lock"
                if os.path.lexists(lock):
                    stack.enter_context(byte_lock(lock))
                if parent == root:
                    break
        yield


def file_manifest(source, *, allow_sqlite=False):
    before = source.stat()
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    checksum = hashlib.sha256()
    with source.open("rb") as handle:
        if identity(os.fstat(handle.fileno())) != identity(before):
            raise DataError("文件在读取前已变化")
        header = handle.read(16)
        if header == b"SQLite format 3\x00" and not allow_sqlite:
            raise DataError("SQLite原库须先通过一致性备份登记，不能忽略WAL直接散列")
        checksum.update(header)
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
        if identity(os.fstat(handle.fileno())) != identity(before):
            raise DataError("文件在读取过程中已变化")
    if identity(source.stat()) != identity(before):
        raise DataError("文件身份在读取后已变化")
    return dict(sha256=checksum.hexdigest(), size=before.st_size, identity=list(identity(before)))


def register_file(root, policy, args):
    marker = root_marker(root, policy)
    source = managed_file(root, args.path)
    if args.schema_version < 1:
        raise DataError("对象schema版本须为正整数")
    with runner_locks(root, source):
        manifest = file_manifest(source)
        relative = source.relative_to(root).as_posix()
        artifact_id = str(uuid.uuid5(uuid.UUID(marker["root_id"]), "artifact:" + os.path.normcase(relative)))
        plan = dict(action="register", root_id=marker["root_id"], artifact_id=artifact_id,
                    path=relative, role=args.role, schema_version=args.schema_version,
                    policy_hash=digest(policy), **manifest)
        plan_hash = digest(plan)
        if args.approve_hash is None:
            return dict(plan_hash=plan_hash, applied=False, **plan)
        if args.approve_hash != plan_hash:
            raise DataError("登记计划摘要不符，文件或配置在预览后已变化")
        with write_index(root, policy) as db:
            check_budget(root, db, policy)
            existing = db.execute("SELECT * FROM artifacts WHERE path=?", (relative,)).fetchone()
            identity = json.dumps(manifest["identity"])
            if existing and (existing["sha256"], existing["identity"], existing["role"], existing["schema_version"]) != (manifest["sha256"], identity, args.role, args.schema_version):
                raise DataError("已登记对象身份或角色不符，不能原地覆盖")
            if not existing:
                db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (artifact_id, relative, args.role,
                           manifest["sha256"], manifest["size"], identity, args.schema_version, 1, time.time()))
                db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "register", "committed", json.dumps(plan)))
        return dict(plan_hash=plan_hash, artifact_id=artifact_id, applied=True, changed=existing is None)


def artifact_row(db, artifact_id):
    row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    if row is None:
        raise DataError("未知对象ID受保护，不能解析或操作")
    return row


def read_location(root, db, row):
    """校验仍存在的原件，再选择已登记首选位置；异常位置不能被静默跳过。"""
    def inspect(base, relative, identity):
        path = owned_path(base, relative)
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        source = managed_file(base, str(path))
        with runner_locks(base, source):
            image = file_manifest(source, allow_sqlite=row["role"] == "sqlite-backup")
        if image["sha256"] != row["sha256"] or image["size"] != row["size"] or json.dumps(image["identity"]) != identity:
            raise DataError("登记位置当前身份或原始摘要不符")
        return base, source, image
    original = inspect(root, row["path"], row["identity"])
    if has_table(db, "placements"):
        positions = db.execute("SELECT * FROM placements WHERE artifact_id=? AND state IN ('preferred','available') ORDER BY CASE state WHEN 'preferred' THEN 0 ELSE 1 END,path LIMIT 1001", (row["id"],)).fetchall()
        if len(positions) > 1000 or sum(item["state"] == "preferred" for item in positions) > 1:
            raise DataError("迁移位置清单过大或首选位置不唯一")
        for item in positions:
            if item["state"] == "preferred" or original is None:
                result = inspect(volume_root(root, db, item["volume_id"]), item["path"], item["identity"])
                if result is None and item["state"] == "preferred":
                    raise DataError("已登记首选位置缺失，须先核对位置状态")
                if result:
                    return result
    if original:
        return original
    if has_table(db, "locations"):
        positions = db.execute("SELECT * FROM locations WHERE artifact_id=? ORDER BY path LIMIT 1001", (row["id"],)).fetchall()
        if len(positions) > 1000:
            raise DataError("恢复位置清单超过有界范围")
        for item in positions:
            result = inspect(root, item["path"], item["identity"])
            if result:
                return result
    raise DataError("原件及已登记可用位置全部缺失")


def resolve_artifact(root, policy, args):
    root_marker(root, policy)
    with closing(open_index(root)) as db:
        row = dict(artifact_row(db, args.artifact_id))
        _, source, _ = read_location(root, db, row)
    if not args.inspect:
        with write_index(root, policy) as db:
            check_budget(root, db, policy)
            if dict(artifact_row(db, args.artifact_id)) != row:
                raise DataError("对象在解析过程中已变化")
            read_location(root, db, row)
            row["last_used"] = time.time()
            db.execute("UPDATE artifacts SET last_used=? WHERE id=?", (row["last_used"], args.artifact_id))
    return dict(artifact_id=row["id"], path=str(source), role=row["role"], sha256=row["sha256"],
                size=row["size"], sealed=bool(row["sealed"]), last_used=row["last_used"], last_used_updated=not args.inspect)


def process_start(pid):
    """PID必须与操作系统进程出生身份一起使用；权限不足返回未知而非死亡。"""
    if not 1 <= pid <= 0x7fffffff:
        raise DataError("owner-pid超出有效范围")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise DataError("无法核实进程身份，不能把权限不足当作死亡")
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)):
                raise DataError("无法核实进程出生身份")
            if exited.dwHighDateTime or exited.dwLowDateTime:
                return None
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None
    except (PermissionError, IndexError) as error:
        raise DataError("无法核实进程出生身份") from error


def lease_state(run):
    try:
        current = process_start(run["owner_pid"])
    except DataError:
        return "unknown"
    if current is None:
        return "dead"
    return "alive" if current == run["owner_start"] else "pid-reused"


def run_folder(root, run):
    """持久分配可能尚未创建任意父层；只检查已存在层，不消除重解析点。"""
    relative = Path(run["path"])
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "runs":
        raise DataError("运行路径身份无效")
    current = root
    for part in relative.parts:
        current = current / part
        if not os.path.lexists(current):
            if run["state"] == "allocating":
                return None
            raise DataError("已启动运行目录缺失，拒绝推定为正常分配")
        if not checked_path(current).is_dir():
            raise DataError("运行目录层不是普通目录，须先处理明确障碍")
    return current


def run_payload_bytes(root, run):
    folder = run_folder(root, run)
    if folder is None:
        return 0
    measured = inventory(folder, None)
    if measured["truncated"]:
        raise DataError("活动目录超过有界盘点范围，不能确定容量")
    internal = sum(checked_path(folder / name).stat().st_size for name in (".run-id.json", ".runner.lock")
                   if os.path.lexists(folder / name))
    return measured["logical_bytes"] - internal


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


def run_row(db, run_id):
    run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise DataError("未知运行ID受保护")
    return run


def authorize_run(run, token):
    if not token or not hmac.compare_digest(run["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
        raise DataError("租约令牌不符")
    if lease_state(run) != "alive":
        raise DataError("运行所有者身份不能核实；须先预览明确的租约恢复")


def begin_run(root, policy, args):
    write_guard(root, policy)
    if not args.request_id or len(args.request_id) > 128 or "\x00" in args.request_id or args.reserve_bytes <= 0:
        raise DataError("请求ID须非空且不超过128字符；预留须为正数")
    owner_start = process_start(args.owner_pid)
    if owner_start is None or (args.owner_start is not None and args.owner_start != owner_start):
        raise DataError("PID与进程出生身份不符，不能将复用PID当原所有者")
    token = args.token or secrets.token_hex(32)
    run_id = str(uuid.uuid5(uuid.UUID(policy["root_id"]), "run:" + args.request_id))
    relative = f"runs/{run_id}"
    with write_index(root, policy) as db:
        existing = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if existing:
            authorize_run(existing, args.token)
            if existing["state"] not in ("allocating", "running") or existing["reserved_bytes"] != args.reserve_bytes:
                raise DataError("同请求运行已封口或预留不同，不能覆盖")
        else:
            check_budget(root, db, policy, args.reserve_bytes)
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (run_id, args.request_id, relative, "allocating", args.owner_pid,
                       owner_start, hashlib.sha256(token.encode()).hexdigest(), time.time() + policy["lease_seconds"], args.reserve_bytes, time.time(), None))
            db.execute("INSERT INTO operations VALUES (?,?,?,?)", (run_id, "begin", "allocating", json.dumps(dict(run_id=run_id))))
            db.commit()  # 先持久预留；中断后不能把它当作未发生。
            db.execute("BEGIN IMMEDIATE")
        parent = checked_path(root / "runs", missing_leaf=True)
        parent.mkdir(exist_ok=True)
        folder = checked_path(root / relative, missing_leaf=True)
        if not folder.exists():
            folder.mkdir()
        marker = folder / ".run-id.json"
        expected = dict(run_id=run_id, root_id=policy["root_id"])
        if os.path.lexists(marker):
            if json.loads(checked_path(marker).read_text(encoding="utf-8")) != expected:
                raise DataError("运行目录身份不符")
        elif list(folder.iterdir()):
            raise DataError("既有未登记运行内容受保护，不接管")
        else:
            with marker.open("x", encoding="utf-8") as output:
                json.dump(expected, output)
        db.execute("UPDATE runs SET state='running' WHERE id=?", (run_id,))
        db.execute("UPDATE operations SET phase='running' WHERE id=?", (run_id,))
    return dict(run_id=run_id, path=str(folder), token=token, reserved_bytes=args.reserve_bytes, owner_start=owner_start)


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
        # Cover new artifact/link rows, indexes and WAL before any registration writes.
        registration_bytes = len(json.dumps([(path.relative_to(root).as_posix(), manifest)
                                             for path, manifest in manifests]).encode("utf-8"))
        growth = 0 if run["state"] == "sealed" else 65536 + registration_bytes * 8
        check_budget(root, db, policy, growth, finishing_run_id=run["id"])
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


def protection(root, db, artifact_id, *, own_job=None, activity_only=False):
    artifact = artifact_row(db, artifact_id)
    reasons = []
    if not activity_only:
        if artifact["role"] in PROTECTED_ROLES:
            reasons.append("protected-role:" + artifact["role"])
        if {part.casefold() for part in Path(artifact["path"]).parts} & PROTECTED_DIRECTORIES:
            reasons.append("protected-evidence-path")
        reasons.extend("pin:" + row[0] for row in db.execute("SELECT label FROM pins WHERE artifact_id=? ORDER BY label", (artifact_id,)))
    references = [dict(row) for row in db.execute("SELECT * FROM refs WHERE target=? ORDER BY owner", (artifact_id,))]
    if not activity_only:
        reasons.extend(row["kind"] + ":" + row["owner"] for row in references if row["kind"] != "cache")
    reasons.extend(dependency_protection(root, db, artifact_id, own_job=own_job, activity_only=activity_only))
    if not activity_only:
        if db.execute("SELECT count(*) FROM unknown_refs").fetchone()[0]:
            reasons.append("unknown-legacy-references")
        if has_table(db, "jobs"):
            for job in db.execute("SELECT * FROM jobs WHERE phase NOT IN ('sealed','abandoned')"):
                plan = json.loads(job["plan"])
                if any(source["id"] == artifact_id for source in plan.get("sources", plan.get("manifest", {}).get("sources", []))):
                    reasons.append("operation:" + job["id"])
        if has_table(db, "safety_jobs"):
            for job in db.execute("SELECT * FROM safety_jobs WHERE phase NOT IN ('sealed','abandoned')"):
                if job["id"] == own_job:
                    continue
                safety_plan = json.loads(job["plan"])
                if any(source["id"] == artifact_id for source in safety_plan.get("sources", safety_plan.get("items", []))):
                    reasons.append("operation:" + job["id"])
    if has_table(db, "readers"):
        reasons.extend("read-lease:" + row["id"] + ":" + lease_state(row)
                       for row in db.execute("SELECT * FROM readers WHERE artifact_id=? AND state='active'", (artifact_id,)))
    path = owned_path(root, artifact["path"])
    for run in db.execute("SELECT * FROM runs WHERE state IN ('allocating','running')"):
        if path.is_relative_to(root / run["path"]):
            reasons.append("lease:" + run["id"] + ":" + lease_state(run))
    try:
        with runner_locks(root, path):
            pass
    except DataError:
        reasons.append("runner-lock")
    return dict(artifact_id=artifact_id, protected=bool(reasons), reasons=reasons,
                cache_references=[row["owner"] for row in references if row["kind"] == "cache"],
                last_used=artifact["last_used"], references=references)


def protect_artifact(root, policy, args):
    root_marker(root, policy)
    db = open_index(root)
    try:
        return protection(root, db, args.artifact_id)
    finally:
        db.close()


def pin_artifact(root, policy, args):
    if not args.label or len(args.label) > 128 or "\x00" in args.label:
        raise DataError("pin标签须为1至128字符")
    with write_index(root, policy) as db:
        check_budget(root, db, policy)
        artifact_row(db, args.artifact_id)
        if args.action == "add":
            db.execute("INSERT OR IGNORE INTO pins VALUES (?,?)", (args.artifact_id, args.label))
        else:
            db.execute("DELETE FROM pins WHERE artifact_id=? AND label=?", (args.artifact_id, args.label))
        return protection(root, db, args.artifact_id)


def change_reference(root, policy, args):
    if not args.owner or len(args.owner) > 256 or "\x00" in args.owner:
        raise DataError("引用所有者须为1至256字符")
    if args.action == "add":
        if args.owner.startswith("artifact:"):
            raise DataError("对象依赖须使用dependency入口，不能绕过有向图循环检查")
        with write_index(root, policy) as db:
            check_budget(root, db, policy)
            artifact_row(db, args.artifact_id)
            previous = db.execute("SELECT kind FROM refs WHERE owner=? AND target=?", (args.owner, args.artifact_id)).fetchone()
            if previous and previous[0] != args.kind:
                raise DataError("不能把既有持久或未知引用降级为可撤销缓存")
            db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", (args.owner, args.artifact_id, args.kind))
        return dict(artifact_id=args.artifact_id, owner=args.owner, kind=args.kind, applied=True)
    root_marker(root, policy)
    def preview(db):
        safety = protection(root, db, args.artifact_id)
        if safety["protected"]:
            raise DataError("对象有持久、未知或活动保护，不能失效加速缓存")
        reference = db.execute("SELECT * FROM refs WHERE owner=? AND target=?", (args.owner, args.artifact_id)).fetchone()
        if reference is None or reference["kind"] != "cache":
            raise DataError("只有已登记可撤销缓存引用可以批准失效")
        artifact = artifact_row(db, args.artifact_id)
        source = managed_file(root, str(root / artifact["path"]))
        with runner_locks(root, source):
            manifest = file_manifest(source)
        if manifest["sha256"] != artifact["sha256"] or json.dumps(manifest["identity"]) != artifact["identity"]:
            raise DataError("批准对象当前身份或摘要不符")
        plan = dict(action="invalidate-cache-reference", root_id=policy["root_id"], owner=args.owner,
                    artifact_id=args.artifact_id, references=safety["references"], identity=artifact["identity"],
                    sha256=artifact["sha256"], policy_hash=digest(policy))
        return dict(plan_hash=digest(plan), may_recompute=True, applied=False, **plan)
    if args.action == "invalidate-preview":
        db = open_index(root)
        try:
            return preview(db)
        finally:
            db.close()
    with write_index(root, policy) as db:
        check_budget(root, db, policy)
        plan = preview(db)
        if args.approve_hash != plan["plan_hash"]:
            raise DataError("缓存失效须批准当前具体计划摘要")
        db.execute("DELETE FROM refs WHERE owner=? AND target=?", (args.owner, args.artifact_id))
        db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "invalidate-cache-reference", "committed", json.dumps(plan)))
        plan["applied"] = True
        return plan


def manage_lease(root, policy, args):
    root_marker(root, policy)
    def report(db):
        run = run_row(db, args.run_id)
        return dict(run_id=run["id"], state=run["state"], owner_pid=run["owner_pid"], owner_start=run["owner_start"],
                    owner_state=lease_state(run), heartbeat_expired=run["expires"] < time.time(), reserved_bytes=run["reserved_bytes"])
    def recovery(db):
        result = report(db)
        if result["owner_state"] not in ("dead", "pid-reused"):
            raise DataError("所有者仍活动或身份未知；过期心跳不能单独证明死亡")
        run = run_row(db, args.run_id)
        run_folder(root, run)
        with runner_locks(root, root / run["path"] / ".lease-probe"):
            pass
        return dict(plan_hash=digest(dict(action="recover-lease", run=dict(run), proof=result["owner_state"], policy_hash=digest(policy))), **result)
    if args.action in ("status", "recover-preview"):
        db = open_index(root)
        try:
            return report(db) if args.action == "status" else recovery(db)
        finally:
            db.close()
    with write_index(root, policy) as db:
        if args.action in ("release", "recover"):
            # 核销预留不增长payload；禁止用业务限额或全树扫描卡死必要维护。
            if shutil.disk_usage(root).free < policy["metadata_reserve_bytes"]:
                raise DataError("租约维护所需元数据余量不足；保留状态并拒绝写入")
        else:
            check_budget(root, db, policy)
        run = run_row(db, args.run_id)
        if args.action == "recover":
            plan = recovery(db)
            if args.approve_hash != plan["plan_hash"]:
                raise DataError("租约恢复须批准当前进程证明与具体计划摘要")
        else:
            authorize_run(run, args.token)
        if run["state"] not in ("allocating", "running"):
            raise DataError("运行已封口或释放，不能改写租约")
        run_folder(root, run)
        with runner_locks(root, root / run["path"] / ".lease-probe"):
            if args.action == "heartbeat":
                db.execute("UPDATE runs SET expires=? WHERE id=?", (time.time() + policy["lease_seconds"], args.run_id))
            else:
                db.execute("UPDATE runs SET state='abandoned',reserved_bytes=0,outcome='incomplete' WHERE id=?", (args.run_id,))
                db.execute("UPDATE operations SET phase='abandoned' WHERE id=?", (args.run_id,))
        return report(db)


def cache_references(root, policy, args):
    marker = root_marker(root, policy)
    database = managed_file(root, args.database)
    for suffix in ("-wal", "-shm", "-journal"):
        side = Path(str(database) + suffix)
        if os.path.lexists(side) and not checked_path(side).is_file():
            raise DataError("旧缓存SQLite侧文件须为普通文件")
    wal, shm = Path(str(database) + "-wal"), Path(str(database) + "-shm")
    with database.open("rb") as handle:
        header = handle.read(20)
    if len(header) >= 20 and header[:16] == b"SQLite format 3\x00" and (header[18] == 2 or header[19] == 2):
        raise DataError("旧缓存为WAL模式；普通只读连接仍可能写侧文件，须先提供停写一致性备份，拒绝源目录写入")
    journal = Path(str(database) + "-journal")
    if (wal.exists() and wal.stat().st_size) or (journal.exists() and journal.stat().st_size):
        raise DataError("旧缓存存在未纳入一致性备份的日志；拒绝忽略日志或隐式恢复")
    relative = database.relative_to(root).as_posix()
    refs, truncated = [], False
    source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    index = open_index(root)
    try:
        source.execute("PRAGMA query_only=ON")
        source.execute("BEGIN")
        tables = [name for name in ("batches", "reusable") if source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()]
        for table in tables:
            # 表名来自固定白名单；值过大的行不取回，保留未知引用保护。
            rows = source.execute(f"SELECT CASE WHEN length(key)<=256 THEN key END, CASE WHEN length(value)<=65536 THEN value END FROM {table} LIMIT ?", (args.limit + 1,)).fetchall()
            if len(rows) > args.limit:
                truncated = True
            for key, raw in rows[:args.limit]:
                owner = "cache:" + digest(dict(database=relative, table=table, key=key))
                record = dict(owner=owner, table=table, key=key, value_hash=digest(raw), target=None, reason="unknown-cache-row")
                try:
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError("缓存行不是对象")
                    if value.get("status") in ("failed", "invalid"):
                        continue
                    if value.get("status") != "success" or not isinstance(value.get("sha256"), str):
                        raise ValueError("缺少成功报告身份")
                    origin = value.get("origin", str(database.parent) if table == "batches" else None)
                    artifact = value["artifact"]
                    if not isinstance(origin, str) or not Path(origin).is_absolute() or not isinstance(artifact, str) or Path(artifact).is_absolute():
                        raise ValueError("缓存路径身份不完整")
                    native = managed_file(root, str(Path(origin) / artifact / "native.json"))
                    row = index.execute("SELECT * FROM artifacts WHERE path=?", (native.relative_to(root).as_posix(),)).fetchone()
                    info = native.stat()
                    if row and row["sha256"] == value["sha256"] and row["identity"] == json.dumps([info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]):
                        record.update(target=row["id"], reason="legacy-original-path-required")
                except (ValueError, TypeError, KeyError, OSError):
                    pass  # 不能解释的行不忽略；记录为未知并保护整个根。
                refs.append(record)
        if truncated or not tables:
            refs.append(dict(owner="cache-scan:" + digest(relative), target=None, reason="incomplete-cache-scan"))
    finally:
        source.close()
        index.close()
    info = database.stat()
    plan = dict(action="cache-references", root_id=marker["root_id"], database=relative,
                source_identity=[info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns], references=refs,
                truncated=truncated, policy_hash=digest(policy))
    plan_hash = digest(plan)
    if args.approve_hash is None:
        return dict(plan_hash=plan_hash, applied=False, **plan)
    if args.approve_hash != plan_hash:
        raise DataError("缓存引用清单在预览后已变化，须重新批准")
    with write_index(root, policy) as db:
        check_budget(root, db, policy)
        for reference in refs:
            if reference["target"] is None:
                db.execute("INSERT OR REPLACE INTO unknown_refs VALUES (?,?)", (reference["owner"], reference["reason"]))
            else:
                db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,'cache')", (reference["owner"], reference["target"]))
                # 旧消费者仍按绝对origin读native.json；兼容依赖必须另外保留，不能用失效元数据冒充旧库已切换。
                db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,'durable')", ("legacy-path:" + reference["owner"], reference["target"]))
        db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "cache-references", "committed", json.dumps(plan)))
    return dict(plan_hash=plan_hash, applied=True, **plan)


FACT_BYTES = 16 * 1024
FACT_SCHEMA = 3
QUERY_BYTES = 1024 * 1024
DOCUMENT_BYTES = 16 * 1024 * 1024


def compact_json(value, maximum):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, RecursionError) as error:
        raise DataError("事实JSON包含非有限数值或过深结构") from error
    if len(text.encode("utf-8")) > maximum:
        raise DataError("事实或查询超过固定字节边界，须缩小选取范围")
    return text


def fact_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS facts (id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id), payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")


def has_table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def document(root, db, artifact_id):
    row = artifact_row(db, artifact_id)
    if not row["sealed"] or row["size"] > DOCUMENT_BYTES:
        raise DataError("事实来源须已封口，JSON输入上限16MiB；不能整文件读取更大报告")
    if any(reason.startswith(("lease:", "runner-lock")) for reason in protection(root, db, artifact_id)["reasons"]):
        raise DataError("事实来源仍被运行租约或字节锁保护，不能提取")
    source_root, source, source_image = read_location(root, db, row)
    with runner_locks(source_root, source), source.open("rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read(DOCUMENT_BYTES + 1)
        after = os.fstat(handle.fileno())
        identity = lambda info: [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
        if (len(raw) > DOCUMENT_BYTES or identity(before) != source_image["identity"] or
                identity(before) != identity(after) or identity(after) != identity(source.stat()) or
                hashlib.sha256(raw).hexdigest() != row["sha256"]):
            raise DataError("提取源身份或摘要已变化")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise DataError("源JSON含非有限数值")
        return number
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DataError("源JSON包含重复键，不能确定事实")
            result[key] = value
        return result
    def reject_constant(value):
        raise DataError("源JSON含非有限数值:" + value)
    try:
        value = json.loads(raw, parse_float=finite_float, parse_constant=reject_constant, object_pairs_hook=object_pairs)
    except (RecursionError, ValueError) as error:
        raise DataError("源JSON语法、数值或嵌套无效") from error
    if not isinstance(value, dict):
        raise DataError("事实来源须为JSON对象")
    return value, dict(artifact_id=artifact_id, sha256=row["sha256"], identity=json.loads(row["identity"]),
                       path=row["path"], schema_version=row["schema_version"])


def numeric(value, *, count=False):
    if value is None:
        return None
    if ((type(value) is not int if count else type(value) not in (int, float)) or
            value < 0 or value > (2**63 - 1 if count else 1e308) or not math.isfinite(value)):
        raise DataError("已有数值类型或范围无效，不能编造替代值")
    return value


def check_request(request):
    for key in ("seed", "input_seed", "iterations"):
        if request.get(key) is not None:
            numeric(request[key], count=True)
            if key == "iterations" and request[key] == 0:
                raise DataError("实际请求iterations须为正整数")
    if request.get("trace") is not None and type(request["trace"]) is not bool:
        raise DataError("实际请求trace须为JSON布尔值，不能用0/1替代")
    for key in ("condition", "stats", "purpose", "behavior_identity"):
        if request.get(key) is not None and (not isinstance(request[key], str) or not request[key]):
            raise DataError("实际请求身份字段须为非空字符串")
    for key in ("times", "reset_events"):
        if request.get(key) is not None and not isinstance(request[key], list):
            raise DataError("实际请求时刻及重置事件须为列表")
    for value in request.get("times") or []:
        numeric(value)


def extracted_fact(root, db, args):
    value, source = document(root, db, args.artifact_id)
    context_source = None
    metadata = value
    if args.context_artifact_id:
        metadata, context_source = document(root, db, args.context_artifact_id)
        if metadata.get("sha256") != source["sha256"]:
            raise DataError("上下文须以实际缓存行sha256绑定原生报告")
    request = metadata.get("request")
    if request is not None and not isinstance(request, dict):
        raise DataError("已记录request须为对象")
    if request is not None:
        check_request(request)
    details = metadata.get("condition_details")
    if details is not None:
        keys = {"fields", "class_name", "engine", "options", "config", "simulation_config", "cbor2", "rules"}
        if not isinstance(details, dict) or set(details) != keys or not request or digest(details) != request.get("condition"):
            raise DataError("完整条件展开与TaskStore条件摘要不符")
        if (any(not isinstance(details[key], dict) for key in ("fields", "engine", "config", "simulation_config", "rules")) or
                not isinstance(details["options"], list) or not isinstance(details["class_name"], str) or not isinstance(details["cbor2"], str)):
            raise DataError("记录条件字段结构无效，不能推定配置相同")
    context = dict(condition=details, request={key: item for key, item in (request or {}).items() if key != "condition"},
                   fidelity=metadata.get("fidelity"))
    native = value.get("sim")
    uncertainty, seconds, metric, action_sequence = None, None, None, None
    if isinstance(native, dict):
        players = native.get("players")
        if not isinstance(players, list) or not players:
            raise DataError("原生报告缺少玩家列表")
        selected = [player for player in players if isinstance(player, dict) and
                    (args.player_name is None or player.get("name") == args.player_name)]
        if len(selected) != 1:
            raise DataError("原生报告须唯一选择玩家，不能混合角色")
        data = selected[0].get("collected_data", {})
        if not isinstance(data, dict):
            raise DataError("原生collected_data须为对象")
        if "action_sequence" in data:
            if not isinstance(data["action_sequence"], list):
                raise DataError("原生动作序列须为列表，不能推定尝试概率")
            action_sequence = dict(artifact_id=args.artifact_id, entries=len(data["action_sequence"]),
                                   json_pointer=f"/sim/players/{players.index(selected[0])}/collected_data/action_sequence")
        metric = "raid_dps" if len(players) > 1 else "dps"
        statistics = native.get("statistics", {}) if len(players) > 1 else data
        damage = statistics.get(metric, {}) if isinstance(statistics, dict) else {}
        if not isinstance(damage, dict):
            raise DataError("原生伤害汇总须为对象")
        dps, samples = numeric(damage.get("mean")), numeric(damage.get("count"), count=True)
        uncertainty = {key: damage[key] for key in ("std_dev", "mean_std_dev", "variance", "confidence", "confidence_estimator") if key in damage} or None
        length = data.get("fight_length", {})
        seconds = numeric(length.get("mean")) if isinstance(length, dict) else None
        if context_source and (metadata.get("dps") != dps or metadata.get("samples") != samples):
            raise DataError("实际缓存摘要与原生报告数值不符")
        kind, status = "native_summary", metadata.get("status", "reported")
    else:
        summary = value.get("search_result", value)
        if not isinstance(summary, dict):
            raise DataError("已有结果摘要须为对象")
        dps, samples = numeric(summary.get("dps")), numeric(summary.get("samples"), count=True)
        kind = "search_summary" if "search_result" in value else "batch_summary"
        metric = summary.get("metric", "dps" if dps is not None else None)
        status = value.get("status")
        uncertainty = summary.get("uncertainty")
    if not isinstance(status, str):
        raise DataError("事实源缺少状态，不能推定模拟成功")
    flags = metadata if context_source else value
    search = value.get("search", {})
    if not isinstance(search, dict):
        raise DataError("已记录search须为对象")
    search_summary = {key: search[key] for key in ("dataset", "rounds", "candidate_count", "unique_candidates", "partial_round", "stop_reason", "no_improvement") if key in search}
    if "stop_reason" not in search_summary and "stop_reason" in value:
        search_summary["stop_reason"] = value["stop_reason"]
    search_censored = search_summary.get("stop_reason") in ("search_deadline", "cancelled")
    partial_round = search_summary.get("partial_round")
    if partial_round is not None and type(partial_round) is not bool:
        raise DataError("实际partial_round须为JSON布尔值")
    censored = flags.get("censored", True if status == "budget_exhausted" or search_censored else None)
    incomplete = flags.get("incomplete", True if status in ("failed", "incomplete", "cancelled", "budget_exhausted", "validation_incomplete") or partial_round is True or search_censored else None)
    for flag in (censored, incomplete):
        if flag is not None and type(flag) is not bool:
            raise DataError("删失/未完成标记须为布尔值或缺失")
    validation = value.get("independent_validation_complete")
    if validation is not None and type(validation) is not bool:
        raise DataError("独立验证完成标记须为JSON布尔值或缺失")
    validation_status = ("incomplete" if status == "validation_incomplete" or validation is False else
                         "complete" if validation is True else "unknown")
    sample_censored = flags.get("censored") if kind != "search_summary" else None
    sample_incomplete = flags.get("incomplete") if kind != "search_summary" else None
    summary_complete = (kind == "search_summary" and status == "completed" and validation_status == "complete" and
                        partial_round is False and search_summary.get("stop_reason") in ("no_improvement", "candidate_limit", "space_stalled") and
                        censored is not True and incomplete is not True)
    sample_complete = (True if dps is not None and samples is not None and samples > 0 and
                       ((request and status == "success" and sample_censored is not True and sample_incomplete is not True) or
                        summary_complete) else None)
    fact_id = str(uuid.uuid5(uuid.UUID(args.artifact_id), "fact-v3:" + digest(dict(context_source=context_source, player=args.player_name))))
    fact = dict(fact_id=fact_id, fact_schema=FACT_SCHEMA, source=source, context_source=context_source,
                source_kind=kind, status=status, censored=censored, incomplete=incomplete,
                censoring_scope="search" if search_censored else "result" if censored is True else None,
                sample_censored=sample_censored, sample_incomplete=sample_incomplete, sample_complete=sample_complete,
                dps=dps, metric=metric, samples=samples, seconds=seconds, uncertainty=uncertainty,
                fight_length_seconds=seconds, elapsed_seconds=numeric(value.get("elapsed_seconds")),
                phase=value.get("phase"), completed_batches=numeric(value.get("completed_batches"), count=True),
                search_summary=search_summary or None, validation_status=validation_status,
                requested_iterations=numeric(metadata.get("requested_iterations", (request or {}).get("iterations")), count=True),
                context=context, condition_hash=(request or {}).get("condition"), error=flags.get("error"),
                independent_validation_complete=validation,
                observations=dict(action_trace=value.get("action_trace"), action_sequence=action_sequence,
                                  probabilities=value.get("probabilities"),
                                  feedback=metadata.get("feedback"), position_summary=metadata.get("position_summary")))
    compact_json(fact, FACT_BYTES)
    return fact


def extract_facts(root, policy, args):
    with write_index(root, policy) as db:
        fact = extracted_fact(root, db, args)
        payload = compact_json(fact, FACT_BYTES)
        existing = db.execute("SELECT payload FROM facts WHERE id=?", (fact["fact_id"],)).fetchone() if has_table(db, "facts") else None
        if existing:
            if existing[0] != payload:
                raise DataError("同身份事实已存在且内容不符，不能覆盖")
            return dict(fact_id=fact["fact_id"], changed=False)
        check_budget(root, db, policy, 65536 + len(payload.encode("utf-8")) * 8)
        fact_tables(db)
        db.execute("INSERT INTO facts VALUES (?,?,?)", (fact["fact_id"], args.artifact_id, payload))
        for source in (fact["source"], fact["context_source"]):
            if source:
                db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", ("fact:" + fact["fact_id"], source["artifact_id"], "durable"))
        db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "extract-fact", "committed", json.dumps(dict(fact_id=fact["fact_id"]))))
    return dict(fact_id=fact["fact_id"], changed=True)


def fact_row(db, fact_id):
    row = db.execute("SELECT payload FROM facts WHERE id=?", (fact_id,)).fetchone() if has_table(db, "facts") else None
    if not row:
        raise DataError("未知事实ID")
    return json.loads(row[0])


@contextmanager
def fact_reader(root, policy):
    marker = root_marker(root, policy)
    db = open_index(root)
    try:
        identity = db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()
        if not identity or identity[0] != marker["root_id"]:
            raise DataError("事实索引根身份不符")
        db.execute("BEGIN")
        yield db
    finally:
        db.close()


def query_facts(root, policy, args):
    if not 1 <= args.limit <= 1000 or not 0 <= args.offset <= 1000000:
        raise DataError("事实查询limit须1..1000，offset须0..1000000")
    with fact_reader(root, policy) as db:
        if args.snapshot_id:
            stored = db.execute("SELECT payload FROM snapshots WHERE id=?", (args.snapshot_id,)).fetchone() if has_table(db, "snapshots") else None
            if not stored:
                raise DataError("未知快照ID")
            snapshot = json.loads(stored[0])
            rows = snapshot["rows"][args.offset:args.offset + args.limit + 1]
        elif has_table(db, "facts"):
            rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM facts ORDER BY id LIMIT ? OFFSET ?", (args.limit + 1, args.offset))]
        else:
            rows = []
    result = dict(fact_schema=FACT_SCHEMA, snapshot_id=args.snapshot_id, rows=rows[:args.limit], has_more=len(rows) > args.limit,
                  next_offset=args.offset + min(len(rows), args.limit))
    compact_json(result, QUERY_BYTES)
    return result


def context_leaves(value, prefix=""):
    if isinstance(value, dict) and value:
        result = {}
        for key, item in value.items():
            # 每个键段分别编码；点只分隔层级，字面点号/百分号/路径字符不混淆。
            segment = quote(key, safe="").replace(".", "%2E") if key else "%EMPTY"
            result.update(context_leaves(item, prefix + "." + segment if prefix else segment))
        return result
    return {prefix: value}


def compare_facts(root, policy, args):
    if not args.axis or len(args.axis) > 16 or len(args.stratify) > 16 or set(args.axis) & set(args.stratify):
        raise DataError("比较须显式声明1..16个互不重叠的变化轴，分层上限16")
    with fact_reader(root, policy) as db:
        left, right = fact_row(db, args.left), fact_row(db, args.right)
    complete_context = all(row["context"]["condition"] and row["context"]["fidelity"] is not None for row in (left, right))
    for row in (left, right):
        context = row["context"]
        check_request(context["request"])
        required = {"seed", "input_seed", "iterations", "stats", "program", "purpose", "times", "trace", "reset_events"}
        if not required <= context["request"].keys() or any(context["request"][key] is None for key in required):
            raise DataError("比较缺少实际请求、种子、保真度或采样预算")
        if complete_context and context["condition"]["config"].get("total_budget_seconds") is None:
            raise DataError("比较缺少记录的总预算")
    unknown_conditions = []
    if complete_context:
        scope = "expanded_conditions"
        a, b = context_leaves(left["context"]), context_leaves(right["context"])
    else:
        condition = left.get("condition_hash")
        if (not isinstance(condition, str) or len(condition) != 64 or any(character not in "0123456789abcdef" for character in condition) or
                condition != right.get("condition_hash")):
            raise DataError("无完整展开时只允许相同实际TaskStore条件摘要，不能跨未知条件比较")
        if any(not axis.startswith("request.") for axis in (*args.axis, *args.stratify)):
            raise DataError("相同不透明条件比较只能声明实际request字段变化或分层")
        scope = "same_opaque_condition"
        if any(not row["context"]["condition"] for row in (left, right)):
            unknown_conditions.append("condition_details")
        if any(row["context"]["fidelity"] is None for row in (left, right)):
            unknown_conditions.append("fidelity_label")
        if any(not row["context"]["condition"] or row["context"]["condition"]["config"].get("total_budget_seconds") is None for row in (left, right)):
            unknown_conditions.append("total_budget_value")
        a, b = (context_leaves(dict(request=row["context"]["request"], fidelity=row["context"]["fidelity"])) for row in (left, right))
    for axis in (*args.axis, *args.stratify):
        if axis not in a or axis not in b or a[axis] is None or b[axis] is None:
            raise DataError("变化轴或分层字段缺失；须使用完整叶字段路径")
    differences = {key for key in a.keys() | b.keys() if key not in a or key not in b or
                   compact_json(a[key], FACT_BYTES) != compact_json(b[key], FACT_BYTES)}
    if differences - set(args.axis) - set(args.stratify):
        raise DataError("未声明条件变化:" + ",".join(sorted(differences - set(args.axis) - set(args.stratify))))
    if left["source_kind"] != right["source_kind"] or left["metric"] != right["metric"]:
        raise DataError("报告口径或指标不同，拒绝混合比较")
    strata = {key: dict(left=a[key], right=b[key]) for key in args.stratify}
    comparable = not (differences & set(args.stratify))
    eligible = all(row.get("sample_complete") is True and row["dps"] is not None and
                   row["samples"] is not None and row["samples"] > 0 and not row["censored"] and not row["incomplete"] for row in (left, right))
    result = dict(left=args.left, right=args.right, axes={key: dict(left=a[key], right=b[key]) for key in args.axis},
                  comparison_scope=scope, unknown_conditions=unknown_conditions,
                  validation_status={side: row.get("validation_status", "unknown") for side, row in (("left", left), ("right", right))},
                  validation_complete=False if any(row.get("validation_status") == "incomplete" for row in (left, right)) else
                                      True if all(row.get("validation_status") == "complete" for row in (left, right)) else None,
                  sample_complete=dict(left=left.get("sample_complete"), right=right.get("sample_complete")),
                  termination={side: dict(censored=row["censored"], incomplete=row["incomplete"], search=row.get("search_summary"))
                               for side, row in (("left", left), ("right", right))},
                  elapsed_seconds=dict(left=left.get("elapsed_seconds"), right=right.get("elapsed_seconds")),
                  strata=strata, comparable=comparable and eligible, delta_dps=right["dps"] - left["dps"] if comparable and eligible else None,
                  delta_confidence_interval=None, samples=dict(left=left["samples"], right=right["samples"]),
                  uncertainty=dict(left=left["uncertainty"], right=right["uncertainty"]),
                  outcomes=dict(left=left["status"], right=right["status"]))
    compact_json(result, QUERY_BYTES)
    return result


def snapshot_facts(root, policy, args):
    root_id = root_marker(root, policy)["root_id"]
    ids = sorted(set(args.fact_id))
    if not ids or len(ids) > 1000:
        raise DataError("快照须显式选择1..1000个事实ID")
    def plan(db):
        payload = dict(root_id=root_id, fact_schema=FACT_SCHEMA, rows=[fact_row(db, identity) for identity in ids])
        compact_json(payload, QUERY_BYTES)
        checked = set()
        for fact in payload["rows"]:
            for source in (fact["source"], fact["context_source"]):
                if source and source["artifact_id"] not in checked:
                    _, current = document(root, db, source["artifact_id"])
                    if current["sha256"] != source["sha256"]:
                        raise DataError("快照来源摘要已改变，不能发布")
                    checked.add(source["artifact_id"])
        snapshot_id = str(uuid.uuid5(uuid.UUID(root_id), "snapshot:" + digest(payload)))
        return payload, dict(snapshot_id=snapshot_id, plan_hash=digest(dict(action="snapshot", payload=payload, policy=policy)), applied=False)
    if args.approve_hash is None:
        with fact_reader(root, policy) as db:
            return plan(db)[1]
    with write_index(root, policy) as db:
        payload, preview = plan(db)
        if args.approve_hash != preview["plan_hash"]:
            raise DataError("快照须批准当前选择与源身份摘要")
        text = compact_json(payload, QUERY_BYTES)
        existing = db.execute("SELECT payload FROM snapshots WHERE id=?", (preview["snapshot_id"],)).fetchone() if has_table(db, "snapshots") else None
        if existing and existing[0] != text:
            raise DataError("快照身份冲突，不能覆盖")
        if not existing:
            check_budget(root, db, policy, 65536 + len(text.encode("utf-8")) * 8)
            fact_tables(db)
            db.execute("INSERT INTO snapshots VALUES (?,?)", (preview["snapshot_id"], text))
            for fact in payload["rows"]:
                for source in (fact["source"], fact["context_source"]):
                    if source:
                        db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", ("snapshot:" + preview["snapshot_id"], source["artifact_id"], "durable"))
            db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "snapshot", "committed", json.dumps(preview)))
        preview["applied"] = True
        return preview


def lifecycle_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, phase TEXT NOT NULL, plan TEXT NOT NULL, reserved_bytes INTEGER NOT NULL, product TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS archives(id TEXT PRIMARY KEY, manifest TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS locations(artifact_id TEXT REFERENCES artifacts(id), path TEXT UNIQUE, identity TEXT NOT NULL, PRIMARY KEY(artifact_id,path))")


def relative_path(root, relative):
    """仅校验相对名字并拼接；调用者仍须立即核验文件系统路径。"""
    if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative or ":" in relative:
        raise DataError("受管相对路径无效")
    parts = relative.split("/")
    if any(part in ("", ".", "..") or part.endswith((".", " ")) for part in parts):
        raise DataError("受管相对路径含越界或Windows别名")
    devices = {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)), *("LPT" + str(i) for i in range(1, 10))}
    if any(part.split(".")[0].upper() in devices for part in parts):
        raise DataError("相对路径含Windows设备名")
    return root.joinpath(*parts)


def owned_path(root, relative):
    """允许新目录链，但逐层检查现有祖先；拒绝路径别名及链接。"""
    path = relative_path(root, relative)
    for parent in (*reversed(path.parents), path):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise DataError("数据路径含链接或重解析点")
        if parent != path and not stat.S_ISDIR(info.st_mode):
            raise DataError("路径祖先不是目录，拒绝将异常边界当作缺失")
    return path


def job_remaining(root, db):
    if not has_table(db, "jobs"):
        return 0
    remaining = 0
    for job in db.execute("SELECT * FROM jobs WHERE phase NOT IN ('sealed','abandoned')"):
        plan = json.loads(job["plan"])
        actual = 0
        for relative in (".staging/" + job["id"], plan["destination"]):
            path = owned_path(root, relative)
            if path.exists():
                measured = inventory(path, 1000)
                if measured["truncated"]:
                    raise DataError("操作工作区盘点不完整")
                actual += measured["logical_bytes"]
        if "metadata_phase_bytes" in plan:
            phases = ("reserved", "writing", "verified", "published", "sealed")
            if job["phase"] not in phases:
                raise DataError("操作阶段无效，拒绝计算可用预留")
            future = phases[phases.index(job["phase"]) + 1:]
            remaining += (max(0, plan["payload_reserved_bytes"] - actual)
                          + sum(plan["metadata_phase_bytes"][phase] for phase in future)
                          + plan["retry_metadata_bytes"])
        else:
            remaining += max(0, job["reserved_bytes"] - actual)
    return remaining


def phase_commit(db, operation_id, phase):
    db.execute("UPDATE jobs SET phase=? WHERE id=?", (phase, operation_id))
    db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "lifecycle", phase, json.dumps(dict(operation_id=operation_id))))
    db.commit()
    db.execute("BEGIN IMMEDIATE")


def product_manifest(directory):
    measured = inventory(directory, 1000)
    if measured["truncated"]:
        raise DataError("操作产品清单超过有界上限")
    result = []
    for parent, directories, files in os.walk(directory, followlinks=False):
        for name in files:
            path = checked_path(Path(parent) / name)
            result.append(dict(path=path.relative_to(directory).as_posix(), **file_manifest(path, allow_sqlite=True)))
    return sorted(result, key=lambda item: item["path"])


def check_product(db, operation_id, directory):
    expected = job_row(db, operation_id)["product"]
    if expected is None or compact_json(product_manifest(directory), QUERY_BYTES) != expected:
        raise DataError("已验证产品身份或摘要变化，拒绝发布或封口")


def operation_result(root, db, job):
    plan = json.loads(job["plan"])
    result = dict(operation_id=job["id"], phase=job["phase"], applied=job["phase"] == "sealed", plan_hash=digest(plan), kind=job["kind"])
    if job["kind"] == "archive":
        result.update(archive_id=job["id"], manifest_path=str(owned_path(root, plan["destination"] + "/manifest.json")))
    elif job["kind"] == "restore":
        result["restored"] = [dict(artifact_id=item["id"], path=str(owned_path(root, plan["destination"] + "/" + item["path"]))) for item in plan["manifest"]["sources"]]
    else:
        path = plan["destination"] + "/image.sqlite3"
        row = db.execute("SELECT id FROM artifacts WHERE path=?", (path,)).fetchone()
        result.update(path=str(owned_path(root, path)), artifact_id=row[0] if row else None)
    return result


def job_row(db, operation_id):
    job = db.execute("SELECT * FROM jobs WHERE id=?", (operation_id,)).fetchone() if has_table(db, "jobs") else None
    if job is None:
        raise DataError("未知生命周期操作")
    return job


def manage_operation(root, policy, args):
    root_marker(root, policy)
    if args.action in ("status", "abandon-preview"):
        with closing(open_index(root)) as db:
            job = job_row(db, args.operation_id)
            if args.action == "status":
                return operation_result(root, db, job)
            preview = dict(action="abandon", operation_id=job["id"], phase=job["phase"], plan_hash=digest(json.loads(job["plan"])), retained_bytes=True)
            preview["approval_hash"] = digest(preview)
            return preview
    with write_index(root, policy) as db:
        job = job_row(db, args.operation_id)
        preview = dict(action="abandon", operation_id=job["id"], phase=job["phase"], plan_hash=digest(json.loads(job["plan"])), retained_bytes=True)
        preview["approval_hash"] = digest(preview)
        if args.approve_hash != preview["approval_hash"] or job["phase"] == "sealed":
            raise DataError("放弃操作须批准当前清单，已封口操作不能放弃")
        plan = json.loads(job["plan"])
        write_peak = plan.get("metadata_phase_bytes", {}).get("writing", 4 * len(job["plan"].encode("utf-8")) + 131072)
        if shutil.disk_usage(root).free < policy["metadata_reserve_bytes"] + write_peak:
            raise DataError("缺少操作日志写入空间")
        phase_commit(db, job["id"], "abandoned")
        return dict(preview, applied=True)


def artifact_image(root, db, row):
    _, source, manifest = read_location(root, db, row)
    if not row["sealed"]:
        raise DataError("封口文件身份或摘要不匹配")
    return dict(id=row["id"], path=row["path"], role=row["role"], schema_version=row["schema_version"], **manifest)


def idle_image(root, db, row):
    if any(reason.startswith(("lease:", "read-lease:", "runner-lock")) for reason in protection(root, db, row["id"], activity_only=True)["reasons"]):
        raise DataError("活动租约或文件锁阻止读取生命周期输入")
    return artifact_image(root, db, row)


def archive_sources(root, db, ids):
    if not ids or len(ids) > 1000 or len(set(ids)) != len(ids):
        raise DataError("归档须列出1至1000个不同的登记ID")
    sources = []
    index_paths(root)
    for artifact_id in sorted(ids):
        row = artifact_row(db, artifact_id)
        reasons = protection(root, db, artifact_id, activity_only=True)["reasons"]
        if any(reason.startswith(("lease:", "read-lease:", "runner-lock")) for reason in reasons):
            raise DataError("活动租约或文件锁阻止归档")
        sources.append(artifact_image(root, db, row))
    return sources


class SegmentReader:
    def __init__(self, handle, size):
        self.handle, self.remaining = handle, size
        self.hash = hashlib.sha256()

    def read(self, size=-1):
        size = self.remaining if size < 0 else min(size, self.remaining)
        block = self.handle.read(size)
        self.remaining -= len(block)
        self.hash.update(block)
        return block


def write_json_file(path, value):
    with path.open("xb") as handle:
        handle.write(compact_json(value, QUERY_BYTES).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def private_stage(root, plan):
    stage = owned_path(root, ".staging/" + plan["operation_id"])
    marker = dict(root_id=plan["root_id"], operation_id=plan["operation_id"], plan_hash=digest(plan))
    if stage.exists():
        if json.loads(checked_path(stage / ".job.json").read_text(encoding="utf-8")) != marker:
            raise DataError("临时工作区身份不匹配")
    else:
        stage.parent.mkdir(parents=True, exist_ok=True)
        creating = stage.parent / ("creating-" + str(uuid.uuid4()))
        creating.mkdir()
        write_json_file(creating / ".job.json", marker)
        if os.path.lexists(stage):
            raise DataError("临时操作目录在建立期间出现，拒绝覆盖")
        os.replace(creating, stage)
    return stage


def quarantine_retry(root, stage, db, operation_id):
    """不删除未完成产品；先清单化，再转到操作私有隔离子目录。"""
    data = stage / "data"
    if not data.exists():
        return
    measured = inventory(data, 1000)
    if measured["truncated"]:
        raise DataError("未完成工作区过大，拒绝自动重试")
    manifests = []
    for parent, directories, files in os.walk(data, followlinks=False):
        for name in files:
            path = checked_path(Path(parent) / name)
            manifests.append((path.relative_to(data).as_posix(), file_manifest(path, allow_sqlite=True)))
    # 每个文件的身份在移动前重核；目录重解析点已由inventory拒绝。
    for relative, manifest in manifests:
        if file_manifest(checked_path(data / relative), allow_sqlite=True) != manifest:
            raise DataError("临时产品在隔离前变化")
    destination = stage / ("retained-" + str(uuid.uuid4()))
    db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "retry-quarantine", "prepared", json.dumps(dict(operation_id=operation_id, source=str(data), destination=str(destination), logical_bytes=measured["logical_bytes"]))))
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    os.replace(data, destination)


def create_archive(root, db, plan, data):
    manifest = dict(format=1, root_id=plan["root_id"], archive_id=plan["operation_id"], sources=plan["sources"], parts=[])
    part_size = plan["part_bytes"]
    number = 0
    archive = None
    index_paths(root)

    def finish_part():
        nonlocal archive, number
        archive.close()
        compressed.close()
        output.flush()
        os.fsync(output.fileno())
        handles.close()
        os.replace(temporary, data / part_name)
        manifest["parts"].append(dict(path=plan["destination"] + "/" + part_name,
            **file_manifest(data / part_name), members=members))
        number += 1
        archive = None

    with ExitStack() as handles:
        for source in plan["sources"]:
            source_root, path, current_image = read_location(root, db, artifact_row(db, source["id"]))
            if current_image != {key: source[key] for key in ("sha256", "size", "identity")}:
                raise DataError("归档读取位置或身份改变")
            with runner_locks(source_root, path):
                with path.open("rb") as handle:
                    whole = hashlib.sha256()
                    for offset in range(0, max(1, source["size"]), part_size):
                        length = min(part_size, source["size"] - offset)
                        if archive is not None and (payload + length > part_size or len(members) >= 1000):
                            finish_part()
                        if archive is None:
                            if number >= 1000:
                                raise DataError("归档分包超过1000，拒绝继续写入")
                            part_name = "part-%06d.tar.gz" % number
                            temporary = data / (part_name + ".tmp")
                            output = handles.enter_context(temporary.open("xb"))
                            compressed = handles.enter_context(gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0))
                            archive = handles.enter_context(tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT))
                            payload, members = 0, []
                        reader = SegmentReader(handle, length)
                        name = "objects/" + source["id"] + "/" + str(offset)
                        member = tarfile.TarInfo(name)
                        member.size = length
                        archive.addfile(member, reader)
                        if reader.remaining:
                            raise DataError("归档原件提前结束")
                        # 再次有界读取原片段，供原文件整体摘要验证；不装载整个原件。
                        handle.seek(offset)
                        remaining = length
                        while remaining:
                            block = handle.read(min(1024 * 1024, remaining))
                            if not block:
                                raise DataError("归档原件变化")
                            whole.update(block)
                            remaining -= len(block)
                        members.append(dict(name=name, artifact_id=source["id"], offset=offset, size=length, sha256=reader.hash.hexdigest()))
                        payload += length
                if whole.hexdigest() != source["sha256"] or file_manifest(path, allow_sqlite=source["role"] == "sqlite-backup") != {key: source[key] for key in ("sha256", "size", "identity")}:
                    raise DataError("归档原件身份或原SHA发生变化")
        if archive is not None:
            finish_part()
    write_json_file(data / "manifest.json", manifest)
    return manifest


class LimitedReader:
    def __init__(self, handle, limit):
        self.handle, self.remaining = handle, limit

    def read(self, size=-1):
        requested = min(self.remaining + 1, 1024 * 1024 if size < 0 else size)
        block = self.handle.read(requested)
        self.remaining -= len(block)
        if self.remaining < 0:
            raise DataError("归档解压超过声明上限")
        return block


def verify_archive(root, manifest, data=None, *, package_root=None):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list) or not isinstance(manifest.get("parts"), list) or not 1 <= len(manifest["sources"]) <= 1000 or not 1 <= len(manifest["parts"]) <= 1000:
        raise DataError("归档清单须含有界来源和分包列表")
    for source in manifest["sources"]:
        if not isinstance(source, dict) or not {"id", "path", "role", "sha256", "size"} <= source.keys() or type(source["size"]) is not int or source["size"] < 0:
            raise DataError("归档来源字段无效")
        if any(not isinstance(source[key], str) for key in ("id", "path", "role", "sha256")):
            raise DataError("归档来源字段类型无效")
    for part in manifest["parts"]:
        if not isinstance(part, dict) or not {"path", "sha256", "size", "members"} <= part.keys() or type(part["size"]) is not int or part["size"] < 0 or not isinstance(part["members"], list) or not 1 <= len(part["members"]) <= 1000:
            raise DataError("归档包字段无效")
        if not isinstance(part["sha256"], str):
            raise DataError("归档包摘要类型无效")
        owned_path(root, part["path"])
        for member in part["members"]:
            if not isinstance(member, dict) or not {"name", "artifact_id", "offset", "size", "sha256"} <= member.keys() or type(member["size"]) is not int or type(member["offset"]) is not int or min(member["size"], member["offset"]) < 0:
                raise DataError("归档成员字段无效")
            if any(not isinstance(member[key], str) for key in ("name", "artifact_id", "sha256")):
                raise DataError("归档成员字段类型无效")
    if manifest.get("format") != 1 or manifest.get("root_id") != root_marker(root, {"root_id": None})["root_id"]:
        raise DataError("归档格式或根身份不匹配")
    sources = {source["id"]: source for source in manifest["sources"]}
    if len(sources) != len(manifest["sources"]) or not sources:
        raise DataError("归档来源重复或为空")
    hashes = {key: hashlib.sha256() for key in sources}
    offsets = {key: 0 for key in sources}
    for source in sources.values():
        owned_path(root, source["path"])
        if data is not None:
            output = owned_path(data, source["path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb"):
                pass
    names = set()
    for part in manifest["parts"]:
        package = checked_path(package_root / Path(part["path"]).name) if package_root else managed_file(root, str(relative_path(root, part["path"])))
        current = file_manifest(package)
        if current["sha256"] != part["sha256"] or current["size"] != part["size"]:
            raise DataError("归档包摘要或大小不匹配")
        expected = part["members"]
        limit = sum(512 + ((member["size"] + 511) // 512) * 512 for member in expected) + 16384
        with package.open("rb") as raw, gzip.GzipFile(fileobj=raw, mode="rb") as decompressed:
            bounded = LimitedReader(decompressed, limit)
            for descriptor in expected:
                header = bounded.read(512)
                if len(header) != 512:
                    raise DataError("归档成员头提前结束")
                member = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
                owned_path(root, descriptor["name"])
                if member is None or not member.isreg() or member.pax_headers or member.name != descriptor["name"] or member.size != descriptor["size"] or member.name in names:
                    raise DataError("归档成员含链接、重复、路径或大小不匹配")
                names.add(member.name)
                key = descriptor["artifact_id"]
                if key not in sources or descriptor["offset"] != offsets[key] or descriptor["size"] < 0 or offsets[key] + member.size > sources[key]["size"]:
                    raise DataError("归档片段范围不连续或越界")
                checksum = hashlib.sha256()
                with ExitStack() as stack:
                    output = stack.enter_context(owned_path(data, sources[key]["path"]).open("ab")) if data else None
                    remaining = member.size
                    while remaining:
                        block = bounded.read(min(1024 * 1024, remaining))
                        if not block:
                            raise DataError("归档成员字节提前结束")
                        remaining -= len(block)
                        checksum.update(block)
                        hashes[key].update(block)
                        if output:
                            output.write(block)
                    if output:
                        output.flush()
                        os.fsync(output.fileno())
                if checksum.hexdigest() != descriptor["sha256"]:
                    raise DataError("归档成员原字节摘要不匹配")
                offsets[key] += member.size
                padding = (-member.size) % 512
                if padding and (len(block := bounded.read(padding)) != padding or any(block)):
                    raise DataError("归档成员填充损坏")
            trailer = bounded.read(1024)
            if len(trailer) != 1024 or any(trailer):
                raise DataError("归档缺少结束标记或含未列出的成员")
            while block := bounded.read(1024 * 1024):
                if any(block):
                    raise DataError("归档尾部含未声明数据")
        if file_manifest(package) != current:
            raise DataError("归档包在校验中变化")
    for key, source in sources.items():
        if offsets[key] != source["size"] or hashes[key].hexdigest() != source["sha256"]:
            raise DataError("恢复原SHA或原大小不匹配")


def lifecycle_plan(root, policy, db, args):
    if args.operation_id:
        job = job_row(db, args.operation_id)
        if job["kind"] != args.command:
            raise DataError("操作类型不匹配")
        return json.loads(job["plan"])
    plan = dict(kind=args.command, root_id=root_marker(root, policy)["root_id"], policy_hash=digest(policy))
    if args.command == "backup-sqlite" and args.request_id and has_table(db, "jobs"):
        operation_id = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "operation:" + digest(dict(kind=args.command, root_id=plan["root_id"], request_id=args.request_id))))
        existing = db.execute("SELECT * FROM jobs WHERE id=?", (operation_id,)).fetchone()
        if existing:
            saved = json.loads(existing["plan"])
            path = checked_path(args.database)
            info = path.stat()
            if path.relative_to(root).as_posix() != saved["source"] or [info.st_dev, info.st_ino] != saved["source_identity"]:
                raise DataError("备份请求ID的源身份发生变化")
            return saved
    if args.command == "archive":
        plan.update(sources=archive_sources(root, db, args.artifact_id), part_bytes=policy["archive_part_bytes"])
        if not isinstance(plan["part_bytes"], int) or plan["part_bytes"] <= 0:
            raise DataError("分包大小须先配置")
        count = sum(max(1, (source["size"] + plan["part_bytes"] - 1) // plan["part_bytes"]) for source in plan["sources"])
        if count > 1000:
            raise DataError("本批归档分包超过1000，请分批登记归档")
        plan["reserved_bytes"] = sum(source["size"] for source in plan["sources"]) * 2 + count * 65536 + 524288
        plan["product_bound"] = sum(source["size"] for source in plan["sources"]) * 2 + count * 32768 + 65536
    elif args.command == "restore":
        if args.manifest:
            manifest_path = managed_file(root, args.manifest)
        else:
            row = db.execute("SELECT manifest FROM archives WHERE id=?", (args.archive_id,)).fetchone() if has_table(db, "archives") else None
            if row is None:
                raise DataError("未知归档ID")
            manifest_path = managed_file(root, str(root / row[0]))
        registered = db.execute("SELECT * FROM artifacts WHERE path=?", (manifest_path.relative_to(root).as_posix(),)).fetchone()
        if registered is None:
            raise DataError("恢复清单须先登记")
        registered_manifest = idle_image(root, db, registered)
        if manifest_path.stat().st_size > QUERY_BYTES:
            raise DataError("归档清单过大")
        with manifest_path.open("rb") as handle:
            raw_manifest = handle.read(QUERY_BYTES + 1)
        if len(raw_manifest) > QUERY_BYTES or hashlib.sha256(raw_manifest).hexdigest() != registered_manifest["sha256"] or file_manifest(manifest_path) != {key: registered_manifest[key] for key in ("sha256", "size", "identity")}:
            raise DataError("归档清单在读取时变化")
        plan["manifest"] = json.loads(raw_manifest)
        verify_archive(root, plan["manifest"])
        for part in plan["manifest"]["parts"]:
            registered = db.execute("SELECT * FROM artifacts WHERE path=?", (part["path"],)).fetchone()
            if registered is None or idle_image(root, db, registered)["sha256"] != part["sha256"]:
                raise DataError("归档包须先登记并核对当前身份")
        for source in plan["manifest"]["sources"]:
            row = artifact_row(db, source["id"])
            if row["sha256"] != source["sha256"] or row["size"] != source["size"] or row["role"] != source["role"] or row["path"] != source["path"]:
                raise DataError("归档与登记来源不一致")
        target = Path(args.destination) if args.destination else None
        if target is None or not target.is_absolute() or not target.is_relative_to(root):
            raise DataError("恢复目的须为受管根内的绝对新路径")
        relative = target.relative_to(root).as_posix()
        owned_path(root, relative)
        if relative.split("/")[0].startswith(".") or relative.startswith("index.sqlite3") or os.path.lexists(target):
            raise DataError("恢复拒绝覆盖已有路径或管理目录")
        plan["destination"] = relative
        plan["reserved_bytes"] = sum(source["size"] for source in plan["manifest"]["sources"]) * 2 + 524288
        plan["product_bound"] = sum(source["size"] for source in plan["manifest"]["sources"])
    else:
        if not args.request_id or len(args.request_id) > 128:
            raise DataError("备份须提供不超过128字符的请求ID")
        if not args.database or not Path(args.database).is_absolute():
            raise DataError("备份须提供SQLite源的绝对路径")
        source = checked_path(args.database)
        if not source.is_relative_to(root) or not source.is_file():
            raise DataError("SQLite源须为受管根内普通文件")
        if source.relative_to(root).parts[0] == ".staging":
            raise DataError("SQLite备份不能读取未封口工作区")
        for run in db.execute("SELECT path FROM runs WHERE state IN ('allocating','running')"):
            if source.is_relative_to(root / run["path"]):
                raise DataError("活动运行租约阻止SQLite备份")
        with source.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                raise DataError("源不是SQLite数据库")
        for suffix in ("-wal", "-shm", "-journal"):
            if os.path.lexists(Path(str(source) + suffix)):
                checked_path(str(source) + suffix)
        identity = source.stat()
        plan.update(request_id=args.request_id, source=source.relative_to(root).as_posix(), source_identity=[identity.st_dev, identity.st_ino])
        wal = Path(str(source) + "-wal")
        plan["reserved_bytes"] = (source.stat().st_size + (wal.stat().st_size if wal.exists() else 0)) * 2 + 524288
        plan["product_bound"] = plan["reserved_bytes"] - 262144
    stable = dict(plan)
    if args.command == "backup-sqlite":
        stable = dict(kind=args.command, root_id=plan["root_id"], request_id=args.request_id)
    plan["operation_id"] = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "operation:" + digest(stable)))
    if "destination" not in plan:
        plan["destination"] = (".archives/" if args.command == "archive" else ".backups/") + plan["operation_id"]
    if has_table(db, "jobs"):
        existing = db.execute("SELECT * FROM jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        if existing:
            saved = json.loads(existing["plan"])
            if args.command == "backup-sqlite" and (saved["source"] != plan["source"] or saved["source_identity"] != plan["source_identity"]):
                raise DataError("备份请求ID已绑定另一个源身份")
            return saved
    return metadata_peak_plan(plan, db)


def metadata_peak_plan(plan, db):
    """按实际编码字节估计每次事务的主库/WAL复制、索引及页面峰值。"""
    page_size = db.execute("PRAGMA page_size").fetchone()[0]
    page_count = db.execute("PRAGMA page_count").fetchone()[0]
    depth_bound = max(1, math.ceil(math.log2(page_count + 1)))
    if plan["kind"] == "restore":
        paths = [source["path"] for source in plan["manifest"]["sources"]]
    elif plan["kind"] == "archive":
        count = sum(max(1, (source["size"] + plan["part_bytes"] - 1) // plan["part_bytes"]) for source in plan["sources"])
        paths = ["part-%06d.tar.gz" % number for number in range(count)] + ["manifest.json"]
    else:
        paths = ["image.sqlite3"]
    # 字段与product_manifest一致，数值长度取超出系统stat最大值的保守上界。
    products = [dict(path=path, sha256="f" * 64, size=(1 << 128) - 1,
                     identity=[(1 << 128) - 1] * 4) for path in paths]
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    product_bytes = len(encode(products))
    catalogue = [dict(id="f" * 36, path=plan["destination"] + "/" + item["path"],
                      role="sqlite-backup", identity=json.dumps(item["identity"]), sha256=item["sha256"],
                      size=item["size"], schema_version=1, sealed=1, last_used=1e128) for item in products]
    if plan["kind"] == "backup-sqlite":
        catalogue.append(dict(catalogue[0], path=plan["source"], sealed=0))
    catalogue_bytes = len(encode(catalogue))
    root = Path(db.execute("PRAGMA database_list").fetchone()[2]).parent
    stage = root / ".staging" / plan["operation_id"]
    log_bytes = len(encode(dict(operation_id=plan["operation_id"], kind=plan["kind"], phase="published",
                                source=str(stage / "data"), destination=str(stage / ("retained-" + "f" * 36)),
                                logical_bytes=(1 << 128) - 1)))
    source_catalogue_bytes = len(encode(catalogue[-1])) if plan["kind"] == "backup-sqlite" else 0
    pages = lambda size: ((size + page_size - 1) // page_size) * page_size
    payload = plan["reserved_bytes"]
    plan.update(payload_reserved_bytes=payload, metadata_phase_bytes={}, retry_metadata_bytes=0,
                metadata_peak_bytes=0, product_metadata_bound_bytes=product_bytes)
    for _ in range(16):
        previous = encode(plan)
        plan_bytes = len(previous)
        phases = dict(
            reserved=pages(4 * (plan_bytes + 3 * source_catalogue_bytes + log_bytes)) + 131072,
            writing=pages(4 * (plan_bytes + log_bytes)) + 65536,
            verified=pages(4 * (plan_bytes + product_bytes + log_bytes)) + 65536,
            published=pages(4 * (plan_bytes + product_bytes + log_bytes)) + 65536,
            sealed=pages(4 * (plan_bytes + product_bytes + 3 * catalogue_bytes + log_bytes)) + 65536
                   + len(catalogue) * (12 + 18 * depth_bound) * page_size)
        retry = max(phases["writing"], phases["verified"]) + pages(log_bytes * 4) + 65536
        peak = sum(phases.values()) + retry
        plan.update(metadata_phase_bytes=phases, retry_metadata_bytes=retry,
                    metadata_peak_bytes=peak, reserved_bytes=payload + peak)
        if encode(plan) == previous:
            return plan
    raise DataError("元数据峰值计划未收敛，拒绝写入")


def backup_image(root, plan, data):
    source = checked_path(root / plan["source"])
    current = source.stat()
    if [current.st_dev, current.st_ino] != plan["source_identity"]:
        raise DataError("SQLite源文件被替换")
    for suffix in ("-wal", "-shm", "-journal"):
        side = Path(str(source) + suffix)
        if os.path.lexists(side):
            checked_path(side)
    with runner_locks(root, source):
        reader = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)
        writer = None
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM sqlite_master").fetchone()
            page_size = reader.execute("PRAGMA page_size").fetchone()[0]
            snapshot_bytes = reader.execute("PRAGMA page_count").fetchone()[0] * page_size
            if snapshot_bytes > plan["product_bound"]:
                raise DataError("SQLite固定快照超过已批准payload上界，拒绝创建映像")
            writer = sqlite3.connect(data / "image.sqlite3")
            deadline = time.monotonic() + 30
            def progress(status, remaining, total):
                if time.monotonic() > deadline or total * page_size > plan["product_bound"]:
                    raise DataError("SQLite备份超过时间或已批准预留")
            reader.backup(writer, pages=128, progress=progress, sleep=0.01)
            after = source.stat()
            if [after.st_dev, after.st_ino] != plan["source_identity"]:
                raise DataError("SQLite源身份在一致性备份中变化")
            writer.execute("PRAGMA journal_mode=DELETE")
            if writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise DataError("SQLite备份完整性检查失败")
        finally:
            if writer is not None:
                writer.close()
            reader.close()
    return file_manifest(checked_path(data / "image.sqlite3"), allow_sqlite=True)


def seal_job(root, db, plan):
    destination = owned_path(root, plan["destination"])
    check_product(db, plan["operation_id"], destination)
    if plan["kind"] == "archive":
        manifest_path = checked_path(destination / "manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["sources"] != plan["sources"] or manifest["archive_id"] != plan["operation_id"]:
            raise DataError("归档清单与批准来源不一致")
        verify_archive(root, manifest)
        db.execute("INSERT OR IGNORE INTO archives VALUES (?,?)", (plan["operation_id"], manifest_path.relative_to(root).as_posix()))
        for path in [manifest_path, *(root / part["path"] for part in manifest["parts"])]:
            image = file_manifest(checked_path(path))
            relative = path.relative_to(root).as_posix()
            identity = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "artifact:" + os.path.normcase(relative)))
            db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (identity, relative, "archive", image["sha256"], image["size"], json.dumps(image["identity"]), 1, 1, time.time()))
            db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", ("archive:" + plan["operation_id"], identity, "durable"))
    elif plan["kind"] == "restore":
        for source in plan["manifest"]["sources"]:
            path = checked_path(relative_path(destination, source["path"]))
            image = file_manifest(path, allow_sqlite=source["role"] == "sqlite-backup")
            if image["sha256"] != source["sha256"] or image["size"] != source["size"]:
                raise DataError("发布后恢复原SHA不一致")
            db.execute("INSERT OR IGNORE INTO locations VALUES (?,?,?)", (source["id"], path.relative_to(root).as_posix(), json.dumps(image["identity"])))
    else:
        path = checked_path(destination / "image.sqlite3")
        image = file_manifest(path, allow_sqlite=True)
        relative = path.relative_to(root).as_posix()
        identity = str(uuid.uuid5(uuid.UUID(plan["root_id"]), "artifact:" + os.path.normcase(relative)))
        db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (identity, relative, "sqlite-backup", image["sha256"], image["size"], json.dumps(image["identity"]), 1, 1, time.time()))
    phase_commit(db, plan["operation_id"], "sealed")


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


def dependency_protection(root, db, artifact_id, *, own_job=None, activity_only=False):
    pending, seen, reasons = [artifact_id], set(), []
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if len(seen) > 1000:
            raise DataError("依赖闭包超过1000项，拒绝不完整保护计算")
        row = db.execute("SELECT * FROM artifacts WHERE id=?", (current,)).fetchone()
        if row is None:
            reasons.append("unknown-dependency-owner:" + current)
            continue
        refs = db.execute("SELECT owner,kind FROM refs WHERE target=?", (current,)).fetchall()
        if current != artifact_id:
            if not activity_only and (row["role"] in PROTECTED_ROLES or {part.casefold() for part in Path(row["path"]).parts} & PROTECTED_DIRECTORIES or
                    db.execute("SELECT 1 FROM pins WHERE artifact_id=?", (current,)).fetchone() or any(ref["kind"] != "cache" for ref in refs)):
                reasons.append("persistent-dependency:" + current)
            if has_table(db, "readers") and db.execute("SELECT 1 FROM readers WHERE artifact_id=? AND state='active'", (current,)).fetchone():
                reasons.append("read-lease:dependency:" + current)
            if any(row["path"].startswith(run["path"] + "/") for run in db.execute("SELECT path FROM runs WHERE state IN ('allocating','running')")):
                reasons.append("lease:dependency:" + current)
            try:
                with runner_locks(root, owned_path(root, row["path"])):
                    pass
            except DataError:
                reasons.append("runner-lock:dependency:" + current)
            for table in (() if activity_only else ("jobs", "safety_jobs")):
                if has_table(db, table):
                    for job in db.execute("SELECT * FROM " + table + " WHERE phase NOT IN ('sealed','abandoned')"):
                        if table == "safety_jobs" and job["id"] == own_job:
                            continue
                        plan = json.loads(job["plan"])
                        sources = plan.get("sources", plan.get("items", plan.get("manifest", {}).get("sources", [])))
                        if any(source["id"] == current for source in sources):
                            reasons.append("operation:dependency:" + job["id"])
        pending.extend(ref["owner"][9:] for ref in refs if ref["owner"].startswith("artifact:"))
    return reasons


def dependency_add(root, policy, args):
    with write_index(root, policy) as db:
        artifact_row(db, args.artifact_id)
        artifact_row(db, args.requires)
        pending, seen = [args.requires], set()
        while pending:
            current = pending.pop()
            if current == args.artifact_id:
                raise DataError("依赖成环，拒绝登记")
            if current in seen:
                continue
            seen.add(current)
            if len(seen) > 1000:
                raise DataError("依赖闭包过大")
            pending.extend(row[0] for row in db.execute("SELECT target FROM refs WHERE owner=?", ("artifact:" + current,)))
        check_budget(root, db, policy, 65536)
        owner = "artifact:" + args.artifact_id
        previous = db.execute("SELECT kind FROM refs WHERE owner=? AND target=?", (owner, args.requires)).fetchone()
        if previous and previous[0] != args.kind:
            raise DataError("依赖不得降级或覆盖")
        db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", (owner, args.requires, args.kind))
        return dict(artifact_id=args.artifact_id, requires=args.requires, kind=args.kind, applied=True)


def legacy_register(root, policy, args):
    marker = root_marker(root, policy)
    directory = checked_path(args.directory)
    if not directory.is_dir() or not directory.is_relative_to(root) or directory == root:
        raise DataError("旧目录须为受管根内明确子目录，不能扫描整根")
    def plan(db):
        measured = inventory(directory, args.limit)
        if measured["truncated"]:
            raise DataError("旧目录清单不完整，须明确分批")
        rows, sidecars = [], []
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in sorted(files):
                path = checked_path(Path(parent) / name)
                if name == ".runner.lock":
                    continue
                if any(name.endswith(suffix) for suffix in ("-wal", "-shm", "-journal")):
                    base = Path(parent) / name.rsplit("-", 1)[0]
                    if base.is_file():
                        with checked_path(base).open("rb") as handle:
                            if handle.read(16) == b"SQLite format 3\x00":
                                sidecars.append(path.relative_to(root).as_posix())
                                continue
                path = managed_file(root, str(path))
                if any(path.is_relative_to(root / run[0]) for run in db.execute("SELECT path FROM runs WHERE state IN ('allocating','running')")):
                    raise DataError("活动运行阻止旧目录登记")
                with runner_locks(root, path):
                    with path.open("rb") as handle:
                        sql = handle.read(16) == b"SQLite format 3\x00"
                    image = file_manifest(path, allow_sqlite=sql)
                relative = path.relative_to(root).as_posix()
                rows.append(dict(artifact_id=str(uuid.uuid5(uuid.UUID(marker["root_id"]), "artifact:" + os.path.normcase(relative))),
                                 path=relative, role="sqlite-source" if sql else args.role, schema_version=1, sealed=not sql,
                                 logical_snapshot=False if sql else None, **image))
        result = dict(action="legacy-register", root_id=marker["root_id"], directory=directory.relative_to(root).as_posix(),
                      policy_hash=digest(policy), artifacts=sorted(rows, key=lambda row: row["path"]), protected_sqlite_sidecars=sorted(sidecars))
        result["plan_hash"] = digest(result)
        return result
    if args.approve_hash is None:
        with closing(open_index(root)) as db:
            return dict(plan(db), applied=False)
    with write_index(root, policy) as db:
        preview = plan(db)
        if args.approve_hash != preview["plan_hash"]:
            raise DataError("旧目录身份/摘要/配置已变，须重新批准")
        check_budget(root, db, policy, 131072 + len(compact_json(preview, QUERY_BYTES).encode()) * 8)
        for row in preview["artifacts"]:
            existing = db.execute("SELECT * FROM artifacts WHERE id=?", (row["artifact_id"],)).fetchone()
            values = (row["sha256"], json.dumps(row["identity"]), row["role"])
            if existing and (existing["sha256"], existing["identity"], existing["role"]) != values:
                raise DataError("旧对象已登记不同版本或角色，不覆盖")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)", (row["artifact_id"], row["path"], row["role"], row["sha256"], row["size"], values[1], 1, int(row["sealed"]), time.time()))
            db.execute("INSERT OR IGNORE INTO refs VALUES (?,?,?)", ("legacy-path:" + preview["directory"], row["artifact_id"], "unknown"))
        return dict(preview, applied=True)


def reader_lease(root, policy, args):
    root_marker(root, policy)
    if args.action in ("status", "recover-preview"):
        with closing(open_index(root)) as db:
            row = db.execute("SELECT * FROM readers WHERE id=?", (args.lease_id,)).fetchone() if has_table(db, "readers") else None
            if row is None:
                raise DataError("未知读取租约")
            preview = dict(lease_id=row["id"], artifact_id=row["artifact_id"], state=row["state"],
                           owner_state=lease_state(row), heartbeat_expired=time.time() > row["expires"], expires=row["expires"])
            if args.action == "recover-preview":
                preview.pop("heartbeat_expired")
                preview["plan_hash"] = digest(preview)
            return preview
    with write_index(root, policy) as db:
        if args.action == "acquire":
            if not args.artifact_id or not args.owner_pid:
                raise DataError("读取租约需要数据ID及调用者PID")
            owner_start = process_start(args.owner_pid)
            if owner_start in (None, "unknown"):
                raise DataError("无法核实读取者出生身份")
            if any(reason.startswith("operation:") for reason in protection(root, db, args.artifact_id)["reasons"]):
                raise DataError("未完成的位置操作阻止新增读者租约")
            resolved = resolve_artifact(root, policy, argparse.Namespace(artifact_id=args.artifact_id, inspect=True))
            check_budget(root, db, policy, 131072)
            db.execute("CREATE TABLE IF NOT EXISTS readers(id TEXT PRIMARY KEY,artifact_id TEXT REFERENCES artifacts(id),owner_pid INTEGER,owner_start TEXT,token_hash TEXT,expires REAL,state TEXT)")
            identity, token = str(uuid.uuid4()), args.token or secrets.token_urlsafe(32)
            db.execute("INSERT INTO readers VALUES (?,?,?,?,?,?,?)", (identity, args.artifact_id, args.owner_pid, owner_start,
                       hashlib.sha256(token.encode()).hexdigest(), time.time() + policy["lease_seconds"], "active"))
            db.execute("UPDATE artifacts SET last_used=? WHERE id=?", (time.time(), args.artifact_id))
            return dict(lease_id=identity, token=token, path=resolved["path"], artifact_id=args.artifact_id)
        row = db.execute("SELECT * FROM readers WHERE id=?", (args.lease_id,)).fetchone() if has_table(db, "readers") else None
        if row is None:
            raise DataError("未知读取租约")
        preview = dict(lease_id=row["id"], artifact_id=row["artifact_id"], state=row["state"], owner_state=lease_state(row), expires=row["expires"])
        preview["plan_hash"] = digest(preview)
        if args.action == "recover":
            if preview["owner_state"] not in ("dead", "pid-reused") or args.approve_hash != preview["plan_hash"]:
                raise DataError("读取者未确定死亡/复用或当前恢复计划未批准；过期不能单独回收")
        else:
            authorize_run(row, args.token)
        if shutil.disk_usage(root).free < policy["metadata_reserve_bytes"]:
            raise DataError("读取租约维护缺少元数据空间")
        if args.action == "heartbeat":
            check_budget(root, db, policy, 65536)
            db.execute("UPDATE readers SET expires=? WHERE id=?", (time.time() + policy["lease_seconds"], row["id"]))
        else:
            db.execute("UPDATE readers SET state='released' WHERE id=?", (row["id"],))
        return dict(preview, applied=True)


def safety_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS volumes(id TEXT PRIMARY KEY,path TEXT UNIQUE,marker TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS placements(artifact_id TEXT REFERENCES artifacts(id),volume_id TEXT,path TEXT,identity TEXT,state TEXT,PRIMARY KEY(artifact_id,volume_id,path))")
    db.execute("CREATE TABLE IF NOT EXISTS custody(artifact_id TEXT PRIMARY KEY REFERENCES artifacts(id),operation_id TEXT,path TEXT,identity TEXT,state TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS safety_jobs(id TEXT PRIMARY KEY,kind TEXT,phase TEXT,plan TEXT,reserved_bytes INTEGER,progress TEXT)")


def bounded_text(path, limit=QUERY_BYTES):
    path = checked_path(path)
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read(limit + 1)
        if (len(raw) > limit or not stat.S_ISREG(before.st_mode) or
                identity(before) != identity(os.fstat(handle.fileno())) or identity(before) != identity(checked_path(path).stat())):
            raise DataError("管理清单/标记超过有界长度或读取身份变化")
    return raw.decode("utf-8")


def volume_root(root, db, volume_id):
    if not volume_id:
        return root
    row = db.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone() if has_table(db, "volumes") else None
    if row is None:
        raise DataError("目标卷未登记")
    path = checked_path(row["path"])
    marker = checked_path(path / ".simdata-volume.json")
    if bounded_text(marker) != row["marker"] or json.loads(row["marker"])["root_id"] != db.execute("SELECT value FROM metadata WHERE key='root_id'").fetchone()[0]:
        raise DataError("受管卷身份或边界变化")
    return path


def domain_inventory(root, db, *, observe_runs=False):
    measured = inventory(root, None, run_db=db if observe_runs else None)
    if has_table(db, "volumes"):
        for row in db.execute("SELECT id FROM volumes ORDER BY id"):
            other = inventory(volume_root(root, db, row["id"]), None)
            measured["logical_bytes"] += other["logical_bytes"]
            measured["truncated"] = measured["truncated"] or other["truncated"]
    return measured


def safety_remaining(db):
    if not has_table(db, "safety_jobs"):
        return 0
    # 保守保留整个未封口预留；原件、复制件和隔离件均由域盘点另外计入。
    return db.execute("SELECT coalesce(sum(reserved_bytes),0) FROM safety_jobs WHERE phase NOT IN ('sealed','abandoned')").fetchone()[0]


def migration_materialized(root, db, job):
    plan = json.loads(job["plan"])
    target_root = volume_root(root, db, plan["volume_id"])
    if "target_device" in plan and target_root.stat().st_dev != plan["target_device"]:
        raise DataError("迁移目标实际卷身份变化")
    actual = 0
    work = owned_path(target_root, ".staging/" + job["id"])
    data = owned_path(work, "data")
    if os.path.lexists(data):
        marker = dict(root_id=plan["root_id"], operation_id=job["id"], plan_hash=digest(plan))
        if json.loads(bounded_text(work / ".job.json")) != marker:
            raise DataError("未完成迁移工作区身份不符，不能抵扣预留")
        measured = inventory(data, None)
        if measured["truncated"]:
            raise DataError("迁移工作区盘点不完整")
        actual += measured["logical_bytes"]
    destination = owned_path(target_root, plan["destination"])
    if os.path.lexists(destination):
        if job["phase"] not in ("verified", "published", "sealed"):
            raise DataError("未发布迁移出现未知目标，不能抵扣预留")
        measured = inventory(destination, None)
        if measured["truncated"]:
            raise DataError("迁移产品盘点不完整")
        actual += measured["logical_bytes"]
    if actual > plan["payload_reserved_bytes"]:
        raise DataError("迁移保留产品超过已批准载荷预留，须保留现场并明确处理")
    return actual


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


def check_physical_volume(root, db, policy, target, growth=0):
    future = physical_future(root, db, target.stat().st_dev)
    headroom = policy["maintenance_reserve_bytes"] + policy["metadata_reserve_bytes"]
    if shutil.disk_usage(target).free < future + growth + headroom:
        raise DataError("实际目标卷未来载荷/元数据并发预留和维护余量不足，拒绝超卖")
    return dict(future_reserved_bytes=future, headroom_bytes=headroom)


def safety_metadata_peak(db, payload):
    encoded = len(compact_json(payload, QUERY_BYTES).encode("utf-8"))
    page = db.execute("PRAGMA page_size").fetchone()[0]
    checkpoint = db.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
    # 两代主库/WAL页面、计划/进度重写、六个索引DDL与逐项日志的保守余量。
    return max(1048576, 2 * (max(1000, checkpoint) + 64) * page) + encoded * 16 + len(payload) * 32 * page


def canonical_operation_id(identity):
    try:
        if str(uuid.UUID(identity)) != identity:
            raise ValueError("noncanonical")
    except (ValueError, AttributeError, TypeError) as error:
        raise DataError("操作ID须为规范小写UUID，两个入口使用同一命名") from error
    return identity


def register_volume(root, policy, args):
    root_id = root_marker(root, policy)["root_id"]
    target = checked_path(args.path)
    if not target.is_dir() or target.is_relative_to(root) or root.is_relative_to(target):
        raise DataError("受管卷必须是与主根分离的既有空目录")
    if policy["mode"] == "test":
        temporary = Path(tempfile.gettempdir()).resolve()
        synthetic = SKILL_ROOT.parents[2] / ".local" / ("simdata-synthetic-" + root_id)
        if not target.is_relative_to(temporary) and not target.is_relative_to(synthetic):
            raise DataError("测试卷必须位于临时目录或根ID限定的仓库合成目录")
    volume_id = str(uuid.uuid5(uuid.UUID(root_id), "volume:" + os.path.normcase(str(target))))
    marker = dict(root_id=root_id, volume_id=volume_id, mode=policy["mode"], path=str(target))
    text = compact_json(marker, QUERY_BYTES)
    plan = dict(action="volume-register", marker=marker, policy_hash=digest(policy))
    plan["plan_hash"] = digest(plan)
    with closing(open_index(root)) as db:
        old = db.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone() if has_table(db, "volumes") else None
        if old:
            volume_root(root, db, volume_id)
            return dict(plan, applied=True)
    contents = list(target.iterdir())
    marker_path = target / ".simdata-volume.json"
    if contents and not (contents == [marker_path] and bounded_text(marker_path) == text):
        raise DataError("不能接管非空未知卷")
    if not args.approve_hash:
        return dict(plan, applied=False)
    if args.approve_hash != plan["plan_hash"]:
        raise DataError("受管卷须批准当前预览")
    with write_index(root, policy) as db:
        check_budget(root, db, policy, 262144)
        if shutil.disk_usage(target).free < 262144 + policy["maintenance_reserve_bytes"]:
            raise DataError("目标卷无维护空间")
        if not os.path.lexists(marker_path):
            with marker_path.open("x", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        safety_tables(db)
        db.execute("INSERT INTO volumes VALUES (?,?,?)", (volume_id, str(target), text))
    return dict(plan, applied=True)


def safety_phase(db, identity, phase, progress):
    db.execute("UPDATE safety_jobs SET phase=?,progress=?,reserved_bytes=CASE WHEN ?='sealed' THEN 0 ELSE reserved_bytes END WHERE id=?",
               (phase, compact_json(progress, QUERY_BYTES), phase, identity))
    db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "safety", phase, compact_json(dict(operation_id=identity), QUERY_BYTES)))
    db.commit()
    db.execute("BEGIN IMMEDIATE")


def safety_source(root, db, identity, *, destructive=False, own_job=None):
    row = artifact_row(db, identity)
    protected = protection(root, db, identity, own_job=own_job)
    reasons = protected["reasons"]
    if destructive and (reasons or protected["cache_references"]):
        raise DataError("持久/未知引用、活动租约、锁或尚未批准失效的加速缓存阻止隔离/删除")
    if any(value.startswith(("lease:", "read-lease:", "runner-lock", "operation:")) for value in reasons):
        raise DataError("活动操作、租约或锁阻止位置变更")
    image = artifact_image(root, db, row)
    if destructive:
        original = managed_file(root, str(root / row["path"]))
        image = dict(id=row["id"], path=row["path"], role=row["role"], schema_version=row["schema_version"],
                     **file_manifest(original, allow_sqlite=row["role"] == "sqlite-backup"))
        if not row["sealed"] or json.dumps(image["identity"]) != row["identity"] or image["sha256"] != row["sha256"]:
            raise DataError("原路径隔离对象身份不符")
    return dict(image, references=protected["references"], reasons=reasons)


def safety_job_status(root, policy, args):
    root_marker(root, policy)
    with closing(open_index(root)) as db:
        job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (args.operation_id,)).fetchone() if has_table(db, "safety_jobs") else None
        if job is None:
            raise DataError("未知安全生命周期操作")
        result = dict(operation_id=job["id"], kind=job["kind"], phase=job["phase"], plan_hash=digest(json.loads(job["plan"])), progress=json.loads(job["progress"]))
    if args.action == "status":
        return result
    preview = dict(action="abandon", operation_id=job["id"], kind=job["kind"], phase=job["phase"], plan_hash=result["plan_hash"], retained_bytes=True)
    preview["approval_hash"] = digest(preview)
    if args.action == "abandon-preview":
        return preview
    with write_index(root, policy) as db:
        current = db.execute("SELECT * FROM safety_jobs WHERE id=?", (args.operation_id,)).fetchone()
        if dict(current) != dict(job) or args.approve_hash != preview["approval_hash"]:
            raise DataError("放弃操作须批准当前清单，全部复制件保留")
        if job["kind"] != "migration" or job["phase"] in ("sealed", "abandoned"):
            raise DataError("只允许放弃未封口非破坏性迁移；隔离/删除须恢复其具体操作")
        if shutil.disk_usage(root).free < policy["metadata_reserve_bytes"] + 131072:
            raise DataError("放弃操作缺少日志空间")
        safety_phase(db, args.operation_id, "abandoned", result["progress"])
    return dict(preview, applied=True)


def migration(root, policy, args):
    root_id = root_marker(root, policy)["root_id"]
    def preview(db):
        if args.operation_id and has_table(db, "safety_jobs"):
            job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (args.operation_id,)).fetchone()
            if job:
                plan = json.loads(job["plan"])
                if job["kind"] != "migration" or sorted(args.artifact_id) != [item["id"] for item in plan["sources"]]:
                    raise DataError("重试输入与迁移清单不符")
                return plan, job
        if not args.artifact_id or len(set(args.artifact_id)) != len(args.artifact_id) or len(args.artifact_id) > 1000:
            raise DataError("迁移须明确列出不同的已登记对象")
        destination_root = volume_root(root, db, args.volume_id)
        if not args.destination or not Path(args.destination).is_absolute():
            raise DataError("迁移目标须为受管卷内绝对路径")
        destination = Path(args.destination)
        if not destination.is_relative_to(destination_root):
            raise DataError("迁移目标越界")
        relative = destination.relative_to(destination_root).as_posix()
        target = owned_path(destination_root, relative)
        if relative.split("/")[0].startswith(".") or relative.startswith("index.sqlite3") or os.path.lexists(target):
            raise DataError("迁移目标须为新的非管理目录，拒绝覆盖")
        sources = [safety_source(root, db, identity) for identity in sorted(args.artifact_id)]
        identity = args.operation_id or str(uuid.uuid5(uuid.UUID(root_id), "migration:" + digest(dict(sources=sources, volume=args.volume_id, destination=relative))))
        canonical_operation_id(identity)
        payload_reserve = sum(item["size"] for item in sources) * 2
        metadata_reserve = safety_metadata_peak(db, dict(sources=sources, destination=relative, root=str(root), target=str(destination_root)))
        reserve = payload_reserve + metadata_reserve
        return dict(action="migration", root_id=root_id, operation_id=identity, sources=sources, volume_id=args.volume_id,
                    target_device=destination_root.stat().st_dev,
                    destination=relative, policy_hash=digest(policy), payload_reserved_bytes=payload_reserve,
                    metadata_reserved_bytes=metadata_reserve, reserved_bytes=reserve), None
    with closing(open_index(root)) as db:
        plan, job = preview(db)
    approval = digest(plan)
    if not args.approve_hash:
        return dict(plan, plan_hash=approval, applied=False)
    if args.approve_hash != approval or plan["policy_hash"] != digest(policy):
        raise DataError("迁移须批准当前清单和配置")
    with write_index(root, policy) as db:
        target_root = volume_root(root, db, plan["volume_id"])
        target = owned_path(target_root, plan["destination"])
        stage = owned_path(target_root, ".staging/" + plan["operation_id"] + "/data")
        safety_tables(db)
        job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        if job is None:
            current, _ = preview(db)
            if digest(current) != approval:
                raise DataError("迁移预览后来源变化")
            check_budget(root, db, policy, plan["reserved_bytes"], physical_growth=plan["metadata_reserved_bytes"] if plan["volume_id"] else plan["reserved_bytes"])
            target_growth = plan["payload_reserved_bytes"] + (plan["metadata_reserved_bytes"] if target_root.stat().st_dev == root.stat().st_dev else 0)
            check_physical_volume(root, db, policy, target_root, target_growth)
            db.execute("INSERT INTO safety_jobs VALUES (?,?,?,?,?,?)", (plan["operation_id"], "migration", "reserved", compact_json(plan, QUERY_BYTES), plan["reserved_bytes"], "{}"))
            safety_phase(db, plan["operation_id"], "reserved", {})
            job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        if job["plan"] != compact_json(plan, QUERY_BYTES):
            raise DataError("迁移日志身份不符")
        if job["phase"] == "abandoned":
            raise DataError("已放弃迁移不能重新启用，保留所有文件")
        if "target_device" in plan and target_root.stat().st_dev != plan["target_device"]:
            raise DataError("迁移批准后实际目标卷身份变化")
        progress = json.loads(job["progress"])
        if job["phase"] == "sealed":
            for item in plan["sources"]:
                copied = file_manifest(checked_path(target / item["path"]), allow_sqlite=item["role"] == "sqlite-backup")
                if copied != progress[item["id"]]:
                    raise DataError("迁移封口产物已变化")
        else:
            for item in plan["sources"]:
                if safety_source(root, db, item["id"], own_job=plan["operation_id"]) != item:
                    raise DataError("迁移来源或保护状态已变化")
            if job["phase"] in ("reserved", "writing"):
                if os.path.lexists(target):
                    raise DataError("迁移发布前目标已出现")
                private_stage(target_root, plan)
                stage.mkdir(exist_ok=True)
                checked_path(stage)
                safety_phase(db, plan["operation_id"], "writing", progress)
                for item in plan["sources"]:
                    source_root, source, _ = read_location(root, db, artifact_row(db, item["id"]))
                    output = owned_path(stage, item["path"])
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if item["id"] not in progress:
                        check_budget(root, db, policy)
                        check_physical_volume(root, db, policy, target_root)
                        if migration_materialized(root, db, job) + item["size"] > plan["payload_reserved_bytes"]:
                            raise DataError("复制重试耗尽已批准载荷预留，保留部分产品")
                        if os.path.lexists(output):
                            os.replace(checked_path(output), output.with_name(output.name + ".retained-" + str(uuid.uuid4())))
                        if shutil.disk_usage(target_root).free < item["size"] + policy["metadata_reserve_bytes"]:
                            raise DataError("复制期间目标卷空间不足")
                        with runner_locks(source_root, source), source.open("rb") as incoming, output.open("xb") as outgoing:
                            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                            outgoing.flush()
                            os.fsync(outgoing.fileno())
                        copied = file_manifest(output, allow_sqlite=item["role"] == "sqlite-backup")
                        if copied["sha256"] != item["sha256"] or copied["size"] != item["size"]:
                            raise DataError("迁移复制摘要不符，保留现场")
                        progress[item["id"]] = copied
                        safety_phase(db, plan["operation_id"], "writing", progress)
                    elif file_manifest(checked_path(output), allow_sqlite=item["role"] == "sqlite-backup") != progress[item["id"]]:
                        raise DataError("已验证临时复制件变化")
                safety_phase(db, plan["operation_id"], "verified", progress)
            if not os.path.lexists(target):
                for item in plan["sources"]:
                    if file_manifest(checked_path(stage / item["path"]), allow_sqlite=item["role"] == "sqlite-backup") != progress[item["id"]]:
                        raise DataError("发布前复制件变化")
                    if safety_source(root, db, item["id"], own_job=plan["operation_id"]) != item:
                        raise DataError("发布前来源变化")
                target.parent.mkdir(parents=True, exist_ok=True)
                checked_path(target.parent)
                os.replace(stage, target)  # stage 与 target 总在同一个目标卷；跨卷原件始终保留。
            for item in plan["sources"]:
                if file_manifest(checked_path(target / item["path"]), allow_sqlite=item["role"] == "sqlite-backup") != progress[item["id"]]:
                    raise DataError("已发布复制件身份不符")
            safety_phase(db, plan["operation_id"], "published", progress)
            for item in plan["sources"]:
                db.execute("UPDATE placements SET state='available' WHERE artifact_id=? AND state='preferred'", (item["id"],))
                db.execute("INSERT OR REPLACE INTO placements VALUES (?,?,?,?,?)", (item["id"], plan["volume_id"], plan["destination"] + "/" + item["path"], json.dumps(progress[item["id"]]["identity"]), "preferred"))
            safety_phase(db, plan["operation_id"], "sealed", progress)
        return dict(operation_id=plan["operation_id"], phase="sealed", applied=True, plan_hash=approval,
                    copies=[dict(artifact_id=item["id"], path=str(target / item["path"])) for item in plan["sources"]], originals_retained=True)


def quarantine(root, policy, args):
    root_id = root_marker(root, policy)["root_id"]
    recovering = args.command == "recover-quarantine"
    def preview(db):
        if args.operation_id and has_table(db, "safety_jobs"):
            old = db.execute("SELECT * FROM safety_jobs WHERE id=?", (args.operation_id,)).fetchone()
            if old:
                plan = json.loads(old["plan"])
                if old["kind"] != args.command or sorted(args.artifact_id) != [item["id"] for item in plan["sources"]]:
                    raise DataError("隔离重试与原清单不同")
                return plan
        if not args.artifact_id or len(set(args.artifact_id)) != len(args.artifact_id) or len(args.artifact_id) > 1000:
            raise DataError("隔离或恢复须明确列出不同的登记ID")
        sources = []
        for identity in sorted(args.artifact_id):
            if recovering:
                row = artifact_row(db, identity)
                custody = db.execute("SELECT * FROM custody WHERE artifact_id=? AND state='quarantined'", (identity,)).fetchone() if has_table(db, "custody") else None
                if custody is None:
                    raise DataError("对象不在可恢复隔离中")
                protected = protection(root, db, identity)
                if any(reason.startswith(("lease:", "read-lease:", "runner-lock", "operation:")) for reason in protected["reasons"]):
                    raise DataError("活动消费阻止隔离恢复")
                source = checked_path(owned_path(root, custody["path"]))
                image = file_manifest(source, allow_sqlite=row["role"] == "sqlite-backup")
                if image["sha256"] != row["sha256"] or json.dumps(image["identity"]) != custody["identity"]:
                    raise DataError("隔离文件当前身份不符")
                if os.path.lexists(owned_path(root, row["path"])):
                    raise DataError("原路径已存在，恢复拒绝覆盖")
                sources.append(dict(id=identity, path=row["path"], role=row["role"], custody_path=custody["path"], **image))
            else:
                sources.append(safety_source(root, db, identity, destructive=True))
        generation = [dict(row) for row in db.execute("SELECT artifact_id,operation_id,state FROM custody WHERE artifact_id IN (" + ",".join("?" for _ in args.artifact_id) + ") ORDER BY artifact_id", args.artifact_id)] if has_table(db, "custody") else []
        identity = args.operation_id or str(uuid.uuid5(uuid.UUID(root_id), args.command + ":" + digest(dict(sources=sources, generation=generation))))
        canonical_operation_id(identity)
        return dict(action=args.command, root_id=root_id, operation_id=identity, sources=sources,
                    policy_hash=digest(policy), reserved_bytes=safety_metadata_peak(db, dict(sources=sources, root=str(root), action=args.command)))
    with closing(open_index(root)) as db:
        plan = preview(db)
    approval = digest(plan)
    if not args.approve_hash:
        return dict(plan, plan_hash=approval, applied=False, space_released=False)
    if args.approve_hash != approval or plan["policy_hash"] != digest(policy):
        raise DataError("隔离或恢复须批准当前清单")
    with write_index(root, policy) as db:
        safety_tables(db)
        job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        if job is None:
            if digest(preview(db)) != approval:
                raise DataError("隔离预览后文件或引用变化")
            check_budget(root, db, policy, plan["reserved_bytes"])
            db.execute("INSERT INTO safety_jobs VALUES (?,?,?,?,?,?)", (plan["operation_id"], args.command, "reserved", compact_json(plan, QUERY_BYTES), plan["reserved_bytes"], "{}"))
            safety_phase(db, plan["operation_id"], "reserved", {})
            job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        if job["plan"] != compact_json(plan, QUERY_BYTES):
            raise DataError("隔离日志身份不符")
        progress = json.loads(job["progress"])
        for item in plan["sources"]:
            original = owned_path(root, item["path"])
            isolated = owned_path(root, item["custody_path"] if recovering else ".quarantine/" + plan["operation_id"] + "/" + item["path"])
            incoming, outgoing = (isolated, original) if recovering else (original, isolated)
            protected = protection(root, db, item["id"], own_job=plan["operation_id"])
            reasons = protected["reasons"]
            if (not recovering and (reasons or protected["cache_references"])) or any(value.startswith(("lease:", "read-lease:", "runner-lock", "operation:")) for value in reasons):
                raise DataError("隔离执行前发现保护或活动消费者")
            if item["id"] not in progress:
                incoming_exists, outgoing_exists = os.path.lexists(incoming), os.path.lexists(outgoing)
                if incoming_exists and outgoing_exists:
                    raise DataError("隔离原路径和目标同时存在，拒绝覆盖")
                expected = dict(sha256=item["sha256"], size=item["size"], identity=item["identity"])
                if incoming_exists:
                    if file_manifest(checked_path(incoming), allow_sqlite=item["role"] == "sqlite-backup") != expected:
                        raise DataError("隔离前来源身份改变")
                    if recovering and any(os.path.lexists(path) for path in (original,)):
                        raise DataError("恢复拒绝覆盖")
                    outgoing.parent.mkdir(parents=True, exist_ok=True)
                    checked_path(outgoing.parent)
                    # 日志在移动前持久化；中断后只有身份完全匹配的目标才能被接管。
                    safety_phase(db, plan["operation_id"], "writing", progress)
                    with runner_locks(root, original), deletion_handle(incoming, expected, destination=outgoing, boundary=root) as relocate:
                        relocate()
                elif not outgoing_exists:
                    raise DataError("隔离两端均缺失，保留日志等待调查")
                observed = file_manifest(checked_path(outgoing), allow_sqlite=item["role"] == "sqlite-backup")
                if observed != expected:
                    raise DataError("隔离或恢复后的字节/身份不符")
                progress[item["id"]] = observed
                if recovering:
                    db.execute("UPDATE custody SET state='restored' WHERE artifact_id=?", (item["id"],))
                else:
                    db.execute("INSERT OR REPLACE INTO custody VALUES (?,?,?,?,?)", (item["id"], plan["operation_id"], isolated.relative_to(root).as_posix(), json.dumps(observed["identity"]), "quarantined"))
                safety_phase(db, plan["operation_id"], "published", progress)
            elif file_manifest(checked_path(outgoing), allow_sqlite=item["role"] == "sqlite-backup") != progress[item["id"]]:
                raise DataError("已隔离或恢复对象被改变")
        if job["phase"] != "sealed":
            safety_phase(db, plan["operation_id"], "sealed", progress)
        return dict(operation_id=plan["operation_id"], phase="sealed", applied=True, plan_hash=approval, space_released=False,
                    items=[dict(artifact_id=item["id"], path=str(owned_path(root, item["path"] if recovering else ".quarantine/" + plan["operation_id"] + "/" + item["path"]))) for item in plan["sources"]])


@contextmanager
def deletion_handle(path, expected, *, destination=None, boundary=None):
    """Windows拒绝写入/删除共享，校验和删除使用同一个内核文件句柄。"""
    checked_path(path)
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        directory_handles = ExitStack()
        if boundary is not None:
            if not path.is_relative_to(boundary) or (destination is not None and not destination.is_relative_to(boundary)):
                raise DataError("句柄操作越过受管边界")
            directories = {parent for leaf in (path, destination) if leaf is not None
                           for parent in leaf.parents if parent.is_relative_to(boundary)}
            class FileInformation(ctypes.Structure):
                _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                            ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                            ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD), ("size_low", wintypes.DWORD),
                            ("links", wintypes.DWORD), ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]
            kernel.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.POINTER(FileInformation))
            kernel.GetFileInformationByHandle.restype = wintypes.BOOL
            try:
                for directory in sorted(directories, key=lambda item: len(item.parts)):
                    checked_path(directory)
                    name = "\\\\?\\" + str(directory) if not str(directory).startswith("\\\\") else "\\\\?\\UNC\\" + str(directory)[2:]
                    opened_directory = kernel.CreateFileW(name, 0x80000000, 3, None, 3, 0x02000000 | 0x00200000, None)
                    if opened_directory == wintypes.HANDLE(-1).value:
                        raise DataError("无法锁定受管目录边界，拒绝移动/删除")
                    directory_handles.callback(kernel.CloseHandle, opened_directory)
                    information = FileInformation()
                    if (not kernel.GetFileInformationByHandle(opened_directory, ctypes.byref(information)) or
                            not information.attributes & 0x10 or information.attributes & 0x400):
                        raise DataError("目录句柄不是普通受管目录")
                    checked_path(directory)
            except BaseException:
                directory_handles.close()
                raise
        name = "\\\\?\\" + str(path) if not str(path).startswith("\\\\") else "\\\\?\\UNC\\" + str(path)[2:]
        native = kernel.CreateFileW(name, 0x80000000 | 0x10000, 1, None, 3, 0x00200000, None)
        if native == wintypes.HANDLE(-1).value:
            directory_handles.close()
            raise DataError("无法取得排他删除句柄；活动句柄或权限不足时拒绝删除")
        try:
            descriptor = msvcrt.open_osfhandle(native, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(native)
            directory_handles.close()
            raise
        handle = os.fdopen(descriptor, "rb")
        kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel.SetFileInformationByHandle.restype = wintypes.BOOL
        def remove():
            if destination is not None:
                checked_path(destination.parent)
                if os.path.lexists(destination):
                    raise DataError("隔离/恢复目标已出现，拒绝覆盖")
                target_name = "\\\\?\\" + str(destination) if not str(destination).startswith("\\\\") else "\\\\?\\UNC\\" + str(destination)[2:]
                name_bytes = target_name.encode("utf-16-le")
                class RenameInformation(ctypes.Structure):
                    _fields_ = [("replace", wintypes.BOOL), ("root", wintypes.HANDLE),
                                ("length", wintypes.DWORD), ("name", wintypes.WCHAR * (len(name_bytes) // 2 + 1))]
                information = RenameInformation(False, None, len(name_bytes), target_name)
                if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(handle.fileno()), 3,
                                                         ctypes.byref(information), RenameInformation.name.offset + len(name_bytes)):
                    raise DataError("内核拒绝移动已验证句柄，错误=" + str(ctypes.get_last_error()) + "；保留原件及操作日志")
                return
            disposition = wintypes.BOOL(True)
            if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(handle.fileno()), 4,
                                                     ctypes.byref(disposition), ctypes.sizeof(disposition)):
                raise DataError("内核拒绝删除已验证文件句柄，保留日志和现场")
    else:
        import fcntl
        directory_handles = ExitStack()
        handle = os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def remove():
            if (path.stat().st_dev, path.stat().st_ino) != (os.fstat(handle.fileno()).st_dev, os.fstat(handle.fileno()).st_ino):
                raise DataError("删除前路径身份变化")
            if destination is not None:
                if os.path.lexists(destination):
                    raise DataError("隔离/恢复目标已出现，拒绝覆盖")
                os.link(path, destination, follow_symlinks=False)
                path.unlink()
            else:
                path.unlink()
    with directory_handles, handle:
        opened = os.fstat(handle.fileno())
        identity = lambda info: [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
        checksum = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
        if (not stat.S_ISREG(opened.st_mode) or identity(opened) != expected["identity"] or
                identity(os.fstat(handle.fileno())) != expected["identity"] or
                identity(checked_path(path).stat()) != expected["identity"] or checksum.hexdigest() != expected["sha256"]):
            raise DataError("删除句柄当前身份或原始字节摘要不符")
        yield remove


def purge_item(root, db, identity, own_job=None):
    row = artifact_row(db, identity)
    custody = db.execute("SELECT * FROM custody WHERE artifact_id=? AND state='quarantined'", (identity,)).fetchone() if has_table(db, "custody") else None
    if custody is None:
        raise DataError("永久删除仅接受明确隔离的对象副本")
    protected = protection(root, db, identity, own_job=own_job)
    reasons = protected["reasons"]
    if reasons or protected["cache_references"]:
        raise DataError("保护引用、锁、租约或未失效加速缓存阻止永久删除")
    path = checked_path(owned_path(root, custody["path"]))
    image = file_manifest(path, allow_sqlite=row["role"] == "sqlite-backup")
    if image["sha256"] != row["sha256"] or json.dumps(image["identity"]) != custody["identity"]:
        raise DataError("隔离副本当前身份不符")
    item = dict(id=identity, path=custody["path"], quarantine_id=custody["operation_id"], role=row["role"], references=protected["references"], **image)
    item["confirmation_hash"] = digest(item)
    return item


def purge_renewal_state(root, db, identity):
    canonical_operation_id(identity)
    job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (identity,)).fetchone() if has_table(db, "safety_jobs") else None
    if job is None or job["kind"] != "purge" or job["phase"] not in ("reserved", "writing", "published"):
        raise DataError("只能为已登记、未完成的具体删除操作重新取得批准")
    previous = json.loads(job["plan"])
    progress = json.loads(job["progress"])
    items, completed = [], []
    for old in previous["items"]:
        path = owned_path(root, old["path"])
        state = progress.get(old["id"])
        if state in ("purged", "deleting") and not os.path.lexists(path):
            custody = db.execute("SELECT * FROM custody WHERE artifact_id=?", (old["id"],)).fetchone()
            row = artifact_row(db, old["id"])
            if (custody is None or custody["operation_id"] != old["quarantine_id"] or custody["path"] != old["path"] or
                    custody["identity"] != json.dumps(old["identity"]) or custody["state"] not in ("quarantined", "purged") or
                    (row["sha256"], row["size"], row["role"], row["identity"]) !=
                    (old["sha256"], old["size"], old["role"], json.dumps(old["identity"])) or
                    (state == "purged" and custody["state"] != "purged")):
                raise DataError("重新批准前已删墓碑/中断证据与原清单不符")
            items.append(old)
            completed.append(old["id"])
        else:
            if state == "purged":
                raise DataError("原已删路径重新出现，不接管或删除新文件")
            current = purge_item(root, db, old["id"], identity)
            if any(current[key] != old[key] for key in ("id", "path", "quarantine_id", "sha256", "size", "identity", "role")):
                raise DataError("重新批准不能更换原隔离对象身份")
            items.append(current)
    binding = dict(prior_plan_hash=digest(previous), phase=job["phase"], progress_hash=digest(progress))
    return items, completed, binding


def purge_current_confirmation(item, plan):
    if "renewal" not in plan:
        return item
    current = {key: value for key, value in item.items() if key != "confirmation_hash"}
    confirmation = digest(dict(item=current, renewal=plan["renewal"], created=plan["created"], expires=plan["expires"],
                               completed=item["id"] in plan["completed_ids"]))
    return dict(current, confirmation_hash=confirmation)


def purge(root, policy, args):
    root_id = root_marker(root, policy)["root_id"]
    if not args.plan:
        if args.approve_hash or args.confirm_item or (args.renew_operation and args.artifact_id) or (not args.renew_operation and
                (not args.artifact_id or len(set(args.artifact_id)) != len(args.artifact_id) or len(args.artifact_id) > 1000)):
            raise DataError("删除先预览具体登记ID，再保存清单并逐项确认")
        if args.valid_seconds is None or not 1 <= args.valid_seconds <= 86400:
            raise DataError("删除清单有效时长必须明确给定1至86400秒，未设生产默认值")
        with closing(open_index(root)) as db:
            if args.renew_operation:
                items, completed, binding = purge_renewal_state(root, db, args.renew_operation)
            else:
                items = [purge_item(root, db, identity) for identity in sorted(args.artifact_id)]
        now = time.time()
        plan = dict(action="purge", root_id=root_id, policy_hash=digest(policy), operation_id=args.renew_operation or str(uuid.uuid4()),
                    created=now, expires=now + args.valid_seconds, items=items, space_release_after_delete_only=True)
        if args.renew_operation:
            plan.update(renewal=binding, completed_ids=completed)
            plan["items"] = [purge_current_confirmation(item, plan) for item in items]
        return dict(plan, plan_hash=digest(plan), applied=False)
    if args.artifact_id or args.valid_seconds is not None or args.renew_operation:
        raise DataError("执行删除必须仅使用保存的具体清单，不能同时换选对象")
    saved_path = checked_path(args.plan)
    if saved_path.stat().st_size > QUERY_BYTES:
        raise DataError("删除授权清单超过1MiB")
    plan = json.loads(bounded_text(saved_path))
    if not isinstance(plan, dict):
        raise DataError("删除授权清单必须是完整JSON对象")
    approval = plan.pop("plan_hash", None)
    plan.pop("applied", None)
    if approval is None or approval != digest(plan) or args.approve_hash != approval:
        raise DataError("删除清单完整摘要须明确批准")
    if plan.get("action") != "purge" or plan.get("root_id") != root_id or plan.get("policy_hash") != digest(policy):
        raise DataError("删除清单根身份、动作或配置不符")
    canonical_operation_id(plan.get("operation_id"))
    if (type(plan.get("created")) not in (float, int) or type(plan.get("expires")) not in (float, int) or
            not math.isfinite(plan["created"]) or not math.isfinite(plan["expires"]) or
            not plan["created"] <= time.time() < plan["expires"] or not 0 < plan["expires"] - plan["created"] <= 86400):
        raise DataError("删除授权已过期或时钟/有效时长无效")
    items = plan.get("items")
    required = {"id", "path", "quarantine_id", "role", "references", "sha256", "size", "identity", "confirmation_hash"}
    if (not isinstance(items, list) or not 1 <= len(items) <= 1000 or
            any(not isinstance(item, dict) or set(item) != required or not all(isinstance(item[key], str) for key in ("id", "path", "quarantine_id", "role", "sha256", "confirmation_hash")) for item in items) or
            len({item["id"] for item in items}) != len(items)):
        raise DataError("删除对象清单无效")
    confirmations = {item["id"] + ":" + item["confirmation_hash"] for item in items}
    if len(args.confirm_item) != len(confirmations) or set(args.confirm_item) != confirmations:
        raise DataError("永久删除必须逐项确认完整的对象ID与当前确认摘要")
    with write_index(root, policy) as db, ExitStack() as handles:
        safety_tables(db)
        job = db.execute("SELECT * FROM safety_jobs WHERE id=?", (plan["operation_id"],)).fetchone()
        replacing_authority = job is not None and job["plan"] != compact_json(plan, QUERY_BYTES)
        if replacing_authority:
            current_items, current_completed, binding = purge_renewal_state(root, db, plan["operation_id"])
            if (plan.get("renewal") != binding or plan.get("completed_ids") != current_completed or
                    plan["items"] != [purge_current_confirmation(item, plan) for item in current_items]):
                raise DataError("重新批准清单未绑定当前原操作、墓碑、剩余身份及引用")
        elif job is None and "renewal" in plan:
            raise DataError("重新批准清单的原删除操作不存在")
        progress = json.loads(job["progress"]) if job else {}
        # 全部对象和排他句柄先验证，任一对象失败不会删除前面的对象。
        removers = {}
        for item in items:
            if progress.get(item["id"]) == "purged":
                if os.path.lexists(owned_path(root, item["path"])):
                    raise DataError("已删除路径重新出现，拒绝接管或删除")
                custody = db.execute("SELECT * FROM custody WHERE artifact_id=?", (item["id"],)).fetchone()
                if custody is None or custody["path"] != item["path"] or custody["state"] != "purged":
                    raise DataError("已删除墓碑与原隔离清单不符")
                continue
            path = owned_path(root, item["path"])
            if progress.get(item["id"]) == "deleting" and not os.path.lexists(path):
                custody = db.execute("SELECT * FROM custody WHERE artifact_id=?", (item["id"],)).fetchone()
                if custody is None or custody["path"] != item["path"] or custody["identity"] != json.dumps(item["identity"]):
                    raise DataError("删除中断日志与隔离身份不符")
                progress[item["id"]] = "purged"
                continue
            if purge_current_confirmation(purge_item(root, db, item["id"], plan["operation_id"]), plan) != item:
                raise DataError("预览后隔离清单或引用变化，旧确认无效")
            item_handles = handles.enter_context(ExitStack())
            removers[item["id"]] = (item_handles.enter_context(deletion_handle(path, item, boundary=root)), item_handles.close)
        if job and job["phase"] == "sealed":
            if any(progress.get(item["id"]) != "purged" for item in items):
                raise DataError("删除封口日志缺少逐项完成证据")
            return dict(operation_id=plan["operation_id"], applied=True, phase="sealed", purged=[item["id"] for item in items])
        reserve = safety_metadata_peak(db, plan)
        if not plan["created"] <= time.time() < plan["expires"]:
            raise DataError("逐项预检期间批准已过期，须重新取得当前清单批准")
        if shutil.disk_usage(root).free < policy["metadata_reserve_bytes"] + reserve:
            raise DataError("删除仍须保留足够的日志空间")
        if job is None:
            check_budget(root, db, policy, reserve)
            # sources仅用于活动操作保护；完整授权清单本身保持不可变。
            db.execute("INSERT INTO safety_jobs VALUES (?,?,?,?,?,?)", (plan["operation_id"], "purge", "reserved", compact_json(plan, QUERY_BYTES), reserve, "{}"))
            safety_phase(db, plan["operation_id"], "reserved", {})
        elif replacing_authority:
            growth = max(0, reserve - job["reserved_bytes"]) + len(compact_json(plan, QUERY_BYTES).encode("utf-8")) * 4 + 131072
            check_budget(root, db, policy, growth)
            db.execute("INSERT INTO operations VALUES (?,?,?,?)", (str(uuid.uuid4()), "purge-renew", "approved",
                       compact_json(dict(operation_id=plan["operation_id"], old_plan_hash=digest(json.loads(job["plan"])),
                                         new_plan_hash=digest(plan), old_expires=json.loads(job["plan"])["expires"], renewal=plan["renewal"]), QUERY_BYTES)))
            db.execute("UPDATE safety_jobs SET plan=?,reserved_bytes=? WHERE id=?", (compact_json(plan, QUERY_BYTES), reserve, plan["operation_id"]))
            for identity in plan["completed_ids"]:
                db.execute("UPDATE custody SET state='purged' WHERE artifact_id=?", (identity,))
            safety_phase(db, plan["operation_id"], job["phase"], progress)
        for item in items:
            if item["id"] in removers:
                if not plan["created"] <= time.time() < plan["expires"]:
                    raise DataError("当前删除批准已过期，剩余对象保留并须重新逐项批准")
                progress[item["id"]] = "deleting"
                safety_phase(db, plan["operation_id"], "writing", progress)
                if not plan["created"] <= time.time() < plan["expires"]:
                    raise DataError("删除日志提交期间批准过期，尚未删除的对象保留")
                remove, close_item = removers[item["id"]]
                remove()
                # Windows删除在句柄关闭时完成；逐项关闭后再持久化已删除状态。
                close_item()
                progress[item["id"]] = "purged"
            db.execute("UPDATE custody SET state='purged' WHERE artifact_id=?", (item["id"],))
            safety_phase(db, plan["operation_id"], "published", progress)
        safety_phase(db, plan["operation_id"], "sealed", progress)
        return dict(operation_id=plan["operation_id"], applied=True, phase="sealed", purged=[item["id"] for item in items])


def install_junction(repository, apply):
    if sys.platform != "win32":
        raise DataError("目录联接安装仅支持Windows")
    repository = checked_path(repository)
    if repository != SKILL_ROOT.parents[2] or SKILL_ROOT.relative_to(repository).as_posix() != ".agents/skills/sim2gse-data":
        raise DataError("只能为当前技能所在仓库安装联接")
    link = repository / ".claude" / "skills" / "sim2gse-data"
    for parent in (repository / ".claude", link.parent):
        if parent.exists():
            checked_path(parent)
    if os.path.lexists(link):
        if not link.is_junction() or link.resolve(strict=True) != SKILL_ROOT:
            raise DataError("既有入口不是指向本技能的目录联接，不覆盖")
        return dict(installed=True, changed=False, link=str(link), target=str(SKILL_ROOT))
    if apply:
        link.parent.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ, SIMDATA_LINK=str(link), SIMDATA_TARGET=str(SKILL_ROOT))
        result = subprocess.run([
            "pwsh", "-NoProfile", "-NonInteractive", "-Command",
            "New-Item -ItemType Junction -Path $env:SIMDATA_LINK -Target $env:SIMDATA_TARGET -ErrorAction Stop | Out-Null",
        ], env=environment, capture_output=True)
        if result.returncode or not link.is_junction() or link.resolve(strict=True) != SKILL_ROOT:
            raise DataError("目录联接安装失败；保留现场，请检查目录权限")
    return dict(installed=apply, changed=apply, link=str(link), target=str(SKILL_ROOT))


def maintenance_status(root, policy, args):
    if not 1 <= args.limit <= 1000 or not 0 <= args.offset <= 1000000:
        raise DataError("维护状态须使用有界分页")
    report = index_status(root, policy)
    with closing(open_index(root)) as db:
        rows = db.execute("SELECT id,role,size,sealed,last_used FROM artifacts ORDER BY id LIMIT ? OFFSET ?",
                          (args.limit + 1, args.offset)).fetchall()
        report.update(items=[dict(row) for row in rows[:args.limit]], has_more=len(rows) > args.limit,
                      next_offset=args.offset + args.limit if len(rows) > args.limit else None)
    return dict(report, automatic_cleanup=False, applied=False, last_used_updated=False,
                instruction="明确选择动作并预览具体计划；永久删除须保存清单和逐项批准，不按atime或年龄清理")


def schedule_preview(root, policy, args):
    if not args.config or not args.python:
        raise DataError("计划任务预览须明确技能外机器配置和已有Python绝对路径")
    executable = checked_path(args.python)
    if not Path(args.python).is_absolute() or not executable.is_file():
        raise DataError("Python须为已有可执行文件绝对路径")
    unresolved = [key for key in ("data_root", "root_id", "capacity_bytes", "retention_days", "maintenance_interval_hours",
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


def main():
    parser = argparse.ArgumentParser(description="Sim2GSE 共用数据管理入口")
    commands = parser.add_subparsers(dest="command", required=True)
    installer = commands.add_parser("install-junction", help="预览或显式安装仓库内共用目录联接")
    installer.add_argument("--repository", required=True)
    installer.add_argument("--apply", action="store_true")
    for name in ("inventory", "status", "check-config", "init-root", "register", "resolve", "begin", "finish", "protect", "pin", "reference", "lease", "cache-references", "extract", "query", "export", "compare", "snapshot", "archive", "restore", "backup-sqlite", "operation", "read-lease", "legacy-register", "dependency", "volume-register", "migration", "safety-operation", "quarantine", "recover-quarantine", "purge", "maintenance", "schedule-preview"):
        command = commands.add_parser(name, help="查看或按显式授权管理指定的数据根")
        command.add_argument("--root")
        command.add_argument("--config")
        command.add_argument("--limit", type=int, default=1000)
        if name == "schedule-preview":
            command.add_argument("--python")
            command.add_argument("--start-at")
        if name == "maintenance":
            command.add_argument("--task", choices=("status", "archive", "restore", "backup-sqlite", "migration", "quarantine", "recover-quarantine", "purge", "operation", "safety-operation"), default="status")
            command.add_argument("--artifact-id", action="append", default=[])
            command.add_argument("--confirm-item", action="append", default=[])
            command.add_argument("--valid-seconds", type=int)
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--action", choices=("status", "abandon-preview", "abandon"), default="status")
            command.add_argument("--volume-id", default="")
            for option in ("operation-id", "approve-hash", "plan", "renew-operation", "destination", "archive-id", "manifest", "database", "request-id"):
                command.add_argument("--" + option)
        if name == "inventory":
            command.add_argument("--incremental", action="store_true")
            command.add_argument("--cursor")
            command.add_argument("--complete", action="store_true")
        if name == "purge":
            command.add_argument("--artifact-id", action="append", default=[])
            command.add_argument("--valid-seconds", type=int)
            command.add_argument("--renew-operation")
            command.add_argument("--plan")
            command.add_argument("--approve-hash")
            command.add_argument("--confirm-item", action="append", default=[])
        if name in ("quarantine", "recover-quarantine"):
            command.add_argument("--artifact-id", action="append", default=[])
            command.add_argument("--operation-id")
            command.add_argument("--approve-hash")
        if name == "volume-register":
            command.add_argument("--path", required=True)
            command.add_argument("--approve-hash")
        if name == "migration":
            command.add_argument("--artifact-id", action="append", default=[])
            command.add_argument("--destination")
            command.add_argument("--volume-id", default="")
            command.add_argument("--operation-id")
            command.add_argument("--approve-hash")
        if name == "safety-operation":
            command.add_argument("--operation-id", required=True)
            command.add_argument("--action", choices=("status", "abandon-preview", "abandon"), default="status")
            command.add_argument("--approve-hash")
        if name == "legacy-register":
            command.add_argument("--directory", required=True)
            command.add_argument("--role", choices=("raw", "input", "native", "evidence", "model", "analysis", "cache", "unknown"), default="unknown")
            command.add_argument("--approve-hash")
        if name == "dependency":
            command.add_argument("--artifact-id", required=True)
            command.add_argument("--requires", required=True)
            command.add_argument("--kind", choices=("durable", "cache", "unknown"), default="durable")
        if name == "read-lease":
            command.add_argument("--action", choices=("acquire", "status", "heartbeat", "release", "recover-preview", "recover"), required=True)
            command.add_argument("--artifact-id")
            command.add_argument("--owner-pid", type=int)
            command.add_argument("--lease-id")
            command.add_argument("--token")
            command.add_argument("--approve-hash")
        if name in ("archive", "restore", "backup-sqlite"):
            command.add_argument("--operation-id")
            command.add_argument("--approve-hash")
        if name == "archive":
            command.add_argument("--artifact-id", action="append", default=[])
        if name == "restore":
            command.add_argument("--archive-id")
            command.add_argument("--manifest")
            command.add_argument("--destination")
        if name == "backup-sqlite":
            command.add_argument("--database")
            command.add_argument("--request-id")
        if name == "operation":
            command.add_argument("--operation-id", required=True)
            command.add_argument("--action", choices=("status", "abandon-preview", "abandon"), default="status")
            command.add_argument("--approve-hash")
        if name == "check-config":
            command.add_argument("--for-write", action="store_true", help="仅预检，不执行数据写入")
        if name == "init-root":
            command.add_argument("--approve-hash")
        if name == "register":
            command.add_argument("--path", required=True)
            command.add_argument("--role", choices=("raw", "input", "native", "evidence", "model", "analysis", "cache", "unknown"), default="unknown")
            command.add_argument("--schema-version", type=int, default=1)
            command.add_argument("--approve-hash")
        if name == "resolve":
            command.add_argument("--artifact-id", required=True)
            command.add_argument("--inspect", action="store_true", help="仅检查，不刷新业务last_used")
        if name == "begin":
            command.add_argument("--request-id", required=True)
            command.add_argument("--owner-pid", type=int, required=True)
            command.add_argument("--owner-start")
            command.add_argument("--reserve-bytes", type=int, required=True)
            command.add_argument("--token")
        if name == "finish":
            command.add_argument("--run-id", required=True)
            command.add_argument("--token", required=True)
            command.add_argument("--outcome", choices=("success", "failed", "incomplete", "censored"), required=True)
        if name in ("protect", "pin", "reference"):
            command.add_argument("--artifact-id", required=True)
        if name == "pin":
            command.add_argument("--label", required=True)
            command.add_argument("--action", choices=("add", "remove"), required=True)
        if name == "reference":
            command.add_argument("--owner", required=True)
            command.add_argument("--kind", choices=("durable", "cache", "unknown"), default="unknown")
            command.add_argument("--action", choices=("add", "invalidate-preview", "invalidate"), required=True)
            command.add_argument("--approve-hash")
        if name == "lease":
            command.add_argument("--run-id", required=True)
            command.add_argument("--action", choices=("status", "heartbeat", "release", "recover-preview", "recover"), required=True)
            command.add_argument("--token")
            command.add_argument("--approve-hash")
        if name == "cache-references":
            command.add_argument("--database", required=True)
            command.add_argument("--approve-hash")
        if name == "extract":
            command.add_argument("--artifact-id", required=True)
            command.add_argument("--context-artifact-id")
            command.add_argument("--player-name")
        if name in ("query", "export"):
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--snapshot-id")
        if name == "compare":
            command.add_argument("--left", required=True)
            command.add_argument("--right", required=True)
            command.add_argument("--axis", action="append", default=[])
            command.add_argument("--stratify", action="append", default=[])
        if name == "snapshot":
            command.add_argument("--fact-id", action="append", required=True)
            command.add_argument("--approve-hash")
    args = parser.parse_args()
    try:
        if args.command == "install-junction":
            print(json.dumps(install_junction(args.repository, args.apply), ensure_ascii=False))
            return 0
        policy = load_policy(args.config)
        root_value = args.root or policy["data_root"]
        if not isinstance(root_value, str) or not Path(root_value).is_absolute():
            raise DataError("须显式指定绝对数据根路径")
        root = checked_path(root_value, missing_leaf=args.command == "init-root")
        if policy["data_root"] is not None and checked_path(policy["data_root"], missing_leaf=args.command == "init-root") != root:
            raise DataError("命令与配置的数据根不一致")
        if args.command == "init-root":
            print(json.dumps(init_root(root, policy, args.approve_hash), ensure_ascii=False))
            return 0
        if not root.is_dir() or not 1 <= args.limit <= 100000:
            raise DataError("数据根须为目录；盘点上限须在1至100000之间")
        if args.command == "schedule-preview":
            print(compact_json(schedule_preview(root, policy, args), QUERY_BYTES))
            return 0
        if args.command == "maintenance":
            allowed = {
                "status": {"offset"},
                "archive": {"artifact_id", "operation_id", "approve_hash"},
                "restore": {"archive_id", "manifest", "destination", "operation_id", "approve_hash"},
                "backup-sqlite": {"database", "request_id", "operation_id", "approve_hash"},
                "migration": {"artifact_id", "destination", "volume_id", "operation_id", "approve_hash"},
                "quarantine": {"artifact_id", "operation_id", "approve_hash"},
                "recover-quarantine": {"artifact_id", "operation_id", "approve_hash"},
                "purge": {"artifact_id", "plan", "approve_hash", "confirm_item", "valid_seconds", "renew_operation"},
                "operation": {"operation_id", "action", "approve_hash"},
                "safety-operation": {"operation_id", "action", "approve_hash"},
            }[args.task]
            for key in ("artifact_id", "operation_id", "approve_hash", "plan", "confirm_item", "valid_seconds", "renew_operation", "destination", "archive_id", "manifest", "database", "request_id", "volume_id", "offset", "action"):
                if key not in allowed and getattr(args, key) not in (None, [], "", 0, "status"):
                    raise DataError("维护动作不接受参数: " + key)
            if args.task == "status":
                if args.approve_hash or args.plan or args.artifact_id or args.confirm_item:
                    raise DataError("状态预览不能携带操作授权")
                print(compact_json(maintenance_status(root, policy, args), QUERY_BYTES))
                return 0
            args.command = args.task
            if args.command in ("operation", "safety-operation") and not args.operation_id:
                raise DataError("操作维护须明确operation-id")
        if args.command in ("extract", "query", "export", "compare", "snapshot"):
            handler = {"extract": extract_facts, "query": query_facts, "export": query_facts,
                       "compare": compare_facts, "snapshot": snapshot_facts}[args.command]
            print(compact_json(handler(root, policy, args), QUERY_BYTES))
            return 0
        if args.command in ("archive", "restore", "backup-sqlite", "operation", "read-lease", "legacy-register", "dependency", "volume-register", "migration", "safety-operation", "quarantine", "recover-quarantine", "purge"):
            handler = {"read-lease": reader_lease, "legacy-register": legacy_register, "dependency": dependency_add,
                       "volume-register": register_volume, "migration": migration, "safety-operation": safety_job_status,
                       "quarantine": quarantine, "recover-quarantine": quarantine,
                       "purge": purge,
                       "operation": manage_operation}.get(args.command, lifecycle_execute)
            print(compact_json(handler(root, policy, args), QUERY_BYTES))
            return 0
        if args.command in ("register", "resolve", "begin", "finish", "protect", "pin", "reference", "lease", "cache-references"):
            handler = {"register": register_file, "resolve": resolve_artifact, "begin": begin_run, "finish": finish_run,
                       "protect": protect_artifact, "pin": pin_artifact, "reference": change_reference, "lease": manage_lease,
                       "cache-references": cache_references}[args.command]
            print(json.dumps(handler(root, policy, args), ensure_ascii=False))
            return 0
        if args.command == "check-config" and args.for_write:
            require_write_policy(policy)
            if policy["mode"] == "test":
                root_marker(root, policy)
        index_present = False
        if args.command != "inventory" and os.path.lexists(root / "index.sqlite3"):
            checked_path(root / "index.sqlite3")
            index_present = True
        if args.command == "inventory" and args.cursor and not args.incremental:
            raise DataError("游标须用于incremental续扫")
        if args.command == "inventory" and args.complete and args.incremental:
            raise DataError("complete完整核算不能携带增量观察游标")
        report = (inventory_page(root, args.limit, args.cursor) if args.incremental else inventory(root, None if args.complete else args.limit)) if args.command == "inventory" else {
            "root": str(root), "index_present": index_present,
            "disk_free_bytes": shutil.disk_usage(root).free,
        }
        report.update({key: value for key, value in policy.items() if key != "data_root"})
        if index_present:
            report.update(index_status(root, policy))
        report.update(unknown_data_protected=True, last_used_updated=False)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (DataError, OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error, tarfile.TarError, EOFError, zlib.error) as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
