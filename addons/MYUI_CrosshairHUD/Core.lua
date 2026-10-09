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

local C_Timer = _G.C_Timer
local CreateFrame = _G.CreateFrame
local Enum = _G.Enum
local GetRuneCooldown = _G.GetRuneCooldown
local GetTime = _G.GetTime
local UIParent = _G.UIParent
local UnitHealthPercent = _G.UnitHealthPercent
local UnitPowerMax = _G.UnitPowerMax
local UnitPowerPercent = _G.UnitPowerPercent

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
    -- 检测函数**调用时再取**，不在加载时缓存：一是免得加载顺序影响行为，
    -- 二是它在 12.x 里可能对某些值出错，所以整个调用都要 pcall。
    local detector = rawget(_G, "issecretvalue")
    if detector then
        local ok, secret = pcall(detector, value)
        -- 检测函数本身失效时**宁可当作不可读**（fail closed）：既然无法确定它是不是
        -- 秘密值，就不该拿它去参与算术。反过来（当成可读）会让秘密值悄悄流进计算。
        if not ok or secret then return true end
    end
    return value == nil
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

local function NewArcCurve(start, span, reverse, endMargin)
    local CurveUtil = _G.C_CurveUtil
    local linear = Enum and Enum.LuaCurveType and Enum.LuaCurveType.Linear
    if not (CurveUtil and CurveUtil.CreateCurve and linear) then return nil end

    local ok, curve = pcall(CurveUtil.CreateCurve)
    if not ok or not curve or not curve.AddPoint then return nil end

    local low, high = Logic.ArcCurvePoints(start, span, reverse, endMargin)
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
        Logic.ARCS.health.reverse, Logic.ARCS.health.endMargin)
    arcCurves.power = NewArcCurve(Logic.ARCS.power.start, Logic.ARCS.power.span,
        Logic.ARCS.power.reverse, Logic.ARCS.power.endMargin)
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
    last.healthReadOK = got
    if got then
        last.healthRotation, last.hasHealthArc = angle, true
    end
end

local function UpdatePowerArc()
    local got, angle = PowerArc()
    last.powerReadOK = got
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

-- 监控条目可能挂在灵界打击下，需同时匹配关联的增益编号。
local function BloodInfoMatches(info)
    if type(info) ~= "table" then return false end
    for _, key in ipairs({ "spellID", "overrideSpellID", "overrideTooltipSpellID", "linkedSpellID" }) do
        if MaybeNumber(info[key]) == 463730 then return true end
    end
    if type(info.linkedSpellIDs) == "table" then
        for _, id in ipairs(info.linkedSpellIDs) do
            if MaybeNumber(id) == 463730 then return true end
        end
    end
    return false
end

local function UniqueBloodBinding(info)
    if type(info) ~= "table" then return false end
    local current = MaybeNumber(info.linkedSpellID)
    if type(current) == "number" then return current == 463730 end
    local found = false
    if type(info.linkedSpellIDs) == "table" then
        for _, id in ipairs(info.linkedSpellIDs) do
            local readable = MaybeNumber(id)
            if type(readable) ~= "number" or readable ~= 463730 then return false end
            found = true
        end
    end
    return found or BloodInfoMatches(info)
end

local function BloodAuraForItem(item)
    local cached = item.auraDataCached
    if Unreadable(cached) or type(cached) ~= "table" then return end
    local unit = item.auraDataUnit
    local active = item.IsActive and MaybeBoolean(item:IsActive())
    if Unreadable(unit) or unit ~= "player" or active == false then return end
    local actual = MaybeNumber(cached.spellId)
    if type(actual) == "number" then
        if actual ~= 463730 then return end
    else
        local info = item.GetCooldownInfo and item:GetCooldownInfo()
        local api = _G.C_CooldownViewer
        if api and api.GetCooldownViewerCooldownInfo and item.GetCooldownID then
            local id = MaybeNumber(item:GetCooldownID())
            if type(id) == "number" then
                info = api.GetCooldownViewerCooldownInfo(id) or info
            end
        end
        if not UniqueBloodBinding(info) then return end
    end
    -- 字段访问同样在逐条目的异常保护内；返回自己的表，不泄漏受限缓存表。
    return { applications = cached.applications }
end

local function TrackedBloodAura()
    for _, name in ipairs({ "BuffIconCooldownViewer", "BuffBarCooldownViewer" }) do
        local viewer = _G[name]
        if viewer and viewer.GetItemFrames then
            local ok, frames = pcall(viewer.GetItemFrames, viewer)
            if ok and type(frames) == "table" then
                for _, item in ipairs(frames) do
                    local readable, aura = pcall(BloodAuraForItem, item)
                    if readable and type(aura) == "table" then return aura end
                end
            end
        end
    end
end

-- 只确认是否取得数值，受限层数原样交给原生进度条，绝不做算术或比较。
local function HasStackValue(value)
    local detector = rawget(_G, "issecretvalue")
    if detector then
        local ok, secret = pcall(detector, value)
        if not ok then return false end
        if secret then return true end
    end
    return type(value) == "number"
end

-- 独立扫描玩家增益：身份必须可读，层数允许受限并原样交给引擎。
local function IndependentBloodAura()
    local api = _G.C_UnitAuras
    if not (api and api.GetUnitAuras) then return nil, "接口不可用" end
    local stage = "请求增益列表"
    local ok, aura, status = pcall(function()
        local records = api.GetUnitAuras("player", "HELPFUL")
        if Unreadable(records) or type(records) ~= "table" then return nil, "记录不可读取" end
        stage = "遍历增益列表"
        local unknown = false
        for _, record in ipairs(records) do
            local readable, found, identityKnown = pcall(function()
                if Unreadable(record) or type(record) ~= "table" then return nil, false end
                local id = MaybeNumber(record.spellId)
                if id == nil then return nil, false end
                if id == 463730 then return { applications = record.applications }, true end
                return nil, true
            end)
            if readable and found then return found, "已找到" end
            if not readable or not identityKnown then unknown = true end
        end
        return nil, unknown and "增益身份受限或缺失" or "确认不存在"
    end)
    if not ok then
        local detail = not Unreadable(aura) and type(aura) == "string" and aura or "错误内容受限或不可读取"
        return nil, stage .. "失败：" .. detail
    end
    return aura, status
end

local function UpdateBloodAura()
    last.bloodPresent, last.bloodStacks, last.hasBloodStacks = false, nil, false
    last.bloodScanStatus = "开关关闭"
    if not Config.Available("coagulatedBlood") then return end
    if NS.NativeBlood then
        last.bloodScanStatus = "原生容器直接管理；插件不读取层数"
        return
    end
    if Config.Get().elements.coagulatedBlood.enabled == false then return end
    local aura, scanStatus = IndependentBloodAura()
    last.bloodScanStatus = scanStatus
    local ok = true
    if scanStatus == "确认不存在" then return end
    if type(aura) ~= "table" then ok, aura = pcall(TrackedBloodAura) end
    if not ok or type(aura) ~= "table" then
        local api = _G.C_UnitAuras
        if not (api and api.GetPlayerAuraBySpellID) then return end
        ok, aura = pcall(function()
            local direct = api.GetPlayerAuraBySpellID(463730)
            if Unreadable(direct) or type(direct) ~= "table" then return end
            return { applications = direct.applications }
        end)
    end
    if not ok or Unreadable(aura) or type(aura) ~= "table" then return end
    last.bloodPresent = true
    local readable, stacks = pcall(function() return aura.applications end)
    if readable then
        last.bloodStacks = stacks
        last.hasBloodStacks = HasStackValue(stacks)
    end
end

local function UpdateDeathStrike()
    last.costMarker = nil
    if Config.Get().elements.deathStrike.enabled == false then return end
    local api, powerType = _G.C_Spell, PowerType()
    if not (api and api.GetSpellPowerCost and UnitPowerMax and powerType) then return end
    pcall(function()
        local costs = api.GetSpellPowerCost(49998)
        if Unreadable(costs) or type(costs) ~= "table" then return end
        local selected
        for _, entry in ipairs(costs) do
            if not Unreadable(entry) and type(entry) == "table"
                and MaybeNumber(entry.type) == powerType then
                local required = MaybeNumber(entry.requiredAuraID)
                local active = MaybeBoolean(entry.hasRequiredAura)
                local applicable = required == 0 or (required ~= nil and active == true)
                local cost = MaybeNumber(entry.minCost)
                if applicable and type(cost) == "number" and cost >= 0
                    and (selected == nil or cost < selected) then
                    selected = cost
                end
            end
        end
        local maximum = MaybeNumber(UnitPowerMax("player", powerType, false))
        last.costMarker = Logic.CostMarker(selected, maximum)
    end)
end

local function UpdateDKFeatures()
    UpdateBloodAura()
    UpdateDeathStrike()
end

-- 沸点是配对信号推断，不读取实际回声或历史。复用已有刷新节奏。
-- BoilingPointEcho (MIT) 的 cast/HIDE 相关性思路；不复制独立图标与计时框架。
--[[
MIT License

Copyright (c) 2026 Wan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
]]
local boiling = {}
local function ClearBoiling()
    boiling.proc, boiling.pending, boiling.cast, boiling.hide, boiling.deadline = nil, nil, nil, nil, nil
end

local function BoilingFraction()
    local cfg = Config.Get()
    if cfg.enabled == false or cfg.elements.boilingPoint.enabled == false
        or not Config.Available("boilingPoint") then
        ClearBoiling()
        return nil
    end
    local now = GetTime()
    if boiling.deadline and now >= boiling.deadline then
        if boiling.pending then
            boiling.deadline = boiling.deadline + 3
            boiling.pending, boiling.proc = nil, nil
        end
        if now >= boiling.deadline then ClearBoiling() end
    end
    if boiling.deadline then return Logic.DisplayFraction(boiling.deadline - now, 3) end
end

local function BoilingEvent(event, unit, _, spellID)
    BoilingFraction()
    local cfg = Config.Get()
    if cfg.enabled == false or cfg.elements.boilingPoint.enabled == false
        or not Config.Available("boilingPoint") then return end
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        if Unreadable(unit) or unit ~= "player" or MaybeNumber(spellID) ~= 50842 then return end
        boiling.cast = GetTime()
    else
        if MaybeNumber(unit) ~= 50842 then return end
        if event == "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW" then
            boiling.proc = true
            if boiling.deadline then boiling.pending = true end
            return
        end
        boiling.hide = GetTime()
    end
    if boiling.cast and boiling.hide and math.abs(boiling.cast - boiling.hide) <= 0.30 + 1e-9 then
        -- SHOW 不重置当前轮；确认再次手动消耗时按新施法时刻起算，取消旧待续标记。
        boiling.deadline = boiling.cast + 3
        boiling.cast, boiling.hide, boiling.proc, boiling.pending = nil, nil, nil, nil
    end
end

--------------------------------------------------------------------------
-- 显示状态表
--------------------------------------------------------------------------

-- 填充色交给配置层解析（取不到来源色时它自己回落到自定义色）。
-- 背景**只有自定义色一种**，没有第二种来源（见 Config.ResolveBg）。
local function FillColor(elementConfig)
    return Config.ResolveFill(elementConfig)
end

local function BgColor(elementConfig)
    return Config.ResolveBg(elementConfig)
end

-- 阴影的颜色与浓淡。**全局一处设置**，由配置层解析后投影到每个元素的阴影层上
-- （状态表本身仍是逐元素的，契约不变）。三处构造状态表的地方都从这里取。
local SHADOW_FALLBACK = { 0, 0, 0 }   -- 配置缺项时的兜底；正常不会走到

local function ShadowColor()
    return Config.ResolveShadow() or SHADOW_FALLBACK
end

local function ShadowAlpha()
    return Config.ResolveShadowAlpha()
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
        bgColor = BgColor(elementConfig),
        bgAlpha = elementConfig.bgAlpha or 1,
        shadowColor = ShadowColor(),
        shadowAlpha = ShadowAlpha(),
    }
end

local function BuildState()
    local cfg = Config.Get()
    local elements = cfg.elements
    local state = {}

    state.health = ElementState(elements.health, last.healthRotation, last.hasHealthArc)
    state.power = ElementState(elements.power, last.powerRotation, last.hasPowerArc)
    local blood = elements.coagulatedBlood
    state.coagulatedBlood = ElementState(blood, nil, false)
    state.coagulatedBlood.visible = Config.Available("coagulatedBlood")
        and blood.enabled ~= false and (NS.NativeBlood ~= nil or last.bloodPresent == true)
    state.coagulatedBlood.stacks = last.bloodStacks
    state.coagulatedBlood.hasStacks = last.hasBloodStacks == true
    state.coagulatedBlood.maxStacks = blood.maxStacks
    local fraction = BoilingFraction()
    local arc = Logic.ARCS.boilingPoint
    state.boilingPoint = ElementState(elements.boilingPoint,
        fraction and Logic.MaskAngle(arc.start, arc.span, fraction, arc.reverse), fraction ~= nil)
    state.boilingPoint.visible = fraction ~= nil
    if NS.Debug then NS.Debug.ApplyProbe(state) end
    local marker = elements.deathStrike
    state.deathStrike = { visible = marker.enabled ~= false and last.costMarker ~= nil,
        points = last.costMarker, thickness = marker.thickness,
        fillColor = marker.fill, fillAlpha = marker.fillAlpha }

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
            Logic.MaskAngle(start, Logic.PIPS.span, rune.frac, false, Logic.PIPS.endMargin), true, rune.state)
    end

    local crosshair = elements.crosshair
    state.crosshair = {
        visible = crosshair.enabled ~= false,
        fillColor = FillColor(crosshair),
        fillAlpha = crosshair.fillAlpha or 1,
        shadowColor = ShadowColor(),
        shadowAlpha = ShadowAlpha(),
    }
    return state
end

--------------------------------------------------------------------------
-- 应用
--------------------------------------------------------------------------

-- 「现在该不该显示」的唯一出口。
--
-- 之所以收成一处：渲染侧（画不画）与解锁元素侧（给不给拖动框）问的是同一个问题。
-- 两处各写一遍的话，一旦不一致，症状就是「屏幕上看不见它，正中却留着一个能拖的
-- 空框」——那正是本模块存在的理由。
local function ShouldShow()
    if NS.Debug and NS.Debug.IsDemo() then
        -- 演示模式存在的意义就是「条件不满足时也能看」，所以它绕过可见性。
        -- 与它绕过总开关是同一个道理。
        return true
    end
    local visibility = NS.Visibility
    if not (visibility and visibility.ShouldShow) then
        return Config.Get().enabled ~= false
    end

    -- 解锁模式是**编辑模式**：条件让路，这样把可见性设成「仅战斗中」之后，
    -- 人在城里也拖得到它——否则就再也调不了位置了。
    --
    -- 但「这东西不该存在」（总开关关着、「从不」）不让路：那时给一个拖动框，
    -- 只会让人对着一个不存在的东西拖。
    local api = rawget(_G, "EllesmereUI")
    if api and api._unlockActive
        and visibility.IsOff and not visibility.IsOff() then
        return true
    end

    return visibility.ShouldShow() and true or false
end

local function Refresh()
    if not Elements.frame then return end

    if not ShouldShow() then
        Elements.Apply(nil)
        return
    end

    if NS.Debug and NS.Debug.IsDemo() then
        Elements.Apply(NS.Debug.DemoState())
        return
    end
    Elements.Apply(BuildState())
end
Core.Refresh = Refresh

-- 票据 07 用：解锁元素是否应当报告为隐藏。
-- 与渲染侧共用同一个出口，两处不可能给出不同答案。
function Core.IsHidden()
    return not ShouldShow()
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
        healthReadOK = last.healthReadOK,
        powerReadOK = last.powerReadOK,
        hasMarker = last.costMarker ~= nil,
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
    UpdateDKFeatures()
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
    "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",
}) do
    events:RegisterEvent(event)
end
for _, event in ipairs({
    "UNIT_HEALTH", "UNIT_MAXHEALTH",
    "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "UNIT_MAXPOWER",
    "UNIT_AURA",
    "UNIT_SPELLCAST_SUCCEEDED",
}) do
    events:RegisterUnitEvent(event, "player")
end

local talentPending = false

local function OnEvent(_, event, ...)
    if event == "PLAYER_SPECIALIZATION_CHANGED" or event == "ACTIVE_TALENT_GROUP_CHANGED" then
        ClearBoiling()
        Core.UpdateReadings()
        Refresh()
        local EUI = rawget(_G, "EllesmereUI")
        if EUI and EUI.RefreshPage then EUI:RefreshPage() end
    elseif event == "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW" or event == "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE"
        or event == "UNIT_SPELLCAST_SUCCEEDED" then
        BoilingEvent(event, ...)
        Refresh()
    elseif event == "UNIT_AURA" then
        UpdateDKFeatures()
        Refresh()
    elseif event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then
        UpdateHealthArc()
        Refresh()
    elseif event == "UNIT_POWER_UPDATE" or event == "UNIT_POWER_FREQUENT"
        or event == "UNIT_MAXPOWER" then
        UpdatePowerArc()
        UpdateDeathStrike()
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
        -- 界面缩放变化后要**重走整套摆放**：只调 SetScale 是白调（重算的还是同一组
        -- 值，与界面缩放无关），像素吸附只发生在 ApplyPosition 里——漏了它就偏移。
        Core.ApplyScaleAndStrata()
    else
        UpdateRunes()
        Refresh()
    end
end
events:SetScript("OnEvent", OnEvent)

-- 符文轮询。**不能纯事件驱动**：回复速度（急速等）变化不保证触发事件，
-- 而时长是动态值，纯事件驱动会让进度条在增益生效期间走偏。
C_Timer.NewTicker(POLL_INTERVAL, function()
    UpdateDKFeatures()
    if NS.Debug and NS.Debug.IsDemo() then
        Refresh()
        return
    end
    UpdateRunes()
    Refresh()
end)

--------------------------------------------------------------------------
-- 启动
--------------------------------------------------------------------------

-- 位置存的是 EUI 归一后的 UIParent 单位坐标。HUD 的 cfg.scale 只改变框体尺寸
-- 与内部纹理摆放，并没有调用 frame:SetScale；因此 SetPoint 必须直接使用保存坐标。
local function ApplyPosition()
    local frame = Elements.frame
    if not frame then return end
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

    frame:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, x, y)
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
    UpdateDKFeatures()
    BoilingFraction()
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
            label = "准星HUD",
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
            -- **自作定位，必须声明**：否则尺寸变化（NotifyElementResized）与初始化时，
            -- EUI 会用他自己的换算把存下来的 CENTER 位置重贴一遍
            -- （EUI_UnlockMode.lua:1630 的 ApplyCenterPosition），把框贴到别处——
            -- 实机现象就是"X/Y 显示 0,0，框却不在 0,0；改宽度/高度时啪地跳走"。
            -- 设了它，EUI 改为回调下面这个 applyPos，两边不再各贴一次。
            noInitHook = true,
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
        title = "准星HUD",
        -- 文案通用，不写死职业：这个 HUD 以后要扩展到全职业
        description = "屏幕中心准星HUD：生命值条、能量条与职业资源条。",
        pages = { "准星HUD" },
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
        page = "准星HUD",
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

    -- 可见性接线。条件变化时 EUI 会回调这里，重算后两处一起更新。
    -- 接不上时模块自己降级为「一直显示」，不影响上面三件。
    local visibility = NS.Visibility
    if visibility and visibility.Install then visibility.Install(Refresh) end
end

-- 开发包才加载可选工具；正式包没有该文件，也不建立这些测试回调。
if NS.Debug then
    NS.Debug.Attach({ Core=Core, Logic=Logic, Config=Config, Elements=Elements,
        last=last, BuildState=BuildState, ElementState=ElementState,
        FillColor=FillColor, ShadowColor=ShadowColor, ShadowAlpha=ShadowAlpha,
        MaybeNumber=MaybeNumber, TrackedBloodAura=TrackedBloodAura })
end
