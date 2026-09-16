-- 渲染模块。
--
-- 持有全部纹理对象与遮罩，**不读配置、不读游戏数据**。
-- 对外只接受一张「显示状态表」，由 Core 从「配置 + 游戏读数」算好后整表下发：
--
--   state.health / state.power = { visible, rotation, state, fillColor, fillAlpha,
--                                  bgColor, bgAlpha }
--   state.crosshair            = { visible, fillColor, fillAlpha }   （准星是线，没有背景色）
--   state.runes[1..6]          = { visible, rotation, state, fillColor, fillAlpha,
--                                  bgColor, bgAlpha }
--
-- 填充与背景的透明度是**两个**值：合成一个就只能整条一起淡化，分不开。
--
-- runes 的槽位由 Core 完成排序后填入——本模块只管"第 i 格画成什么样"。
--
-- 关键约定一：**这里收的是遮罩的旋转角，不是填充比例。**
-- 受限上下文里血量与符能是秘密值，比例进不了 Lua；Core 把「比例 → 角度」做成曲线
-- 交给引擎求值，本模块拿到的角度**可能是秘密值**——只许原样交给 SetRotation，
-- 绝不比较、绝不运算、绝不转成字符串。
--
-- 关键约定二：**空转态（state == "empty"）要求完全隐藏填充纹理，不是把角度设成 0。**
-- 调用方不得越过这张表去直接操作本模块内部的纹理。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

local Logic = NS.Logic
NS.Elements = NS.Elements or {}
local Elements = NS.Elements

local MEDIA = "Interface\\AddOns\\MYUI\\Media\\CrosshairHUD\\"

local CreateFrame = _G.CreateFrame
local UIParent = _G.UIParent

local SQUARE = 128          -- 容器边长（设计稿单位），圆心居中
local PIP_SIZE = 32

-- 容器是正方形的，所以「宽度 ÷ 设计边长」就是整体缩放——解锁模式的齿轮面板里
-- 改宽度／高度要走这条换算，Core 因此需要这个常量
Elements.DESIGN_SIZE = SQUARE

-- 纹理摆放（设计稿单位，偏移相对圆心、y 向下；与素材包 manifest 一致）
local PLACEMENT = {
    crosshair = { file = "crosshair",   w = 64, h = 64,  ox = 0,   oy = 0 },
    health    = { file = "health_arc",  w = 64, h = 128, ox = -32, oy = 16 },
    power     = { file = "power_arc",   w = 64, h = 128, ox = 32,  oy = 16 },
}

local PIP_OFFSETS = {
    { ox = -38, oy = -38 }, { ox = -24, oy = -48 }, { ox = -8, oy = -53 },
    { ox = 8,   oy = -53 }, { ox = 24,  oy = -48 }, { ox = 38, oy = -38 },
}

Elements.frame = nil
Elements.scale = 1

local parts = {}          -- key -> 该元素的可重定位部件
local placements = {}     -- key -> 摆放规格，供 SetScale 重新摆放

--------------------------------------------------------------------------

local function NewTexture(sub, file)
    local texture = Elements.frame:CreateTexture(nil, "ARTWORK", nil, sub)
    texture:SetTexture(MEDIA .. file .. ".png")
    return texture
end

-- y 取负：设计稿 y 向下，魔兽 y 向上
local function Place(texture, spec)
    local s = Elements.scale
    texture:SetSize(spec.w * s, spec.h * s)
    texture:SetPoint("CENTER", Elements.frame, "CENTER", spec.ox * s, -spec.oy * s)
end

local function NewMask()
    local mask = Elements.frame:CreateMaskTexture()
    mask:SetTexture(MEDIA .. "mask_half.png", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    mask:SetAllPoints(Elements.frame)
    return mask
end

-- 底图 + 填充图 + 遮罩。填充图用遮罩切出已填充的角度区间。
local function BuildFillable(key, spec)
    local bg = NewTexture(0, spec.file)
    local fill = NewTexture(1, spec.file)
    local mask = NewMask()
    fill:AddMaskTexture(mask)

    parts[key] = { bg = bg, fill = fill, mask = mask }
    placements[key] = spec
    Place(bg, spec)
    Place(fill, spec)
end

--------------------------------------------------------------------------

function Elements.Create()
    local frame = CreateFrame("Frame", nil, UIParent)
    frame:SetSize(SQUARE * Elements.scale, SQUARE * Elements.scale)
    frame:SetPoint("CENTER")
    frame:SetFrameStrata("MEDIUM")
    Elements.frame = frame

    BuildFillable("health", PLACEMENT.health)
    BuildFillable("power", PLACEMENT.power)

    parts.runes = {}
    placements.runes = {}
    for i = 1, Logic.PIPS.count do
        local entry = { file = "resource_0" .. i, w = PIP_SIZE, h = PIP_SIZE,
                        ox = PIP_OFFSETS[i].ox, oy = PIP_OFFSETS[i].oy }
        BuildFillable("rune" .. i, entry)
        parts.runes[i] = parts["rune" .. i]
        placements.runes[i] = entry
    end

    parts.crosshair = NewTexture(2, PLACEMENT.crosshair.file)
    placements.crosshair = PLACEMENT.crosshair
    Place(parts.crosshair, PLACEMENT.crosshair)

    return frame
end

function Elements.SetStrata(strata)
    if Elements.frame then
        Elements.frame:SetFrameStrata(strata)
    end
end

function Elements.SetScale(scale)
    Elements.scale = scale
    if not Elements.frame then return end
    Elements.frame:SetSize(SQUARE * scale, SQUARE * scale)

    Place(parts.health.bg, placements.health)
    Place(parts.health.fill, placements.health)
    Place(parts.power.bg, placements.power)
    Place(parts.power.fill, placements.power)
    for i = 1, Logic.PIPS.count do
        Place(parts.runes[i].bg, placements.runes[i])
        Place(parts.runes[i].fill, placements.runes[i])
    end
    Place(parts.crosshair, placements.crosshair)
end

function Elements.SetVisible(visible)
    if Elements.frame then
        Elements.frame:SetShown(visible ~= false)
    end
end

--------------------------------------------------------------------------

local function ApplyFillable(part, st)
    local visible = st.visible ~= false
    part.bg:SetShown(visible)

    -- 空转必须整格背景色：隐藏填充纹理，而不是把角度设成 0。
    -- 比例为 0 的情形不需要在这里拦：那时遮罩本来就什么都不露。
    local showFill = visible and st.state ~= Logic.RUNE_EMPTY and st.rotation ~= nil
    part.fill:SetShown(showFill)
    if not visible then
        return
    end

    local bg = st.bgColor
    part.bg:SetVertexColor(bg[1], bg[2], bg[3], st.bgAlpha or 1)

    if showFill then
        local fc = st.fillColor
        part.fill:SetVertexColor(fc[1], fc[2], fc[3], st.fillAlpha or 1)
        -- rotation 可能是秘密值：只能原样交给 setter
        part.mask:SetRotation(st.rotation)
    end
end

-- 状态表 → 屏幕。state 为 nil 时整块隐藏。
function Elements.Apply(state)
    if not Elements.frame then return end
    if not state then
        Elements.SetVisible(false)
        return
    end
    Elements.SetVisible(true)

    if state.health then
        ApplyFillable(parts.health, state.health)
    end
    if state.power then
        ApplyFillable(parts.power, state.power)
    end

    for i = 1, Logic.PIPS.count do
        local slot = state.runes and state.runes[i]
        if slot then
            ApplyFillable(parts.runes[i], slot)
        end
    end

    local ch = state.crosshair
    if ch then
        parts.crosshair:SetShown(ch.visible ~= false)
        local fc = ch.fillColor
        parts.crosshair:SetVertexColor(fc[1], fc[2], fc[3], ch.fillAlpha or 1)
    end
end
