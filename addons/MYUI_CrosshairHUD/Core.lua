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
local UnitHealthPercent = _G.UnitHealthPercent
local UnitPower = _G.UnitPower
local UnitPowerMax = _G.UnitPowerMax
local UnitPowerPercent = _G.UnitPowerPercent
local print = _G.print

local POLL_INTERVAL = 0.1      -- 符文必须轮询：回复速度变化不保证触发事件
local TALENT_DEBOUNCE = 0.1
local LOGIN_DELAY = 0.5

Core.mediaRoot = MEDIA_ROOT

--------------------------------------------------------------------------
-- 读数：秘密值防御
--
-- 受限上下文（副本、PvP）里 UnitHealth／UnitPower 返回的是**秘密值**：实机探针
-- 确认它们连加法都做不了（pcall 直接失败），所以「读到血量比例再自己算角度」这
-- 条路在那里根本不存在——秘密值永远进不了 Lua 参与运算。
--
-- 血量与符能的弧线因此改走**引擎端求值**（见下方「弧线角度」）。这里剩下的
-- Unreadable／MaybeNumber／MaybeBoolean 只服务符文读数：GetRuneCooldown 结构上
-- 不返回秘密值，但仍然按"读到不可读的值就保留上一次"处理，绝不猜一个数字。
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
-- 弧线角度：比例 → 角度交给引擎求值
--
-- 血量和符能的比例在受限上下文里是秘密值，拿不到 Lua 里来。官方给的途径是把这条
-- 映射做成曲线交给引擎：UnitHealthPercent／UnitPowerPercent 接收一条曲线，文档写明
-- 「可用曲线缩放以用于显示」，返回的是**用百分比求值曲线的结果**；数值曲线的
-- AddPoint 收的就是数字，而求值结果正好可以原样喂给纹理的 SetRotation——Rotation
-- 正是 Enum.SecretAspect 之一，旋转本来就能被秘密值驱动。全程本插件不读那个值，
-- 只是把它从 setter 转交到 setter（EllesmereUI 对血量取色用的是同一套做法）。
--
-- MaskAngle 对比例是**仿射**的，所以两个端点就精确等价于原公式；端点由
-- Logic.ArcCurvePoints 从 MaskAngle 导出，离线测试继续守着几何。
--------------------------------------------------------------------------

local arcCurves = {}

local function NewArcCurve(start, span, reverse)
    local CurveUtil = _G.C_CurveUtil
    local linear = Enum and Enum.LuaCurveType and Enum.LuaCurveType.Linear
    if not (CurveUtil and CurveUtil.CreateCurve and linear) then return nil end

    local ok, curve = pcall(CurveUtil.CreateCurve)
    if not ok or not curve or not curve.AddPoint then return nil end

    local low, high = Logic.ArcCurvePoints(start, span, reverse)
    local built = pcall(function()
        curve:SetType(linear)
        curve:AddPoint(0, low)
        curve:AddPoint(1, high)
    end)
    if not built then return nil end
    return curve
end

-- 曲线在 PLAYER_LOGIN 时建；也导出给离线测试，让测试走同一段装配
function Core.BuildArcCurves()
    arcCurves.health = NewArcCurve(Logic.ARCS.health.start, Logic.ARCS.health.span,
        Logic.ARCS.health.reverse)
    arcCurves.power = NewArcCurve(Logic.ARCS.power.start, Logic.ARCS.power.span,
        Logic.ARCS.power.reverse)
end

local function PowerType()
    return Enum and Enum.PowerType and Enum.PowerType.RunicPower
end

--------------------------------------------------------------------------
-- 最近一次成功读到的值（读不到就保留它）
--
-- 弧线的角度**可能是秘密值**：只许原样存放、原样转交，绝不检查、比较或运算。
-- "有没有读到"一律用另一个普通布尔值表示，绝不用 `angle ~= nil` 去测它。
--------------------------------------------------------------------------

local last = { hasHealthArc = false, hasPowerArc = false, runes = {} }
for i = 1, Logic.PIPS.count do
    last.runes[i] = { index = i, frac = 0, state = Logic.RUNE_EMPTY, remaining = nil }
end

-- 返回：普通布尔「读到了吗」，以及角度（可能秘密，调用方只许转交）
local function HealthArc()
    local curve = arcCurves.health
    if not (curve and UnitHealthPercent) then return false end
    local ok, angle = pcall(UnitHealthPercent, "player", false, curve)
    if not ok then return false end
    return true, angle
end

local function PowerArc()
    local curve = arcCurves.power
    local powerType = PowerType()
    if not (curve and UnitPowerPercent and powerType) then return false end
    -- 参数次序是 单位、能量类型、unmodified、曲线
    local ok, angle = pcall(UnitPowerPercent, "player", powerType, false, curve)
    if not ok then return false end
    return true, angle
end

local function UpdateHealthArc()
    local got, angle = HealthArc()
    if got then
        last.healthRotation, last.hasHealthArc = angle, true
    end
end

local function UpdatePowerArc()
    local got, angle = PowerArc()
    if got then
        last.powerRotation, last.hasPowerArc = angle, true
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

-- rotation 可能是秘密值：本函数只转交，不检查
local function ElementState(elementConfig, rotation, hasRotation, runeState)
    return {
        visible = elementConfig.enabled ~= false,
        rotation = rotation,
        hasRotation = hasRotation == true,
        state = runeState,
        fillColor = FillColor(elementConfig),
        fillAlpha = elementConfig.fillAlpha or 1,
        bgColor = elementConfig.bg,
        bgAlpha = elementConfig.bgAlpha or 1,
    }
end

local function BuildState()
    local cfg = Config.Get()
    local elements = cfg.elements
    local state = {}

    state.health = ElementState(elements.health, last.healthRotation, last.hasHealthArc)
    state.power = ElementState(elements.power, last.powerRotation, last.hasPowerArc)

    -- 符文：先排序得到「槽位 → 符文索引」，再把每个符文的状态铺到槽位上。
    -- 6 张符文格纹理各自是环上不同角度的弧段，位置固定——重排换的是显示哪个
    -- 符文的状态，不是换纹理。
    local order = Logic.RuneOrder(last.runes, Logic.PIPS.count)
    state.runes = {}
    for slot = 1, Logic.PIPS.count do
        local rune = last.runes[order[slot]]
        -- 符文的角度由本插件自己算（这条接口不返回秘密值）；比例 0 的情形不必
        -- 特殊处理——那时遮罩本来就什么都不露。
        local start = Logic.PIPS.start + (slot - 1) * Logic.PIPS.step
        state.runes[slot] = ElementState(elements.runes,
            Logic.MaskAngle(start, Logic.PIPS.span, rune.frac), true, rune.state)
    end

    local crosshair = elements.crosshair
    state.crosshair = {
        visible = crosshair.enabled ~= false,
        fillColor = FillColor(crosshair),
        fillAlpha = crosshair.fillAlpha or 1,
    }
    return state
end

--------------------------------------------------------------------------
-- 应用
--------------------------------------------------------------------------

Core.demo = false          -- /chh demo：用假数据驱动，便于在没有战斗时检查渲染

local demoFill = 0

-- 假数据是普通数值，角度直接算；实机那条路必须经引擎求值（见「弧线角度」）
local function ArcRotation(arc, fill)
    return Logic.MaskAngle(arc.start, arc.span, fill, arc.reverse)
end

local function DemoState()
    demoFill = (demoFill + 0.01) % 1.2
    if demoFill > 1 then demoFill = 1 end

    local elements = Config.Get().elements
    local state = {}
    -- 方向必须与真实行为一致，否则拿它检查外观会得出相反的结论：
    -- 血条满血起、逐步掉；符能空起、逐步涨。
    state.health = ElementState(elements.health,
        ArcRotation(Logic.ARCS.health, 1 - demoFill), true)
    state.power = ElementState(elements.power,
        ArcRotation(Logic.ARCS.power, demoFill), true)
    state.runes = {}
    for slot = 1, Logic.PIPS.count do
        local fill = 1.8 * demoFill - (slot - 1) * 0.16
        if fill < 0 then fill = 0 elseif fill > 1 then fill = 1 end
        local start = Logic.PIPS.start + (slot - 1) * Logic.PIPS.step
        state.runes[slot] = ElementState(elements.runes,
            Logic.MaskAngle(start, Logic.PIPS.span, fill), true)
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
    local runes = {}
    for i = 1, Logic.PIPS.count do
        local rune = last.runes[i]
        runes[i] = { index = rune.index, frac = rune.frac, state = rune.state }
    end
    return {
        hasHealth = last.hasHealthArc,
        hasPower = last.hasPowerArc,
        -- 实机里这两个是秘密值，只许原样转交；离线测试里它们是普通数值，可断言
        healthRotation = last.healthRotation,
        powerRotation = last.powerRotation,
        runes = runes,
    }
end

-- 重新读一遍三条资源。事件处理与离线测试都走这里，避免两套路径。
function Core.UpdateReadings()
    UpdateHealthArc()
    UpdatePowerArc()
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
    -- RUNE_POWER_UPDATE 是**普通事件**不是单位事件：它自带 runeIndex 负载，
    -- 没有单位令牌。用 RegisterUnitEvent 注册会在加载期直接报
    -- "Attempt to register unknown event"，整个文件从此不再执行。
    "RUNE_POWER_UPDATE",
}) do
    events:RegisterEvent(event)
end
for _, event in ipairs({
    "UNIT_HEALTH", "UNIT_MAXHEALTH",
    "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "UNIT_MAXPOWER",
}) do
    events:RegisterUnitEvent(event, "player")
end

local talentPending = false

local function OnEvent(_, event)
    if event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then
        UpdateHealthArc()
        Refresh()
    elseif event == "UNIT_POWER_UPDATE" or event == "UNIT_POWER_FREQUENT"
        or event == "UNIT_MAXPOWER" then
        UpdatePowerArc()
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
    Core.BuildArcCurves()
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

-- 读数探针：逐条报告"这一次读数究竟发生了什么"。
-- 只报告**类型与判定结果**，绝不把数值本身转成字符串（秘密值可能不允许转字符串）。
local function Probe(label, call)
    local results = { pcall(call) }
    if not results[1] then
        print("  " .. label .. "：调用抛错 → " .. tostring(results[2]))
        return
    end

    local value = results[2]
    local detector = rawget(_G, "issecretvalue")
    local verdict
    if not detector then
        verdict = "无 issecretvalue"
    else
        local detOk, secret = pcall(detector, value)
        verdict = detOk and ("issecretvalue=" .. tostring(secret))
            or ("issecretvalue 抛错：" .. tostring(secret))
    end

    local arithOk = pcall(function() return value + 0 end)
    print(string.format("  %s：返回%d个 type=%s  %s  可取数=%s",
        label, #results - 1, type(value), verdict, tostring(arithOk)))
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
    -- 只报"有没有取到"，绝不打印角度本身：实机里它是秘密值，不允许转字符串
    print(string.format("  弧线角度：血量%s  符能%s",
        last.hasHealthArc and "已取到" or "没取到",
        last.hasPowerArc and "已取到" or "没取到"))

    -- 读数探针：血量／符能两条弧都空着时，先看是取数接口的问题还是求值链的问题。
    print("  弧线求值链：C_CurveUtil=" .. Presence(_G.C_CurveUtil ~= nil)
        .. "  UnitHealthPercent=" .. Presence(UnitHealthPercent ~= nil)
        .. "  UnitPowerPercent=" .. Presence(UnitPowerPercent ~= nil))
    print("  读数探针：")
    Probe("UnitHealth", function() return UnitHealth("player") end)
    Probe("UnitHealthMax", function() return UnitHealthMax("player") end)
    local powerType = Enum and Enum.PowerType and Enum.PowerType.RunicPower
    print("  符能类型：Enum.PowerType.RunicPower=" .. tostring(powerType))
    if powerType then
        Probe("UnitPower", function() return UnitPower("player", powerType) end)
        Probe("UnitPowerMax", function() return UnitPowerMax("player", powerType) end)
    end
    Probe("GetRuneCooldown(1)", function() return GetRuneCooldown(1) end)
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
-- 侧边栏**行**由核心 MYUI 登记（见 MYUI/Series.lua）：行必须在册，而本插件被
-- 行上的电源按钮禁用后下次重载就不再加载，自己写不回去。这里只登记**页面**与
-- 解锁元素——它们本来就只在本插件加载时存在，被禁用时点开那一行自然没有页面，
-- 与 EUI 自家被禁用的模块行为一致。
--
-- EUI 的官方入口 `EllesmereUI:RegisterModule` 有一张只含自家目录名的白名单，
-- 第三方调用会被**静默拒绝**，所以模块表只能直接写。
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

-- 解锁模式齿轮面板里的「宽度／高度」。本 HUD 是正方形的等比缩放，所以这两个框改的
-- 就是整体缩放本身——与配置页的缩放滑块共用同一个值，不另存一份。
-- 齿轮里的 X/Y 不需要本插件做任何事：它走的就是 EUI 原有的位置四件套。
local function SetHUDSize(_, value)
    local size = tonumber(value)
    if not size or size <= 0 then return end
    local design = Elements.DESIGN_SIZE or 128
    local scale = size / design
    local low = Config.SCALE_MIN or 0.5
    local high = Config.SCALE_MAX or 2.0
    if scale < low then scale = low elseif scale > high then scale = high end
    if scale == Config.Get().scale then return end
    Config.Get().scale = scale
    Core.ApplyConfig()
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
            -- **不要设 noResize**：EUI 把齿轮面板里的宽度/高度/X/Y 几行全放在
            -- `if canResize and elem then` 块里，设了它就等于把 X/Y 输入也一起藏掉。
            -- 本元素的"尺寸"就是整体缩放，交给下面两个 setter 承接。
            setWidth = SetHUDSize,
            setHeight = SetHUDSize,
            linkedDimensions = true,
            -- 尺寸匹配对等比缩放的框体语义不成立（换算会差一个缩放因子），
            -- 给出理由让匹配按钮不可用，比默默改错值好
            matchUnavailable = function()
                return "准星 HUD 的尺寸由整体缩放决定"
            end,
            noSizeMatchTarget = true,
        }),
    }, ADDON)
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

-- 解锁模式齿轮菜单里的「元素选项」→ 直接跳到本元素的设置页。
-- EUI 只在 _ELEMENT_SETTINGS_MAP 里有这个 key 时才画出那一项，所以第三方要做的
-- 全部事情就是把条目写进去；页面名必须是 RegisterModule 里声明过的那个。
local function RegisterSettingsNav()
    local api = EUIAPI()
    local map = api and api._ELEMENT_SETTINGS_MAP
    if not map then return end

    map[UNLOCK_KEY] = {
        module = ADDON,
        page = "Crosshair HUD",
        -- 跳过去之后高亮这一行，让人一眼看到跟尺寸有关的设置在哪
        highlightText = "HUD 缩放",
    }
end

function NS.Mount()
    -- 侧边栏那一行由核心 MYUI 登记：核心不会被行上的电源按钮禁用，所以行一直在册，
    -- 本插件被禁用后只会置灰、还能点回来。这里再调一次是幂等兜底，防的是核心的
    -- PLAYER_LOGIN 处理恰好排在本函数之后。
    local core = rawget(_G, "MYUI")
    if core and core.InjectSidebar then core.InjectSidebar() end

    RegisterModule()
    RegisterUnlockElement()
    RegisterSettingsNav()
end
