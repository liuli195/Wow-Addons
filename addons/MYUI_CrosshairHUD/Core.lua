-- 装配模块。
--
-- 事件注册、符文轮询、把游戏数值换算成显示状态、把配置变化应用下去、
-- 以及 EUI 侧边栏与页面的挂载注入。
--
-- 本票（骨架与加载）只提供骨架与一条诊断入口。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

local ADDON = "MYUI_CrosshairHUD"
local MEDIA_ROOT = "Interface\\AddOns\\MYUI\\Media\\CrosshairHUD\\"

local C_AddOns = _G.C_AddOns
local SlashCmdList = assert(rawget(_G, "SlashCmdList"))
local print = _G.print

NS.Core = NS.Core or {}
NS.Core.mediaRoot = MEDIA_ROOT

-- 素材清单：纹理缺失时魔兽**不会报错**，所以这里列出来供人工核对
local MEDIA_FILES = {
    "crosshair.png", "health_arc.png", "power_arc.png", "mask_half.png",
    "resource_01.png", "resource_02.png", "resource_03.png",
    "resource_04.png", "resource_05.png", "resource_06.png",
}

local function Presence(ok)
    return ok and "|cff40c040就位|r" or "|cffff4040缺失|r"
end

local function AddOnLoaded(name)
    return C_AddOns and C_AddOns.IsAddOnLoaded and C_AddOns.IsAddOnLoaded(name) or false
end

local function HasEUI()
    return rawget(_G, "EllesmereUI") ~= nil
end

local function Version()
    if C_AddOns and C_AddOns.GetAddOnMetadata then
        return C_AddOns.GetAddOnMetadata(ADDON, "Version") or "未知"
    end
    return "未知"
end

local function Report()
    print("|cff9fd4ff" .. ADDON .. "|r 诊断：")
    print("  版本：" .. Version())
    print("  EllesmereUI：" .. Presence(HasEUI()))
    print("  MYUI（共享素材）：" .. Presence(AddOnLoaded("MYUI")))
    print("  加载顺序：Logic → Elements → Config → Core，本文件是 Core")
    print("  素材目录（" .. #MEDIA_FILES .. " 个成品，魔兽对缺失纹理不报错，请人工核对）：")
    print("    " .. MEDIA_ROOT)
    for _, name in ipairs(MEDIA_FILES) do
        print("    · " .. name)
    end
end

_G.SLASH_MYUICHH1 = "/chh"
SlashCmdList["MYUICHH"] = function(msg)
    msg = (msg or ""):lower():gsub("%s+", "")
    if msg == "media" then
        print("|cff9fd4ff" .. ADDON .. "|r 素材目录：" .. MEDIA_ROOT)
        for _, name in ipairs(MEDIA_FILES) do
            print("    · " .. name)
        end
        return
    end
    Report()
end

-- 待实现：
--   票据 04 事件与轮询、票据 05 配置应用、票据 07 EUI 挂载与解锁拖动
