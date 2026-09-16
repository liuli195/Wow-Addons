-- 装配模块。
--
-- 事件注册、符文轮询、把游戏数值换算成显示状态、把配置变化应用下去、
-- 以及 EUI 侧边栏与页面的挂载注入（票据 07）。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

local Logic = NS.Logic
local Elements = NS.Elements
local Config = NS.Config

NS.Core = NS.Core or {}
local Core = NS.Core

local ADDON = "MYUI_CrosshairHUD"
local MEDIA_ROOT = "Interface\\AddOns\\MYUI\\Media\\CrosshairHUD\\"

local C_AddOns = _G.C_AddOns
local C_Timer = _G.C_Timer
local CreateFrame = _G.CreateFrame
local Enum = _G.Enum
local GetRuneCooldown = _G.GetRuneCooldown
local GetTime = _G.GetTime
local InCombatLockdown = _G.InCombatLockdown
local SlashCmdList = assert(rawget(_G, "SlashCmdList"))
local UIParent = _G.UIParent
local UnitHealth = _G.UnitHealth
local UnitHealthMax = _G.UnitHealthMax
local UnitPower = _G.UnitPower
local UnitPowerMax = _G.UnitPowerMax
local print = _G.print

local POLL_INTERVAL = 0.1      -- 符文必须轮询：回复速度变化不保证触发事件
local TALENT_DEBOUNCE = 0.1
local LOGIN_DELAY = 0.5

Core.mediaRoot = MEDIA_ROOT

--------------------------------------------------------------------------
-- 读数：秘密值防御
--
-- 四个血量／符能接口都可能返回秘密值，其中 UnitHealth 是 SecretReturns
-- （可能**无条件**返回），另三个是"受限时才可能"。
-- 取到不可读值时返回 nil，由调用方**跳过本次更新、保留上一次的值**，
-- 绝不让秘密值参与比较或算术。
--------------------------------------------------------------------------

local function Unreadable(value)
    if value == nil then return true end
    -- 检测函数**调用时再取**，不在加载时缓存：一是免得加载顺序影响行为，
    -- 二是它在 12.x 里可能对某些值出错，所以整个调用都要 pcall。
    local detector = rawget(_G, "issecretvalue")
    if detector then
        local ok, secret = pcall(detector, value)
        -- 检测函数本身失效时**宁可当作不可读**（fail closed）：既然无法确定它是不是
        -- 秘密值，就不该拿它去参与算术。反过来（当成可读）会让秘密值悄悄流进计算。
        if not ok or secret then return true end
    end
    return false
end

local function ReadNumber(call)
    local ok, value = pcall(call)
    if not ok or Unreadable(value) then return nil end
    local arith, copy = pcall(function() return value + 0 end)
    if not arith or type(copy) ~= "number" then return nil end
    return copy
end

local function Clamp01(value)
    if value < 0 then return 0 elseif value > 1 then return 1 end
    return value
end

---@param value number
---@return number|nil
local function MaybeNumber(value)
    if Unreadable(value) then return nil end
    return value
end

---@param value boolean
---@return boolean|nil
local function MaybeBoolean(value)
    if Unreadable(value) then return nil end
    return value
end

--------------------------------------------------------------------------
-- 最近一次成功读到的值（读不到就保留它）
--------------------------------------------------------------------------

local last = { health = 0, power = 0, runes = {} }
for i = 1, Logic.PIPS.count do
    last.runes[i] = { index = i, frac = 0, state = Logic.RUNE_EMPTY, remaining = nil }
end

local function UpdateHealth()
    local current = ReadNumber(function() return UnitHealth("player") end)
    local maximum = ReadNumber(function() return UnitHealthMax("player") end)
    if current and maximum and maximum > 0 then
        last.health = Clamp01(current / maximum)
    end
end

local function UpdatePower()
    local powerType = Enum and Enum.PowerType and Enum.PowerType.RunicPower
    if not powerType then return end
    local current = ReadNumber(function() return UnitPower("player", powerType) end)
    local maximum = ReadNumber(function() return UnitPowerMax("player", powerType) end)
    if current and maximum and maximum > 0 then
        last.power = Clamp01(current / maximum)
    end
end

-- 符文：判定顺序由 Logic.RuneCharge 保证（先就绪 → 再判空 → 最后除法）
local function UpdateRunes()
    local now = GetTime()
    for i = 1, Logic.PIPS.count do
        local rawStart, rawDuration, rawReady = GetRuneCooldown(i)
        -- 本接口结构上不返回秘密值（无 SecretReturns 标注），但真遇上不可读时
        -- 一律降级成 nil，交给 RuneCharge 的「空转」分支——**绝不猜一个数值**。
        local start = MaybeNumber(rawStart)
        local duration = MaybeNumber(rawDuration)
        local ready = MaybeBoolean(rawReady)
        local frac, state, remaining = Logic.RuneCharge(start, duration, ready, now)
        last.runes[i] = { index = i, frac = frac, state = state, remaining = remaining }
    end
end

--------------------------------------------------------------------------
-- 显示状态表
--------------------------------------------------------------------------

-- 填充色的来源交给配置层解析（职业配色取不到时它自己回落到自定义色）
local function FillColor(elementConfig)
    return Config.ResolveFill(elementConfig)
end

local function ElementState(elementConfig, fill, runeState)
    return {
        visible = elementConfig.enabled ~= false,
        fill = fill,
        state = runeState,
        fillColor = FillColor(elementConfig),
        bgColor = elementConfig.bg,
        alpha = elementConfig.alpha or 1,
    }
end

local function BuildState()
    local cfg = Config.Get()
    local elements = cfg.elements
    local state = {}

    state.health = ElementState(elements.health, last.health)
    state.power = ElementState(elements.power, last.power)

    -- 符文：先排序得到「槽位 → 符文索引」，再把每个符文的状态铺到槽位上。
    -- 6 张符文格纹理各自是环上不同角度的弧段，位置固定——重排换的是显示哪个
    -- 符文的状态，不是换纹理。
    local order = Logic.RuneOrder(last.runes, Logic.PIPS.count)
    state.runes = {}
    for slot = 1, Logic.PIPS.count do
        local rune = last.runes[order[slot]]
        state.runes[slot] = ElementState(elements.runes, rune.frac, rune.state)
    end

    local crosshair = elements.crosshair
    state.crosshair = {
        visible = crosshair.enabled ~= false,
        fillColor = FillColor(crosshair),
        alpha = crosshair.alpha or 1,
    }
    return state
end

--------------------------------------------------------------------------
-- 应用
--------------------------------------------------------------------------

Core.demo = false          -- /chh demo：用假数据驱动，便于在没有战斗时检查渲染

local demoFill = 0

local function DemoState()
    demoFill = (demoFill + 0.01) % 1.2
    if demoFill > 1 then demoFill = 1 end

    local elements = Config.Get().elements
    local state = {}
    state.health = ElementState(elements.health, demoFill)
    state.power = ElementState(elements.power, 1 - demoFill)
    state.runes = {}
    for slot = 1, Logic.PIPS.count do
        local fill = 1.8 * demoFill - (slot - 1) * 0.16
        if fill < 0 then fill = 0 elseif fill > 1 then fill = 1 end
        state.runes[slot] = ElementState(elements.runes, fill)
    end
    state.crosshair = {
        visible = elements.crosshair.enabled ~= false,
        fillColor = FillColor(elements.crosshair),
        alpha = elements.crosshair.alpha or 1,
    }
    return state
end

local function Refresh()
    if not Elements.frame then return end

    if Core.demo then
        Elements.Apply(DemoState())
        return
    end
    if not Config.Get().enabled then
        Elements.Apply(nil)
        return
    end
    Elements.Apply(BuildState())
end
Core.Refresh = Refresh

-- 票据 07 用：解锁元素是否应当报告为隐藏
function Core.IsHidden()
    return not Config.Get().enabled
end

-- 最近一次**成功读到**的读数。既是诊断入口，也是秘密值降级那条分支的
-- 唯一可测面——那条分支在实机无法按需触发，只能离线验。
function Core.GetReadings()
    return { health = last.health, power = last.power }
end

-- 重新读一遍三条资源。事件处理与离线测试都走这里，避免两套路径。
function Core.UpdateReadings()
    UpdateHealth()
    UpdatePower()
    UpdateRunes()
end

--------------------------------------------------------------------------
-- 事件
--------------------------------------------------------------------------

local events = CreateFrame("Frame")
for _, event in ipairs({
    "PLAYER_SPECIALIZATION_CHANGED", "ACTIVE_TALENT_GROUP_CHANGED",
    "TRAIT_CONFIG_UPDATED", "PLAYER_TALENT_UPDATE",
    "PLAYER_ENTERING_WORLD", "PLAYER_DEAD", "PLAYER_ALIVE",
    "ZONE_CHANGED_NEW_AREA", "UI_SCALE_CHANGED",
}) do
    events:RegisterEvent(event)
end
for _, event in ipairs({
    "UNIT_HEALTH", "UNIT_MAXHEALTH",
    "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "UNIT_MAXPOWER",
    "RUNE_POWER_UPDATE",
}) do
    events:RegisterUnitEvent(event, "player")
end

local talentPending = false

local function OnEvent(_, event)
    if event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then
        UpdateHealth()
        Refresh()
    elseif event == "UNIT_POWER_UPDATE" or event == "UNIT_POWER_FREQUENT"
        or event == "UNIT_MAXPOWER" then
        UpdatePower()
        Refresh()
    elseif event == "RUNE_POWER_UPDATE" then
        -- 事件负载可能不可读：忽略参数、整表重读
        UpdateRunes()
        Refresh()
    elseif event == "TRAIT_CONFIG_UPDATED" or event == "PLAYER_TALENT_UPDATE" then
        -- 天赋改动会成串触发，去抖合并成一次
        if not talentPending then
            talentPending = true
            C_Timer.After(TALENT_DEBOUNCE, function()
                talentPending = false
                UpdateRunes()
                Refresh()
            end)
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- 登录竞态：专精事件在登录时不触发，等数据就绪再读一次
        C_Timer.After(LOGIN_DELAY, function()
            Core.UpdateReadings()
            Refresh()
        end)
    elseif event == "UI_SCALE_CHANGED" then
        -- 界面缩放变化后重新摆放：否则 HUD 会偏移
        Elements.SetScale(Config.Get().scale)
    else
        UpdateRunes()
        Refresh()
    end
end
events:SetScript("OnEvent", OnEvent)

-- 符文轮询。**不能纯事件驱动**：回复速度（急速等）变化不保证触发事件，
-- 而时长是动态值，纯事件驱动会让进度条在增益生效期间走偏。
C_Timer.NewTicker(POLL_INTERVAL, function()
    if Core.demo then
        Refresh()
        return
    end
    UpdateRunes()
    Refresh()
end)

--------------------------------------------------------------------------
-- 启动
--------------------------------------------------------------------------

-- 位置：存的是 UIParent 单位的坐标；父框整体缩放了 k 倍，而 SetPoint 的偏移量
-- 读的是**框体自身空间**，所以要除以 k（未缩放时 k == 1，是恒等变换）。
local function ApplyPosition()
    local frame = Elements.frame
    if not frame then return end
    local scale = Config.Get().scale or 1.0
    local pos = Config.Get().position

    frame:ClearAllPoints()
    if not (pos and pos.point) then
        frame:SetPoint("CENTER")
        return
    end

    local x, y = pos.x or 0, pos.y or 0
    local EUI = rawget(_G, "EllesmereUI")
    local PP = EUI and EUI.PP
    if PP and UIParent then
        local uiScale = UIParent:GetEffectiveScale()
        local isCenter = pos.point == "CENTER"
            and (pos.relPoint == "CENTER" or pos.relPoint == nil)
        -- 居中锚点必须用 SnapCenterForDim：普通吸附会让奇数像素尺寸的框体
        -- 每次保存/退出或切专精漂 1 像素
        if isCenter and PP.SnapCenterForDim then
            local width = frame:GetWidth() * (frame:GetEffectiveScale() / uiScale)
            local height = frame:GetHeight() * (frame:GetEffectiveScale() / uiScale)
            x = PP.SnapCenterForDim(x, width, uiScale)
            y = PP.SnapCenterForDim(y, height, uiScale)
        elseif PP.SnapForES then
            x = PP.SnapForES(x, uiScale)
            y = PP.SnapForES(y, uiScale)
        end
    end

    frame:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, x / scale, y / scale)
end
Core.ApplyPosition = ApplyPosition

local function ApplyScaleAndStrata()
    local cfg = Config.Get()
    Elements.SetScale(cfg.scale or 1.0)
    Elements.SetStrata(cfg.strata or "MEDIUM")
    ApplyPosition()
end
Core.ApplyScaleAndStrata = ApplyScaleAndStrata

-- 配置页里的每一项改完都走这里
function Core.ApplyConfig()
    ApplyScaleAndStrata()
    Refresh()
end

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterAllEvents()

    Config.Load()
    Elements.Create()
    ApplyScaleAndStrata()
    if NS.Mount then NS.Mount() end      -- 票据 07 接入
    Core.UpdateReadings()
    Refresh()
end)

--------------------------------------------------------------------------
-- 诊断入口
--------------------------------------------------------------------------

local function Presence(ok)
    return ok and "|cff40c040就位|r" or "|cffff4040缺失|r"
end

local function Version()
    if C_AddOns and C_AddOns.GetAddOnMetadata then
        return C_AddOns.GetAddOnMetadata(ADDON, "Version") or "未知"
    end
    return "未知"
end

local function Report()
    local cfg = Config.Get()
    print("|cff9fd4ff" .. ADDON .. "|r 诊断：")
    print("  版本：" .. Version())
    print("  EllesmereUI：" .. Presence(rawget(_G, "EllesmereUI") ~= nil))
    print("  MYUI（共享素材）："
        .. Presence(C_AddOns and C_AddOns.IsAddOnLoaded and C_AddOns.IsAddOnLoaded("MYUI")))
    print(string.format("  启用=%s  缩放=%.2f  层级=%s  假数据=%s",
        tostring(cfg.enabled), cfg.scale or 1, cfg.strata or "MEDIUM",
        Core.demo and "开" or "关"))
    print(string.format("  最近读数：血量 %.3f  符能 %.3f", last.health, last.power))
    if InCombatLockdown and InCombatLockdown() then
        print("  （战斗中）")
    end
end

_G.SLASH_MYUICHH1 = "/chh"
SlashCmdList["MYUICHH"] = function(msg)
    msg = (msg or ""):lower():gsub("%s+", "")
    if msg == "demo" then
        Core.demo = not Core.demo
        demoFill = 0
        Refresh()
        print("|cff9fd4ff" .. ADDON .. "|r 假数据驱动已" .. (Core.demo and "开启" or "关闭"))
        return
    end
    if msg == "media" then
        print("|cff9fd4ff" .. ADDON .. "|r 素材目录：" .. MEDIA_ROOT)
        return
    end
    Report()
end

--------------------------------------------------------------------------
-- EUI 挂载（票据 07）
--
-- 侧边栏读三张挂在 EllesmereUI 命名空间上的普通表；文件夹名没有前缀要求。
-- 注入必须早于用户首次打开 EUI 面板——行只在首次建面板时创建。
--------------------------------------------------------------------------

local UNLOCK_KEY = "MYUI_CrosshairHUD"
local UNLOCK_ORDER = 900

local function EUIAPI()
    return rawget(_G, "EllesmereUI")
end

-- **屏幕上的宽高**（UIParent 单位）。EUI 的拖动框画在 UIParent 空间，而我们的
-- 父框整体缩放了 k 倍——上报设计稿尺寸会让拖动框大小错一圈。
local function ScreenSize()
    local frame = Elements.frame
    if not frame then return 1, 1 end
    local uiScale = UIParent:GetEffectiveScale()
    local frameScale = frame:GetEffectiveScale()
    if not (uiScale and uiScale > 0 and frameScale and frameScale > 0) then return 1, 1 end
    local k = frameScale / uiScale
    -- 永远返回数字：返回 nil 会让 EUI 的尺寸判断直接报错
    return frame:GetWidth() * k, frame:GetHeight() * k
end

local function SavePos(_, point, relPoint, x, y)
    if not (point and x and y) then return end
    local cfg = Config.Get()
    -- EUI 交来的坐标已经是 UIParent 单位、锚点已归一成 CENTER/CENTER
    cfg.position = { point = point, relPoint = relPoint or point, x = x, y = y }
    local api = EUIAPI()
    if not (api and api._unlockActive) then
        ApplyPosition()
    end
end

local function LoadPos()
    local pos = Config.Get().position
    if not pos then return nil end
    return { point = pos.point, relPoint = pos.relPoint or pos.point, x = pos.x, y = pos.y }
end

local function ClearPos()
    Config.Get().position = nil
    -- EUI 不会替我们复位，只会因为 loadPos 返回 nil 而不再动它——所以自己摆回正中
    ApplyPosition()
end

local function RegisterUnlockElement()
    local api = EUIAPI()
    if not (api and api.RegisterUnlockElements and api.MakeUnlockElement) then
        return   -- EUI 未装，或旧客户端上 EUI 整体停摆（接口根本不存在）
    end

    api:RegisterUnlockElements({
        api.MakeUnlockElement({
            key = UNLOCK_KEY,
            label = "Crosshair HUD",
            group = "MYUI",
            order = UNLOCK_ORDER,
            getFrame = function() return Elements.frame end,
            getSize = ScreenSize,
            savePos = SavePos,
            loadPos = LoadPos,
            clearPos = ClearPos,
            applyPos = function() ApplyPosition() end,
            -- 主开关关闭 → 报告隐藏 → 每次同步都会收起 mover，不留可拖动空框
            isHidden = Core.IsHidden,
            -- 本 HUD 有整体缩放，自动改宽高与尺寸匹配的语义对它不成立，先关掉
            noResize = true,
            noSizeMatchTarget = true,
        }),
    }, ADDON)
end

local function InjectSidebar()
    local api = EUIAPI()
    if not (api and api._modules and api._addonInfoByFolder and api.ADDON_GROUPS) then
        return false
    end
    if api._addonInfoByFolder[ADDON] then return true end   -- 幂等

    -- 不设 alwaysLoaded：本插件是真插件，保留行右边的电源按钮
    api._addonInfoByFolder[ADDON] = { folder = ADDON, display = "Crosshair HUD" }
    if api._syncExempt then api._syncExempt[ADDON] = true end

    local group
    for _, candidate in ipairs(api.ADDON_GROUPS) do
        if candidate.key == "myui" then group = candidate break end
    end
    if not group then
        group = { key = "myui", label = "MYUI", members = {} }
        api.ADDON_GROUPS[#api.ADDON_GROUPS + 1] = group
    end
    group.members[#group.members + 1] = ADDON
    return true
end

local function RegisterModule()
    local api = EUIAPI()
    if not (api and api._modules) then return end
    if api._modules[ADDON] then return end

    api._modules[ADDON] = {
        title = "Crosshair HUD",
        description = "屏幕中心准星 HUD：血量、符能与死亡骑士符文。",
        pages = { "Crosshair HUD" },
        buildPage = Config.BuildPage,
        onReset = function()
            local saved = rawget(_G, "MYUI_CrosshairHUDDB")
            if type(saved) == "table" then
                for key in pairs(saved) do saved[key] = nil end
            end
            Config.Load()
            Core.ApplyConfig()
        end,
    }
end

function NS.Mount()
    InjectSidebar()
    RegisterModule()
    RegisterUnlockElement()
end
