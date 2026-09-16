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

    elements = {
        health = {
            enabled = true,
            fillMode = "custom",    -- "custom" | "class"（职业配色）
            fill = { 0.851, 0.506, 0.553 },   -- #D9818D
            bg   = { 0.208, 0.165, 0.188 },   -- #352A30
            alpha = 1,
        },
        power = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.498, 0.686, 0.796 },   -- #7FAFCB
            bg   = { 0.161, 0.212, 0.251 },   -- #293640
            alpha = 1,
        },
        runes = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.855, 0.839, 0.796 },   -- #DAD6CB
            bg   = { 0.384, 0.396, 0.408 },   -- #626568
            alpha = 1,
        },
        crosshair = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.898, 0.914, 0.914 },   -- #E5E9E9
            alpha = 1,
            -- 准星是线不是块，**没有背景色**
        },
    },
}

-- 元素在页面上与状态表里的固定顺序
Config.ELEMENT_ORDER = { "health", "power", "runes", "crosshair" }

Config.ELEMENT_LABELS = {
    health = "血弧", power = "符能弧", runes = "符文格", crosshair = "准星",
}

local STRATA_VALUES = { "LOW", "MEDIUM", "HIGH", "DIALOG" }

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

local function ClassColor()
    local EUI = rawget(_G, "EllesmereUI")
    if not (EUI and EUI.GetClassColor and UnitClass) then return nil end
    local ok, _, classFile = pcall(UnitClass, "player")
    if not ok or not classFile then return nil end
    local fetched, color = pcall(EUI.GetClassColor, classFile)
    if fetched and type(color) == "table" and color.r then
        return { color.r, color.g, color.b }
    end
    return nil
end

-- 「职业配色」取不到时**回落到自定义色**，而不是画成黑色或什么都不画
function Config.ResolveFill(elementConfig)
    if elementConfig.fillMode == "class" then
        local color = ClassColor()
        if color then return color end
    end
    return elementConfig.fill
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
        { type = "dropdown", text = "图层", values = STRATA_VALUES,
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

        -- 填充色：职业配色 / 自定义二选一，计入**一项**配置
        _, h = W:DualRow(parent, y,
            { type = "dropdown", text = "填充色来源", values = { "custom", "class" },
              getValue = function() return element.fillMode or "custom" end,
              setValue = function(value) element.fillMode = value; refresh() end,
              disabled = function() return Config.Grayed(key) end },
            { type = "colorpicker", text = "自定义", hasAlpha = false,
              getValue = function()
                  local c = element.fill
                  return c[1], c[2], c[3]
              end,
              setValue = function(r, g, b)
                  element.fill = { r, g, b }
                  element.fillMode = "custom"
                  refresh()
              end,
              disabled = function() return Config.Grayed(key) end })
        y = y - h

        -- 准星是线不是块：**没有背景色**
        if key ~= "crosshair" then
            _, h = W:ColorPicker(parent, "背景色", y,
                function()
                    local c = element.bg
                    return c[1], c[2], c[3]
                end,
                function(r, g, b) element.bg = { r, g, b }; refresh() end,
                false)
            y = y - h
        end

        _, h = W:Slider(parent, "透明度", y, 0, 100, 1,
            function() return (element.alpha or 1) * 100 end,
            function(value) element.alpha = value / 100; refresh() end)
        y = y - h
    end

    return math.abs(y)
end
