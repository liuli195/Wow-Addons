"""Sim2GSE 数据生命周期的共用命令行入口；仅使用标准库。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]


class DataError(ValueError):
    pass


def checked_path(path):
    """先检查原路径各层，再解析，避免把联接越界隐藏在 resolve 中。"""
    if "\x00" in os.fspath(path):
        raise DataError("路径含NUL字符，不能作为文件系统路径")
    if ".." in os.fspath(path).replace("\\", "/").split("/"):
        raise DataError("路径含上级路径组件，不能在规范化时隐藏链接")
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        info = component.lstat()
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
    if policy["data_root"] is not None and (
            not isinstance(policy["data_root"], str) or not Path(policy["data_root"]).is_absolute()):
        raise DataError("data_root须为未设置或绝对目录路径")
    for key in ("capacity_bytes", "retention_days", "maintenance_interval_hours",
                "maintenance_reserve_bytes", "archive_part_bytes"):
        value = policy[key]
        if value is not None and (type(value) is not int or value <= 0):
            raise DataError(f"{key}须为未设置或正整数")
    return policy


def require_write_policy(policy):
    if not policy["production_enabled"]:
        raise DataError("生产管理未启用；只读操作仍可使用")
    required = ("capacity_bytes", "retention_days", "maintenance_interval_hours",
                "maintenance_reserve_bytes", "archive_part_bytes")
    if any(policy[key] is None for key in required):
        raise DataError("生产策略未完整配置；须先商量容量、保留、频率及维护空间")
    if policy["maintenance_reserve_bytes"] >= policy["capacity_bytes"]:
        raise DataError("维护预留须小于容量")


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
    for name in ("inventory", "status", "check-config"):
        command = commands.add_parser(name, help="只读查看显式指定的数据根")
        command.add_argument("--root")
        command.add_argument("--config")
        command.add_argument("--limit", type=int, default=1000)
        if name == "check-config":
            command.add_argument("--for-write", action="store_true", help="仅预检，不执行数据写入")
    args = parser.parse_args()
    try:
        if args.command == "install-junction":
            print(json.dumps(install_junction(args.repository, args.apply), ensure_ascii=False))
            return 0
        policy = load_policy(args.config)
        root_value = args.root or policy["data_root"]
        if not isinstance(root_value, str) or not Path(root_value).is_absolute():
            raise DataError("须显式指定绝对数据根路径")
        root = checked_path(root_value)
        if policy["data_root"] is not None and checked_path(policy["data_root"]) != root:
            raise DataError("命令与配置的数据根不一致")
        if not root.is_dir() or not 1 <= args.limit <= 100000:
            raise DataError("数据根须为目录；盘点上限须在1至100000之间")
        if args.command == "check-config" and args.for_write:
            require_write_policy(policy)
        index_present = False
        if args.command != "inventory" and os.path.lexists(root / "index.sqlite3"):
            checked_path(root / "index.sqlite3")
            index_present = True
        report = inventory(root, args.limit) if args.command == "inventory" else {
            "root": str(root), "index_present": index_present,
            "disk_free_bytes": shutil.disk_usage(root).free,
        }
        report.update({key: value for key, value in policy.items() if key != "data_root"})
        report.update(unknown_data_protected=True, last_used_updated=False)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (DataError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
