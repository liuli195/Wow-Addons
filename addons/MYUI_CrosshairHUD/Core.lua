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

-- 填充色的来源：自定义取配置里的值；职业配色由票据 05 接上 EUI 的职业色接口
local function FillColor(elementConfig)
    return elementConfig.fill
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

local function ApplyScaleAndStrata()
    local cfg = Config.Get()
    Elements.SetScale(cfg.scale or 1.0)
    Elements.SetStrata(cfg.strata or "MEDIUM")
end
Core.ApplyScaleAndStrata = ApplyScaleAndStrata

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterAllEvents()

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
