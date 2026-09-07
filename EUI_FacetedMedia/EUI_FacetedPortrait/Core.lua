local BAR_KEY = "sm:EUI Faceted Bar"
local BORDER_KEY = "sm:EUI Faceted Border"

local BAR_TEXTURE = "Interface\\AddOns\\SharedMedia_MyMedia\\statusbar\\EUI Faceted Bar.tga"
local MEDIA = "Interface\\AddOns\\EUI_FacetedPortrait\\Media\\"
local POWER_TEXTURE = MEDIA .. "FacetedPowerBar.tga"
local PORTRAIT_MASK = MEDIA .. "FacetedHexPortraitMask.tga"
local PORTRAIT_BORDER = MEDIA .. "FacetedHexPortraitBorder.tga"

local UNITS = {
    "player", "target", "focus", "pet", "targettarget", "focustarget",
    "boss1", "boss2", "boss3", "boss4", "boss5",
}

local unitFrames = EllesmereUI
    and EllesmereUI._ModuleNS
    and EllesmereUI._ModuleNS["EllesmereUIUnitFrames"]

if not unitFrames then return end

local originalPortraitMask = unitFrames.PORTRAIT_MASKS
    and unitFrames.PORTRAIT_MASKS.hexagon

local function GetSettings(unit)
    if unitFrames.UF_GetSettings then
        return unitFrames.UF_GetSettings(unit)
    end
    local profile = unitFrames.db and unitFrames.db.profile
    if not profile then return nil end
    if unit and unit:match("^boss%d$") then return profile.boss end
    return profile[unit]
end

local function GetDonorSettings()
    local profile = unitFrames.db and unitFrames.db.profile
    if not profile then return nil end
    local enabled = profile.enabledFrames or {}
    if enabled.focus ~= false and profile.focus then return profile.focus end
    if enabled.target ~= false and profile.target then return profile.target end
    return profile.player
end

local function EffectiveHealthKey(unit, settings)
    local profile = unitFrames.db and unitFrames.db.profile
    if not settings or not profile then return nil end
    local isMini = unit == "pet" or unit == "targettarget"
        or unit == "focustarget" or (unit and unit:match("^boss%d$"))
    if isMini and unitFrames.ResolveHealthBarTextureKey then
        return unitFrames.ResolveHealthBarTextureKey(settings, GetDonorSettings())
    end
    return settings.healthBarTexture or profile.healthBarTexture or "none"
end

local function IsActive(unit, settings)
    return EffectiveHealthKey(unit, settings) == BAR_KEY
        and settings.borderTexture == BORDER_KEY
end

local function DisablePixelSnap(texture)
    local PP = EllesmereUI and EllesmereUI.PP
    if PP and PP.DisablePixelSnap then
        PP.DisablePixelSnap(texture)
    elseif texture.SetSnapToPixelGrid then
        texture:SetSnapToPixelGrid(false)
        texture:SetTexelSnappingBias(0)
    end
end

local function EnsureBarBorder(frame, bar, key)
    local state = frame._facetedMedia
    if state[key] then return state[key] end

    local border = CreateFrame("Frame", nil, frame)
    border:SetAllPoints(bar)
    border:EnableMouse(false)
    border:SetFrameLevel(bar:GetFrameLevel() + 5)
    if border.SetClipsChildren then border:SetClipsChildren(false) end

    state[key] = border
    return border
end

local function ApplyBarBorder(border, color, alpha)
    EllesmereUI.ApplyBorderStyle(
        border, 1, color.r, color.g, color.b, alpha,
        BORDER_KEY, 5, 5, 0, 0)
    border:Show()
end

local function ReadBackgroundColor(background)
    if background.GetColorTexture then
        local r, g, b, a = background:GetColorTexture()
        if r then return r, g, b, a or 1 end
    end
    local r, g, b, a = background:GetVertexColor()
    return r or 0, g or 0, b or 0, a or 1
end

local function ApplyBarBackground(bar, state, key, texturePath)
    if not (bar and bar.bg) then return end
    local alphaKey = key .. "Alpha"
    local backgroundAlpha = bar.bg:GetAlpha()
    if backgroundAlpha > 0 then state[alphaKey] = backgroundAlpha end
    local r, g, b, a = ReadBackgroundColor(bar.bg)
    if not state[key] then
        state[key] = bar:CreateTexture(nil, "BACKGROUND", nil, -7)
        state[key]:SetAllPoints(bar)
        state[key]:SetTexture(texturePath)
        DisablePixelSnap(state[key])
    end
    state[key]:SetVertexColor(r, g, b, a * (state[alphaKey] or 1))
    state[key]:Show()
    bar.bg:SetAlpha(0)
end

local function RestoreBarBackground(bar, state, key)
    if state[key] then state[key]:Hide() end
    if bar and bar.bg and state[key .. "Alpha"] then
        bar.bg:SetAlpha(state[key .. "Alpha"])
    end
end

local function ApplyPortrait(frame, settings, active)
    local portrait = frame.Portrait and frame.Portrait.backdrop
    if not portrait then return end

    local state = frame._facetedMedia
    local nativeBorder = portrait._shapeBorderTex
    local shape = settings.detachedPortraitShape or "portrait"
    local detached = (settings.portraitStyle or "attached") == "detached"
    local useCustom = active and detached and shape == "hexagon"

    if not useCustom then
        if state.portraitBorder then state.portraitBorder:Hide() end
        if portrait._shapeMask and originalPortraitMask and detached and shape == "hexagon" then
            portrait._shapeMask:ClearAllPoints()
            local PP = EllesmereUI and EllesmereUI.PP
            if (settings.detachedPortraitBorderSize or 7) >= 1 then
                if PP and PP.Point then
                    PP.Point(portrait._shapeMask, "TOPLEFT", portrait, "TOPLEFT", 1, -1)
                    PP.Point(portrait._shapeMask, "BOTTOMRIGHT", portrait, "BOTTOMRIGHT", -1, 1)
                else
                    portrait._shapeMask:SetPoint("TOPLEFT", portrait, "TOPLEFT", 1, -1)
                    portrait._shapeMask:SetPoint("BOTTOMRIGHT", portrait, "BOTTOMRIGHT", -1, 1)
                end
            else
                portrait._shapeMask:SetAllPoints(portrait)
            end
            portrait._shapeMask:SetTexture(
                originalPortraitMask, "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
        end
        if nativeBorder and detached and shape == "hexagon" then nativeBorder:Show() end
        return
    end

    if portrait._shapeMask then
        portrait._shapeMask:ClearAllPoints()
        portrait._shapeMask:SetAllPoints(portrait)
        portrait._shapeMask:SetTexture(
            PORTRAIT_MASK, "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
    end

    local custom = state.portraitBorder
    if not custom then
        custom = portrait:CreateTexture(nil, "OVERLAY", nil, 7)
        custom:SetTexture(PORTRAIT_BORDER)
        custom:SetAllPoints(portrait)
        DisablePixelSnap(custom)
        state.portraitBorder = custom
    end

    if nativeBorder then
        local r, g, b, a = nativeBorder:GetVertexColor()
        custom:SetVertexColor(r or 1, g or 1, b or 1, a or 1)
        nativeBorder:Hide()
    end
    custom:Show()
end

local function Deactivate(frame, settings)
    local state = frame._facetedMedia
    if not state then return end
    state.active = false
    if state.healthBorder then state.healthBorder:Hide() end
    if state.powerBorder then state.powerBorder:Hide() end
    RestoreBarBackground(frame.Health, state, "healthBackground")
    RestoreBarBackground(frame.Power, state, "powerBackground")
    if frame.Power and frame.Power._pbBorder and unitFrames.UpdatePowerBorder then
        unitFrames.UpdatePowerBorder(frame.Power, settings)
    end
    if frame.unifiedBorder and (settings.borderSize or 1) > 0 then
        frame.unifiedBorder:Show()
    end
    ApplyPortrait(frame, settings, false)
end

local function ApplyFrame(frame, unit)
    local health = frame and frame.Health
    local settings = health and GetSettings(unit)
    if not settings then return end

    frame._facetedMedia = frame._facetedMedia or {}
    local state = frame._facetedMedia
    if not IsActive(unit, settings) then
        Deactivate(frame, settings)
        return
    end

    state.active = true
    health:SetStatusBarTexture(BAR_TEXTURE)
    local fill = health:GetStatusBarTexture()
    if fill then
        fill:SetHorizTile(false)
        fill:SetVertTile(false)
        DisablePixelSnap(fill)
    end

    local power = frame.Power
    if power then
        power:SetStatusBarTexture(POWER_TEXTURE)
        local powerFill = power:GetStatusBarTexture()
        if powerFill then
            powerFill:SetHorizTile(false)
            powerFill:SetVertTile(false)
            DisablePixelSnap(powerFill)
        end
    end

    ApplyBarBackground(health, state, "healthBackground", BAR_TEXTURE)
    ApplyBarBackground(power, state, "powerBackground", POWER_TEXTURE)

    local color = settings.borderColor or { r = 1, g = 1, b = 1 }
    local alpha = settings.borderAlpha or 1
    ApplyBarBorder(
        EnsureBarBorder(frame, health, "healthBorder"), color, alpha)
    if power then
        ApplyBarBorder(
            EnsureBarBorder(frame, power, "powerBorder"), color, alpha)
        if power._pbBorder then power._pbBorder:Hide() end
    end

    if frame.unifiedBorder then frame.unifiedBorder:Hide() end
    ApplyPortrait(frame, settings, true)
end

local applying = false
local function ApplyAll()
    if applying then return end
    if InCombatLockdown() then
        unitFrames._facetedApplyAfterCombat = true
        return
    end
    local frames = unitFrames.frames
    if not frames then return end
    applying = true
    for _, unit in ipairs(UNITS) do
        ApplyFrame(frames[unit], unit)
    end
    applying = false
end

local scheduled = false
local function ScheduleApply()
    if scheduled then return end
    scheduled = true
    C_Timer.After(0, function()
        scheduled = false
        ApplyAll()
    end)
end

local function ScheduleAfterReload()
    -- EUI's public ReloadFrames only arms its next-frame throttle. Wait two frames
    -- so the real layout pass finishes before restoring the material geometry.
    C_Timer.After(0, function()
        C_Timer.After(0, ScheduleApply)
    end)
end

local hooked = false
local function Start(attempt)
    attempt = attempt or 0
    if not (unitFrames.frames and unitFrames.db and unitFrames.ReloadFrames) then
        if attempt < 30 then
            C_Timer.After(0.1, function() Start(attempt + 1) end)
        end
        return
    end
    if not hooked then
        hooked = true
        hooksecurefunc(unitFrames, "ReloadFrames", ScheduleAfterReload)
    end
    ApplyAll()
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("PLAYER_TARGET_CHANGED")
events:RegisterEvent("PLAYER_FOCUS_CHANGED")
events:RegisterEvent("UNIT_FACTION")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:RegisterEvent("DISPLAY_SIZE_CHANGED")
events:RegisterEvent("UI_SCALE_CHANGED")
events:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_LOGIN" then
        Start()
    elseif event == "PLAYER_REGEN_ENABLED" and unitFrames._facetedApplyAfterCombat then
        unitFrames._facetedApplyAfterCombat = nil
        ScheduleApply()
    else
        ScheduleApply()
    end
end)
