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

-- 定义一个函数来检查所有姓名板单位的施法状态
function aura_env.CheckCasting()
    -- 初始化变量以存储选中的法术信息
    local selectedSpell = nil -- 表，包含 unit、spellName、spellID、priority
    local interruptNotAvailable = false -- 标识打断法术是否在冷却中

    -- 遍历姓名板 1 到 40
    for i = 1, 40 do
        local unit = "nameplate" .. i
        if UnitExists(unit) and UnitCanAttack("player", unit) then
            -- 检查单位是否正在施法或引导施法
            local castInfo = {}
            local castName, _, _, _, castendTime, _, _, castnotInterruptible, castSpellID = UnitCastingInfo(unit)
            if castName and not castnotInterruptible then
                castInfo = {
                    name = castName,
                    id = castSpellID,
                    type = "施放",
                    endTime = castendTime / 1000 -- 将毫秒转换为秒
                }
                --print(string.format("------单位 %s 正在施放法术: %s (法术ID: %s)------", unit, castName, tostring(castSpellID)))
            end

            local channelName, _, _, _, channelendTime, _, channelnotInterruptible, channelSpellID = UnitChannelInfo(unit)
            if channelName and not channelnotInterruptible then
                castInfo = {
                    name = channelName,
                    id = channelSpellID,
                    type = "引导施法",
                    endTime = channelendTime / 1000 -- 将毫秒转换为秒
                }
                --print(string.format("单位 %s 正在引导施法: %s (法术ID: %s)", unit, channelName, tostring(channelSpellID)))
            end

            -- 如果单位没有施法，继续下一个单位
            if castInfo.id then
                -- 检查法术是否在优先级列表中
                local spellPriority = priorityMap[castInfo.id] or (#priorityList + 1)
                if priorityMap[castInfo.id] then
                    --print(string.format("法术 %s 在优先级列表中的优先级为: %d", castInfo.name, spellPriority))
                    if not selectedSpell or spellPriority < selectedSpell.priority then
                        -- 更新选中的法术为当前单位的法术
                        selectedSpell = {
                            unit = unit,
                            spellName = castInfo.name,
                            spellID = castInfo.id,
                            priority = spellPriority,
                            endTime = castInfo.endTime
                        }
                        --print(string.format("更新为当前最高优先级法术: %s (优先级: %d)", castInfo.name, spellPriority))
                    end
                end
            end
        end
    end

    -- 检查打断法术是否在冷却中
    if selectedSpell then
        for _, interruptSpellID in ipairs(interruptSpells) do
            if IsPlayerSpell(interruptSpellID) then
                local cooldown = C_Spell.GetSpellCooldown(interruptSpellID)
                local cooldownRemaining = cooldown.startTime + cooldown.duration - GetTime()
                if cooldownRemaining > 0 and cooldownRemaining > (selectedSpell.endTime - GetTime()) then
                    interruptNotAvailable = true
                    break
                end
            end
        end

        -- 决定触发哪个法术
        if not interruptNotAvailable or not interruptSpells then
            --print(string.format("触发优先级高的法术：单位 %s, 法术 %s (法术ID: %s)", selectedSpell.unit, selectedSpell.spellName, tostring(selectedSpell.spellID)))
            return true, selectedSpell.unit, selectedSpell.spellName
        else
            --print("打断法术在冷却中")
            return false
        end
    else
        return false
    end
end

-- 写入自定义触发器中，调用检查函数
function()
    local shouldTrigger, unit, spellName = aura_env.CheckCasting()
    local r, g, b, a = unpack(aura_env.config.color)
    --print("颜色为", r, g, b, a)
    if shouldTrigger then
        --print(string.format("触发提示：单位 %s 正在施放 %s", unit, spellName))
        local region = WeakAuras.GetRegion(aura_env.id, unit)
        region:Color(r, g, b, a)
        return true
    else
        return false
    end
end

--战斗日志过滤事件，施法开始，结束，失败事件
CLEU:SPELL_CAST_SUCCESS:SPELL_CAST_START:SPELL_CAST_FAILED:SPELL_INTERRUPT

--目标变化，焦点目标变化，移动，进出战斗，鼠标指向和点击事件
PLAYER_TARGET_CHANGED,PLAYER_STARTED_MOVING,PLAYER_STOPPED_MOVING,PLAYER_REGEN_DISABLED,PLAYER_REGEN_ENABLED,PLAYER_FOCUS_CHANGED,UPDATE_MOUSEOVER_UNIT,GLOBAL_MOUSE_DOWN,GLOBAL_MOUSE_UP

WeakAuras.ScanEvents("HIDE_ON_GROUND", true)

--矶石宝库--
430097,449455,445207
--塞兹仙林的迷雾--
322938,324914,321828,326046,340544,450505,322450
--通灵战潮--
334748,328667,324293,338353,328667,323190
--艾拉-卡拉，回响之城--
432967,434793,434802,448248,433841
--破晨号--
449734,431309,450756,432520
--千丝之城--
443430,443437,452162,446086
--格瑞姆巴托--
451871,76711,451224
--围攻伯拉勒斯--
256957,272571,275826