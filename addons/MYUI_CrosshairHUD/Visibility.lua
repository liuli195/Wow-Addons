-- 可见性模块：回答「准星 HUD 现在该不该显示」。
--
-- 为什么单独一个文件：这里调用的是 EllesmereUI 的**内部**接口，不是它承诺给第三方的
-- 契约。本项目已有先例——EUI 改版导致三张表改名，所有访问点都得补判空守卫，而且
-- **失效表现是静默的**。把这批调用集中在一个文件里，EUI 改版时只需要翻这一处。
--
-- 对外只有一条问答，且**只返回真布尔**：EUI 的求值结果是四值协议
-- （真／假／悬停／空），其中「悬停」是个真值字符串——任何写成「如果是真」的调用方
-- 都会在悬停模式下静默判错。四值压在这里，调用方永远不需要看见它。
--
-- 依赖方向仍是 Core → Visibility → （EUI）。本文件不碰渲染，也不碰配置数据本身。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

local Visibility = NS.Visibility or {}
NS.Visibility = Visibility

-- 只接一次。放在文件层而不是表里：它是本模块的内部状态，调用方不需要看见。
local installed = false

local function EUI()
    return rawget(_G, "EllesmereUI")
end

-- 每次都现取：配置加载会**替换整个表对象**，缓存引用的人会从此读写一张废表。
local function Cfg()
    local ns = _G.MYUI_CHH
    return ns and ns.Config
end

-- 旧标量兜底要用的状态表。**语义必须与 EUI 的调度器逐条对齐**：
-- 「队伍」排除团队（它内部就是 `IsInGroup() and not inRaid`），交互状态取 EUI 自己的
-- 缓存值而不是 `InCombatLockdown()`——两套谓词混用会让 EUI 的判定与本插件触发的
-- 重算在锁定期窗口里对同一状态给出不同答案。
local function VisibilityState()
    local api = EUI()
    local inRaid = _G.IsInRaid and _G.IsInRaid() or false
    return {
        inCombat = (api and api.IsInCombat and api.IsInCombat()) or false,
        inRaid = inRaid,
        inParty = (_G.IsInGroup and _G.IsInGroup() and not inRaid) or false,
    }
end

-- 唯一的对外问答：现在该不该显示。
--
-- 降级方向是**认不出来就显示**。理由是降级发生时配置页上那一行很可能同时失效
-- （同一批接口），用户没有任何自救手段；显示至少还能用——「条件不起作用」与
-- 「东西没了」在用户眼里是两码事。
function Visibility.ShouldShow()
    -- 「关掉状态」（总开关关、「从不」）排在**降级之前**：它是我们自己存的数据，
    -- 不需要 EUI 就能判，因此接口全没了也照样隐藏。这与「条件判不出来」是两回事
    -- ——后者才走降级。放在这里还有一个好处：这条语义只有 IsOff 一处定义，
    -- 不会在别处再抄一遍。
    if Visibility.IsOff() then
        return false
    end

    local api = EUI()
    if not api then
        return true
    end

    local config = Cfg()
    local settings = config and config.Get and config.Get() or nil

    -- 判定链照 EUI 自家消费者的顺序，**三步缺一不可**（见资源条的 ShouldShowSecondary）：
    --   1. 选项通道的隐藏否决
    --   2. 多选模式集
    --   3. 旧标量兜底
    --
    -- 第 1 步是**独立的一半判定**，漏掉的后果不是报错，而是一整类条件静默地
    -- 什么都不做——「目标」「敌对目标」「骑乘中」「御空术坐骑」「副本」「住宅」
    -- 「休息中」「载具」全都存在选项通道的字段里，不在这条链的第 2 步里。
    -- 实机复现过：勾「敌对目标」毫无反应。
    if api.CheckVisibilityOptions and settings
        and api.CheckVisibilityOptions(settings) then
        return false
    end

    if not api.EvalVisibilityExtended then
        return true
    end

    local verdict = api.EvalVisibilityExtended(settings, "visibility", nil,
        config and config.VIS_CAPS or nil)

    -- 「空」的语义是「回落旧标量逻辑」，**不是**「显示」。
    --
    -- 这条路是**常态而非常态之外的兜底**：EUI 把「只勾了一个条件」直接存进标量
    -- （与旧版单选逐字节一致），共享引擎对这种情况一律交回空，由调用方按标量
    -- 自己判。把它当成「显示」的后果是——只勾「仅战斗中」时整个条件静默失效。
    if verdict == nil then
        -- 标量本身的语义**全归 EUI**：它自己的判定函数就认这几个标量
        -- （never 落到假，always 与 mouseover 都落到真），这里不再各写一份——
        -- 各写一份就会有第二处需要跟着 EUI 同步的副本。
        if api.CheckVisibilityMode then
            local mode = settings and settings.visibility or "always"
            return api.CheckVisibilityMode(mode, VisibilityState()) and true or false
        end
        -- 判定函数也没了：这是「条件判不出来」，走降级（显示）。
        -- 「从不」到不了这里——上面已经由 IsOff 拦掉了。
        return true
    end

    -- 只把「明确的假」判为隐藏。四值协议里的「悬停」是真值字符串，若写成
    -- 「如果是真」会在悬停模式下静默判错；本版不启用悬停，所以它落到显示侧。
    return verdict ~= false
end

-- 「这东西不该存在」——与「现在不满足条件」相对。
--
-- 解锁模式的让路规则要靠它把两类分开：条件隐藏是**活的**，编辑时该让你调得到；
-- 而总开关关着、或选了「从不」，是「这东西本就不该有」，那时冒出一个能拖的空框
-- 只会让人对着不存在的东西拖。
function Visibility.IsOff()
    local config = Cfg()
    local settings = config and config.Get and config.Get() or nil
    if not settings then return false end
    if settings.enabled == false then return true end
    if settings.visibility == "never" then return true end
    return false
end

-- 装配接线。幂等：装配入口可以被再走一遍（界面重载等），不能越接越多。
--
-- 漏接的后果是**静默的**——条件永远不生效，而且不报错、不显示异常，看起来只是
-- 「设置好像没用」。所以这条由装配入口的测试盯着。
function Visibility.Install(onChange)
    if installed then return end

    local api = EUI()
    if not (api and api.RegisterVisibilityUpdater) then
        -- 没有注册入口就什么都不接：ShouldShow 仍然答「显示」，功能退化为 v1 行为。
        return
    end

    installed = true
    api.RegisterVisibilityUpdater(function()
        if onChange then onChange() end
    end)
end
