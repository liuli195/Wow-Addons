# MYUI Crosshair HUD

## Purpose

让玩家不必把视线离开屏幕中心就能读到自己的生命值、能量与职业资源：屏幕中心画出准星、左右两条弧与顶部六个资源格，整个 HUD 等比缩放、在 EllesmereUI 的解锁模式里定位，外观与开关都在 EllesmereUI 的设置面板里配置。首版只面向死亡骑士（六个格子对应六个符文），界面文案不出现任何具体职业名称；两侧数值文字不在首版范围内。

## Requirements

### Requirement: Crosshair HUD draws four elements at the screen centre

系统 MUST 在屏幕中心绘制一组准星 HUD：一个准星、一条生命值弧、一条能量弧与六个职业资源格。使用默认配置时，它 MUST 位于屏幕正中且四个元素全部可见。

#### Scenario: Default first load

- **WHEN** 玩家首次加载插件并使用默认配置
- **THEN** 屏幕中心出现准星、两条弧与六个资源格，位置居中
### Requirement: Health and power arcs fill proportionally from their lower ends

生命值弧 MUST 按当前生命值比例填充，能量弧 MUST 按当前能量比例填充。两条弧 MUST 都从靠近下方的那一端起始，并 MUST 左右镜像地向上增长（一侧顺时针、另一侧逆时针）。填充 MUST NOT 越出弧的两端。

#### Scenario: Health is full

- **WHEN** 玩家满血
- **THEN** 生命值弧整条显示为填充色

#### Scenario: Health drops

- **WHEN** 玩家受到伤害
- **THEN** 被削掉的那一段改为背景色，剩余部分仍从下方那一端起填充

#### Scenario: Power grows and drains

- **WHEN** 玩家获得或消耗能量
- **THEN** 能量弧按比例增减，增长方向与生命值弧左右镜像
### Requirement: Six class resource pips show each resource's charge

系统 MUST 为职业资源绘制六个等间距的格子，每格显示对应那一份资源的充能比例。某份资源已被消耗但尚未开始充能时，它的格子 MUST 整格显示背景色，MUST NOT 显示成接近零的填充比例。

#### Scenario: Resource is ready

- **WHEN** 某份资源已经就绪
- **THEN** 对应格子显示为填满

#### Scenario: Resource is recharging

- **WHEN** 某份资源正在充能
- **THEN** 对应格子按剩余时间的比例部分填充

#### Scenario: Resource has not started charging

- **WHEN** 某份资源已被消耗但排在充能队列之后
- **THEN** 该格整格显示背景色，而不是接近零的填充比例

#### Scenario: More resources are spent than can charge at once

- **WHEN** 玩家一次消耗四个以上资源
- **THEN** 多出来的格子整格显示背景色，界面不报错
### Requirement: Ready class resources gather at one end in a stable order

就绪的资源 MUST 聚在格子序列的同一端，使「还有几个能用」一眼可见。排序 MUST 稳定：剩余时间相同的资源在连续刷新之间 MUST 保持相同次序，槽位 MUST NOT 来回抖动。

#### Scenario: A ready resource is spent

- **WHEN** 玩家消耗其中一份就绪的资源
- **THEN** 其余就绪的资源移动到同一端，被消耗的那一格转为充能中并排在其后

#### Scenario: Two resources share the same remaining time

- **WHEN** 两份资源的剩余时间完全相同
- **THEN** 它们在连续两次刷新之间的先后次序保持不变
### Requirement: Resource values remain correct in restricted contexts

系统 MUST 在副本、PvP 等受限上下文中继续按当前数值显示生命值与能量。系统 MUST NOT 对客户端标记为不可读（秘密）的读数做比较、运算或字符串化；无法确认读数可读时 MUST 跳过本次更新并保留上一次的显示值，「有没有读到」MUST 由另一个普通布尔表示。

#### Scenario: Player enters restricted content

- **WHEN** 玩家进入副本或 PvP 等受限内容
- **THEN** 两条弧仍按当前生命值与能量正确填充

#### Scenario: A reading is marked unreadable

- **WHEN** 客户端把某个读数标记为不可读
- **THEN** 本次更新被跳过、保留上一次的显示值，且不产生 Lua 错误
### Requirement: The master switch and per-element switches control visibility

系统 MUST 提供总开关与四个元素各自的开关；总开关关闭时整个 HUD MUST 不可见，四个元素开关 MUST 置灰不可操作。单个元素关闭时只有该元素消失。总开关关闭后 MUST NOT 在解锁模式里残留可拖动的空框。

#### Scenario: Master switch is turned off

- **WHEN** 玩家关闭总开关
- **THEN** HUD 整体消失，四个元素开关置灰不可点

#### Scenario: A single element is turned off

- **WHEN** 玩家关闭其中某一个元素
- **THEN** 只有该元素消失，其余元素不受影响

#### Scenario: Unlock mode after the master switch is off

- **WHEN** 玩家在总开关关闭后进入解锁模式
- **THEN** 屏幕中心没有可拖动的空框

#### Scenario: Master switch is turned back on

- **WHEN** 玩家重新打开总开关
- **THEN** 各元素按各自的开关恢复显示
### Requirement: The whole HUD scales proportionally within a fixed range

系统 MUST 支持以 0.5–2.0 倍整体等比缩放 HUD。配置页的缩放滑块与解锁模式里的宽度／高度 MUST 读写同一个值，MUST NOT 两处各存一份，也 MUST NOT 允许超出该范围的值生效。

#### Scenario: Slider at both ends

- **WHEN** 玩家把缩放滑块拖到最小或最大
- **THEN** HUD 整体等比变化，位置不走动、画面不发糊

#### Scenario: Size is changed in unlock mode

- **WHEN** 玩家在解锁模式的元素选项面板里改宽度或高度
- **THEN** 配置页的缩放滑块回读同一个值
### Requirement: Each element's fill colour, background colour and opacity are configurable

系统 MUST 让每个元素各自配置填充色与填充透明度、背景色与背景透明度（准星没有背景色）。修改 MUST 立即生效且 MUST NOT 影响其他元素；元素关闭时它自己的控件 MUST 置灰不可点。颜色 MUST 与它自己的透明度显示在同一格内，填充与背景的透明度 MUST 互相独立。

#### Scenario: Fill colour is changed

- **WHEN** 玩家修改某个元素的填充色
- **THEN** 该元素立即变色，其他元素不受影响

#### Scenario: Fill opacity is changed

- **WHEN** 玩家只调整填充透明度
- **THEN** 只有填充部分变透明，背景保持不变，反过来亦然

#### Scenario: Element is disabled

- **WHEN** 玩家关闭某个元素
- **THEN** 该元素的控件置灰不可点
### Requirement: Fill colour can follow the EllesmereUI palette but background colour cannot

填充色 MUST 允许在「自定义颜色」与来源配色之间二选一。来源配色 MUST 只取自 EllesmereUI 统一管理的配色（生命值弧与准星用职业色、能量弧用能量色、职业资源格用职业资源色），MUST NOT 退回暴雪的默认色表。取不到该来源时 MUST 回落到该元素的自定义色，MUST NOT 显示为黑或无色。背景色 MUST 只有自定义颜色，MUST NOT 提供任何来源配色。

#### Scenario: A source palette is selected

- **WHEN** 玩家为某个元素选择来源配色
- **THEN** 该元素的填充色变为 EllesmereUI 中该来源的颜色，并在玩家于 EllesmereUI 里改过该颜色之后跟随变化

#### Scenario: The source palette is unavailable

- **WHEN** EllesmereUI 的配色接口取不到该来源的颜色
- **THEN** 填充色回落到该元素的自定义颜色，不会出现无色或黑块

#### Scenario: Background colour is configured

- **WHEN** 玩家查看任一元素的背景色配置
- **THEN** 背景只有自定义色块与背景透明度，没有来源色块
### Requirement: Palette swatches are selectable but not editable

系统 MUST 复用 EllesmereUI 的颜色控件。来源色块 MUST 只能被选中、MUST NOT 可编辑：点击来源色块 MUST NOT 打开取色器；打开自定义色的取色器后取消 MUST NOT 改变当前的来源选择。

#### Scenario: A palette swatch is clicked

- **WHEN** 玩家点击来源色块
- **THEN** 只是选中该来源，不打开取色器

#### Scenario: The custom colour picker is cancelled

- **WHEN** 玩家打开自定义色的取色器后直接取消
- **THEN** 填充色的来源保持原样
### Requirement: The configuration page lives in the EllesmereUI MYUI group

系统 MUST 在 EllesmereUI 设置面板的 `MYUI` 分组下以「准星HUD」为名占一行，点开即为其配置页。页面 MUST 由 EllesmereUI 的标准控件构建，外观与 EUI 自家页面一致，并按常规、生命值条、能量条、职业资源条、准星五组呈现。该行右侧 MUST 保留电源按钮。

#### Scenario: The page is opened

- **WHEN** 玩家在 EllesmereUI 设置面板里点击「准星HUD」这一行
- **THEN** 打开配置页，页面按五组列出可配置项

#### Scenario: Global search builds the page

- **WHEN** 玩家在 EllesmereUI 的全局搜索里输入关键字
- **THEN** 页面在离屏、无内容头接口的状态下也能被安全构建，不报错
### Requirement: Configuration items occupy half a row and pair left to right

配置项 MUST 按「每项占半格、从左到右成对排列、末行不足时右侧留空」的规则排布。系统 MUST NOT 为了填满而行间挪动配置项，MUST NOT 使用通栏控件代替左右分栏。

#### Scenario: A group has an odd number of items

- **WHEN** 某组的配置项数为奇数
- **THEN** 最后一项独占左侧半格，右侧留空
### Requirement: The HUD is positioned in EllesmereUI's unlock mode

系统 MUST 复用 EllesmereUI 的解锁模式定位：进入解锁模式时出现拖动框、可以拖动，X/Y 微调 MUST 在解锁模式的元素选项面板里提供，配置页 MUST NOT 另设一套位置控件。拖动框 MUST 与 HUD 严格重合；在解锁模式里改宽度或高度时位置 MUST NOT 跳走；退出解锁模式并重载后位置 MUST 保持。元素选项面板里 MUST 提供跳到本插件配置页的入口。

#### Scenario: Entering unlock mode

- **WHEN** 玩家进入 EllesmereUI 的解锁模式
- **THEN** 出现与 HUD 严格重合的拖动框，可以拖动它改变位置

#### Scenario: Size is changed while positioned

- **WHEN** 玩家在解锁模式里改宽度或高度
- **THEN** HUD 按比例缩放，位置不发生跳动

#### Scenario: Position persists

- **WHEN** 玩家拖动后退出解锁模式并重载界面
- **THEN** HUD 仍在拖动后的位置

#### Scenario: Jumping back to the options page

- **WHEN** 玩家在解锁模式的元素选项面板里点击跳转入口
- **THEN** 打开本插件的配置页
### Requirement: The HUD never intercepts mouse input

HUD MUST NOT 启用鼠标交互：落在它覆盖区域内的点击 MUST 穿透到游戏。

#### Scenario: Clicking the screen centre

- **WHEN** 玩家点击 HUD 覆盖的屏幕中心区域
- **THEN** 点击被游戏接收，HUD 不拦截
### Requirement: The HUD re-aligns after UI scale changes

界面缩放发生变化后，系统 MUST 重新对齐并重新做像素吸附，HUD MUST NOT 偏移或发糊。

#### Scenario: UI scale is changed

- **WHEN** 玩家改变界面缩放
- **THEN** HUD 仍在原来的位置，边缘不发糊
### Requirement: The HUD recovers from structural game events

切换专精、改动天赋、死亡与复活、进出副本、登录之后，系统 MUST 重新读取资源并恢复显示，MUST NOT 报错，也 MUST NOT 需要玩家重载界面。

#### Scenario: Spec or talent change

- **WHEN** 玩家切换专精或改动天赋
- **THEN** 显示恢复正常且不报错

#### Scenario: Death and resurrection

- **WHEN** 玩家死亡后复活
- **THEN** 生命值弧恢复正常显示，不报错

#### Scenario: Zone transition

- **WHEN** 玩家进出副本
- **THEN** 三条资源显示正常，不报错
### Requirement: Settings persist in the addon's own storage

配置 MUST 存在插件自己的存档里，MUST NOT 存进 EllesmereUI 的配置档案。重载界面与重新登录后设置 MUST 保留；切换 EllesmereUI 的配置档案 MUST NOT 改变本插件的配置。

#### Scenario: Reload after changing settings

- **WHEN** 玩家改几条配置后重载界面
- **THEN** 设置全部保留

#### Scenario: EllesmereUI profile switch

- **WHEN** 玩家切换 EllesmereUI 的配置档案
- **THEN** 本插件的配置不变
### Requirement: Frame strata is configurable

系统 MUST 提供框架层级配置（低／中／高／对话框，默认中）。在该层级下 HUD MUST 位于所有窗口类界面之下。

#### Scenario: A window is opened over the HUD

- **WHEN** 玩家打开暴雪设置窗口或任意下拉菜单
- **THEN** HUD 显示在它们之下
### Requirement: A diagnostic command reports the environment

系统 MUST 提供一条斜杠命令，打印插件版本、EllesmereUI 与公共核心的就位状态、当前配置摘要、各读数的可读性以及素材目录。该命令 MUST 还能切换假数据驱动，供不在战斗时检查外观。

#### Scenario: The diagnostic command is run

- **WHEN** 玩家执行该斜杠命令
- **THEN** 打印版本、依赖就位状态与读数可读性，且不打印不可读的读数本身

#### Scenario: Fake data drives the HUD

- **WHEN** 玩家用该命令开启假数据驱动
- **THEN** 三条资源按循环变化的比例显示，可以独立检查外观
### Requirement: Shipped textures are used as designed with one added mask

系统 MUST 原样使用设计稿导出的成品纹理：不重新导出、不重切、不改图形。唯一新增的素材 MUST 是用于角度填充的半平面遮罩，它的明暗方向与软边宽度 MUST 与填充换算的约定一致，使缩放到上限时纹理仍不被放大。

#### Scenario: Shipped textures are verified

- **WHEN** 校验随插件发布的纹理
- **THEN** 尺寸与素材规格一致，半平面遮罩的明暗方向与软边宽度符合约定
### Requirement: User-facing text names no specific class

界面文案 MUST 使用与职业无关的名称（生命值条、能量条、职业资源条、准星），MUST NOT 出现任何具体职业名称。

#### Scenario: Configuration page and addon list are read

- **WHEN** 玩家查看配置页与插件说明
- **THEN** 文案里没有任何具体职业名称
