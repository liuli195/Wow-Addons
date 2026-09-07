--姓名板染色
function(allstates, ...)
--local nameplates = C_NamePlate.GetNamePlates()
--if nameplates then
--for _, nameplate in ipairs(nameplates) do

for i=1 , 40 do
    --local unit = nameplate.namePlateUnitToken
    local unit = "nameplate" .. i
    local show = true

    if UnitExists(unit) then
        show = true
    else
        show = false
    end

    --获取反应状态
    local reaction = UnitReaction(unit, "player")
    local colorcalss = 0

     if UnitIsTapDenied(unit) and not UnitPlayerControlled(unit) then
            colorcalss = 1
        elseif UnitPlayerControlled(unit) then
            colorcalss = 2
        elseif UnitReaction(unit, "player") then
            colorcalss = 3
        end

     --获取生命信息
     local max_hp = UnitHealthMax(unit)
     local current_hp = UnitHealth(unit)
     local php = current_hp/max_hp*100

     --获取职业信息
     local className, classId = UnitClass(unit)

     --获取仇恨信息
     local isTanking, status, scaledPercentage, rawPercentage, rawThreat = UnitDetailedThreatSituation("player", unit)

     --姓名板是否是目标
     local isSame = UnitIsUnit(unit, "target")

     allstates[unit] = {
        progressType = 'static',
        show = show,
        changed = true,
        value = current_hp,
        total = max_hp,
        php = php,
        colorcalss = colorcalss,
        reaction = reaction,
        classId = classId,
        isTanking = isTanking,
        status = status,
        scaledPercentage = scaledPercentage,
        rawPercentage = rawPercentage,
        rawThreat = rawThreat,
        isSame = isSame,
        unit = unit,
    }
end
--end
return true
end

--自定义变量
{
    value = true,
    total = true,
    php = 'number',
    colorcalss = 'number',
    reaction = 'number',
    classId = 'string',
    isTanking = 'bool',
    status = 'number',
    scaledPercentage = 'number',
    rawPercentage = 'number',
    rawThreat = 'number',
    isSame = 'bool',
}

--放到自定义文本中，目前无法和默认条件协同工作
function()  
     local r, g, b = 1, 1, 1
     if UnitIsTapDenied(aura_env.cloneId) and not UnitPlayerControlled(aura_env.cloneId) then
         r, g, b = 0.6, 0.6, 0.6
        elseif UnitPlayerControlled(aura_env.cloneId) then
            local colors = RAID_CLASS_COLORS[select(2, UnitClass(aura_env.cloneId))]
            r, g, b = colors.r, colors.g, colors.b
        elseif UnitReaction(aura_env.cloneId, "player") then
            local colors = FACTION_BAR_COLORS and FACTION_BAR_COLORS[UnitReaction(aura_env.cloneId, "player")]
            r, g, b = colors.r, colors.g, colors.b
     end

     local region = WeakAuras.GetRegion(aura_env.id, aura_env.cloneId)

     if region then
     region:Color(r, g, b, 0.8)
     end
   --if UnitExists(aura_env.cloneId) then
       --return true
   --end
   return r..g..b
end

--姓名板鼠标指向发光,改进版本
function()
    for i=1, 40 do
        local unit = "nameplate" .. i
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