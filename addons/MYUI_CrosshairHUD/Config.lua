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

-- 界面上的元素名（稳定键仍是 health／power／runes，只换显示名）
Config.ELEMENT_LABELS = {
    health = "生命值条", power = "能量条", runes = "职业资源条", crosshair = "准星",
}

-- 与填充色来源同理：values 是映射表 + 显式 order。传数组时 EUI 会用 pairs 自己
-- 拼顺序，每次建页的排列都可能不同。
-- **键是存下来的值，内容是显示文字**：键必须是魔兽认的层级名（要交给
-- SetFrameStrata），界面上显示中文。`_noLoc` 关掉二次本地化——内容本来就是中文。
local STRATA_VALUES = {
    LOW = "低", MEDIUM = "中", HIGH = "高", DIALOG = "对话框",
    _noLoc = true,
}
local STRATA_ORDER = { "LOW", "MEDIUM", "HIGH", "DIALOG" }
-- 导出给测试：键必须是魔兽认的层级名，测试就是盯这个的
Config.STRATA_VALUES, Config.STRATA_ORDER = STRATA_VALUES, STRATA_ORDER

-- 整体缩放的取值范围。**尺寸的唯一入口是解锁模式齿轮里的宽度／高度**（它们写的就是
-- 这个 scale），这里是那个入口的钳位范围——超范围不会静默生效，齿轮回读实际值回写。
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

-- 职业色**只认 EUI 的接口**。职业色／能量色／职业资源色都由 EUI 统一管理，
-- 本插件不能打破这一条：**不许退回暴雪自己的色表**（`C_ClassColor`／
-- `RAID_CLASS_COLORS`）——那是暴雪默认色，不是用户在 EUI 里配的色，混着用会让同一套
-- 界面里出现两套职业色。取不到就返回 nil，由调用方回落到自定义色。
local function ClassColor()
    local EUI = rawget(_G, "EllesmereUI")
    local classFile = PlayerClass()
    if not (EUI and EUI.GetClassColor and classFile) then return nil end

    -- 取色本身也要 pcall：EUI 的颜色缓存以类名令牌为键，而 UnitClass 在受限上下文里
    -- 可能交回秘密令牌——秘密值不能当表键，查表会直接抛错。
    local ok, color = pcall(EUI.GetClassColor, classFile)
    return ok and Channels(color) or nil
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
--
-- **背景没有第二个色块**：背景只有自定义色一种。这条有回归测试盯着
-- （test_config_color.py），因为它来回漂过好几次——不要再给背景加来源色。
-- `editable = false` 是**规则的一部分**：来源色由 EUI 统一管理，这里只能选用、
-- 不能改色，点了方框之后再点也绝不开取色器。页面照这个标志决定点击行为，
-- test_config_plan.py 断言它——实机上报过"再点会弹取色器"，就是漏了这条。
Config.FILL_SOURCE = {
    health    = { mode = "class",    tooltip = "Class Colored",        editable = false },
    power     = { mode = "power",    tooltip = "Power Colored",        editable = false },
    runes     = { mode = "resource", tooltip = "Class Resource Color", editable = false },
    crosshair = { mode = "class",    tooltip = "Class Colored",        editable = false },
}

--- 某一格的第二个色块用哪个来源。**"背景只有自定义色"这条规则的唯一出口**：
--- 页面靠它决定要不要建第二个色块，测试靠它断言这条规则没被改回去。
---   slot = "fill" → 按元素取（见上表）
---   slot = "bg"   → **恒为 nil**：背景没有第二个色块
function Config.SourceFor(elementKey, slot)
    if slot ~= "fill" then return nil end
    return Config.FILL_SOURCE[elementKey]
end

--- 常规节的格子清单。与元素节同一套规则：每项半格、成对成行。
--- **不含缩放**——尺寸由解锁模式齿轮里的宽度／高度负责（它们写的是同一个 scale，
--- 两个框互相联动，超范围还会钳位后回写实际值）。页面上再放一个缩放就是第二个
--- 入口，用户明确要求去掉。test_config_plan.py 断言这里没有它。
function Config.GeneralCells()
    return {
        { kind = "toggle", text = "启用准星HUD", key = "enabled" },
        { kind = "dropdown", text = "图层" },
    }
end

--- 页面上的格子清单。**每项只占半格**：页面按顺序两格一行渲染，末行不足则右边留空
--- ——不是把空位挪到某一行、也不是为了填满而移动配置项。
---
--- 这条规则在实机里来回漂过五次，所以它必须是**数据**而不是散在页面里的判断：
--- test_config_plan.py 直接断言这份清单。
---
--- 每格：
---   { kind = "toggle", text, key }
---   { kind = "color",  text, colorKey, alphaKey, modeKey, source }
--- `source` 非空表示这格有第二个色块（来源色）；背景恒为 nil。
--- 颜色格的 alphaKey 是**它自己**的透明度——颜色与滑块同格，不能分家。
function Config.CellPlan(elementKey)
    local plan = {
        { kind = "toggle", text = "启用", key = "enabled" },
        {
            kind = "color", text = "填充颜色",
            colorKey = "fill", alphaKey = "fillAlpha", modeKey = "fillMode",
            source = Config.SourceFor(elementKey, "fill"),
        },
    }
    -- 准星是线不是块：没有背景，也就没有这一格
    if elementKey ~= "crosshair" then
        plan[3] = {
            kind = "color", text = "条背景",
            colorKey = "bg", alphaKey = "bgAlpha",
            source = Config.SourceFor(elementKey, "bg"),
        }
    end
    return plan
end

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

-- 背景**只有自定义色一种**，没有第二种来源（用户定）。所以它不走取值链，
-- 直接用存下来的自定义色。
function Config.ResolveBg(elementConfig)
    return elementConfig.bg
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

    -- 一格的形状照 EUI 原文：**这一格是 slider，色块内联挂在它左侧**
    -- （EUI 的 `_lastInline` 惯例，见 EUI_UnitFrames_Options 的 boss 分支）——
    -- 于是"标签 + 色块 + 透明度滑块"同处一格。填充颜色与条背景都是这个形状。
    -- 内联的是裸 BuildColorSwatch，所以点击与选中态照那个分支自己接。
    --
    -- 页面按半格成对排列：每项只占半格、从左到右填，**最后一行右边可以留空**，
    -- 不为了填满而挪动配置项。
    --
    -- 来源色块的含义由元素决定（见 Config.FILL_SOURCE）：血弧与准星是职业色，
    -- 符能弧是能量色，符文格是职业资源色。背景的第二种来源固定是职业色。

    -- 内联色块：挂在该格控件的左侧，可挂多个（自右向左）。
    -- spec = { tooltip, getRGB, setRGB, select, isSelected, alpha }
    local function AttachSwatch(rgn, spec, grayed, Changed)
        local swatch = EUI.BuildColorSwatch(rgn, rgn:GetFrameLevel() + 5, spec.getRGB,
            spec.setRGB, false, 20)
        swatch:SetPoint("RIGHT", rgn._lastInline or rgn._control, "LEFT", -8, 0)
        rgn._lastInline = swatch

        swatch:HookScript("OnEnter", function()
            if EUI.ShowWidgetTooltip then EUI.ShowWidgetTooltip(swatch, spec.tooltip) end
        end)
        swatch:HookScript("OnLeave", function()
            if EUI.HideWidgetTooltip then EUI.HideWidgetTooltip() end
        end)

        swatch._eabOrigClick = swatch:GetScript("OnClick")
        swatch:SetScript("OnClick", function(self)
            if grayed() then return end
            local selected = spec.isSelected and spec.isSelected()
            -- **来源色块永远不可编辑**：职业色／能量色／职业资源色由 EUI 统一管理，
            -- 这里只能选、不能改——再点一次也绝不开取色器（EUI 的色块约定是
            -- "已选中时再点开取色器"，但那是对可编辑的自定义色块说的）。
            if not spec.editable then
                if not selected then
                    spec.select()
                    Changed()
                end
                return
            end
            if not selected then
                spec.select()
                Changed()
                return
            end
            if self._eabOrigClick then self._eabOrigClick(self) end
        end)

        local function Refresh()
            local alpha = spec.alpha and spec.alpha() or 1
            if grayed() then alpha = 0.3 end
            swatch:SetAlpha(alpha)
        end
        Refresh()
        if EUI.RegisterWidgetRefresh then EUI.RegisterWidgetRefresh(Refresh) end
        return swatch
    end

    -- 一格里的色块：自定义 +（可选）第二种来源。
    -- modeKey 是"用哪个来源"存在哪（填充是 fillMode）；source 为 nil 表示这格
    -- **没有第二种来源**（背景就是），此时只有一个自定义色块，modeKey 也为 nil。
    local function CellSwatches(elementConfig, colorKey, modeKey, source)
        local function Selected(mode)
            if not modeKey then return mode == "custom" end
            return (elementConfig[modeKey] or "custom") == mode
        end
        local list = { {
            tooltip = "Custom Color",
            getRGB = function()
                local c = elementConfig[colorKey]
                return c[1], c[2], c[3]
            end,
            setRGB = function(r, g, b)
                elementConfig[colorKey] = { r, g, b }
                if modeKey then elementConfig[modeKey] = "custom" end
            end,
            select = function()
                if modeKey then elementConfig[modeKey] = "custom" end
            end,
            isSelected = function() return Selected("custom") end,
            alpha = function() return Selected("custom") and 1 or 0.3 end,
            editable = true,      -- 只有自定义色块能开取色器
        } }
        if source then
            list[2] = {
                tooltip = source.tooltip,
                getRGB = function() return Config.SourceColor(source.mode) end,
                setRGB = function() end,      -- 不可编辑：点它只表示"用这个来源"
                editable = source.editable == true,
                select = function() elementConfig[modeKey] = source.mode end,
                isSelected = function() return Selected(source.mode) end,
                alpha = function()
                    -- 取不到色（本职业在映射表里没登记）时藏掉，而不是留一个黑方块
                    if not Config.SourceColor(source.mode) then return 0 end
                    return Selected(source.mode) and 1 or 0.3
                end,
            }
        end
        return list
    end

    -- 照清单把一格翻译成 EUI 的 slot 配置。排版与内容都在清单里，这里只做翻译。
    local function CellSlot(element, cell, grayed)
        if cell.kind == "toggle" then
            return { type = "toggle", text = cell.text,
                getValue = function() return element[cell.key] ~= false end,
                setValue = function(value) element[cell.key] = value; refresh() end,
                -- 总开关关掉时子开关置灰不可点
                disabled = function() return Config.Get().enabled == false end }
        end
        -- 颜色格：滑块是**这一格自己的**透明度，色块随后内联挂在它左侧
        return { type = "slider", text = cell.text, min = 0, max = 100, step = 1,
            getValue = function() return (element[cell.alphaKey] or 1) * 100 end,
            setValue = function(value)
                element[cell.alphaKey] = value / 100
                refresh()
            end,
            disabled = grayed }
    end

    local _, h = W:SectionHeader(parent, "常规", y)
    y = y - h

    -- 常规节也照清单渲染（Config.GeneralCells）：每项半格、成对成行。
    -- **这里不再有缩放**——尺寸归解锁模式齿轮里的宽度／高度管，两者是同一个 scale。
    local function GeneralSlot(cell)
        if cell.kind == "toggle" then
            local key = cell.key
            return { type = "toggle", text = cell.text,
                getValue = function() return cfg[key] ~= false end,
                setValue = function(value)
                    cfg[key] = value
                    refresh()
                    -- 总开关会改变四个子开关的可用状态，重走一遍刷新列表
                    if EUI and EUI.RefreshPage then EUI:RefreshPage() end
                end }
        end
        return { type = "dropdown", text = cell.text,
            values = STRATA_VALUES, order = STRATA_ORDER,
            getValue = function() return cfg.strata or "MEDIUM" end,
            setValue = function(value) cfg.strata = value; refresh() end }
    end

    local general = Config.GeneralCells()
    local gindex = 1
    while general[gindex] do
        local left, right = general[gindex], general[gindex + 1]
        _, h = W:DualRow(parent, y, GeneralSlot(left),
            right and GeneralSlot(right) or { type = "spacer" })
        y = y - h
        gindex = gindex + 2
    end

    -- 位置**不在这里配**：解锁模式里点齿轮（元素选项）就能改 X/Y，那是 EUI 现成的
    -- 能力，而且与拖动框同处一个会话，比在配置页里另开一套更顺。这里自建只会重复。

    for _, key in ipairs(Config.ELEMENT_ORDER) do
        local element = cfg.elements[key]
        local label = Config.ELEMENT_LABELS[key]
        local grayed = function() return Config.Grayed(key) end
        local function Changed()
            refresh()
            -- 选中态挂在 EUI 的控件刷新列表上：必须叫一次页面刷新，否则不动
            if EUI.RefreshPage then EUI:RefreshPage() end
        end

        _, h = W:SectionHeader(parent, label, y)
        y = y - h

        -- 每项按顺序占半格，成对成行，**末行右边留空**——不为了填满而挪动配置项。
        -- 颜色那两格是 slider + 内联色块：色块与它自己的透明度滑块同处一格。
        -- 页面只是照 Config.CellPlan 渲染：**排版规则不在这里**。
        -- 每项一格、两格一行、末行不足则右边留空——那是清单本身决定的。
        local plan = Config.CellPlan(key)
        local index = 1
        while plan[index] do
            local left, right = plan[index], plan[index + 1]
            local row
            row, h = W:DualRow(parent, y, CellSlot(element, left, grayed),
                right and CellSlot(element, right, grayed) or { type = "spacer" })
            y = y - h

            if not EUI._prebuilding and EUI.BuildColorSwatch then
                local leftRgn = row and row._leftRegion
                if left.kind == "color" and leftRgn then
                    local specs = CellSwatches(element, left.colorKey, left.modeKey,
                        left.source)
                    for i = #specs, 1, -1 do
                        AttachSwatch(leftRgn, specs[i], grayed, Changed)
                    end
                end
                local rightRgn = row and row._rightRegion
                if right and right.kind == "color" and rightRgn then
                    local specs = CellSwatches(element, right.colorKey, right.modeKey,
                        right.source)
                    for i = #specs, 1, -1 do
                        AttachSwatch(rightRgn, specs[i], grayed, Changed)
                    end
                end
            end
            index = index + 2
        end
    end

    return math.abs(y)
end
