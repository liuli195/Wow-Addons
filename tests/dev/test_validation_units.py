"""开发验证的纯规则：只读仓库或用明确的内存IO边界，不启动工具或创建文件。"""
import importlib.util
import json
import re
from pathlib import Path
import struct
import subprocess
import sys
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/media"))


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse(source, module):
    return module.parse_documentation("local X = " + source)


def check_parser_rules(module):
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



def test_annotation_parser_and_type_rules():
    check_parser_rules(load("scripts/dev/build_wow_annotations.py"))


def test_setup_workflow_and_check_roles():
    setup = (ROOT / "scripts/dev/setup.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    config = json.loads((ROOT / ".build-and-verify/config.json").read_text(encoding="utf-8"))
    lightweight = re.search(r"\$lightweight = '([^']+)'", workflow).group(1)
    assert re.match(lightweight, 'README.md') and re.match(lightweight, 'docs/guide.md')
    for changed in ('projects/sim2gse/README.md', 'projects/gear-planner/README.md',
                    'tests/sim2gse/research/README.md'):
        assert not re.match(lightweight, changed), '需pytest/Node依赖的路径不得走空venv快路'
    assert "https://github.com/simulationcraft/simc.git" in setup
    assert "simc-source.zip" not in setup
    assert "projects/sim2gse/requirements.txt" in setup
    assert "mingw-w64-x86_64-make" not in workflow
    assert ".tools/sim2gse-upstream/simc" not in workflow
    assert ".tools/sim2gse/product" not in workflow
    assert "run: ./scripts/dev/setup.ps1 -Pr" in workflow
    assert "build-and-verify build --project . --pr" in workflow
    assert "build-and-verify verify --project . --pr --full" in workflow
    assert "build-and-verify verify --project . --pr --base $env:BASE_SHA" in workflow
    sim2gse = next(check for check in config["verify"]["checks"] if check["id"] == "verify.sim2gse-real")
    assert sim2gse["timeoutSeconds"] >= 600
    assert sim2gse["pr"] is False
    sim2gse_build = next(check for check in config["build"]["checks"] if check["id"] == "build.sim2gse-product")
    assert sim2gse_build["pr"] is False


def test_patch_bytes_are_crlf_independent():
    build = load("scripts/dev/sim2gse/build.py")
    prototype = load("scripts/dev/sim2gse/prototype-engine-build.py")
    with patch.object(Path, "read_bytes", return_value=b"one\ntwo\n"):
        lf = build.patch_digest(Path("memory.patch"))
        assert prototype.patch_bytes(Path("memory.patch")) == b"one\ntwo\n"
    with patch.object(Path, "read_bytes", return_value=b"one\r\ntwo\r\n"):
        assert build.patch_digest(Path("memory.patch")) == lf
        assert prototype.patch_bytes(Path("memory.patch")) == b"one\ntwo\n"


@pytest.mark.parametrize(("commit", "tree", "matches"), [
    ("a" * 40, "b" * 40, True),
    ("0" * 40, "b" * 40, False),
    ("a" * 40, "0" * 40, False),
])
def test_upstream_commit_and_tree_identity(commit, tree, matches):
    build = load("scripts/dev/sim2gse/build.py")
    lock = {"upstream_commit": "a" * 40, "upstream_tree": "b" * 40}
    with patch.object(build.subprocess, "run", side_effect=[
        subprocess.CompletedProcess([], 0, stdout=commit + "\n"),
        subprocess.CompletedProcess([], 0, stdout=tree + "\n"),
    ]):
        if matches:
            assert build.verify_upstream(Path("memory-source"), lock) == "a" * 40
        else:
            with pytest.raises(ValueError, match="固定上游提交身份不符"):
                build.verify_upstream(Path("memory-source"), lock)


def test_missing_toc_file_is_rejected_before_lua_starts():
    checks = load("scripts/dev/check.py")
    folder = Path("memory-addon").resolve()
    toc = folder / "Example.toc"
    contents = {
        ROOT / "scripts/dev/versions.json": json.dumps({"client": {"interface": 120100}}),
        toc: "## Interface: 120100\nMissing.lua\n",
    }
    with (
        patch.object(Path, "glob", return_value=[toc]),
        patch.object(Path, "read_text", autospec=True, side_effect=lambda path, **kwargs: contents[path]),
        patch.object(Path, "is_file", return_value=False),
        patch.object(checks, "run") as run,
    ):
        with pytest.raises(ValueError, match="加载文件缺失或越界：Missing.lua"):
            checks.check_toc(folder)
    run.assert_not_called()


def rectangle():
    image = Image.new("RGBA", (4, 2), (255, 255, 255, 0))
    image.putalpha(Image.fromarray(np.array([[20, 40, 60, 80], [100, 120, 140, 160]], dtype=np.uint8)))
    return image


def blp_bytes(image):
    from white_blp import write_white_blp
    with patch.object(Path, "write_bytes") as write:
        write_white_blp(image, Path("memory.blp"))
    return write.call_args.args[0]


def test_white_material_rectangular_levels_and_header():
    from white_blp import _levels, verify_white_blp
    image = rectangle()
    levels = list(_levels(image))
    assert [level.size for level in levels] == [(4, 2), (2, 1), (1, 1)]
    assert np.asarray(levels[1]).tolist() == [[70, 110]]
    assert np.asarray(levels[2]).tolist() == [[90]]
    data = blp_bytes(image)
    assert data[:12] == b"BLP2" + struct.pack("<I", 1) + bytes([1, 8, 8, 1])
    assert struct.unpack_from("<II", data, 12) == (4, 2)
    assert data[148:152] == bytes([255, 255, 255, 255])
    assert [struct.unpack_from("<I", data, 20 + 4*i)[0] for i in range(3)] == [1172, 1188, 1192]
    assert [struct.unpack_from("<I", data, 84 + 4*i)[0] for i in range(3)] == [16, 4, 2]
    assert data[1172:1188] == bytes(8) + bytes([20, 40, 60, 80, 100, 120, 140, 160])
    assert data[1188:] == bytes([0, 0, 70, 110, 0, 90])
    with patch.object(Path, "read_bytes", return_value=data):
        assert verify_white_blp(Path("memory.blp"), image) == 3


@pytest.mark.parametrize(("index", "value", "message"), [
    (10, 0, "格式"), (12, 8, "原始层尺寸"), (148, 0, "白色模板"),
    (20, 0, "尺寸或位置"), (84, 0, "尺寸或位置"), (1172, 1, "不是白色"),
    (1180, 0, "透明度"), (32, 1, "多余或缺失"), (96, 1, "多余或缺失"),
])
def test_white_material_rejects_corrupt_bytes(index, value, message):
    from white_blp import verify_white_blp
    image = rectangle()
    damaged = bytearray(blp_bytes(image))
    damaged[index] = value
    with patch.object(Path, "read_bytes", return_value=bytes(damaged)):
        with pytest.raises(ValueError, match=message):
            verify_white_blp(Path("memory.blp"), image)


@pytest.mark.parametrize(("change", "message"), [("header", "格式"), ("tail", "尺寸"), ("extra", "多余或缺失")])
def test_white_material_rejects_truncation_or_extra_payload(change, message):
    from white_blp import verify_white_blp
    image = rectangle()
    data = blp_bytes(image)
    damaged = data[:100] if change == "header" else data[:-1] if change == "tail" else data + b"x"
    with patch.object(Path, "read_bytes", return_value=damaged):
        with pytest.raises(ValueError, match=message):
            verify_white_blp(Path("memory.blp"), image)


@pytest.mark.parametrize(("size", "color", "message"), [((3, 2), "white", "2的幂"), ((4, 2), "red", "白色")])
def test_invalid_source_does_not_reach_the_writer(size, color, message):
    from white_blp import write_white_blp
    with patch.object(Path, "write_bytes") as write:
        with pytest.raises(ValueError, match=message):
            write_white_blp(Image.new("RGBA", size, color), Path("memory.blp"))
    write.assert_not_called()


def test_runtime_manifest_and_toc_whitelists():
    module = load("scripts/dev/package_crosshair_hud.py")
    manifest = {"assets": [{"file": "z.png"}, {"file": "a.png"}]}
    with patch.object(Path, "read_text", return_value=json.dumps(manifest)):
        assert module.expected_files(ROOT) == sorted([
            "MYUI/MYUI.toc", "MYUI/Series.lua",
            "MYUI_CrosshairHUD/Logic.lua", "MYUI_CrosshairHUD/NativeBlood.lua",
            "MYUI_CrosshairHUD/Elements.lua", "MYUI_CrosshairHUD/Config.lua",
            "MYUI_CrosshairHUD/Visibility.lua", "MYUI_CrosshairHUD/Core.lua",
            "MYUI_CrosshairHUD/Diagnostics.lua", "MYUI_CrosshairHUD/MYUI_CrosshairHUD.toc",
            "MYUI/Media/CrosshairHUD/a.blp", "MYUI/Media/CrosshairHUD/z.blp",
            "MYUI/Media/CrosshairHUD/mask_half.blp", "MYUI/Media/CrosshairHUD/death_strike_marker.blp",
            "MYUI/Media/CrosshairHUD/coagulated_blood_fill.blp",
        ])
    with patch.object(Path, "read_text", return_value="## Interface: 120100\n  # comment\n\n Logic.lua \nCore.lua\n"):
        assert module.toc_files(Path("memory.toc")) == ["Logic.lua", "Core.lua"]
    assert module.toc_files(ROOT / "addons/MYUI_CrosshairHUD/MYUI_CrosshairHUD.toc") == list(module.RUNTIME)
    assert module.toc_files(ROOT / "addons/MYUI/MYUI.toc") == ["Series.lua"]


def test_committed_crosshair_names_sizes_and_source_pixels():
    media = ROOT / "addons/MYUI/Media/CrosshairHUD"
    manifest = json.loads((ROOT / "assets/CrosshairHUDMedia/manifest.json").read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        assert (media / asset["file"]).read_bytes() == (ROOT / "assets/CrosshairHUDMedia/Textures" / asset["file"]).read_bytes()
    names = {p.stem for p in media.glob("*.blp")}
    assert len(names) == 15
    assert {name for name in names if name.startswith("crosshair")} == {
        "crosshair_arm", "crosshair_arm_shadow", "crosshair_point", "crosshair_point_shadow"}
    assert not names.intersection({"power_arc", "power_arc_shadow", "resource_04", "resource_05",
                                   "resource_06", "coagulated_blood_arc", "crosshair"})
    for name, size in {"crosshair_arm": (256, 64), "crosshair_arm_shadow": (512, 256),
                       "crosshair_point": (64, 64), "crosshair_point_shadow": (256, 256)}.items():
        with Image.open(media / f"{name}.png") as image:
            assert image.size == size
    with Image.open(ROOT / "assets/CrosshairHUDMedia/Textures/crosshair.png") as source:
        with Image.open(media / "crosshair_arm.png") as arm:
            assert np.array_equal(np.asarray(arm.crop((57, 21, 199, 43)).getchannel("A")),
                                  np.asarray(source.crop((565, 501, 707, 523)).getchannel("A")))
        with Image.open(media / "crosshair_point.png") as point:
            assert np.array_equal(np.asarray(point.crop((9, 9, 55, 55)).getchannel("A")),
                                  np.asarray(source.crop((489, 489, 535, 535)).getchannel("A")))


def test_generated_mask_has_exact_soft_transition():
    from build_crosshair_media import build_mask
    captured = []
    with patch.object(Image.Image, "save", lambda image, *args, **kwargs: captured.append(image)):
        build_mask(Path("memory"))
    assert len(captured) == 1
    mask = captured[0]
    assert mask.size == (1024, 1024)
    row = np.asarray(mask.getchannel("A"))[512]
    assert row[508:514].tolist() == [255, 191, 127, 63, 0, 0]
    assert np.count_nonzero((row > 0) & (row < 255)) == 3
