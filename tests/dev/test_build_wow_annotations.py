"""验证注解生成器的解析与产出规则。

用例对应实机数据里出现过的构造与已修缺陷，不依赖游戏运行时。
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.real


def load():
    spec = importlib.util.spec_from_file_location(
        "build_wow_annotations", ROOT / "scripts/dev/build_wow_annotations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load()

    # 产出必须是合法 Lua。文档正文里的 `\n` 若原样铺开会让注释断行、
    # 产出行外文本，这条断言专门盯住那个缺陷。
    syntax = ROOT / "scripts/dev/check_syntax.lua"
    lua = ROOT / ".tools/lua-5.1.5/src/lua.exe"
    produced = sorted((ROOT / "scripts/dev/annotations/api/Blizzard_APIDocumentationGenerated").glob("*.lua"))
    produced += sorted((ROOT / "scripts/dev/annotations/scriptobject").glob("*.lua"))
    assert produced, "注解产出为空"
    directory = produced[0].parent
    command = [str(lua), str(syntax),
               *(os.path.relpath(path, directory) for path in produced)]
    assert len(subprocess.list2cmdline(command)) < 32767, "Lua 语法检查超过 Windows 命令长度"
    result = subprocess.run(command, cwd=directory, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    # 第二个文件故意损坏，证明批量入口没有只检查第一个参数。
    with tempfile.TemporaryDirectory(prefix="wow-syntax-batch-") as temporary:
        folder = Path(temporary)
        (folder / "good.lua").write_text("local x = 1\n", encoding="utf-8")
        (folder / "bad.lua").write_text("local =\n", encoding="utf-8")
        failed = subprocess.run([str(lua), str(syntax), "good.lua", "bad.lua"],
                                cwd=folder, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        assert failed.returncode != 0 and "bad.lua" in failed.stderr, failed.stderr

    # 复用真实生成器，只解析一次；完整生成结果在内存中同时做覆盖与磁盘比较。
    upstream = ROOT / ".tools/wow-api/Annotations/Core"
    generator = module.Generator(module.load_systems(), module.handwritten_types(upstream),
                                 module.enum_names(upstream), module.widget_mapping(),
                                 module.collect_upstream_methods(upstream))
    outputs, skipped = generator.build()
    scripts, _ = generator.script_methods()
    assert set(module.toc_files()) == set(outputs) | set(skipped), "清单文件未产出也未跳过"
    assert not set(outputs) & set(skipped), "文件同时计入产出和跳过"
    for folder, expected in ((module.OUTPUT, outputs), (module.SCRIPT_OUTPUT, scripts)):
        assert {p.name for p in folder.glob("*.lua")} == set(expected), "注解产出文件清单不一致"
        for name, text in expected.items():
            assert (folder / name).read_text(encoding="utf-8") == text, f"注解产出与磁盘不一致：{name}"
    print("PASS: 真实生成、磁盘比对及批量Lua语法检查符合预期")


def test_build_wow_annotations():
    main()


if __name__ == "__main__":
    main()
