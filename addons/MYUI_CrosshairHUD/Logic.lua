-- 纯计算模块。
--
-- 加载时**不得触碰任何魔兽接口**——这是它能被仓库 Lua 5.1 测试环境加载的唯一前提，
-- 也是这条文件边界存在的唯一理由：拆的是「纯计算」与「魔兽接口」的边界，不按功能拆。
--
-- 导出走全局表而不是 addon 私有表 vararg：仓库的测试以零参数 loadfile 加载被测文件。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

local Logic = NS.Logic or {}
NS.Logic = Logic

--------------------------------------------------------------------------
-- 几何常量（设计稿坐标系：256×256，圆心 (128,128)，角度为从正东顺时针、y 向下）
--
-- 放在这里作为**纯数据**，渲染侧引用——否则测试得硬编码第二份副本。
--------------------------------------------------------------------------

Logic.RING = {
    radius = 54,
    stroke = 6,
}

-- reverse = 填充从弧的**另一端**开始。
-- 设计稿里两条弧都从靠近 6 点钟那端向上生长：左弧顺时针（角度递增 ✓），
-- 右弧逆时针（角度递减）。右弧的几何跨度是 339° → 441°，逆时针生长意味着
-- 从 441° 那端往回长，所以它必须 reverse。
Logic.ARCS = {
    health = { start = 99,  span = 102 },
    power  = { start = 339, span = 102, reverse = true },
}

Logic.PIPS = { start = 219, step = 18, span = 12, count = 6 }

--------------------------------------------------------------------------
-- 弧线填充换算
--
-- 遮罩是一张左半不透明的半平面图，矩形中心对准圆心。旋转 θ 后不透明区域为
-- 半平面 {p : p·(cosθ, sinθ) < 0}；换算成魔兽角度即 ψ ∈ (θ+90°, θ+270°)。
-- 设计稿的一条从 a 起、顺时针跨 span 度的弧，在魔兽角度里是 [-(a+span), -a]。
-- 取 θ = -a - span·f - 90，则窗口与弧的交集恰好是前 f 段。
--
-- 验证方式见 tests/addons/MYUI_CrosshairHUD/test_logic.py —— 那里用**独立的几何判据**
-- 逐点核对，而不是断言本函数的返回值等于某个数。
--------------------------------------------------------------------------

-- reverse：填充从**另一端**长起。此时切口在 c = start + span - span·f，而遮罩保留的
-- 永远只是切口的某一侧，所以要把遮罩整体再转 180°（保留另一侧），**不是翻转 f**——
-- 翻转 f 会让 f=0 时反而整条弧全亮。
-- 弧线填充曲线的两个端点。
--
-- 「比例 → 角度」对比例是**仿射**映射，两个端点就把它定死了。这一点在受限上下文里
-- 是决定性的：那里血量和符能是秘密值，加法都做不了，比例根本进不了 Lua 参与运算；
-- 唯一的办法是把这条映射做成 Enum.LuaCurveType.Linear 曲线交给引擎端求值
-- （见 Core 的弧线角度那一节）。端点从 MaskAngle 导出，两者不许各写一份。
function Logic.ArcCurvePoints(start, span, reverse)
    return Logic.MaskAngle(start, span, 0, reverse),
           Logic.MaskAngle(start, span, 1, reverse)
end

function Logic.MaskAngle(start, span, f, reverse)
    if reverse then
        return math.rad(-((start + span - span * f) + 180) - 90)
    end
    return math.rad(-(start + span * f) - 90)
end

--------------------------------------------------------------------------
-- 符文充能计算
--
-- GetRuneCooldown 有三个坑，判定顺序必须固定：先判就绪 → 再判返回是否为空 → 最后才做除法。
--   1. 就绪时 start 为 0，先做除法会得到巨大值
--   2. 空转（同时最多 3 个符文在充能，多余的排队）时整次调用什么都不返回
--   3. duration 可能为 0
--------------------------------------------------------------------------

Logic.RUNE_READY      = "ready"
Logic.RUNE_RECHARGING = "recharging"
Logic.RUNE_EMPTY      = "empty"

-- 返回 比例, 状态, 距就绪的秒数。
-- **状态是唯一权威**：调用方一律按状态分支，不要按比例猜。空转时剩余时间为 nil，
-- 绝不用 math.huge —— 它会顺着排序键流进任何比较里。
function Logic.RuneCharge(start, duration, ready, now)
    if ready == true then
        return 1, Logic.RUNE_READY, 0
    end
    if not start or not duration or duration <= 0 then
        return 0, Logic.RUNE_EMPTY, nil
    end

    local frac = (now - start) / duration
    if frac < 0 then frac = 0 elseif frac > 1 then frac = 1 end   -- 时钟抖动与速率突变钳位
    return frac, Logic.RUNE_RECHARGING, start + duration - now
end

--------------------------------------------------------------------------
-- 符文排序
--
-- 三个排序键缺一不可：就绪在前 → 充能中按剩余升序 → **索引决胜**。
-- 丢了第三个键，同剩余时间的符文在 table.sort（非稳定）下会每轮轮流换位，
-- 用户在槽位抖动——而任何单帧断言都测不出来。
-- 索引决胜取降序，与暴雪自家符文框的比较函数一致。
--------------------------------------------------------------------------

local STATE_RANK = {
    [Logic.RUNE_READY]      = 1,
    [Logic.RUNE_RECHARGING] = 2,
    [Logic.RUNE_EMPTY]      = 3,
}

local function RuneLess(a, b)
    local ra = STATE_RANK[a.state] or 9
    local rb = STATE_RANK[b.state] or 9
    if ra ~= rb then return ra < rb end

    if a.state == Logic.RUNE_RECHARGING then
        local ma = a.remaining or math.huge
        local mb = b.remaining or math.huge
        if ma ~= mb then return ma < mb end
    end

    return a.index > b.index
end

-- runes 是形如 { index = n, state = ..., remaining = ... } 的数组，长度 count。
-- 返回 order[槽位] = 符文索引。
function Logic.RuneOrder(runes, count)
    local list = {}
    for i = 1, count do
        list[i] = runes[i]
    end
    table.sort(list, RuneLess)

    local order = {}
    for i = 1, count do
        order[i] = list[i].index
    end
    return order
end
