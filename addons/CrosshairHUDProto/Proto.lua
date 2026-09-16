-- CrosshairHUD 弧线填充原型（一次性产物，不属于正式插件）
--
-- 目的：用真实客户端定三件事
--   1) 两种候选技术里，哪种能把「圆弧按比例填充」做出来
--        A = 旋转半平面遮罩（MaskTexture 绕圆心旋转，半平面边界即径向切线）
--        B = Cooldown 扫掠（弧纹理作为扫掠纹理，扇形天然形成径向切线）
--   2) 整个 HUD 默认多大（同屏 1.0 / 1.5 / 2.0 三档）
--   3) 符文格用固定槽位还是随就绪状态动态重排
--
-- 填充比例与角度的换算见本文件 MaskAngle / SwipeElapsed 两处注释，是后续正式实现的契约。

-- 全局别名：与仓库其他插件一致，便于静态检查
local CreateFrame = _G.CreateFrame
local GetTime = _G.GetTime
local UIParent = _G.UIParent
local SlashCmdList = assert(rawget(_G, "SlashCmdList"))
local print = _G.print

local MEDIA = "Interface\\AddOns\\CrosshairHUDProto\\Media\\"

----------------------------------------------------------------------
-- 设计稿常量（来自素材包 Source/*.svg 与 manifest.json）
-- 坐标系 256x256，圆心 (128,128)，半径 54，线宽 6，角度为「从正东顺时针、y 向下」
----------------------------------------------------------------------
local SQUARE_UNITS = 128          -- 方形画布边长（设计稿单位），圆心居中
local ARC_SPAN     = 102          -- 两条主弧各 102 度
local HEALTH_START = 99
local POWER_START  = 339
local PIP_START    = 219          -- 第一个符文格起始角
local PIP_STEP     = 18           -- 每格 12 度 + 间隔 6 度
local PIP_SPAN     = 12

local ARCS = {
    health = {
        file = "health_arc", start = HEALTH_START,
        w = 64, h = 128, ox = -32, oy = 16,
        fill = { 0.851, 0.506, 0.553 },   -- #D9818D
        bg   = { 0.208, 0.165, 0.188 },   -- #352A30
    },
    power = {
        file = "power_arc", start = POWER_START,
        w = 64, h = 128, ox = 32, oy = 16,
        fill = { 0.498, 0.686, 0.796 },   -- #7FAFCB
        bg   = { 0.161, 0.212, 0.251 },   -- #293640
    },
}

-- 6 个符文格的纹理各自是环上不同角度的弧段，位置固定、不可互换；
-- 「动态重排」改变的是每个槽位显示哪个符文的状态，不是换纹理。
local PIPS = {
    { file = "resource_01", ox = -38, oy = -38 },
    { file = "resource_02", ox = -24, oy = -48 },
    { file = "resource_03", ox = -8,  oy = -53 },
    { file = "resource_04", ox = 8,   oy = -53 },
    { file = "resource_05", ox = 24,  oy = -48 },
    { file = "resource_06", ox = 38,  oy = -38 },
}
local PIP_FILL = { 0.855, 0.839, 0.796 }   -- #DAD6CB
local PIP_BG   = { 0.384, 0.396, 0.408 }   -- #626568
local CROSSHAIR_COLOR = { 0.898, 0.914, 0.914 }   -- #E5E9E9

----------------------------------------------------------------------
-- 角度换算：填充比例 f（0..1） → 渲染参数
----------------------------------------------------------------------

-- 技术 A：遮罩旋转角（弧度，逆时针为正；魔兽的正角度为逆时针）
--
-- 推导：遮罩矩形以圆心为中心，图像左半不透明。旋转 θ 后，不透明半平面为
-- {点 p : p·(cosθ, sinθ) < 0}，换算成魔兽角度即 ψ ∈ (θ+90°, θ+270°)。
-- 设计稿的一条从 a 起、顺时针跨 span 度的弧，在魔兽角度里是 [-(a+span), -a]。
-- 取 θ = -a - span·f - 90，则窗口与弧的交集恰好是 [-(a+span·f), -a]，即前 f 段。
local function MaskAngle(masterStart, span, f)
    return math.rad(-(masterStart + span * f) - 90)
end

-- 技术 B：Cooldown 的「已流逝比例」e（0..1）
--
-- Cooldown 的扫掠从 12 点钟（魔兽 90°）开始顺时针推进，扫过的区域为
-- [90° - 360°e, 90°]。要求它的下边界落在填充切线处，即魔兽角 -(a + span·f)。
-- 于是 360e = (90 - wrap360(-(a + span·f))) mod 360。
local function SwipeElapsed(masterStart, span, f)
    local boundary = -(masterStart + span * f) % 360
    return ((90 - boundary) % 360) / 360
end

----------------------------------------------------------------------
-- 构件
----------------------------------------------------------------------

local updaters = {}

-- 通用：一块铺满 HUD 的遮罩（128 设计稿单位见方，居中于圆心）
local function NewMask(hud)
    local mask = hud:CreateMaskTexture()
    mask:SetTexture(MEDIA .. "mask_half.png", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    mask:SetAllPoints(hud)
    return mask
end

-- 底图：整段弧，染背景色（设计图上的深灰段）
local function NewArcBackground(hud, S, arc, square)
    local bg = hud:CreateTexture(nil, "ARTWORK", nil, 0)
    if square then
        bg:SetTexture(MEDIA .. "square_" .. arc.file .. ".png")
        bg:SetSize(SQUARE_UNITS * S, SQUARE_UNITS * S)
        bg:SetPoint("CENTER", hud, "CENTER", 0, 0)
    else
        bg:SetTexture(MEDIA .. arc.file .. ".png")
        bg:SetSize(arc.w * S, arc.h * S)
        bg:SetPoint("CENTER", hud, "CENTER", arc.ox * S, -arc.oy * S)
    end
    bg:SetVertexColor(arc.bg[1], arc.bg[2], arc.bg[3], 1)
    return bg
end

-- 技术 A：整段弧染填充色，用旋转的半平面遮罩切出已填充部分
local function BuildArcA(hud, S, arc)
    NewArcBackground(hud, S, arc, false)

    local fill = hud:CreateTexture(nil, "ARTWORK", nil, 1)
    fill:SetTexture(MEDIA .. arc.file .. ".png")
    fill:SetSize(arc.w * S, arc.h * S)
    fill:SetPoint("CENTER", hud, "CENTER", arc.ox * S, -arc.oy * S)
    fill:SetVertexColor(arc.fill[1], arc.fill[2], arc.fill[3], 1)

    local mask = NewMask(hud)
    fill:AddMaskTexture(mask)
    return function(f) mask:SetRotation(MaskAngle(arc.start, ARC_SPAN, f)) end
end

-- 技术 B：底图同上；填充走 Cooldown 的扫掠扇形
local function BuildArcB(hud, S, arc)
    NewArcBackground(hud, S, arc, false)

    local cd = CreateFrame("Cooldown", nil, hud, "CooldownFrameTemplate")
    cd:SetSize(SQUARE_UNITS * S, SQUARE_UNITS * S)
    cd:SetPoint("CENTER", hud, "CENTER", 0, 0)
    -- 接口注解把可选的颜色参数标成必填，这里显式传色；SetSwipeColor 一并保留
    cd:SetSwipeTexture(MEDIA .. "square_" .. arc.file .. ".png",
        arc.fill[1], arc.fill[2], arc.fill[3], 1)
    cd:SetSwipeColor(arc.fill[1], arc.fill[2], arc.fill[3], 1)
    cd:SetReverse(false)
    cd:SetDrawSwipe(true)
    if cd.SetDrawEdge then cd:SetDrawEdge(false) end
    if cd.SetDrawBling then cd:SetDrawBling(false) end
    cd:SetFrameLevel(hud:GetFrameLevel() + 5)
    return function(f)
        cd:SetCooldown(GetTime() - SwipeElapsed(arc.start, ARC_SPAN, f), 1)
    end
end

-- 符文格：单格的部分填充（两种技术各一份）
local function BuildPipA(hud, S, index)
    local pip = PIPS[index]
    local bg = hud:CreateTexture(nil, "ARTWORK", nil, 0)
    bg:SetTexture(MEDIA .. pip.file .. ".png")
    bg:SetSize(32 * S, 32 * S)
    bg:SetPoint("CENTER", hud, "CENTER", pip.ox * S, -pip.oy * S)
    bg:SetVertexColor(PIP_BG[1], PIP_BG[2], PIP_BG[3], 1)

    local fill = hud:CreateTexture(nil, "ARTWORK", nil, 1)
    fill:SetTexture(MEDIA .. pip.file .. ".png")
    fill:SetSize(32 * S, 32 * S)
    fill:SetPoint("CENTER", hud, "CENTER", pip.ox * S, -pip.oy * S)
    fill:SetVertexColor(PIP_FILL[1], PIP_FILL[2], PIP_FILL[3], 1)

    local mask = NewMask(hud)
    fill:AddMaskTexture(mask)
    local start = PIP_START + (index - 1) * PIP_STEP
    return function(f) mask:SetRotation(MaskAngle(start, PIP_SPAN, f)) end
end

local function BuildPipB(hud, S, index)
    local pip = PIPS[index]
    local bg = hud:CreateTexture(nil, "ARTWORK", nil, 0)
    bg:SetTexture(MEDIA .. pip.file .. ".png")
    bg:SetSize(32 * S, 32 * S)
    bg:SetPoint("CENTER", hud, "CENTER", pip.ox * S, -pip.oy * S)
    bg:SetVertexColor(PIP_BG[1], PIP_BG[2], PIP_BG[3], 1)

    local cd = CreateFrame("Cooldown", nil, hud, "CooldownFrameTemplate")
    cd:SetSize(SQUARE_UNITS * S, SQUARE_UNITS * S)
    cd:SetPoint("CENTER", hud, "CENTER", 0, 0)
    cd:SetSwipeTexture(MEDIA .. "square_" .. pip.file .. ".png",
        PIP_FILL[1], PIP_FILL[2], PIP_FILL[3], 1)
    cd:SetSwipeColor(PIP_FILL[1], PIP_FILL[2], PIP_FILL[3], 1)
    cd:SetReverse(false)
    cd:SetDrawSwipe(true)
    if cd.SetDrawEdge then cd:SetDrawEdge(false) end
    if cd.SetDrawBling then cd:SetDrawBling(false) end
    cd:SetFrameLevel(hud:GetFrameLevel() + 5)

    local start = PIP_START + (index - 1) * PIP_STEP
    return function(f)
        cd:SetCooldown(GetTime() - SwipeElapsed(start, PIP_SPAN, f), 1)
    end
end

local function BuildCrosshair(hud, S)
    local t = hud:CreateTexture(nil, "ARTWORK", nil, 2)
    t:SetTexture(MEDIA .. "crosshair.png")
    t:SetSize(64 * S, 64 * S)
    t:SetPoint("CENTER", hud, "CENTER", 0, 0)
    t:SetVertexColor(CROSSHAIR_COLOR[1], CROSSHAIR_COLOR[2], CROSSHAIR_COLOR[3], 1)
end

-- 一套完整 HUD。每个 HUD 返回一个 function(f)，f 为血弧的填充比例。
-- 六个符文格各自用不同相位，模拟充能进度不一的真实状态。
local function BuildHUD(parent, technique, S)
    local hud = CreateFrame("Frame", nil, parent)
    hud:SetSize(SQUARE_UNITS * S, SQUARE_UNITS * S)
    hud:SetFrameLevel(parent:GetFrameLevel() + 2)

    local fns = {}
    local build = (technique == "A") and BuildArcA or BuildArcB
    local buildPip = (technique == "A") and BuildPipA or BuildPipB

    fns[#fns + 1] = build(hud, S, ARCS.health)
    fns[#fns + 1] = build(hud, S, ARCS.power)
    for i = 1, 6 do
        fns[#fns + 1] = buildPip(hud, S, i)
    end
    BuildCrosshair(hud, S)

    return hud, function(f)
        fns[1](f)
        fns[2](f)
        for i = 1, 6 do
            -- 每格相位不同：从右上角往前推，越靠前的格子充得越多
            local pf = 1.8 * f - (i - 1) * 0.16
            if pf < 0 then pf = 0 elseif pf > 1 then pf = 1 end
            fns[2 + i](pf)
        end
    end
end

----------------------------------------------------------------------
-- 界面
----------------------------------------------------------------------

local root = CreateFrame("Frame", "CrosshairHUDProtoFrame", UIParent)
root:SetSize(720, 880)
root:SetPoint("CENTER")
root:SetMovable(true)
root:EnableMouse(true)
root:RegisterForDrag("LeftButton")
root:SetScript("OnDragStart", root.StartMoving)
root:SetScript("OnDragStop", root.StopMoving)
root:SetFrameStrata("DIALOG")
root:SetClampedToScreen(true)

local bg = root:CreateTexture(nil, "BACKGROUND")
bg:SetAllPoints(root)
bg:SetColorTexture(0.05, 0.06, 0.08, 0.30)

-- 记录所有文字，便于「干净模式」整体隐藏（比遍历 regions 判断类型更直接）
local labels = {}

local function Label(parent, text, x, y, size, color)
    -- 用字体模板而不是 SetFont：模板走客户端本地字体，中文才不会变成方框
    local template = "GameFontNormalSmall"
    if size and size >= 14 then
        template = "GameFontNormalLarge"
    elseif size and size >= 12 then
        template = "GameFontNormal"
    end
    local fs = parent:CreateFontString(nil, "OVERLAY", template)
    fs:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    fs:SetText(text)
    if color then fs:SetTextColor(color[1], color[2], color[3]) end
    labels[#labels + 1] = fs
    return fs
end

local DIM = { 0.75, 0.78, 0.82 }
local ACCENT = { 0.55, 0.85, 1.0 }

Label(root, "CrosshairHUD 原型 —— 三件事待定", 16, -14, 15, ACCENT)
Label(root, "1) 哪种技术能填弧    2) 默认多大    3) 符文格是否重排", 16, -36, 12, DIM)
Label(root, "面板可拖动。命令：/chhproto 开关面板   /chhproto clean 去掉底板与文字", 16, -54, 11, DIM)

local ROW_SIZES = { 1.0, 1.5, 2.0 }
local ROW_W = {}
local cursor = 0
for i, S in ipairs(ROW_SIZES) do
    ROW_W[i] = SQUARE_UNITS * S + 16
    cursor = cursor + ROW_W[i] + (i > 1 and 20 or 0)
end

local function BuildRow(title, technique, topY)
    Label(root, title, 16, topY - 4, 13, ACCENT)
    local bandTop = topY - 22
    local bandCentre = bandTop - (SQUARE_UNITS * 2.0) / 2   -- 以最大档为基准居中

    local x = 16
    for i, S in ipairs(ROW_SIZES) do
        local hud, update = BuildHUD(root, technique, S)
        hud:SetPoint("CENTER", root, "TOPLEFT", x + ROW_W[i] / 2, bandCentre)
        updaters[#updaters + 1] = update
        Label(root, string.format("%.1f 倍", S), x, bandCentre - SQUARE_UNITS * S / 2 - 2, 12, DIM)
        x = x + ROW_W[i] + 20
    end
    return bandTop - SQUARE_UNITS * 2.0
end

local y = BuildRow("技术 A —— 旋转半平面遮罩", "A", -76)
y = BuildRow("技术 B —— Cooldown 扫掠", "B", y - 10)

----------------------------------------------------------------------
-- 符文格排列对照
-- 模拟：6 个符文被一次性花光，按乱序依次充能完毕。
--   固定槽位：第 i 个符文永远在第 i 格 —— 亮起来的格子会散落在环上
--   动态重排：就绪的符文挤到最前 —— 亮格聚成一簇，但会跳位
----------------------------------------------------------------------

local READY_ORDER = { 4, 2, 6, 1, 5, 3 }   -- 乱序充能，便于看出差异
local CYCLE = 7.0                          -- 一个循环 7 秒

y = y - 10
Label(root, "符文格排列（模拟：花光后按乱序充能）", 16, y - 4, 13, ACCENT)

local sortDemo = {}

local function BuildSortDemo(xOffset, mode, caption)
    local S = 1.2
    local holder = CreateFrame("Frame", nil, root)
    holder:SetSize(SQUARE_UNITS * S, SQUARE_UNITS * S)
    holder:SetPoint("TOPLEFT", root, "TOPLEFT", xOffset, y - 22)
    holder:SetFrameLevel(root:GetFrameLevel() + 3)

    local slots = {}
    for i = 1, 6 do
        local tex = holder:CreateTexture(nil, "ARTWORK")
        tex:SetTexture(MEDIA .. PIPS[i].file .. ".png")
        tex:SetSize(32 * S, 32 * S)
        tex:SetPoint("CENTER", holder, "CENTER", PIPS[i].ox * S, -PIPS[i].oy * S)
        slots[i] = tex
    end
    Label(root, caption, xOffset, y - 22 - SQUARE_UNITS * S - 2, 12, DIM)

    sortDemo[#sortDemo + 1] = function(frac)
        -- frac: 本次循环已过去的比例
        local runeState = {}     -- [runeIndex] = 0（空）..1（就绪）
        for k, runeIndex in ipairs(READY_ORDER) do
            local readyAt = k * 0.13
            local v = (frac - readyAt) / 0.08
            if v < 0 then v = 0 elseif v > 1 then v = 1 end
            runeState[runeIndex] = 1 - v     -- 1 = 刚花掉，0 = 已充好
        end

        local order = {}         -- slot -> runeIndex
        if mode == "fixed" then
            for i = 1, 6 do order[i] = i end
        else
            local ready, charging = {}, {}
            for i = 1, 6 do
                if runeState[i] <= 0 then ready[#ready + 1] = i else charging[#charging + 1] = i end
            end
            table.sort(charging, function(a, b) return runeState[a] < runeState[b] end)
            local n = 0
            for _, i in ipairs(ready) do n = n + 1; order[n] = i end
            for _, i in ipairs(charging) do n = n + 1; order[n] = i end
        end

        for slot = 1, 6 do
            local rune = order[slot]
            local remain = runeState[rune] or 0
            if remain <= 0 then
                slots[slot]:SetVertexColor(PIP_FILL[1], PIP_FILL[2], PIP_FILL[3], 1)
            else
                -- 充能中的格子用背景色，随进度变亮，便于区分「空」与「快好了」
                local k = 1 - remain
                slots[slot]:SetVertexColor(
                    PIP_BG[1] + (PIP_FILL[1] - PIP_BG[1]) * k,
                    PIP_BG[2] + (PIP_FILL[2] - PIP_BG[2]) * k,
                    PIP_BG[3] + (PIP_FILL[3] - PIP_BG[3]) * k, 1)
            end
        end
    end
end

BuildSortDemo(16, "fixed", "固定槽位（第 i 个符文恒在第 i 格）")
BuildSortDemo(16 + SQUARE_UNITS * 1.2 + 40, "dynamic", "动态重排（就绪的挤到最前）")

Label(root, "看这三点：弧线能否被干净地按比例切开；1.0/1.5/2.0 哪档顺眼；两种排列哪种更好读。",
    16, y - 22 - SQUARE_UNITS * 1.2 - 40, 11, DIM)

----------------------------------------------------------------------
-- 驱动
----------------------------------------------------------------------

local elapsed = 0
local sweepPeriod = 3.2
local holdPeriod = 0.6

root:SetScript("OnUpdate", function(_, dt)
    elapsed = elapsed + dt
    local period = sweepPeriod + holdPeriod
    local t = elapsed % period
    local f = t / sweepPeriod
    if f > 1 then f = 1 end

    for _, update in ipairs(updaters) do
        update(f)
    end
    local sortFrac = (elapsed % CYCLE) / CYCLE
    for _, update in ipairs(sortDemo) do
        update(sortFrac)
    end
end)

----------------------------------------------------------------------
-- 命令与诊断
----------------------------------------------------------------------

local clean = false
local function ApplyClean()
    bg:SetShown(not clean)
    for _, fs in ipairs(labels) do
        fs:SetShown(not clean)
    end
end

_G.SLASH_CROSSHAIRHUDPROTO1 = "/chhproto"
SlashCmdList["CROSSHAIRHUDPROTO"] = function(msg)
    msg = (msg or ""):lower():gsub("%s+", "")
    if msg == "clean" then
        clean = not clean
        ApplyClean()
        print("|cff9fd4ffCrosshairHUDProto|r 底板与文字已" .. (clean and "隐藏" or "显示"))
    else
        root:SetShown(not root:IsShown())
        print("|cff9fd4ffCrosshairHUDProto|r 面板已" .. (root:IsShown() and "显示" or "隐藏"))
    end
end

local diag = CreateFrame("Frame")
local ok, mask = pcall(diag.CreateMaskTexture, diag)
print("|cff9fd4ffCrosshairHUDProto|r 遮罩诊断：CreateMaskTexture "
    .. (ok and "可用" or ("失败（" .. tostring(mask) .. "）")))
if ok and mask then
    print("   MaskTexture.SetRotation = " .. (mask.SetRotation and "存在" or "不存在")
        .. "；SetTexCoord = " .. (mask.SetTexCoord and "存在" or "不存在"))
end
print("|cff9fd4ffCrosshairHUDProto|r 已加载。技术 A 在上一排，技术 B 在下一排；"
    .. "若某排整条弧不显示或形状错乱，那就是该技术不成立。")
