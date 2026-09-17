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

-- 唯一的对外问答：现在该不该显示。
--
-- 降级方向是**认不出来就显示**。理由是降级发生时配置页上那一行很可能同时失效
-- （同一批接口），用户没有任何自救手段；显示至少还能用——「条件不起作用」与
-- 「东西没了」在用户眼里是两码事。
function Visibility.ShouldShow()
    local api = EUI()
    if not (api and api.EvalVisibilityExtended) then
        return true
    end

    -- 判定链尚未接入，见票据 02。
    return true
end

-- 装配接线。幂等：装配入口可以被再走一遍（界面重载等），不能越接越多。
--
-- 漏接的后果是**静默的**——条件永远不生效，而且不报错、不显示异常，看起来只是
-- 「设置好像没用」。所以这条由装配入口的测试盯着。
function Visibility.Install()
    if installed then return end

    local api = EUI()
    if not (api and api.RegisterVisibilityUpdater) then
        -- 没有注册入口就什么都不接：ShouldShow 仍然答「显示」，功能退化为 v1 行为。
        return
    end

    installed = true
    api.RegisterVisibilityUpdater(function()
        -- 判定重算的落点，见票据 02。
    end)
end
