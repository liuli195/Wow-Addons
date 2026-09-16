-- 渲染模块。
--
-- 持有全部纹理对象与遮罩，**不读配置、不读游戏数据**。
-- 对外只接受一张「显示状态表」：由 Core 从「配置 + 游戏读数」算好后整表下发。
-- 状态表必须显式携带 state（ready / recharging / empty）——空转态要求完全隐藏填充纹理，
-- 不是把比例设成 0。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

NS.Elements = NS.Elements or {}

-- 待实现（票据 03）：容器与帧层级、遮罩、两条弧、6 个符文格、准星
