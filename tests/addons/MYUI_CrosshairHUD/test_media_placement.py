"""素材清单与渲染摆放表的一致性测试。

**为什么单列一条**：纹理的显示尺寸与圆心偏移有**两个**出处——素材清单
（`assets/CrosshairHUDMedia/manifest.json`，构建脚本照它校验源图尺寸）和渲染模块里
手写的摆放表。两处一旦对不上，后果不是报错而是**静默变形**：贴图被按错误的尺寸拉伸，
内容整体偏大或偏小，位置也跟着挪，而游戏里看上去"只是有点怪"。

改素材尺寸是件会同时动到这两处的事，所以这条断言守在这里。

判据取自清单本身（Python 从 manifest.json 生成后注入），不是把摆放表的值抄一遍——
那样就成了自己跟自己对账。

**还有一条不是"摆放"的断言也在这里**：元素贴图必须请求 mipmap 采样。它和摆放一样，
是"渲染模块怎么创建纹理"这件事的一部分，而且同样**光看代码看不出来、只有实机能发现**
（实机报过：HUD 缩到 0.8 时边缘锯齿，放到 2.0 反而清楚）。理由写在那段断言上方。

只加载 `Logic.lua` 与 `Elements.lua` 就够：摆放表不碰配置，也不碰 EUI。
"""

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/MYUI_CrosshairHUD"
MANIFEST = ROOT / "assets/CrosshairHUDMedia/manifest.json"


HARNESS = r'''
local dir = assert(arg[1])

Enum = { PowerType = { RunicPower = 6 }, LuaCurveType = { Linear = 0 } }
UIParent = { GetEffectiveScale = function() return 1 end }

----------------------------------------------------------------------
-- 纹理 mock：记下每次 SetSize / SetPoint 收到的值
----------------------------------------------------------------------
local textures = {}
local frame
local function NewTexture(_, _, _, sub)
    local t = { sub = sub, path = nil, size = nil, point = nil, filter = nil }
    function t:SetTexture(path, _, _, filter) t.path = path; t.filter = filter end
    function t:SetSize(w, h) t.size = { w, h } end
    function t:SetPoint(a, b, c, x, y) t.point = { x, y } end
    function t:SetAllPoints() end
    function t:AddMaskTexture() end
    function t:SetShown() end
    function t:SetRotation() end
    function t:SetVertexColor() end
    textures[#textures + 1] = t
    return t
end

function CreateFrame()
    local f = {}
    function f:CreateTexture(a, b, c, sub) return NewTexture(a, b, c, sub) end
    function f:CreateMaskTexture() return NewTexture() end
    function f:SetSize(w, h) f.width, f.height = w, h end
    function f:SetPoint() end
    function f:SetFrameStrata() end
    function f:SetShown() end
    if not frame then frame = f end
    return f
end

assert(loadfile(dir .. "/Logic.lua"))()
local NS = assert(_G.MYUI_CHH)
assert(loadfile(dir .. "/Elements.lua"))()
local Elements = assert(NS.Elements)

Elements.scale = 1
Elements.Create()

----------------------------------------------------------------------
-- 逐条比对：清单说什么尺寸、什么偏移，摆放表就得报什么
----------------------------------------------------------------------
local MANIFEST = __MANIFEST__

for file, want in pairs(MANIFEST) do
    local w, h, ox, oy = want[1], want[2], want[3], want[4]
    local found = 0
    for _, t in ipairs(textures) do
        if t.path and t.path:sub(-#file) == file then
            found = found + 1
            assert(t.size, file .. "：这条纹理没有被 SetSize")
            assert(math.abs(t.size[1] - w) < 0.001 and math.abs(t.size[2] - h) < 0.001,
                string.format("%s：摆放表尺寸 %gx%g，清单是 %gx%g —— 贴图会被拉伸",
                    file, t.size[1], t.size[2], w, h))
            assert(t.point, file .. "：这条纹理没有被 SetPoint")
            assert(math.abs(t.point[1] - ox) < 0.001 and math.abs(t.point[2] + oy) < 0.001,
                string.format("%s：摆放表偏移 (%g,%g)，清单是 (%g,%g) —— 整体会错位",
                    file, t.point[1], t.point[2], ox, oy))
        end
    end
    assert(found > 0, file .. "：渲染模块根本没有为它创建纹理")
end

----------------------------------------------------------------------
-- 元素贴图必须请求 mipmap 采样（SetTexture 的第四个参数）
--
-- 魔兽的默认过滤模式是 LINEAR——**只做双线性、不采样 mipmap**。贴图被缩小显示时
-- 它每个屏幕像素只读 4 个纹理像素，于是高频信息全丢、边缘出现锯齿。
--
-- 实机上报过这个：HUD 缩放到 0.8 时锯齿明显，放到 2.0 反而清楚——正因为 2.0 接近
-- 1:1 不需要缩小。素材密度越高、缩小比例越大，这个问题越明显（本次把密度从 2 提到 8
-- 就是这么把它放大出来的）。修法是按暴雪自家地图代码的写法传 "TRILINEAR"。
--
-- 遮罩不在此列：它是一条线性渐变，没有高频可言，缩小时双线性就够。
----------------------------------------------------------------------
for _, t in ipairs(textures) do
    if t.path and t.path:sub(-4) == ".png" and t.path:sub(-13) ~= "mask_half.png" then
        assert(t.filter == "TRILINEAR",
            string.format("%s：采样模式是 %s，必须是 TRILINEAR —— " ..
                "默认的 LINEAR 不采样 mipmap，贴图缩小显示时会出现锯齿",
                t.path, tostring(t.filter)))
    end
end

io.write("PASS: media placement\n")
'''


def manifest_table():
    """把清单里的尺寸与偏移渲染成 Lua 表。尺寸取 displaySize（设计稿单位），
    偏移取 centerOffset（y 向下为正）；渲染侧 SetPoint 的 y 要取负，断言里再翻。"""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for asset in data["assets"]:
        w, h = asset["displaySize"]
        ox, oy = asset["centerOffset"]
        rows.append(f'    ["{asset["file"]}"] = {{ {w}, {h}, {ox}, {oy} }},')
    return "{\n" + "\n".join(rows) + "\n}"


def test_manifest_matches_renderer_placement():
    harness = HARNESS.replace("__MANIFEST__", manifest_table())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "placement_harness.lua"
        path.write_text(harness, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: media placement" in result.stdout
