-- 渲染模块。
--
-- 持有全部纹理对象与遮罩，**不读配置、不读游戏数据**。
-- 对外只接受一张「显示状态表」，由 Core 从「配置 + 游戏读数」算好后整表下发：
--
--   state.health / state.power = { visible, rotation, state, fillColor, fillAlpha,
--                                  bgColor, bgAlpha, shadowColor, shadowAlpha }
--   state.crosshair            = { visible, fillColor, fillAlpha,
--                                  shadowColor, shadowAlpha }   （准星是线，没有背景色）
--   state.runes[1..6]          = { visible, rotation, state, fillColor, fillAlpha,
--                                  bgColor, bgAlpha, shadowColor, shadowAlpha }
--
-- 填充、背景、阴影的透明度是**三个**值：合成一个就只能整条一起淡化，分不开。
--
-- 阴影是画在底图**之下**的一层。它**不挂遮罩**——包住整条轮廓，不随填充比例变化；
-- 也**不参与空转的隐藏**：空转时填充整格消失，但阴影要留着，那正是它标位置的时候。
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

-- 固定版暴雪文档的新增纹理接口；本机通用类型库尚未包含这些成员。
---@class CHHRadialTexture: Texture
---@field SetRadialProgressBarReverse fun(self: CHHRadialTexture, reverse: boolean)
---@field SetRadialProgressBarFeather fun(self: CHHRadialTexture, feather: number)
---@field GetRadialProgressBarPercent fun(self: CHHRadialTexture): number

local MEDIA = "Interface\\AddOns\\MYUI\\Media\\CrosshairHUD\\"

local CreateFrame = _G.CreateFrame
local UIParent = _G.UIParent

local SQUARE = 128          -- 容器边长（设计稿单位），圆心居中

-- 子层级：阴影必须**低于**底图，否则会盖住条本身（那看起来只是"颜色偏暗"，不报错）。
local SUB_SHADOW = -1
local SUB_BG = 0
local SUB_FILL = 1
local SUB_CROSSHAIR = 2

-- 阴影贴图与形状贴图同名，只多这个后缀（见素材清单的命名约定）
local SHADOW_SUFFIX = "_shadow"

-- 容器是正方形的，所以「宽度 ÷ 设计边长」就是整体缩放——解锁模式的齿轮面板里
-- 改宽度／高度要走这条换算，Core 因此需要这个常量
Elements.DESIGN_SIZE = SQUARE

-- 纹理摆放（设计稿单位，偏移相对圆心、y 向下；以素材清单 manifest.json 为准）
--
-- 尺寸取**清单里的显示尺寸**，不是图形本身的尺寸：贴图外圈留了给阴影的余量，
-- 而每个元素需要的留量不同，所以六个资源格的画布并不等大（32 / 33 / 34）。
-- 这几行与清单是一对，由 test_media_placement.py 钉住，改一边另一边必须跟上。
-- 摆放尺寸就是贴图的**画布**尺寸（设计稿单位），不是内容的尺寸。
--
-- 画布比内容大，是因为它被**对称补过边到 2 的幂**——魔兽只对 2 的幂贴图生成 mipmap，
-- 没有 mipmap 的话 HUD 缩到 1.0 以下就会出锯齿。对称补边的好处是圆心不动：
-- 内容位置与大小都和补边前一样，多出来的只是透明边。
--
-- 所以这里的数字跟 `assets/CrosshairHUDMedia/manifest.json` 的 displaySize 必须一致，
-- 由 test_media_placement.py 守着（它从清单生成期望值，不是把这张表抄一遍）。
local PLACEMENT = {
    health    = { file = "health_arc",  w = 128, h = 128, ox = -32, oy = 16 },
    power     = { file = "health_arc",  w = 128, h = 128, ox = 32,  oy = 16, mirror = true },
    coagulatedBlood = { file = "coagulated_blood_fill", w = 128, h = 128, ox = 0, oy = 0 },
    boilingPoint = { file = "coagulated_blood_fill", w = 128, h = 128, ox = 0, oy = 0 },
}

-- 资源格 1 与 6 的画布本来就是 2 的幂（32 单位 = 256 像素），不需要补边。
local PIP_PLACEMENT = {
    { w = 32, h = 32, ox = -38, oy = -38 }, { w = 64, h = 32, ox = -24, oy = -48 },
    { w = 64, h = 32, ox = -8,  oy = -53 }, { w = 64, h = 32, ox = 8,   oy = -53 },
    { w = 64, h = 32, ox = 24,  oy = -48 }, { w = 32, h = 32, ox = 38,  oy = -38 },
}

Elements.frame = nil
Elements.scale = 1

local parts = {}          -- key -> 该元素的可重定位部件
local placements = {}     -- key -> 摆放规格，供 SetScale 重新摆放
local markerState

local function ApplyMarker(st)
    markerState = st
    local line = parts.deathStrike
    if not line then return end
    local visible = st and st.visible == true and st.points ~= nil
    line:SetShown(visible and true or false)
    if not visible then return end
    local p, s = st.points, Elements.scale
    local dx, dy = p[3] - p[1], p[4] - p[2]
    -- 素材白色主体占画布长度的7/8、宽度的1/4；透明边距不改变实际端点和粗细。
    local length = math.sqrt(dx * dx + dy * dy)
    local cw, ch = length * s / 0.875, (st.thickness or 1.5) * s / 0.25
    local c, sn = dx / length, dy / length
    local w, h = math.abs(c) * cw + math.abs(sn) * ch,
        math.abs(sn) * cw + math.abs(c) * ch
    line:SetSize(w, h)
    line:SetPoint("CENTER", Elements.frame, "CENTER", (p[1] + p[3]) * s / 2,
        (p[2] + p[4]) * s / 2)
    -- 单个矩形内反向映射纹理，四角同时旋转，避免长条旋转后被自己的矩形裁掉。
    local function UV(x, y)
        return 0.5 + (c * x + sn * y) / cw, 0.5 - (-sn * x + c * y) / ch
    end
    local ulx, uly = UV(-w / 2, h / 2)
    local llx, lly = UV(-w / 2, -h / 2)
    local urx, ury = UV(w / 2, h / 2)
    local lrx, lry = UV(w / 2, -h / 2)
    line:SetTexCoord(ulx, uly, llx, lly, urx, ury, lrx, lry)
    local color = st.fillColor
    line:SetVertexColor(color[1], color[2], color[3], st.fillAlpha or 1)
end

--------------------------------------------------------------------------

-- 采样模式必须是 TRILINEAR（第 4 个参数）。
--
-- BLP成品显式包含完整缩小层；仅设置过滤方式不能保证PNG有可用缩小层。
-- 是否缩小取决于实际屏幕像素，HUD倍数为2也不代表贴图接近1:1。
local function SmoothTexture(texture, file, wrap)
    texture:SetTexture(MEDIA .. file .. ".blp", wrap, wrap, "TRILINEAR")
end

local function NewTexture(sub, file)
    local texture = Elements.frame:CreateTexture(nil, "ARTWORK", nil, sub)
    SmoothTexture(texture, file)
    return texture
end

-- y 取负：设计稿 y 向下，魔兽 y 向上
local function Place(texture, spec)
    local s = Elements.scale
    texture:SetSize(spec.w * s, spec.h * s)
    texture:SetPoint("CENTER", Elements.frame, "CENTER", spec.ox * s, -spec.oy * s)
end

-- 一个元素身上**可重定位的图层**。加一层只改这里，不用把 SetScale 逐层再抄一遍。
-- 缺哪层就跳过哪层：准星只有 shadow 与 art，资源格四层齐全。
local LAYERS = { "shadow", "bg", "fill", "art" }

local function PlaceLayers(part, spec)
    for _, layer in ipairs(LAYERS) do
        if part[layer] then Place(part[layer], spec) end
    end
end

local function NewMask()
    local mask = Elements.frame:CreateMaskTexture()
    mask:SetTexture(MEDIA .. "mask_half.blp", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE", "TRILINEAR")
    mask:SetAllPoints(Elements.frame)
    return mask
end

-- 阴影图 + 底图 + 填充图 + 遮罩。
--
-- 填充图用遮罩切出已填充的角度区间；阴影在图的最下面一层，**不挂遮罩**。
local function BuildFillable(key, spec)
    local shadow = NewTexture(spec.shadowSub or SUB_SHADOW, spec.file .. SHADOW_SUFFIX)
    local bg = NewTexture(SUB_BG, spec.file)
    local fill = NewTexture(SUB_FILL, spec.file)
    local mask = NewMask()
    fill:AddMaskTexture(mask)

    if spec.mirror then
        shadow:SetTexCoord(1, 0, 0, 1)
        bg:SetTexCoord(1, 0, 0, 1)
        fill:SetTexCoord(1, 0, 0, 1)
    end

    parts[key] = { shadow = shadow, bg = bg, fill = fill, mask = mask }
    placements[key] = spec
    PlaceLayers(parts[key], spec)
end

--------------------------------------------------------------------------

function Elements.Create()
    local frame = CreateFrame("Frame", nil, UIParent)
    frame:SetSize(SQUARE * Elements.scale, SQUARE * Elements.scale)
    frame:SetPoint("CENTER")
    frame:SetFrameStrata("MEDIUM")
    Elements.frame = frame
    if NS.NativeBlood then NS.NativeBlood.Create(frame) end

    BuildFillable("health", PLACEMENT.health)
    BuildFillable("power", PLACEMENT.power)
    local bloodSpec = PLACEMENT.coagulatedBlood
    local bar = CreateFrame("StatusBar", nil, frame)
    local fill = bar:CreateTexture(nil, "ARTWORK", nil, SUB_FILL)
    ---@cast fill CHHRadialTexture
    bar:SetStatusBarTexture(fill)
    SmoothTexture(fill, "coagulated_blood_fill")
    bar:SetRenderMode(_G.Enum.StatusBarRenderMode.Radial)
    fill:SetAllPoints(bar)
    fill:SetRadialProgressBarReverse(false)
    -- 参照现有遮罩1设计单位的过渡，先按整圆角度比例设置窄边候选。
    -- 暴雪文档未定义羽化宽度的精确换算，实际观感仍需客户端校准。
    fill:SetRadialProgressBarFeather(1 / (2 * math.pi * Logic.ARCS.coagulatedBlood.radius))
    bar:SetAllPoints(frame)
    bar:SetShown(false)
    parts.coagulatedBlood = {
        bg = NewTexture(SUB_BG, bloodSpec.file), fill = fill, bar = bar,
    }
    placements.coagulatedBlood = bloodSpec
    Place(parts.coagulatedBlood.bg, bloodSpec)
    local echo = { bg = NewTexture(SUB_BG, "coagulated_blood_fill"),
        fill = NewTexture(SUB_FILL, "coagulated_blood_fill"), mask = NewMask() }
    echo.bg:SetTexCoord(1, 0, 0, 1)
    echo.fill:SetTexCoord(1, 0, 0, 1)
    echo.fill:AddMaskTexture(echo.mask)
    parts.boilingPoint, placements.boilingPoint = echo, PLACEMENT.boilingPoint
    PlaceLayers(echo, PLACEMENT.boilingPoint)
    parts.deathStrike = NewTexture(SUB_CROSSHAIR, "death_strike_marker")
    SmoothTexture(parts.deathStrike, "death_strike_marker", "CLAMPTOBLACKADDITIVE")
    parts.deathStrike:SetShown(false)

    parts.runes = {}
    placements.runes = {}
    for i = 1, Logic.PIPS.count do
        local spec = PIP_PLACEMENT[i]
        local entry = { file = "resource_0" .. math.min(i, 7 - i), w = spec.w, h = spec.h,
                        ox = spec.ox, oy = spec.oy, mirror = i > 3 }
        BuildFillable("rune" .. i, entry)
        parts.runes[i] = parts["rune" .. i]
        placements.runes[i] = entry
    end

    -- 四臂/臂影同步固定旋转，中心点及其影各一次；不引入图集或旋转框架。
    parts.crosshair, placements.crosshair = {}, {}
    local uv = {
        { 0,0, 0,1, 1,0, 1,1 }, { 0,1, 1,1, 0,0, 1,0 },
        { 1,1, 1,0, 0,1, 0,0 }, { 1,0, 0,0, 1,1, 0,1 },
    }
    local centers = { {15.5,0}, {0,15.5}, {-15.5,0}, {0,-15.5} }
    for i = 1, 4 do
        local vertical = i % 2 == 0
        local part = { art = NewTexture(SUB_CROSSHAIR, "crosshair_arm"),
            shadow = NewTexture(SUB_SHADOW, "crosshair_arm_shadow") }
        local spec = { ox = centers[i][1], oy = centers[i][2],
            w = vertical and 8 or 32, h = vertical and 32 or 8 }
        local shadow = { ox = spec.ox, oy = spec.oy,
            w = vertical and 32 or 64, h = vertical and 64 or 32 }
        part.art:SetTexCoord(unpack(uv[i]))
        part.shadow:SetTexCoord(unpack(uv[i]))
        parts.crosshair[i], placements.crosshair[i] = part, { art = spec, shadow = shadow }
        Place(part.art, spec); Place(part.shadow, shadow)
    end
    local point = { art = NewTexture(SUB_CROSSHAIR, "crosshair_point"),
        shadow = NewTexture(SUB_SHADOW, "crosshair_point_shadow") }
    parts.crosshair[5] = point
    placements.crosshair[5] = { art = { w = 8, h = 8, ox = 0, oy = 0 },
        shadow = { w = 32, h = 32, ox = 0, oy = 0 } }
    Place(point.art, placements.crosshair[5].art)
    Place(point.shadow, placements.crosshair[5].shadow)

    return frame
end

-- 只供现有诊断命令读取；受限数值由调用方检测后决定是否输出。
function Elements.BloodDiagnostics()
    local part = parts.coagulatedBlood
    if not part or not part.bar then return end
    local low, high = part.bar:GetMinMaxValues()
    local fill = part.fill
    ---@cast fill CHHRadialTexture
    return { minimum = low, maximum = high, value = part.bar:GetValue(),
        percent = fill:GetRadialProgressBarPercent() }
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

    PlaceLayers(parts.health, placements.health)
    PlaceLayers(parts.power, placements.power)
    Place(parts.coagulatedBlood.bg, placements.coagulatedBlood)
    PlaceLayers(parts.boilingPoint, placements.boilingPoint)
    for i = 1, Logic.PIPS.count do
        PlaceLayers(parts.runes[i], placements.runes[i])
    end
    for i, part in ipairs(parts.crosshair) do
        Place(part.art, placements.crosshair[i].art)
        Place(part.shadow, placements.crosshair[i].shadow)
    end
    ApplyMarker(markerState)
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
    -- 阴影不跟填充走：空转时填充整格消失，阴影要留着——那正是它标位置的时候
    if part.shadow then part.shadow:SetShown(visible) end

    -- 空转必须整格背景色：隐藏填充纹理，而不是把角度设成 0。
    -- 比例为 0 的情形不需要在这里拦：那时遮罩本来就什么都不露。
    --
    -- **"有没有角度"看 hasRotation 这个普通布尔，不许去比较 rotation 本身**：
    -- rotation 可能是秘密值，而秘密值不许参与比较——Core 的读数段里连"读到了吗"
    -- 都是用另一个布尔表示的，这里不能开这个口子。
    local hasFill = part.bar and st.hasStacks == true or not part.bar and st.hasRotation == true
    local showFill = visible and st.state ~= Logic.RUNE_EMPTY and hasFill
    if part.bar then part.bar:SetShown(showFill) end
    part.fill:SetShown(showFill)
    if not visible then
        return
    end

    -- 颜色通道可能是秘密值，也可能取不到。整次设置是 pcalled 的：取不到就保留
    -- 上一次的颜色，绝不因为一个坏色值把每帧的渲染打断。
    pcall(function()
        local bg = st.bgColor
        part.bg:SetVertexColor(bg[1], bg[2], bg[3], st.bgAlpha or 1)
    end)

    -- 阴影的颜色与浓淡也是各自独立的两个值；同样 pcalled
    if part.shadow then
        pcall(function()
            local sc = st.shadowColor
            part.shadow:SetVertexColor(sc[1], sc[2], sc[3], st.shadowAlpha or 1)
        end)
    end

    if showFill then
        pcall(function()
            local fc = st.fillColor
            if part.bar then
                part.bar:SetStatusBarColor(fc[1], fc[2], fc[3], st.fillAlpha or 1)
            else
                part.fill:SetVertexColor(fc[1], fc[2], fc[3], st.fillAlpha or 1)
            end
        end)
        -- rotation 可能是秘密值：只能原样交给 setter
        if part.bar then
            local ok = pcall(function()
                -- 原生比例按整圆计算；将用户量程换算为短弧角度区间。
                -- 只计算普通配置常量，原始受限层数仍直接传给 SetValue。
                local arc = Logic.ARCS.coagulatedBlood
                local start = arc.start - Logic.FILL_MARGIN - 90
                local unit = st.maxStacks / (arc.span + Logic.FILL_MARGIN)
                part.bar:SetMinMaxValues(-start * unit, (360 - start) * unit)
                part.bar:SetValue(st.stacks)
            end)
            if not ok then part.bar:SetShown(false); part.fill:SetShown(false) end
        else
            part.mask:SetRotation(st.rotation)
        end
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
    local blood = state.coagulatedBlood or { visible = false }
    if NS.NativeBlood then
        NS.NativeBlood.Apply(blood, Elements.scale)
        ApplyFillable(parts.coagulatedBlood, blood.probe and blood or { visible = false })
    else
        ApplyFillable(parts.coagulatedBlood, blood)
    end
    ApplyFillable(parts.boilingPoint, state.boilingPoint or { visible = false })
    ApplyMarker(state.deathStrike)

    for i = 1, Logic.PIPS.count do
        local slot = state.runes and state.runes[i]
        if slot then
            ApplyFillable(parts.runes[i], slot)
        end
    end

    local ch = state.crosshair
    if ch then
        for _, part in ipairs(parts.crosshair) do
            part.art:SetShown(ch.visible ~= false)
            part.shadow:SetShown(ch.visible ~= false)
            pcall(function()
                local fc = ch.fillColor
                part.art:SetVertexColor(fc[1], fc[2], fc[3], ch.fillAlpha or 1)
            end)
            pcall(function()
                local sc = ch.shadowColor
                part.shadow:SetVertexColor(sc[1], sc[2], sc[3], ch.shadowAlpha or 1)
            end)
        end
    end
end
