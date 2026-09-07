--玩家单位点击框体
if aura_env.config.hideDefault == true then
    PlayerFrame:Hide()
    PlayerFrame:SetScript("OnEvent", nil)
end

local button

if not PlayerUnitFrame then
    button = CreateFrame("Button", "PlayerUnitFrame", UIParent, "SecureUnitButtonTemplate")
    button:SetSize(107, 107)
    button:SetPoint("CENTER", 0, 0)
    button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    button:SetAttribute("unit", "player")
    button:SetAttribute("type1", "target")
    button:SetAttribute("type2", "togglemenu")
    button:EnableMouse(true)
else
    button = PlayerUnitFrame
end

--目标单位点击框体
if aura_env.config.hideDefault then
    TargetFrame:Hide()
    TargetFrame:SetScript("OnEvent", nil)
    ComboFrame:Hide()
    ComboFrame:SetScript("OnEvent", nil)
end

local button

if not TargetUnitFrame then
    button = CreateFrame("Button", "TargetUnitFrame", UIParent, "SecureUnitButtonTemplate")
    button:SetSize(240, 30)
    button:SetPoint("CENTER", 175, -320)
    button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    button:SetAttribute("unit", "target")
    button:SetAttribute("type1", "target")
    button:SetAttribute("type2", "togglemenu")
    button:EnableMouse(true)
else
    button = TargetUnitFrame
end

--写入动作的初始化自定义中，玩家单位版本，支持Clique点击施法
PlayerFrame:Hide()
PlayerFrame:SetScript("OnEvent", nil)

if not _G[aura_env.id .. "button"] then
    local region = WeakAuras.GetRegion(aura_env.id)
    local f = CreateFrame("Button", aura_env.id .. "button", region, "SecureUnitButtonTemplate")
    f:SetAllPoints(region)
    f:SetAttribute("unit", "player") -- or whatever unit you're making
    RegisterUnitWatch(f)
    f:EnableMouse(true)
    f:RegisterForClicks("AnyDown", "AnyUp")
    if Clique then
        Clique:RegisterFrame(f)
    else
        f:SetAttribute("type1", "target")
        f:SetAttribute("type2", "togglemenu")
    end
    f.unit = 'player'
    f:SetScript("OnEnter", UnitFrame_OnEnter)
    f:SetScript("OnLeave", UnitFrame_OnLeave)
end

--写入动作的初始化自定义中，宠物单位版本，支持Clique点击施法
PetFrame:Hide()
PetFrame:SetScript("OnEvent", nil)

if not _G[aura_env.id .. "button"] then
    local region = WeakAuras.GetRegion(aura_env.id)
    local f = CreateFrame("Button", aura_env.id .. "button", region, "SecureUnitButtonTemplate")
    f:SetAllPoints(region)
    f:SetAttribute("unit", "pet") -- or whatever unit you're making
    f:RegisterForClicks("AnyDown", "AnyUp")
    if Clique then
        --Clique:RegisterFrame(f)
    else
        f:SetAttribute("type1", "target")
        f:SetAttribute("type2", "togglemenu")
    end
    f.unit = 'pet'
    f:SetScript("OnEnter", UnitFrame_OnEnter)
    f:SetScript("OnLeave", UnitFrame_OnLeave)
    f:Show()
end

--写入动作的初始化自定义中，目标单位版本，支持Clique点击施法
TargetFrame:Hide()
TargetFrame:SetScript("OnEvent", nil)
ComboFrame:Hide()
ComboFrame:SetScript("OnEvent", nil)
if not _G[aura_env.id .. "button"] then
    local region = WeakAuras.GetRegion(aura_env.id)
    local f = CreateFrame("Button", aura_env.id .. "button", region, "SecureUnitButtonTemplate")
    f:SetAllPoints(region)
    f:SetAttribute("unit", "target") -- or whatever unit you're making
    RegisterUnitWatch(f)
    f:EnableMouse(true)
    f:RegisterForClicks("AnyDown", "AnyUp")
    if Clique then
        Clique:RegisterFrame(f)
    else
        f:SetAttribute("type1", "target")
        f:SetAttribute("type2", "togglemenu")
    end
    f.unit = 'target'
    f:SetScript("OnEnter", UnitFrame_OnEnter)
    f:SetScript("OnLeave", UnitFrame_OnLeave)
end

-- 老版本
FocusFrame:Hide()
FocusFrame:SetScript("OnEvent", nil)
local f = CreateFrame("Button", "FocusUnitFrame", UIParent, "SecureUnitButtonTemplate")
f:SetAttribute("unit", "Focus") -- or whatever unit you're making
f:SetAllPoints()
f:EnableMouse(true)
f:SetAllPoints(WeakAuras.GetRegion(aura_env.id))
f:RegisterForClicks("LeftButtonUp", "RightButtonUp")
f:SetAttribute("type1", "target")     -- Left click targets unit
f:SetAttribute("type2", "togglemenu") -- Right click opens the context menu
RegisterUnitWatch(f)
f.unit = 'Focus'                      -- or whatever unit you're making
f:SetScript("OnEnter", UnitFrame_OnEnter)
f:SetScript("OnLeave", UnitFrame_OnLeave)

--写入动作的初始化自定义中，目标的目标单位版本，支持Clique点击施法
TargetFrameToT:Hide()
TargetFrameToT:SetScript("OnEvent", nil)

if not _G[aura_env.id .. "button"] then
    local region = WeakAuras.GetRegion(aura_env.id)
    local f = CreateFrame("Button", aura_env.id .. "button", region, "SecureUnitButtonTemplate")
    f:SetAllPoints(region)
    f:SetAttribute("unit", "targettarget") -- or whatever unit you're making
    RegisterUnitWatch(f)
    f:EnableMouse(true)
    f:RegisterForClicks("AnyDown", "AnyUp")
    if Clique then
        Clique:RegisterFrame(f)
    else
        f:SetAttribute("type1", "target")
        f:SetAttribute("type2", "togglemenu")
    end
    f.unit = 'targettarget'
    f:SetScript("OnEnter", UnitFrame_OnEnter)
    f:SetScript("OnLeave", UnitFrame_OnLeave)
end

--写入动作的初始化自定义中，焦点单位版本，改良版
FocusFrame:Hide()
FocusFrame:SetScript("OnEvent", nil)

if not _G[aura_env.id .. "button"] then
    local region = WeakAuras.GetRegion(aura_env.id)
    local f = CreateFrame("Button", aura_env.id .. "button", region, "SecureUnitButtonTemplate")
    f:SetAllPoints(region)
    f:SetAttribute("unit", "focus") -- or whatever unit you're making
    RegisterUnitWatch(f)
    f:EnableMouse(true)
    f:RegisterForClicks("AnyDown", "AnyUp")
    if Clique then
        Clique:RegisterFrame(f)
    else
        f:SetAttribute("type1", "target")
        f:SetAttribute("type2", "togglemenu")
    end
    f.unit = 'focus'
    f:SetScript("OnEnter", UnitFrame_OnEnter)
    f:SetScript("OnLeave", UnitFrame_OnLeave)
end

--隐藏暴雪默认施法条
playerCastingBarFrame:Hide()
playerCastingBarFrame:SetScript("OnEvent", nil)

--隐藏指定的框架
local frame = _G["ElvUF_Pet_HealthBar"]
if frame then
    frame:SetAlpha(0)
end

--自定义动态分组锚点的框架,测试未成功
function(frames, activeRegions)
    for _, regionData in ipairs(activeRegions) do
        local unit = regionData.region.state and regionData.region.state.Unit
        if unit then
            local Pointframe = _G["ElvUF_PartyGroup1UnitButton"..unit:sub(-1).."_HealthBar"]
            if Pointframe then
                frames[Pointframe] = frames[Pointframe] or {}
                tinsert(frames[Pointframe], regionData)
            end
        end
    end
end