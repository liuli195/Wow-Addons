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
            bg   = { 0.208, 0.165, 0.188 },   -- #352A30
            bgAlpha = 1,
        },
        power = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.498, 0.686, 0.796 },   -- #7FAFCB
            fillAlpha = 1,
            bg   = { 0.161, 0.212, 0.251 },   -- #293640
            bgAlpha = 1,
        },
        runes = {
            enabled = true,
            fillMode = "custom",
            fill = { 0.855, 0.839, 0.796 },   -- #DAD6CB
            fillAlpha = 1,
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
-- 玩家职业令牌。优先用 EUI 缓存好的那个（`_playerClass`）：它加载时就取好了，
-- 不受之后上下文变化影响，EUI 自家的色块也是用它取色的。
local function PlayerClass()
    local EUI = rawget(_G, "EllesmereUI")
    if EUI and EUI._playerClass then return EUI._playerClass end
    if UnitClass then
        local ok, _, file = pcall(UnitClass, "player")
        if ok then return file end
    end
    return nil
end

local function ClassColor()
    local EUI = rawget(_G, "EllesmereUI")
    local classFile = PlayerClass()
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

--- 第二种来源的取色。**三个来源在 EUI 里都有现成接口，本插件不自己定色**：
---   class    → 职业色（血弧、准星）
---   power    → 能量色（符能弧）——按玩家的主能量类型取，DK 是 RUNIC_POWER
---   resource → 职业资源色（符文格）
--- 返回 {r,g,b}（通道可能是秘密值，只许原样转交），取不到返回 nil。
--- 可用与否只看**颜色对象在不在**，绝不去判断通道。
local function SourceColor(source)
    if source == "class" then return ClassColor() end

    local EUI = rawget(_G, "EllesmereUI")
    if not EUI then return nil end
    local classFile = PlayerClass()
    if classFile == nil then return nil end

    if source == "power" then
        local map = EUI.CLASS_POWER_MAP
        local okKey, powerKey = pcall(function() return map and map[classFile] end)
        if not (okKey and powerKey and EUI.GetPowerColor) then return nil end
        local ok, color = pcall(EUI.GetPowerColor, powerKey)
        return ok and Channels(color) or nil
    end

    if source == "resource" then
        -- 色表按**资源名**取（DK 是 "Runes"），资源名由职业推——不是拿职业令牌当键。
        -- 传职业令牌查不到，色块会画成黑。
        local map = EUI.CLASS_RESOURCE_MAP
        local okKey, resourceKey = pcall(function() return map and map[classFile] end)
        if not (okKey and resourceKey and EUI.GetClassResourceColor) then return nil end
        local ok, color = pcall(EUI.GetClassResourceColor, resourceKey)
        return ok and Channels(color) or nil
    end

    return nil
end

-- 第二个色块的含义是**设计决定，不是用户配置**：血弧与准星用职业色，
-- 符能弧用能量色，符文格用职业资源色。tooltip 用 EUI 自己的词条键，由它本地化。
Config.FILL_SOURCE = {
    health    = { mode = "class",    tooltip = "Class Colored" },
    power     = { mode = "power",    tooltip = "Power Colored" },
    runes     = { mode = "resource", tooltip = "Class Resource Color" },
    crosshair = { mode = "class",    tooltip = "Class Colored" },
}

-- 供页面显示第二个色块用（返回散开的通道，取不到什么都不返回）
function Config.SourceColor(source)
    local channels = SourceColor(source)
    if not channels then return nil end
    return channels[1], channels[2], channels[3]
end

-- 第二种来源取不到时**回落到自定义色**，而不是画成黑色或什么都不画。
-- 只有**填充**有第二种来源：背景就是自定义色。
function Config.ResolveFill(elementConfig)
    local mode = elementConfig.fillMode
    if mode and mode ~= "custom" then
        local color = SourceColor(mode)
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

    -- 一行「颜色 | 透明度」：左栏是 multiSwatch（标签 + N 个色块），右栏是透明度滑块。
    --
    -- 这就是 EUI 自己的写法（EUI_UnitFrames_Options：Fill Color 用
    -- `{ type="multiSwatch", text=..., swatches={...} }`，透明度是同一行的右侧
    -- slider）。别自己拼：**multiSwatch 这个 slot 本来就认** `onClick` 与
    -- `refreshAlpha`——点色块切来源、未选中的压到 0.3 都是它按这两个回调画的，
    -- `disabled` 它也会自己灰化并挡住点击。`hasAlpha` 只影响取色器弹窗，不生成行内滑块。
    --
    -- 第二个色块的含义由元素决定（见 Config.FILL_SOURCE）：血弧与准星是职业色，
    -- 符能弧是能量色，符文格是职业资源色。source 为 nil 时只有自定义一个色块
    -- （背景就是这样），此时点它仍然开取色器。
    local function ColorRow(text, elementKey, elementConfig, colorKey, alphaKey, alphaText,
        source)
        local grayed = function() return Config.Grayed(elementKey) end
        local function Changed()
            refresh()
            -- 选中态挂在 EUI 的控件刷新列表上：必须叫一次页面刷新，否则不动
            if EUI.RefreshPage then EUI:RefreshPage() end
        end
        local function IsCustom()
            return (elementConfig.fillMode or "custom") == "custom"
        end

        local swatches = { {
            tooltip = "Custom Color",
            hasAlpha = false,
            getValue = function()
                local c = elementConfig[colorKey]
                return c[1], c[2], c[3]
            end,
            setValue = function(r, g, b)
                elementConfig[colorKey] = { r, g, b }
                -- 只有存在第二种来源时才碰来源：背景没有来源，挑背景色不该动填充的选择
                if source then elementConfig.fillMode = "custom" end
                Changed()
            end,
            refreshAlpha = function()
                if not source then return 1 end
                return IsCustom() and 1 or 0.3
            end,
        } }

        if source then
            -- 已经在自定义上时再点才开取色器，否则只切选择（EUI 的色块约定：
            -- 原取色器点击会被 slot 存到 _eabOrigClick）
            swatches[1].onClick = function(self)
                if IsCustom() then
                    if self._eabOrigClick then self._eabOrigClick(self) end
                    return
                end
                elementConfig.fillMode = "custom"
                Changed()
            end

            swatches[2] = {
                tooltip = source.tooltip,
                hasAlpha = false,
                getValue = function() return Config.SourceColor(source.mode) end,
                setValue = function() end,      -- 不可编辑：点它只表示"用这个来源"
                onClick = function()
                    elementConfig.fillMode = source.mode
                    Changed()
                end,
                refreshAlpha = function()
                    -- 这个职业没有对应的源色（映射表里没登记的职业）时不显示，
                    -- 而不是留一个取不到色、画成黑的方块
                    if not Config.SourceColor(source.mode) then return 0 end
                    return (elementConfig.fillMode == source.mode) and 1 or 0.3
                end,
            }
        end

        local _, height = W:DualRow(parent, y,
            { type = "multiSwatch", text = text, disabled = grayed, swatches = swatches },
            { type = "slider", text = alphaText, min = 0, max = 100, step = 1,
              getValue = function() return (elementConfig[alphaKey] or 1) * 100 end,
              setValue = function(value)
                  elementConfig[alphaKey] = value / 100
                  refresh()
              end,
              disabled = grayed })
        y = y - height
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

        -- 填充：自定义 + 该元素的第二种来源（血=职业色，符能=能量色，符文=职业资源色）
        ColorRow("填充颜色", key, element, "fill", "fillAlpha", "填充不透明度",
            Config.FILL_SOURCE[key])

        -- 准星是线不是块：**没有背景色**。背景也没有第二种来源，只有自定义色。
        if key ~= "crosshair" then
            ColorRow("条背景", key, element, "bg", "bgAlpha", "背景不透明度", nil)
        end
    end

    return math.abs(y)
end
