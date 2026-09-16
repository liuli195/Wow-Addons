-- 配置模块。
--
-- 数据模型、默认值、读写，以及 EUI 配置页面的构建函数（交给 Core 注册）。
-- 它**不需要知道渲染侧的任何东西**——配置变更的「应用」在 Core。依赖方向是
-- Core → {Config, Elements}，Logic 是唯一叶子。
--
-- 默认值取设计稿采样色；**每个元素的背景色各自独立**，所以设计稿里三条资源
-- 各不相同的深色背景能原样还原。
--
-- 存储是自己持有的 SavedVariables（独立存储，不写进 EllesmereUIDB）。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

NS.Config = NS.Config or {}
local Config = NS.Config

local UnitClass = _G.UnitClass

local SAVED = "MYUI_CrosshairHUDDB"

-- 19 项配置的默认值。键名即 SavedVariables 里的键名。
Config.DEFAULTS = {
    enabled = true,                 -- 总开关
    scale = 1.0,                    -- 整体等比缩放 0.5–2.0
    position = nil,                 -- 由 EUI 的位置控件写入；nil = 默认锚点（屏幕居中）
    strata = "MEDIUM",              -- 框架层级

    -- 填充与背景各有各的透明度：合成一个只能整条一起淡化，分不开。
    -- 「填充色来源」放在颜色之外单独一项——它是"用哪个色"的选择，不是颜色本身。
    elements = {
        health = {
            enabled = true,
            fillMode = "custom",    -- "custom" | "class"（职业配色）
            fill = { 0.851, 0.506, 0.553 },   -- #D9818D
            fillAlpha = 1,
            bgMode = "custom",
            bg   = { 0.208, 0.165, 0.188 },   -- #352A30
            bgAlpha = 1,
        },
        power = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.498, 0.686, 0.796 },   -- #7FAFCB
            fillAlpha = 1,
            bgMode = "custom",
            bg   = { 0.161, 0.212, 0.251 },   -- #293640
            bgAlpha = 1,
        },
        runes = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.855, 0.839, 0.796 },   -- #DAD6CB
            fillAlpha = 1,
            bgMode = "custom",
            bg   = { 0.384, 0.396, 0.408 },   -- #626568
            bgAlpha = 1,
        },
        crosshair = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.898, 0.914, 0.914 },   -- #E5E9E9
            fillAlpha = 1,
            -- 准星是线不是块，**没有背景色**
        },
    },
}

-- 元素在页面上与状态表里的固定顺序
Config.ELEMENT_ORDER = { "health", "power", "runes", "crosshair" }

Config.ELEMENT_LABELS = {
    health = "血弧", power = "符能弧", runes = "符文格", crosshair = "准星",
}

-- 与填充色来源同理：values 是映射表 + 显式 order。传数组时 EUI 会用 pairs 自己
-- 拼顺序，每次建页的排列都可能不同。
local STRATA_VALUES = {
    LOW = "LOW", MEDIUM = "MEDIUM", HIGH = "HIGH", DIALOG = "DIALOG",
    _noLoc = true,
}
local STRATA_ORDER = { "LOW", "MEDIUM", "HIGH", "DIALOG" }

-- 整体缩放的取值范围。配置页的滑块与解锁模式齿轮面板里的宽度／高度共用这一份，
-- 两条入口改的是同一个值，不许各存一份。
Config.SCALE_MIN, Config.SCALE_MAX = 0.5, 2.0

local settings = nil

--------------------------------------------------------------------------
-- 读写
--------------------------------------------------------------------------

local function Copy(source)
    local out = {}
    for key, value in pairs(source) do
        out[key] = type(value) == "table" and Copy(value) or value
    end
    return out
end

-- 把存下来的值合并进默认值：缺失的键回落到默认值（独立存储后没有宿主帮我们合并）
local function Merge(dest, defaults)
    for key, value in pairs(defaults) do
        if type(value) == "table" then
            if type(dest[key]) ~= "table" then dest[key] = {} end
            Merge(dest[key], value)
        elseif dest[key] == nil then
            dest[key] = value
        end
    end
    return dest
end

-- 当前生效的配置。未初始化时回落到默认值。
function Config.Get()
    return settings or Config.DEFAULTS
end

function Config.Load()
    local stored = _G[SAVED]
    if type(stored) ~= "table" then
        _G[SAVED] = {}
        stored = _G[SAVED]
    end
    settings = Merge(stored, Copy(Config.DEFAULTS))
    -- 把合并结果写回，保证缺失键以后也在
    _G[SAVED] = settings
    return settings
end

--------------------------------------------------------------------------
-- 填充色的来源
--------------------------------------------------------------------------

-- 取出三个通道。**只搬位置，不读值**：受限上下文里这些通道本身可能就是秘密值，
-- 只许原样交给 SetVertexColor。
--
-- 校验**只到"容器是不是颜色对象"为止，绝不去判断通道**——初版对通道做了
-- `type(...) ~= "number"` 的检查，那正是把整条取值链判死的地方：判断在秘密值上
-- 未必成立，判错就等于三级全部作废、静默回落到自定义色。通道取不到时由渲染侧
-- 兜底（那边整次 SetVertexColor 是 pcalled 的，取不到就保留上一次的颜色）。
local function Channels(color)
    if type(color) ~= "table" then return nil end
    local ok, r, g, b = pcall(function() return color.r, color.g, color.b end)
    if not ok then return nil end
    return { r, g, b }
end

-- 职业色的取值链。**这里差点做错**：EUI 自己的颜色缓存以**类名令牌为键**，而
-- UnitClass 在受限上下文里会交回秘密令牌——秘密值不能当表键，查表会直接出错，
-- 于是静默回落到默认色，表现就是"选了职业配色但毫无变化"。
-- （EUI 源码对这种情况留了原话：退回 C_ClassColor.GetClassColor(secretToken)，
--   "right class, but Blizzard's default shade instead of the user's"。）
--
-- 所以顺序是：先用 EUI 的缓存（能反映用户在 EUI 里改过的职业色），它吃不了秘密
-- 令牌就退回 Blizzard 自己的接口——那个能吃秘密令牌，代价只是拿不到用户改过的色。
-- "取不到"是缺陷，"不是自定义的那个色"只是次要诉求。
local function ClassColor()
    -- 优先用 EUI 自己缓存的类名令牌（`_playerClass`）：它加载时就取好了，
    -- 不受之后上下文变化影响，EUI 自家的色块也是用它取职业色的。
    local EUI = rawget(_G, "EllesmereUI")
    local classFile = EUI and EUI._playerClass or nil
    if classFile == nil and UnitClass then
        local ok, _, file = pcall(UnitClass, "player")
        if ok then classFile = file end
    end
    if classFile == nil then return nil end

    if EUI and EUI.GetClassColor then
        local ok, color = pcall(EUI.GetClassColor, classFile)
        local channels = ok and Channels(color)
        if channels then return channels end
    end

    local api = _G.C_ClassColor
    if api and api.GetClassColor then
        local ok, color = pcall(api.GetClassColor, classFile)
        local channels = ok and Channels(color)
        if channels then return channels end
    end

    -- 老牌全局色表（现代客户端上可能已不存在）。用 rawget 取，与取 EllesmereUI 同一写法。
    local palette = rawget(_G, "RAID_CLASS_COLORS")
    if palette then
        local ok, entry = pcall(function() return palette[classFile] end)
        local channels = ok and Channels(entry)
        if channels then return channels end
    end

    return nil
end

-- 「职业配色」取不到时**回落到自定义色**，而不是画成黑色或什么都不画。
-- 填充与背景各自有来源（`fillMode` / `bgMode`），共用这一段判定。
function Config.ResolveColor(mode, customRGB)
    if mode == "class" then
        local color = ClassColor()
        if color then return color end
    end
    return customRGB
end

function Config.ResolveFill(elementConfig)
    return Config.ResolveColor(elementConfig.fillMode, elementConfig.fill)
end

function Config.ResolveBg(elementConfig)
    return Config.ResolveColor(elementConfig.bgMode, elementConfig.bg)
end

--------------------------------------------------------------------------
-- 页面
--------------------------------------------------------------------------

-- 供 EUI 的 disabled 回调用：总开关关掉时子开关必须置灰不可点
function Config.ElementEnabled(key)
    local cfg = Config.Get()
    return cfg.enabled ~= false and cfg.elements[key].enabled ~= false
end

function Config.Grayed(key)
    local cfg = Config.Get()
    if cfg.enabled == false then return true end
    return cfg.elements[key].enabled == false
end

-- EUI 的页面构建函数。四条契约：返回内容总高度、离屏安全、控件工厂判空、
-- 构建期不注册长生命周期监听。
function Config.BuildPage(_, parent, yOffset)
    local EUI = rawget(_G, "EllesmereUI")
    local W = EUI and EUI.Widgets
    if not W then
        return 60          -- 选项插件未加载或离屏预建：安全返回，绝不索引 nil
    end

    local cfg = Config.Get()
    local y = yOffset
    local Apply = NS.Core and NS.Core.ApplyConfig

    local function refresh()
        if Apply then Apply() end
    end

    -- 一行「标签 + 色块 + 透明度滑块」。
    --
    -- 两个色块就是**自定义颜色**与**职业颜色**：点哪个用哪个，未选中的那个压到 0.3
    -- 表示当前没在用它；而"已经在自定义上时再点一次才开取色器"是 EUI 全局的色块
    -- 约定（BuildTrioColorSwatch 的注释写死的），不是我们发明的交互。
    -- 三元组还会返回一个「默认色」色块——本插件没有"默认色"这个概念，建完就隐藏。
    local function ColorRow(text, elementKey, elementConfig, modeKey, colorKey, alphaKey)
        local row, height = W:DualRow(parent, y,
            { type = "slider", text = text, min = 0, max = 100, step = 1,
              getValue = function() return (elementConfig[alphaKey] or 1) * 100 end,
              setValue = function(value)
                  elementConfig[alphaKey] = value / 100
                  refresh()
              end },
            { type = "spacer" })
        y = y - height

        -- 预建阶段不创建任何内联控件
        if EUI._prebuilding then return end
        local rgn = row._leftRegion
        local ctrl = rgn and rgn._control
        if not (ctrl and EUI.BuildTrioColorSwatch) then return end

        local custom, default, class = EUI.BuildTrioColorSwatch(
            rgn, rgn:GetFrameLevel() + 5, {
                getMode = function() return elementConfig[modeKey] or "custom" end,
                setMode = function(mode) elementConfig[modeKey] = mode end,
                getCustomRGB = function()
                    local c = elementConfig[colorKey]
                    return c[1], c[2], c[3]
                end,
                setCustomRGB = function(r, g, b) elementConfig[colorKey] = { r, g, b } end,
                hasClassColor = true,
                onChange = refresh,
                disabled = function() return Config.Grayed(elementKey) end,
                overrideSize = 20,
            })
        if default then default:Hide() end
        if custom then custom:SetPoint("RIGHT", ctrl, "LEFT", -10, 0) end
        if class and custom then class:SetPoint("RIGHT", custom, "LEFT", -8, 0) end
    end

    local _, h = W:SectionHeader(parent, "常规", y)
    y = y - h

    _, h = W:Toggle(parent, "启用准星 HUD", y,
        function() return cfg.enabled ~= false end,
        function(value)
            cfg.enabled = value
            refresh()
            -- 总开关会改变四个子开关的可用状态，重走一遍刷新列表
            if EUI and EUI.RefreshPage then EUI:RefreshPage() end
        end)
    y = y - h

    _, h = W:DualRow(parent, y,
        { type = "slider", text = "HUD 缩放",
          min = Config.SCALE_MIN, max = Config.SCALE_MAX, step = 0.05,
          tooltip = "整体等比缩放。1.0 为设计稿原始大小。",
          getValue = function() return cfg.scale or 1.0 end,
          setValue = function(value) cfg.scale = value; refresh() end },
        { type = "dropdown", text = "图层", values = STRATA_VALUES, order = STRATA_ORDER,
          getValue = function() return cfg.strata or "MEDIUM" end,
          setValue = function(value) cfg.strata = value; refresh() end })
    y = y - h

    -- 位置**不在这里配**：解锁模式里点齿轮（元素选项）就能改 X/Y，那是 EUI 现成的
    -- 能力，而且与拖动框同处一个会话，比在配置页里另开一套更顺。这里自建只会重复。

    for _, key in ipairs(Config.ELEMENT_ORDER) do
        local element = cfg.elements[key]
        local label = Config.ELEMENT_LABELS[key]

        _, h = W:SectionHeader(parent, label, y)
        y = y - h

        _, h = W:Toggle(parent, "启用", y,
            function() return element.enabled ~= false end,
            function(value) element.enabled = value; refresh() end,
            nil,
            function() return Config.Grayed(key) end)
        y = y - h

        ColorRow("填充色", key, element, "fillMode", "fill", "fillAlpha")

        -- 准星是线不是块：**没有背景色**
        if key ~= "crosshair" then
            ColorRow("条背景", key, element, "bgMode", "bg", "bgAlpha")
        end
    end

    return math.abs(y)
end
