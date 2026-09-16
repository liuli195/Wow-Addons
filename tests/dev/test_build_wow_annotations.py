"""验证注解生成器的解析与产出规则。

用例对应实机数据里出现过的构造与已修缺陷，不依赖游戏运行时。
"""
import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "build_wow_annotations", ROOT / "scripts/dev/build_wow_annotations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse(source, module):
    return module.parse_documentation("local X = " + source)


def main():
    module = load()

    # 表字面量：具名键与数组部分分开存放。
    table = parse('{ A = 1, { Name = "x" } }', module)
    assert table["A"] == 1
    assert [entry["Name"] for entry in table.entries] == ["x"]

    # 数组部分非空的表必须为真值；守卫失守会让文档正文整段消失。
    assert parse('{ "正文" }', module)
    assert parse('{ "正文" }', module).entries == ["正文"]

    # 标量与引用。
    assert parse('{ A = true, B = false, C = nil, D = "s" }', module) == {
        "A": True, "B": False, "C": None, "D": "s"}
    assert parse('{ V = Enum.Foo.Bar }', module)["V"] == ("ref", "Enum.Foo.Bar")
    assert parse('{ V = Constants.A - Constants.B + 1 }', module)["V"][0] == "expr"

    # 数字：负数与十六进制都要能吃下。
    assert parse('{ A = -1, B = 0xFF, C = 1.5 }', module) == {"A": -1, "B": 255, "C": 1.5}

    # 字符串转义：`\n` 还原为换行；产出注解时必须写回转义形式，
    # 否则文档注释断行、产出行外文本，文件不再是合法 Lua。
    assert module.unquote('"a\\nb"') == "a\nb"
    doc = module.Table()
    doc.entries = ["含换行的说明\n第二行"]
    node = module.Table()
    node.update({"Name": "F", "Documentation": doc,
                 "Arguments": module.Table(), "Returns": module.Table()})
    block = module.Generator({}, ()).function_block(
        {"Name": "S", "Type": "System", "Namespace": "C_S"}, node)
    comment = block.splitlines()[0]
    assert comment == "---含换行的说明\\n第二行", comment
    assert "---[Documentation]" in block

    # 类型解析：基础类型映射、枚举加前缀、未知类型降级为 any。
    annotated = module.Table()
    annotated["Name"] = "SomeEnum"
    annotated["Type"] = "Enumeration"
    system = module.Table()
    system["Tables"] = module.Table()
    system["Tables"].entries = [annotated]
    typed = module.Generator({"s": system}, ("Handwritten",), ("Known",))
    assert typed.resolve_type("bool") == "boolean"
    assert typed.resolve_type("cstring") == "string"
    assert typed.resolve_type("luaIndex") == "number"
    assert typed.resolve_type("Known") == "Enum.Known"
    assert typed.resolve_type("SomeEnum") == "Enum.SomeEnum"
    assert typed.resolve_type("Handwritten") == "Handwritten"
    assert typed.resolve_type("Missing") == "any"
    # 联合类型：有一支解析不到就整体降级，避免产出 `A|any` 这种误导写法。
    assert typed.resolve_type("Handwritten|number") == "Handwritten|number"
    assert typed.resolve_type("Handwritten|Missing") == "any"

    # 内层类型与可空标记。
    assert typed.field_type({"Type": "number", "InnerType": "Unknown"}) == "any[]"
    line = typed.annotation("param", {"Name": "x", "Type": "number", "Nilable": True})
    assert line == "---@param x? number"
    line = typed.annotation("return", {"Name": "x", "Type": "number", "Default": 0})
    assert line.startswith("---@return number? x")
    line = typed.annotation("field", {"Name": "x", "Type": "number", "StrideIndex": True})
    assert line.startswith("---@field ... number")

    # 产出必须是合法 Lua。文档正文里的 `\n` 若原样铺开会让注释断行、
    # 产出行外文本，这条断言专门盯住那个缺陷。
    syntax = ROOT / "scripts/dev/check_syntax.lua"
    lua = ROOT / ".tools/lua-5.1.5/src/lua.exe"
    produced = sorted((ROOT / "annotations/wow-api/Blizzard_APIDocumentationGenerated").glob("*.lua"))
    produced += sorted((ROOT / "annotations/wow-api-scriptobject").glob("*.lua"))
    assert produced, "注解产出为空"
    broken = [path.name for path in produced
              if subprocess.run([str(lua), str(syntax), str(path)],
                                cwd=ROOT, capture_output=True).returncode]
    assert not broken, f"注解产出不是合法 Lua：{broken[:5]}"

    # 产出与磁盘一致（--check 是同一份比较逻辑）。
    result = subprocess.run([str(ROOT / ".venv/Scripts/python.exe"),
                             str(ROOT / "scripts/dev/build_wow_annotations.py"), "--check"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr

    # 覆盖率：清单里的每个文件都必须落在产出或跳过里，不允许静默丢弃。
    report = subprocess.run([str(ROOT / ".venv/Scripts/python.exe"),
                             str(ROOT / "scripts/dev/build_wow_annotations.py"), "--report"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert report.returncode == 0, report.stdout + report.stderr
    assert "合计 612" in report.stdout, report.stdout
    print("PASS: 解析、类型映射与产出规则符合预期")


def test_build_wow_annotations():
    main()


if __name__ == "__main__":
    main()
