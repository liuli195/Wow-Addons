--字符串解析函数，解析自定义法术列表字符串
local function ParseSpellIDs(spellString)
    local priorityList = {}
    -- 使用 gmatch 函数遍历字符串中的每个数字部分
    for spellID in string.gmatch(spellString, "%d+") do
        -- 将字符串转换为数字，并插入到数组中
        table.insert(priorityList, tonumber(spellID))
    end
    return priorityList
end

-- 定义法术优先级列表（法术ID 数组，越靠前优先级越高）
local priorityList = ParseSpellIDs(aura_env.config.spellString)

-- 定义打断法术ID列表
local interruptSpells = ParseSpellIDs(aura_env.config.interruptspellString)

-- 将优先级列表转换为优先级映射表，提高查找效率
local priorityMap = {}
for index, spellID in ipairs(priorityList) do
    if not priorityMap[spellID] then
        priorityMap[spellID] = index
    end
end

--定义一个函数来检查所有姓名板单位的施法状态,并更新选择的法术信息
function aura_env.CheckCasting(unit, selectedSpell)
    local castInfo = {}
    if UnitExists(unit) then
        -- 检查单位是否正在施法或引导施法
        local castName, _, _, caststartTime, castendTime, _, _, castnotInterruptible, castSpellID = UnitCastingInfo(unit)
        if castName then
            castInfo = {
                name = castName,
                id = castSpellID,
                type = "cast",
                endTime = castendTime / 1000, -- 将毫秒转换为秒
                startTime = caststartTime / 1000,
                notInterruptible = castnotInterruptible
            }
        end

        local channelName, _, _, channelstartTime, channelendTime, _, channelnotInterruptible, channelSpellID = UnitChannelInfo(unit)
        if channelName then
            castInfo = {
                name = channelName,
                id = channelSpellID,
                type = "channel",
                endTime = channelendTime / 1000, -- 将毫秒转换为秒
                startTime = channelstartTime / 1000,
                notInterruptible = channelnotInterruptible
            }
        end

        -- 如果单位没有施法，继续下一个单位
        if castInfo.id then
            -- 检查法术是否在优先级列表中
            local spellPriority = priorityMap[castInfo.id] or (#priorityList + 1)
            if priorityMap[castInfo.id] then
                if not selectedSpell.unit or spellPriority < selectedSpell.priority then
                    -- 更新选中的法术为当前单位的法术
                    selectedSpell = {
                        unit = unit,
                        spellName = castInfo.name,
                        spellID = castInfo.id,
                        priority = spellPriority,
                        endTime = castInfo.endTime,
                        startTime = castInfo.startTime
                    }
                    return castInfo, selectedSpell
                end
            end
        end
    end
    return castInfo, selectedSpell
end

--定义一个函数来检查打断法术是否在冷却中
function aura_env.CheckCooldown(endTime)
    local interruptNotAvailable = false
    if endTime then
        for _, interruptSpellID in ipairs(interruptSpells) do
            if IsPlayerSpell(interruptSpellID) then
                local cooldown = C_Spell.GetSpellCooldown(interruptSpellID)
                local cooldownRemaining = cooldown.startTime + cooldown.duration - GetTime()
                if cooldownRemaining > 0 and cooldownRemaining > (endTime - GetTime()) then
                    interruptNotAvailable = true
                    break
                end
            end
        end

        -- 决定触发哪个法术
        if not interruptNotAvailable or not interruptSpells then
            return true
        else
            return false
        end
    else
        return false
    end
end

--写入自定义触发器中，进行姓名板染色
function(allstates, ...)
    local selectedSpell = {}

    for i=1 , 40 do
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
        local _, classId = UnitClass(unit)

        --获取仇恨信息
        local isTanking, status, scaledPercentage, rawPercentage, rawThreat = UnitDetailedThreatSituation("player", unit)

        --姓名板是否是目标
        local isSame = UnitIsUnit(unit, "target")

        --获取吸收护盾信息
        local totalAbsorbs = UnitGetTotalAbsorbs(unit)

        --获取施法信息
        local clonecastInfo = {}
        clonecastInfo, selectedSpell = aura_env.CheckCasting(unit, selectedSpell)

        if clonecastInfo and clonecastInfo.id then --如果单位在施法则返回施法信息
            local notcooldown = aura_env.CheckCooldown(clonecastInfo.endTime)
            local duration = clonecastInfo.endTime - clonecastInfo.startTime
            local expirationTime = clonecastInfo.endTime
            local spellName = clonecastInfo.name
            local notInterruptible = clonecastInfo.notInterruptible
            local spellPriority = false
            local type = clonecastInfo.type
            allstates[unit] = {
                progressType = 'timed',
                show = show,
                changed = true,
                duration = duration,
                expirationTime = expirationTime,
                autoHide = true,
                casting = true,
                type = type,
                spellName = spellName,
                notInterruptible = notInterruptible,
                spellPriority = spellPriority,
                notcooldown = notcooldown,
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
        else --否则返回生命值信息
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
                additionalProgress = {
                    {
                        direction = "forward",
                        width = totalAbsorbs,
                        offset = 0
                    }
                }
            }
        end
    end

    local shouldTrigger = aura_env.CheckCooldown(selectedSpell.endTime)

    if shouldTrigger then
        allstates[selectedSpell.unit].spellPriority = true
        allstates[selectedSpell.unit].changed = true
        return true
    end
    return true
end

--自定义变量
{
    additionalProgress = 1,
    value = true,
    total = true,
    casting = 'bool',
    type = 'string',
    spellName = 'string',
    notInterruptible = 'bool',
    spellPriority = 'bool',
    sourceName = 'string',
    notcooldown = 'bool',
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