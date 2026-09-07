"""仓库检查项；日常通过 build-and-verify 调用。"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "AddOns/EUI_FacetedPortrait"
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
LUALS = ROOT / ".tools/luals/bin/lua-language-server.exe"
LUACHECK = ROOT / ".tools/downloads/luacheck.exe"


def run(*command):
    return subprocess.run([str(arg) for arg in command], cwd=ROOT, check=True)


def check_toc(folder):
    tocs = list(folder.glob("*.toc"))
    if not tocs:
        raise ValueError(f"没有插件清单：{folder}")
    interface = str(json.loads((ROOT / "scripts/dev/versions.json").read_text())["client"]["interface"])
    for toc in tocs:
        lines = toc.read_text(encoding="utf-8-sig").splitlines()
        versions = [v.strip() for line in lines if line.startswith("## Interface:")
                    for v in line.split(":", 1)[1].split(",")]
        if interface not in versions:
            raise ValueError(f"{toc}: 未声明目标接口号 {interface}")
        entries = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
        if not entries:
            raise ValueError(f"{toc}: 加载清单为空")
        for entry in entries:
            path = (folder / entry.replace("\\", "/")).resolve()
            if not path.is_relative_to(folder.resolve()) or not path.is_file():
                raise ValueError(f"{toc}: 加载文件缺失或越界：{entry}")
            if path.suffix.lower() == ".lua":
                run(LUA, ROOT / "scripts/dev/check_syntax.lua", path)
    print("PASS: 插件清单、目标接口号和 Lua 5.1 语法")


def check_luals(folder):
    if not list(folder.rglob("*.lua")):
        raise ValueError(f"语言检查范围没有 Lua 文件：{folder}")
    logs = ROOT / ".local/luals"
    logs.mkdir(parents=True, exist_ok=True)
    report_dir = Path(tempfile.mkdtemp(prefix="run-", dir=logs))
    config = json.loads((ROOT / ".luarc.json").read_text(encoding="utf-8"))
    config["workspace.library"] = [str((ROOT / p).resolve()) for p in config["workspace.library"]]
    for library in config["workspace.library"]:
        if not Path(library).is_dir():
            raise ValueError(f"接口定义缺失：{library}")
    config_path = report_dir / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run([str(LUALS), "--check", str(folder.resolve()),
                             "--configpath", str(config_path), "--checklevel=Warning",
                             "--check_format=json", "--logpath", str(report_dir)], cwd=ROOT)
    report = report_dir / "check.json"
    data = json.loads(report.read_text(encoding="utf-8"))  # 缺报告或坏报告必须失败。
    if data == []:  # LuaLS 3.19.1 将空结果序列化为空数组。
        data = {}
    if not isinstance(data, dict):
        raise ValueError("语言诊断报告格式错误")
    problems = 0
    for uri, diagnostics in data.items():
        for diagnostic in diagnostics:
            if diagnostic["severity"] <= 2:
                problems += 1
                line = diagnostic["range"]["start"]["line"] + 1
                print(f"{unquote(urlparse(uri).path)}:{line}: {diagnostic['code']}: {diagnostic['message']}")
    print(f"诊断报告：{report.relative_to(ROOT)}")
    if result.returncode or problems:
        raise ValueError(f"语言检查失败：退出状态 {result.returncode}，问题数 {problems}")


def check_docs():
    files = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "DOC").glob("*.md"))]
    for path in files:
        content = path.read_text(encoding="utf-8")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", content):
            raise ValueError(f"{path}: 含异常控制字符")
        fence = None
        for line in content.splitlines():
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if marker:
                value = marker[1]
                if fence is None:
                    fence = value
                elif value[0] == fence[0] and len(value) >= len(fence):
                    fence = None
        if fence:
            raise ValueError(f"{path}: 代码围栏未闭合")
        for block in re.finditer(r"(?ms)^~~~json\s*\n(.*?)^~~~", content):
            json.loads(block[1])
    print(f"PASS: {len(files)} 份文档的编码、代码围栏和 JSON 示例")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=["luals", "luacheck", "toc", "docs"])
    parser.add_argument("--source", type=Path, default=ADDON)
    args = parser.parse_args()
    try:
        if args.check == "luals":
            check_luals(args.source)
        elif args.check == "luacheck":
            run(LUACHECK, args.source, "--config", ROOT / ".luacheckrc", "--no-color")
        elif args.check == "toc":
            check_toc(args.source)
        else:
            check_docs()
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"FAIL: {error}\n")
