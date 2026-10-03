-- 可选开发工具：不在正式加载清单或正式安装包中。
local NS = _G.MYUI_CHH
local Debug = {}
NS.Debug = Debug
local Logic = NS.Logic
--------------------------------------------------------------------------
-- 假数据驱动
--
-- `/chh demo` 用的两条比例。**方向必须与真实行为一致**：生命值满血起、逐步掉；
-- 能量空起、逐步涨。方向演反了，看的人会拿它得出与真实相反的结论——实机上已经
-- 因此误判过一次（"血条默认是空的"其实是 demo 在演反）。
-- 参数 t 是一轮进度 0..1，越界钳位。
--------------------------------------------------------------------------

function Logic.DemoFills(t)
    if t < 0 then t = 0 elseif t > 1 then t = 1 end
    return 1 - t, t
end


function Debug.Attach(ctx)
local Core, Config, Elements = ctx.Core, ctx.Config, ctx.Elements
local last, BuildState, ElementState = ctx.last, ctx.BuildState, ctx.ElementState
local FillColor, ShadowColor, ShadowAlpha = ctx.FillColor, ctx.ShadowColor, ctx.ShadowAlpha
local MaybeNumber, TrackedBloodAura = ctx.MaybeNumber, ctx.TrackedBloodAura
local Refresh = Core.Refresh
local ADDON = "MYUI_CrosshairHUD"
local MEDIA_ROOT = Core.mediaRoot
local C_AddOns, Enum = _G.C_AddOns, _G.Enum
local UnitClass, UnitHealth, UnitHealthMax = _G.UnitClass, _G.UnitHealth, _G.UnitHealthMax
local UnitHealthPercent, UnitPowerPercent = _G.UnitHealthPercent, _G.UnitPowerPercent
local UnitPower, UnitPowerMax, GetRuneCooldown = _G.UnitPower, _G.UnitPowerMax, _G.GetRuneCooldown
local InCombatLockdown, SlashCmdList, print = _G.InCombatLockdown, rawget(_G, "SlashCmdList"), _G.print
Core.demo = false          -- /chh demo：用假数据驱动，便于在没有战斗时检查渲染

local demoFill = 0

-- 假数据是普通数值，角度直接算；实机那条路必须经引擎求值（见「弧线角度」）
local function ArcRotation(arc, fill)
    return Logic.MaskAngle(arc.start, arc.span, fill, arc.reverse, arc.endMargin)
end

local function DemoState()
    demoFill = (demoFill + 0.01) % 1.2
    if demoFill > 1 then demoFill = 1 end

    local elements = Config.Get().elements
    local state = {}
    -- 方向由 Logic.DemoFills 定（满血起掉、空起涨），那里有测试守着：
    -- 方向演反了，拿它检查外观会得出与真实相反的结论。
    local healthFill, powerFill = Logic.DemoFills(demoFill)
    state.health = ElementState(elements.health,
        ArcRotation(Logic.ARCS.health, healthFill), true)
    state.power = ElementState(elements.power,
        ArcRotation(Logic.ARCS.power, powerFill), true)
    state.runes = {}
    for slot = 1, Logic.PIPS.count do
        local fill = 1.8 * demoFill - (slot - 1) * 0.16
        if fill < 0 then fill = 0 elseif fill > 1 then fill = 1 end
        local start = Logic.PIPS.start + (slot - 1) * Logic.PIPS.step
        state.runes[slot] = ElementState(elements.runes,
            Logic.MaskAngle(start, Logic.PIPS.span, fill, false, Logic.PIPS.endMargin), true)
    end
    state.crosshair = {
        visible = elements.crosshair.enabled ~= false,
        fillColor = FillColor(elements.crosshair),
        -- 键名必须与状态表契约一致（准星带的是 fillAlpha，不是 alpha）——
        -- 写错了渲染层读不到，表现是 demo 下调准星透明度毫无反应。
        fillAlpha = elements.crosshair.fillAlpha or 1,
        shadowColor = ShadowColor(),
        shadowAlpha = ShadowAlpha(),
    }
    -- 新功能仍按真实增益存在与开关显示，不把演示当成真实层数或费用。
    local real = BuildState()
    state.coagulatedBlood, state.deathStrike = real.coagulatedBlood, real.deathStrike
    return state
end


Debug.IsDemo = function() return Core.demo end
Debug.DemoState = DemoState
function Debug.ApplyProbe(state)
local blood = Config.Get().elements.coagulatedBlood
    -- 临时校准走同一绘制入口，不改存档，也不尝试读取受限层数。
    if type(Core.bloodProbeStacks) == "number" then
        state.coagulatedBlood.visible = blood.enabled ~= false
        state.coagulatedBlood.stacks = Core.bloodProbeStacks
        state.coagulatedBlood.hasStacks = true
        state.coagulatedBlood.maxStacks = 150
        state.coagulatedBlood.probe = true
    end
end
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

-- 职业色取值链的探针：只报**类型与成败**，绝不打印颜色本身（通道可能是秘密值）。
local function ColorSource(label, call)
    local results = { pcall(call) }
    if not results[1] then
        print("  " .. label .. "：调用抛错 → " .. tostring(results[2]))
        return
    end
    local color = results[2]
    local channels = "-"
    if type(color) == "table" then
        local ok, r, g, b = pcall(function() return color.r, color.g, color.b end)
        channels = ok
            and (type(r) .. "/" .. type(g) .. "/" .. type(b))
            or ("读通道抛错 → " .. tostring(r))
    end
    local detector = rawget(_G, "issecretvalue")
    local secret = "无检测函数"
    if detector then
        local ok, value = pcall(detector, color)
        secret = ok and tostring(value) or ("抛错 → " .. tostring(value))
    end
    print(string.format("  %s：type=%s 通道=%s issecretvalue=%s",
        label, type(color), channels, secret))
end

local function ReportClassColor()
    print("  职业色取值链：")
    local ok, _, classFile = pcall(UnitClass, "player")
    print("  UnitClass：调用成功=" .. tostring(ok) .. "  类名令牌可读="
        .. tostring(classFile ~= nil))
    if not (ok and classFile) then return end

    local api = rawget(_G, "C_ClassColor")
    local EUI = rawget(_G, "EllesmereUI")
    print("  接口：C_ClassColor=" .. Presence(api ~= nil)
        .. "  EUI 缓存令牌=" .. Presence(EUI and EUI._playerClass ~= nil)
        .. "  EUI.GetClassColor=" .. Presence(EUI and EUI.GetClassColor ~= nil)
        .. "  RAID_CLASS_COLORS=" .. Presence(rawget(_G, "RAID_CLASS_COLORS") ~= nil))

    if EUI and EUI.GetClassColor then
        ColorSource("第一级 EUI 缓存", function() return EUI.GetClassColor(classFile) end)
    end
    if api and api.GetClassColor then
        ColorSource("第二级 C_ClassColor", function() return api.GetClassColor(classFile) end)
    end
    local palette = rawget(_G, "RAID_CLASS_COLORS")
    if palette then
        ColorSource("第三级 全局色表", function() return palette[classFile] end)
    end
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
    print(string.format("  弧线角度：生命值%s  能量%s",
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
    print("  能量类型：Enum.PowerType.RunicPower=" .. tostring(powerType))
    if powerType then
        Probe("UnitPower", function() return UnitPower("player", powerType) end)
        Probe("UnitPowerMax", function() return UnitPowerMax("player", powerType) end)
    end
    Probe("GetRuneCooldown(1)", function() return GetRuneCooldown(1) end)
    ReportClassColor()
    if InCombatLockdown and InCombatLockdown() then
        print("  （战斗中）")
    end
end

_G.SLASH_MYUICHH1 = "/chh"
SlashCmdList["MYUICHH"] = function(msg)
    msg = (msg or ""):lower():gsub("%s+", "")
    if msg == "bloodtestoff" then
        Core.bloodProbeStacks = nil
        Refresh()
        print("凝固之血显示测试已关闭，恢复真实增益。")
        return
    end
    local probe = msg:match("^bloodtest(%d+)$")
    if probe then
        local value = tonumber(probe)
        if value == 0 or value == 10 or value == 16 or value == 75 or value == 150 then
            Core.bloodProbeStacks = value
            Refresh()
            print("凝固之血显示测试：固定" .. value .. "层／150量程；不是实时增益。"
                .. " 输入 /chh bloodtest off 退出，重载也会退出。")
        else
            print("显示测试只接受0、10、16、75、150，不改变真实设置。")
        end
        return
    end
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
    if msg == "blood" then
        local cfg = Config.Get().elements.coagulatedBlood
        if NS.NativeBlood then
            print("凝固之血：开关" .. (cfg.enabled == false and "关闭" or "开启") .. "；显示量程：" .. cfg.maxStacks)
            print(NS.NativeBlood.status)
            print("不依赖暴雪默认增益监控；插件不反向读取受限层数")
            return
        end
        print("独立增益读取：" .. (last.bloodScanStatus or "尚未读取"))
        print("凝固之血：开关" .. (cfg.enabled == false and "关闭" or "开启")
            .. "，增益" .. (last.bloodPresent and "已确认" or "未确认")
            .. "，层数" .. (type(MaybeNumber(last.bloodStacks)) == "number" and "可读取" or "受限或缺失"))
        local function Reading(value)
            local readable = MaybeNumber(value)
            if type(readable) == "number" then return string.format("%.6g", readable) end
            return "受限或缺失"
        end
        print("显示量程：" .. Reading(cfg.maxStacks) .. "；实际读取层数：" .. Reading(last.bloodStacks))
        local renderOk, rendered = pcall(Elements.BloodDiagnostics)
        if renderOk and type(rendered) == "table" then
            print("游戏绘制量程：" .. Reading(rendered.minimum) .. "～" .. Reading(rendered.maximum)
                .. "；绘制数值：" .. Reading(rendered.value) .. "；圆形进度：" .. Reading(rendered.percent))
        else
            print("游戏绘制状态：无法读取")
        end
        local ok, aura = pcall(TrackedBloodAura)
        if ok and type(aura) == "table" then
            print("暴雪增益监控：已找到；层数"
                .. (type(MaybeNumber(aura.applications)) == "number" and "可读取" or "受限或缺失"))
        else
            print("暴雪增益监控：未找到或读取失败")
        end
        local api = _G.C_UnitAuras
        local directOk, direct = pcall(function()
            return api.GetPlayerAuraBySpellID(463730)
        end)
        print("按编号查询：" .. (directOk and "调用成功" or "调用失败")
            .. "，结果" .. (directOk and type(direct) == "table" and "存在" or "缺失或受限"))
        return
    end
    Report()
end


end
