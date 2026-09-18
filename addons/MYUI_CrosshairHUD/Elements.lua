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
    crosshair = { file = "crosshair",   w = 128, h = 128, ox = 0,   oy = 0 },
    health    = { file = "health_arc",  w = 128, h = 128, ox = -32, oy = 16 },
    power     = { file = "power_arc",   w = 128, h = 128, ox = 32,  oy = 16 },
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

--------------------------------------------------------------------------

-- 采样模式必须是 TRILINEAR（第 4 个参数）。
--
-- 魔兽的默认模式是 LINEAR —— **只做双线性、不采样 mipmap**。贴图被缩小显示时，
-- 它每个屏幕像素只读 4 个纹理像素，高频信息全丢，边缘就出锯齿。HUD 缩放调到 1.0
-- 以下时贴图是缩小的，正是这种情况；调到 2.0 时接近 1:1，反而看着更清楚。
--
-- TRILINEAR 会采样 mipmap，缩小多少就用对应层级的预过滤图。暴雪自家会被缩放的
-- 贴图（地图）也是这么传的。
local function NewTexture(sub, file)
    local texture = Elements.frame:CreateTexture(nil, "ARTWORK", nil, sub)
    texture:SetTexture(MEDIA .. file .. ".png", nil, nil, "TRILINEAR")
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
    mask:SetTexture(MEDIA .. "mask_half.png", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    mask:SetAllPoints(Elements.frame)
    return mask
end

-- 阴影图 + 底图 + 填充图 + 遮罩。
--
-- 填充图用遮罩切出已填充的角度区间；阴影在图的最下面一层，**不挂遮罩**。
local function BuildFillable(key, spec)
    local shadow = NewTexture(SUB_SHADOW, spec.file .. SHADOW_SUFFIX)
    local bg = NewTexture(SUB_BG, spec.file)
    local fill = NewTexture(SUB_FILL, spec.file)
    local mask = NewMask()
    fill:AddMaskTexture(mask)

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

    BuildFillable("health", PLACEMENT.health)
    BuildFillable("power", PLACEMENT.power)

    parts.runes = {}
    placements.runes = {}
    for i = 1, Logic.PIPS.count do
        local spec = PIP_PLACEMENT[i]
        local entry = { file = "resource_0" .. i, w = spec.w, h = spec.h,
                        ox = spec.ox, oy = spec.oy }
        BuildFillable("rune" .. i, entry)
        parts.runes[i] = parts["rune" .. i]
        placements.runes[i] = entry
    end

    -- 与其它元素同一个形状：部件表里按图层名取。准星没有 bg/fill（它是线不是块），
    -- 所以只有 shadow 与 art 两层——层名统一，别在别处另起一个叫法。
    parts.crosshair = {
        shadow = NewTexture(SUB_SHADOW, PLACEMENT.crosshair.file .. SHADOW_SUFFIX),
        art = NewTexture(SUB_CROSSHAIR, PLACEMENT.crosshair.file),
    }
    placements.crosshair = PLACEMENT.crosshair
    PlaceLayers(parts.crosshair, PLACEMENT.crosshair)

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

    PlaceLayers(parts.health, placements.health)
    PlaceLayers(parts.power, placements.power)
    for i = 1, Logic.PIPS.count do
        PlaceLayers(parts.runes[i], placements.runes[i])
    end
    PlaceLayers(parts.crosshair, placements.crosshair)
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
    part.shadow:SetShown(visible)

    -- 空转必须整格背景色：隐藏填充纹理，而不是把角度设成 0。
    -- 比例为 0 的情形不需要在这里拦：那时遮罩本来就什么都不露。
    --
    -- **"有没有角度"看 hasRotation 这个普通布尔，不许去比较 rotation 本身**：
    -- rotation 可能是秘密值，而秘密值不许参与比较——Core 的读数段里连"读到了吗"
    -- 都是用另一个布尔表示的，这里不能开这个口子。
    local showFill = visible and st.state ~= Logic.RUNE_EMPTY and st.hasRotation == true
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
    pcall(function()
        local sc = st.shadowColor
        part.shadow:SetVertexColor(sc[1], sc[2], sc[3], st.shadowAlpha or 1)
    end)

    if showFill then
        pcall(function()
            local fc = st.fillColor
            part.fill:SetVertexColor(fc[1], fc[2], fc[3], st.fillAlpha or 1)
        end)
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
        parts.crosshair.art:SetShown(ch.visible ~= false)
        parts.crosshair.shadow:SetShown(ch.visible ~= false)
        pcall(function()
            local fc = ch.fillColor
            parts.crosshair.art:SetVertexColor(fc[1], fc[2], fc[3], ch.fillAlpha or 1)
        end)
        pcall(function()
            local sc = ch.shadowColor
            parts.crosshair.shadow:SetVertexColor(sc[1], sc[2], sc[3], ch.shadowAlpha or 1)
        end)
    end
end
