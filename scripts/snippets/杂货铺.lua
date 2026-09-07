--展示2d头像
-- 写入自定义文本中，实现获取玩家2D头像
function ()
    function Portrait()
    -- 获取当前光环的显示区域（Region）
        if aura_env then
            local region = WeakAuras.GetRegion(aura_env.id, aura_env.cloneId)
    -- 检查region和texture是否存在
             if region and region.texture then
            -- 将玩家的肖像设置为纹理
                 SetPortraitTexture(region.texture, aura_env.cloneId)
             end
        end
    end
    local myTimer = C_Timer.NewTicker(0.5, function() Portrait() end, 10)
    return 123
end

--写入动作显示中，实现获取玩家2D头像
    local function Portrait()
    -- 获取当前光环的显示区域（Region）
        if aura_env then
            local region = WeakAuras.GetRegion(aura_env.id, aura_env.cloneId)
    -- 检查region和texture是否存在
            if region and region.texture then
            -- 将玩家的肖像设置为纹理
                SetPortraitTexture(region.texture, aura_env.cloneId)
            end
        end
    end
    local myTimer = C_Timer.NewTicker(0.5, function() Portrait() end, 10)

--写入自定义触发函数中，实现获取玩家2D头像，自定义动作的改进版本
function ()
    --锚点和隐藏elvui的对应框架
    for unit in WA_IterateGroupMembers() do
        if aura_env and unit then
            -- 获取当前光环的显示区域（Region）
            local region = WeakAuras.GetRegion(aura_env.id, unit)
            -- 检查region和texture是否存在
            if region and region.texture then
                --锚点和隐藏elvui的对应框架
                    --local Hideframe = _G["ElvUF_PartyGroup1UnitButton"..unit:sub(-1).."_HealthBar"]
                    --local Pointframe = _G["ElvUF_PartyGroup1UnitButton"..unit:sub(-1)]
                    --if Hideframe and Pointframe then
                    --Hideframe:SetAlpha(0)
                    --region:ClearAllPoints() -- 清除现有锚点
                    --region:SetPoint("CENTER", Pointframe, "CENTER", 0, 0)
                    end
                -- 将玩家的肖像设置为纹理
                SetPortraitTexture(region.texture, unit)
            end
        end
    end
    return true
end

--写入自定义触发函数中，实现获取BOSS 2D头像
function ()
    -- 获取当前光环的显示区域（Region）
    local show = false
    for i=1, 8 do
        local unit = "boss" .. i
        if aura_env and unit then
            local region = WeakAuras.GetRegion(aura_env.id, unit)
    -- 检查region和texture是否存在
            if region and region.texture then
            -- 将玩家的肖像设置为纹理
                SetPortraitTexture(region.texture, unit)
            end
        end
        if UnitExists(unit) then
            show = true
        end
    end
    return show
end

-- 写入自定义触发函数中，实现鼠标指向边框，适用于小队和团队版本
function ()
    -- 获取当前光环的显示区域（Region）
    for unit in WA_IterateGroupMembers() do
        if UnitExists(unit) then
            local region = WeakAuras.GetRegion(aura_env.id, unit)
            if region then
                 if UnitExists("mouseover") and UnitIsUnit("mouseover", unit) then
                    region:SetAlpha(1)
                 else
                    region:SetAlpha(0)
                 end
            end
        end
    end
    return true
end

--写入自定义触发函数中，实现鼠标指向边框，BOSS版本
function ()
    -- 获取当前光环的显示区域（Region）
    for i=1, 8 do
        local unit = "boss" .. i
        if UnitExists(unit) then
            local region = WeakAuras.GetRegion(aura_env.id, unit)
            if region then
                 if UnitExists("mouseover") and UnitIsUnit("mouseover", unit) then
                    region:SetAlpha(1)
                 else
                    region:SetAlpha(0)
                 end
            end
        end
    end
    return true
end

--采用职业染色，目标版本
function()
    local r, g, b = 1, 1, 1
    if UnitIsTapDenied("target") and not UnitPlayerControlled("target") then
        r, g, b = 0.6, 0.6, 0.6
    elseif UnitPlayerControlled("target") then
        local colors = RAID_CLASS_COLORS[select(2, UnitClass("target"))]
        r, g, b = colors.r, colors.g, colors.b
    elseif UnitReaction("target", "player") then
        local colors = FACTION_BAR_COLORS and FACTION_BAR_COLORS[UnitReaction("target", "player")]
        r, g, b = colors.r, colors.g, colors.b
    end
    aura_env.region:Color(r, g, b, 0.8)
    if UnitExists("target") then
        return true
    end
end

--采用职业染色，自动克隆版本（BOSS版本）
function()
    local r, g, b = 1, 1, 1
    for i=1, 8 do
        local unit = "boss" .. i
        local colors = FACTION_BAR_COLORS and FACTION_BAR_COLORS[UnitReaction(unit, "player")]
        r, g, b = colors.r, colors.g, colors.b
        local region = WeakAuras.GetRegion(aura_env.id, unit)
        region:Color(r, g, b, 0.8)
    end
    return true
end

--采用职业染色，玩家框体版本
function()
    local r, g, b = 1, 1, 1
    if  UnitExists("player") then
        local colors = RAID_CLASS_COLORS[select(2, UnitClass("player"))]
        r, g, b = colors.r, colors.g, colors.b
    end
    aura_env.region:Color(r, g, b, 0.8)
    if UnitExists("player") then
        return true
    end
end

--单位分类
function()
    local faction = UnitFactionGroup(aura_env.cloneId)
    local is_player = UnitIsPlayer(aura_env.cloneId)
    local class = UnitClassification(aura_env.cloneId)
    local lvl = UnitLevel(aura_env.cloneId)
    
    if (class == "worldboss") and (lvl ~= -1) then
        return [[Interface\AddOns\Assets\icon_classification_boss]]
        
    elseif ( lvl == -1) then
        return [[Interface\AddOns\Assets\icon_badges_boss]]
        
    elseif (class == "elite") then
        return [[Interface\AddOns\Assets\icon_classification_elite]]
        
        
        
    elseif (class == "normal" and is_player == 0) then
        return [[Interface\AddOns\Assets\icon_classification_generic]]
        
    elseif (class == "rareelite") then
        return [[Interface\AddOns\Assets\icon_classification_rare]]
        
    elseif (class == "rare") then
        return [[Interface\AddOns\Assets\icon_classification_rare]]
        
        
        
    elseif (is_player and faction == "Alliance") then
        region:SetTexture("Interface\\AddOns\\Assets\\icon_badges_alliance")
    elseif (is_player and faction == "Horde") then
        region:SetTexture("Interface\\AddOns\\Assets\\icon_badges_horde")
    else
        return [[]]
    end
end

-- 展示姓名板的单位类型
function ()
    -- 获取当前光环的显示区域（Region）
    for i=1, 40 do
        local unit = "nameplate" .. i
        if UnitExists(unit) then
            local faction = UnitFactionGroup(unit)
            local is_player = UnitIsPlayer(unit)
            local class = UnitClassification(unit)
            local lvl= UnitLevel(unit)
            local region = WeakAuras.GetRegion(aura_env.id, unit)
            if region then
                if (class == "worldboss") and (lvl ~= -1) then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_classification_boss")
                    region:SetAlpha(1)
                elseif ( lvl == -1) then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_badges_boss")
                    region:SetAlpha(1)
                elseif (class == "elite") then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_classification_elite")
                    region:SetAlpha(1)
                elseif (class == "normal" and is_player == 0) then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_classification_generic")
                    region:SetAlpha(1)
                elseif (class == "rareelite") then 
                   region:SetTexture("Interface\\AddOns\\Assets\\icon_classification_rare")
                   region:SetAlpha(1)
                elseif (class == "rare") then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_classification_rare")
                    region:SetAlpha(1)
                elseif (is_player and faction == "Alliance") then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_badges_alliance")
                    region:SetAlpha(1)
                elseif (is_player and faction == "Horde") then
                    region:SetTexture("Interface\\AddOns\\Assets\\icon_badges_horde")
                    region:SetAlpha(1)
                else
                    region:SetAlpha(0)
                end
            end
        end
    end
    return true
end

--宠物团队标记图标
function()
    local raidMarker = GetRaidTargetIndex("pet")
    local region = WeakAuras.GetRegion(aura_env.id, unit)
    if raidMarker then
        if (raidMarker == 1) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconsxinxin.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 2) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconsdabing.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 3) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconslinxin.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 4) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconssanjiao.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 5) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconsyueliang.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 6) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconsfangkuai.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 7) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconschazi.tga")
            region:SetAlpha(1)
        elseif (raidMarker == 8) then
            region:SetTexture("Interface\\AddOns\\Assets\\TargetingIconskulou.tga")
            region:SetAlpha(1)
        else
            region:SetAlpha(0)
        end
    end
    return raidMarker ~= nil
end

--可以点击的按键
local e = aura_env
if not _G[e.id.."Button"] then
local region = WeakAuras.GetRegion(e.id)
e.btn = CreateFrame("Button", e.id.."Button", region, "SecureActionButtonTemplate")
e.btn:RegisterForClicks("LeftButtonUp","LeftButtonDown", "RightButtonUp", "RightButtonDown")
e.btn:SetAttribute("type1","macro")
e.btn:SetAttribute("type2","macro")
e.btn:SetAllPoints(region)
end

local btn = _G[e.id.."Button"]
btn:SetAttribute("macrotext1","/use 13")
btn:SetAttribute("macrotext2","此处替换右键触发的宏命令注意/和空格")
btn:SetScript("OnEnter", function(self)
GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
GameTooltip:SetItemByID(12345) -- 设置物品ID的鼠标提示
GameTooltip:SetText(
"|cffffffff随便填什么\n左：|r|cff00ffff".."随便填什么".."|r\n|cffffffff右：|r|cffff00ff".."随便填什么".."|r")
end)
btn:SetScript("OnLeave", function(self) GameTooltip:Hide() end)
btn:Show()

--监控驭龙术的复苏之风的充能层数
--事件：UNIT_SPELLCAST_SUCCEEDED:player
function()
    local spellinfo = C_Spell.GetSpellCharges(425782)
    aura_env.vigor = spellinfo.maxCharges
    if spellinfo.cooldownStartTime ~= 0 then
        return true
    end
end

--持续时间信息
function()
    return aura_env.vigor.currentCharges, 3, true
end