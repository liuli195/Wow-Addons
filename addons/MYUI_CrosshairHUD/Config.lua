-- 配置模块。
--
-- 数据模型、默认值、读写，以及 EUI 配置页面的构建函数（交给 Core 注册）。
-- 它**不需要知道渲染侧的任何东西**——配置变更的「应用」在 Core。依赖方向是
-- Core → {Config, Elements}，Logic 是唯一叶子。

local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS

NS.Config = NS.Config or {}

-- 待实现（票据 05）：19 项配置的数据模型与默认值、页面构建
