"""Sim2GSE 数据生命周期的共用命令行入口；仅使用标准库。"""
import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import secrets
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid


SKILL_ROOT = Path(__file__).resolve().parents[1]


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


def inventory(root, limit):
    files = logical_bytes = visited = 0
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                visited += 1
                if visited > limit:
                    return dict(files=files, logical_bytes=logical_bytes, truncated=True)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise DataError("数据根内含链接或重解析点")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    logical_bytes += info.st_size
    return dict(files=files, logical_bytes=logical_bytes, truncated=False)


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
    if relative in (".simdata-root.json", ".manager.lock") or relative.startswith("index.sqlite3") or source.name == ".runner.lock":
        raise DataError("管理索引、侧文件和锁文件不能登记为原始数据")
    return source


@contextmanager
def runner_locks(root, source):
    with ExitStack() as stack:
        for parent in (source.parent, *source.parent.parents):
            if not parent.is_relative_to(root):
                break
            lock = parent / ".runner.lock"
            if os.path.lexists(lock):
                stack.enter_context(byte_lock(lock))
        yield


def file_manifest(source):
    before = source.stat()
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    checksum = hashlib.sha256()
    with source.open("rb") as handle:
        if identity(os.fstat(handle.fileno())) != identity(before):
            raise DataError("文件在读取前已变化")
        header = handle.read(16)
        if header == b"SQLite format 3\x00":
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


def resolve_artifact(root, policy, args):
    root_marker(root, policy)
    db = open_index(root)
    try:
        row = dict(artifact_row(db, args.artifact_id))
    finally:
        db.close()
    source = managed_file(root, str(root / row["path"]))
    with runner_locks(root, source):
        manifest = file_manifest(source)
    if manifest["sha256"] != row["sha256"] or json.dumps(manifest["identity"]) != row["identity"]:
        raise DataError("对象当前身份或摘要与登记不符")
    if not args.inspect:
        with write_index(root, policy) as db:
            check_budget(root, db, policy)
            current = artifact_row(db, args.artifact_id)
            if current["identity"] != row["identity"] or current["path"] != row["path"]:
                raise DataError("对象在解析过程中已变化")
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


def run_payload_bytes(root, run):
    folder = checked_path(root / run["path"], missing_leaf=run["state"] == "allocating")
    if not folder.exists():
        return 0
    measured = inventory(folder, 1000)
    if measured["truncated"]:
        raise DataError("活动目录超过有界盘点范围，不能确定容量")
    internal = sum(checked_path(folder / name).stat().st_size for name in (".run-id.json", ".runner.lock")
                   if os.path.lexists(folder / name))
    return measured["logical_bytes"] - internal


def check_budget(root, db, policy, growth=0):
    # ponytail: 每次变更有界核对至多1000目录项；大根需后续明确盘点策略，不能假称已完整核算。
    measured = inventory(root, 1000)
    if measured["truncated"]:
        raise DataError("容量盘点未完整，拒绝新增长；不能忽略未知文件")
    remaining = sum(max(0, run["reserved_bytes"] - run_payload_bytes(root, run))
                    for run in db.execute("SELECT * FROM runs WHERE state IN ('allocating','running')"))
    reserve = policy["maintenance_reserve_bytes"] + policy["metadata_reserve_bytes"]
    if measured["logical_bytes"] + remaining + growth + reserve > policy["capacity_bytes"]:
        raise DataError("容量不足：原件、索引/WAL、活动预留和维护空间必须共存")
    if shutil.disk_usage(root).free < remaining + growth + reserve:
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
        check_budget(root, db, policy)
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


def protection(root, db, artifact_id):
    artifact = artifact_row(db, artifact_id)
    reasons = []
    if artifact["role"] in ("input", "evidence", "model", "analysis", "unknown"):
        reasons.append("protected-role:" + artifact["role"])
    reasons.extend("pin:" + row[0] for row in db.execute("SELECT label FROM pins WHERE artifact_id=? ORDER BY label", (artifact_id,)))
    references = [dict(row) for row in db.execute("SELECT * FROM refs WHERE target=? ORDER BY owner", (artifact_id,))]
    reasons.extend(row["kind"] + ":" + row["owner"] for row in references if row["kind"] != "cache")
    if db.execute("SELECT count(*) FROM unknown_refs").fetchone()[0]:
        reasons.append("unknown-legacy-references")
    path = managed_file(root, str(root / artifact["path"]))
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
        with runner_locks(root, checked_path(root / run["path"]) / ".lease-probe"):
            pass
        return dict(plan_hash=digest(dict(action="recover-lease", run=dict(run), proof=result["owner_state"], policy_hash=digest(policy))), **result)
    if args.action in ("status", "recover-preview"):
        db = open_index(root)
        try:
            return report(db) if args.action == "status" else recovery(db)
        finally:
            db.close()
    with write_index(root, policy) as db:
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
        with runner_locks(root, checked_path(root / run["path"]) / ".lease-probe"):
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
    if wal.exists() and wal.stat().st_size and not shm.exists():
        raise DataError("旧缓存WAL缺少共享索引；须先停写取得一致性备份，不能忽略WAL")
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


def main():
    parser = argparse.ArgumentParser(description="Sim2GSE 共用数据管理入口")
    commands = parser.add_subparsers(dest="command", required=True)
    installer = commands.add_parser("install-junction", help="预览或显式安装仓库内共用目录联接")
    installer.add_argument("--repository", required=True)
    installer.add_argument("--apply", action="store_true")
    for name in ("inventory", "status", "check-config", "init-root", "register", "resolve", "begin", "finish", "protect", "pin", "reference", "lease", "cache-references"):
        command = commands.add_parser(name, help="只读查看显式指定的数据根")
        command.add_argument("--root")
        command.add_argument("--config")
        command.add_argument("--limit", type=int, default=1000)
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
        report = inventory(root, args.limit) if args.command == "inventory" else {
            "root": str(root), "index_present": index_present,
            "disk_free_bytes": shutil.disk_usage(root).free,
        }
        report.update({key: value for key, value in policy.items() if key != "data_root"})
        if index_present:
            report.update(index_status(root, policy))
        report.update(unknown_data_protected=True, last_used_updated=False)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (DataError, OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error) as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
