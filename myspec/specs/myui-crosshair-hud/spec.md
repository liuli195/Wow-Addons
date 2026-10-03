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

系统 MUST 在受限场景中将客户端允许用于显示的生命值和能量读数交给游戏绘制，MUST NOT 对不可读数值做普通比较、运算或转成文本。接口调用失败时 MUST 保留最近一次成功显示的生命值和能量状态；凝固之血层数 MUST 由游戏直接管理和绘制，不由插件反向读取。

#### Scenario: Restricted display

- **WHEN** 生命值或能量读数受限但游戏显示接口调用成功
- **THEN** 对应弧线继续由游戏按当前读数绘制，不产生非法数值运算

#### Scenario: Reading call fails

- **WHEN** 生命值或能量接口调用失败
- **THEN** 保留最近一次成功显示状态，不猜测当前数值

#### Scenario: Buff stacks are restricted

- **WHEN** 凝固之血层数对插件不可读
- **THEN** 层数仍由游戏绑定到新条，不把受限值打印到报告
### Requirement: The master switch and per-element switches control visibility

系统 MUST 提供总开关、四个基础元素开关以及凝固之血和灵打消耗刻度的独立开关。总开关关闭时整个 HUD MUST 隐藏，相关配置（含阴影、可见性和三个齿轮）MUST 置灰不可操作，MUST NOT 残留可拖动的空框。单项开关关闭时该项 MUST 隐藏，其控件和齿轮 MUST 禁用；重新打开 MUST 恢复可操作状态，MUST NOT 自动打开齿轮弹窗。

#### Scenario: Master off

- **WHEN** 关闭准星 HUD 总开关
- **THEN** 整组隐藏，所有从属配置禁用，解锁模式也没有空框

#### Scenario: Feature off and on

- **WHEN** 关闭后重新开启凝固之血或灵打消耗刻度
- **THEN** 该项按开关隐藏或恢复，自己的齿轮同步禁用或启用，但弹窗不会自动打开
### Requirement: The whole HUD scales proportionally within a fixed range

系统 MUST 支持以 0.5–2.0 倍整体等比缩放 HUD。配置页的缩放滑块与解锁模式里的宽度／高度 MUST 读写同一个值，MUST NOT 两处各存一份，也 MUST NOT 允许超出该范围的值生效。

#### Scenario: Slider at both ends

- **WHEN** 玩家把缩放滑块拖到最小或最大
- **THEN** HUD 整体等比变化，位置不走动、画面不发糊

#### Scenario: Size is changed in unlock mode

- **WHEN** 玩家在解锁模式的元素选项面板里改宽度或高度
- **THEN** 配置页的缩放滑块回读同一个值
### Requirement: Each element's fill colour, background colour and opacity are configurable

系统 MUST 让各组成项独立配置填充颜色与透明度；血条、能量条、职业资源和凝固之血 MUST 另有独立背景颜色与透明度，准星和灵打刻度没有背景。修改 MUST 立即生效，不影响其他项；颜色及其透明度 MUST 同格显示，填充和背景的透明度互相独立。对应开关或总开关关闭时相关控件 MUST 禁用。

#### Scenario: Independent appearance

- **WHEN** 只调整某项填充或背景颜色与透明度
- **THEN** 仅对应图层变化，其他项与另一图层不受影响

#### Scenario: Feature disabled

- **WHEN** 关闭对应开关或总开关
- **THEN** 该项外观控件置灰不可操作
### Requirement: Fill colour can follow the EllesmereUI palette but background colour cannot

四个基础元素的填充色 MUST 可选自定义或 EllesmereUI 的来源配色：生命值和准星用职业色、能量条用能量色、职业资源用资源色。来源不可用时 MUST 回落到该项自定义色，不退回暴雪色表或显示成黑块。背景 MUST 只有自定义颜色；凝固之血和灵打刻度填充也 MUST 只有自定义颜色，不提供职业色选择。

#### Scenario: Source palette

- **WHEN** 基础元素选择来源配色且共享配色变化
- **THEN** 填充颜色跟随对应共享配色

#### Scenario: Unavailable palette

- **WHEN** 取不到所选来源配色
- **THEN** 使用该项自定义色

#### Scenario: Custom only

- **WHEN** 查看背景、凝固之血或灵打刻度颜色配置
- **THEN** 只有自定义颜色，不显示来源色选项
### Requirement: Palette swatches are selectable but not editable

系统 MUST 复用 EllesmereUI 的颜色控件。来源色块 MUST 只能被选中、MUST NOT 可编辑：点击来源色块 MUST NOT 打开取色器；打开自定义色的取色器后取消 MUST NOT 改变当前的来源选择。

#### Scenario: A palette swatch is clicked

- **WHEN** 玩家点击来源色块
- **THEN** 只是选中该来源，不打开取色器

#### Scenario: The custom colour picker is cancelled

- **WHEN** 玩家打开自定义色的取色器后直接取消
- **THEN** 填充色的来源保持原样
### Requirement: The configuration page lives in the EllesmereUI MYUI group

系统 MUST 在 EllesmereUI 设置面板的 MYUI 分组下提供“准星HUD”配置页，保留该行右侧电源按钮，复用现有标准控件。页面 MUST 包含常规、生命值条、能量条、职业资源条、准星、凝固之血和灵打消耗刻度分组，MUST NOT 为新增功能另建设置菜单。

#### Scenario: Open options

- **WHEN** 玩家从 MYUI 分组打开准星HUD
- **THEN** 同一配置页列出上述七组设置

#### Scenario: Global search

- **WHEN** 共享搜索在离屏状态构建配置页
- **THEN** 配置页能安全构建，不因缺少内容头接口报错
### Requirement: Configuration items occupy half a row and pair left to right

配置项 MUST 按「每项占半格、从左到右成对排列、末行不足时右侧留空」的规则排布。系统 MUST NOT 为了填满而行间挪动配置项，MUST NOT 使用通栏控件代替左右分栏。

#### Scenario: A group has an odd number of items

- **WHEN** 某组的配置项数为奇数
- **THEN** 最后一项独占左侧半格，右侧留空
### Requirement: The HUD is positioned in EllesmereUI's unlock mode

系统 MUST 复用 EllesmereUI 的解锁模式定位：进入解锁模式时出现拖动框、可以拖动，X/Y 微调 MUST 在解锁模式的元素选项面板里提供，配置页 MUST NOT 另设一套位置控件。拖动框 MUST 与 HUD 的**元素本体**严格重合：看得见的内容（不透明度不低于 12%）MUST NOT 伸出框外。柔化阴影那圈极淡的尾巴 MAY 伸出框外，但 MUST NOT 超过 4 个设计稿单位——阴影本就比元素大一圈，把它裁到框边会切出一条硬边，反而丢掉分离度。在解锁模式里改宽度或高度时位置 MUST NOT 跳走；退出解锁模式并重载后位置 MUST 保持。元素选项面板里 MUST 提供跳到本插件配置页的入口。

#### Scenario: Entering unlock mode

- **WHEN** 玩家进入 EllesmereUI 的解锁模式
- **THEN** 出现与 HUD 元素本体严格重合的拖动框，可以拖动它改变位置

#### Scenario: Shadow tail at the drag box edge

- **WHEN** 校验元素贴图相对拖动框的范围
- **THEN** 看得见的部分（不透明度 ≥12%）全在框内，整条阴影尾巴伸出框外的距离不超过 4 个设计稿单位

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

正式插件 MUST 保留手动诊断命令 /chh diag（/chh report 也可），默认不运行诊断。调用后 MUST 打开可全选复制的文本窗口，报告插件及游戏版本、依赖状态、配置摘要、最近读数状态和凝固之血绑定状态。聊天 MUST 仅显示短提示，MUST NOT 自动发送报告。报告 MUST NOT 包含账号、角色名、聊天、本机路径、原始错误文本或受限数值。正式包 MUST NOT 提供假数据演示及独立测试工具。

#### Scenario: Manual report

- **WHEN** 玩家执行诊断命令
- **THEN** 出现可复制报告窗口，不向聊天发送详细报告

#### Scenario: Restricted reading in report

- **WHEN** 某个读数不可读或尚未取得
- **THEN** 报告仅说明状态，不把该值转成文本

#### Scenario: Normal gameplay

- **WHEN** 玩家未执行诊断命令
- **THEN** 不自动创建报告、持续日志或发送诊断内容
### Requirement: Shipped textures are used as designed with one added mask

正式游戏素材 MUST 保留确认设计的轮廓、位置及独立透明度，长宽各自 MUST 为 2 的幂，MUST 包含从最大尺寸逐级减半到 1×1 的完整缩小图层，并使用平滑采样。主体、背景、阴影、刻度和遮罩 MUST 遵循同一素材格式标准。血条、能量条和职业资源格 MUST 使用统一的柔和填充切口；凝固之血 MUST 使用游戏原生圆弧填充，其移动切口的处理与旋转遮罩不同，MUST NOT 宣称两者完全相同。正式成品 MUST 经过尺寸、透明度和各级缩小图层检查；仅凭本机检查 MUST NOT 宣称所有屏幕分辨率都已验收。

#### Scenario: Validate game assets

- **WHEN** 检查正式游戏素材
- **THEN** 主体和配套素材均符合统一格式，缺少缩小图层或尺寸不合要求时检查失败

#### Scenario: Scale the HUD

- **WHEN** 玩家在允许范围内放大或缩小 HUD
- **THEN** 所有素材随整体缩放，并使用其对应平滑采样

#### Scenario: Compare fill edges

- **WHEN** 观察血条、能量条及职业资源的移动填充切口
- **THEN** 这三类采用同一柔化规格；凝固之血原生填充单独核对
### Requirement: User-facing text names no specific class

基础元素界面文案 MUST 使用生命值条、能量条、职业资源条、准星等名称。新增职业相关功能的说明 MAY 明确适用职业；凝固之血配置在非死亡骑士时 MUST 置灰，MUST NOT 为保持旧的无职业文案而省略禁用原因。

#### Scenario: Read basic labels

- **WHEN** 查看基础元素设置
- **THEN** 保留原有通用名称

#### Scenario: Non death knight settings

- **WHEN** 非死亡骑士查看凝固之血设置
- **THEN** 设置置灰，说明清楚告知该设置仅供死亡骑士使用
### Requirement: Visibility conditions decide when the HUD appears

系统 MUST 遵循 EllesmereUI 共享可见性系统给出的判定，决定**整条**准星 HUD 是否出现——判定针对整条 HUD，各元素的取舍由元素开关负责，两者是相互独立的两个维度。可选条件 MUST 覆盖该共享系统提供的全部条件（从不、总是、战斗中、脱战、团队、队伍、单人、御空术空中、非御空术空中、御空术坐骑、副本、住宅、骑乘中、目标、敌对目标、休息中、载具），MUST 支持「全部满足／任一满足」两种匹配模式，并 MUST 支持「显示」与「隐藏」两条通道。MUST NOT 提供鼠标悬停条件：共享悬停机制会在光标进入时对元素打开鼠标交互，与《The HUD never intercepts mouse input》相抵触。系统 MUST 在设置面板的常规分区提供一行可见性控件，MUST 紧随总开关之后，且 MUST 与其他配置项一样以「每行两项」的方式参与排布。总开关关闭时，该控件 MUST 置灰不可操作。当共享系统的接口不可用或返回值不可识别时，HUD MUST 保持可见，MUST NOT 因此消失。

#### Scenario: A single condition is set

- **WHEN** 玩家把可见性设为「战斗中」并脱离战斗
- **THEN** HUD 消失
- **AND** 重新进入战斗后 HUD 出现

#### Scenario: Several conditions are combined

- **WHEN** 玩家同时勾选多个条件并切换「全部满足」与「任一满足」
- **THEN** HUD 的显示与否随各条件对应的游戏状态按所选匹配模式变化

#### Scenario: An option-lane condition is set

- **WHEN** 玩家勾选涉及目标、骑乘、副本、住宅、休息或载具的条件
- **THEN** HUD 按该条件对应的游戏状态显示或隐藏

#### Scenario: A hide condition overrides a passing show condition

- **WHEN** 玩家同时勾选了一个已经满足的显示条件与一个已满足的隐藏条件
- **THEN** HUD 隐藏

#### Scenario: The master switch is turned off while a condition is set

- **WHEN** 玩家在设定了可见性条件之后关闭总开关
- **THEN** HUD 消失，且可见性控件置灰不可操作

#### Scenario: The visibility control is placed next to the master switch

- **WHEN** 玩家打开设置面板的常规分区
- **THEN** 可见性控件出现在总开关右边那一格

#### Scenario: Unlock mode while a condition currently fails

- **WHEN** 玩家把可见性设为「战斗中」，在非战斗状态下进入解锁模式
- **THEN** 屏幕中心出现可拖动的框

#### Scenario: Unlock mode while the HUD is turned off

- **WHEN** 玩家关闭总开关，或在可见性里选择「从不」，然后进入解锁模式
- **THEN** 屏幕中心没有可拖动的空框

#### Scenario: Upgrading from a save without visibility settings

- **WHEN** 既有玩家升级后首次进入游戏，且从未设置过可见性
- **THEN** HUD 的显示与升级前完全一致

#### Scenario: The shared visibility interfaces cannot be recognised

- **WHEN** 共享可见性接口缺失，或其返回值不可识别
- **THEN** HUD 保持可见且不报错
### Requirement: Every element carries a soft shadow beneath its base image

四个原有基础元素 MUST 在底图之下保留轮廓外围的柔和阴影。主体覆盖区域 MUST 透明，背景调为透明后阴影 MUST NOT 成为一整块背景。阴影 MUST 不随填充比例变化，MUST 与对应元素一起缩放、受整体图层控制且不拦截鼠标。凝固之血和灵打消耗刻度 MUST NOT 绘制阴影。

#### Scenario: Transparent background

- **WHEN** 将血条、能量条或职业资源背景调为透明
- **THEN** 能透过主体区域看到游戏，只在轮廓周边保留阴影

#### Scenario: Empty and scaled

- **WHEN** 基础元素没有填充或 HUD 整体缩放
- **THEN** 外围阴影仍随对应轮廓保持位置

#### Scenario: Additional features

- **WHEN** 凝固之血条或灵打刻度显示
- **THEN** 新增两项没有阴影
### Requirement: Shadow colour and opacity are one global setting

所有原有阴影 MUST 共用一处自定义颜色和浓淡设置，不提供独立阴影配置。浓淡 MUST 可在 0–100% 调整，默认 MUST 为黑色、80%。设为 0 MUST 隐藏阴影但不改变主体。总开关关闭时阴影控件 MUST 禁用且不允许写入设置。

#### Scenario: Change shared shadow

- **WHEN** 修改阴影颜色或浓淡
- **THEN** 所有原有阴影同步变化，主体颜色不变

#### Scenario: Opacity endpoints

- **WHEN** 将阴影浓淡设为 0 或 100%
- **THEN** 分别完全隐藏阴影或使用最大浓淡，默认80%不是上限

#### Scenario: Master switch off

- **WHEN** 关闭总开关后操作阴影控件或已有取色窗口
- **THEN** 控件禁用，回调也不改变阴影设置
### Requirement: The crosshair carries a centre dot

准星 MUST 在正中带一个白点（中心定位点），它的直径 MUST 与设计稿一致。它是**准星的一部分**：MUST NOT 单独成元素，MUST NOT 有单独的开关；显示、隐藏与染色 MUST 都跟着准星走。

#### Scenario: Crosshair is hidden

- **WHEN** 玩家关掉准星
- **THEN** 中心定位点一并消失

#### Scenario: Crosshair is recoloured

- **WHEN** 玩家给准星改颜色
- **THEN** 中心定位点跟着变成同一个颜色

#### Scenario: Crosshair texture is verified

- **WHEN** 校验准星贴图
- **THEN** 正中有一个直径与设计稿一致的白点
### Requirement: The HUD keeps its own reading chain while the player is disconnected

玩家断线期间，系统 MUST 继续按既有读数链显示当下的读数，MUST NOT 改用"填满并置灰"这类原生断线表现。断线 MUST NOT 让 HUD 报错或停止响应；重新连上之后，两条弧 MUST 恢复正常跟随生命值与能量的变化。

#### Scenario: Player disconnects

- **WHEN** 玩家断线
- **THEN** 生命值弧与能量弧保持显示读数链当下的比例，既不被填满也不变灰

#### Scenario: Player reconnects

- **WHEN** 玩家重新连上
- **THEN** 两条弧恢复跟随生命值与能量的变化，且全程不报错
### Requirement: Coagulated Blood displays raw stacks independently of the default buff viewer

凝固之血条 MUST 仅显示玩家自身法术 463730 的原始增益层数，不换算预计回血量。它 MUST 有独立开关；关闭或没有该增益时背景和填充全部隐藏。开启时 MUST 不按专精限制，且 MUST 不依赖暴雪默认增益监控是否开启，不显示额外增益图标。最大显示层数 MUST 可配置，默认100；达到或超过该量程显示满条，该值 MUST NOT 被称为技能真实上限。临时绑定失败 MUST 隐藏新条并自动重试恢复，不要求用户修改配置或重载。

#### Scenario: Viewer disabled

- **WHEN** 关闭暴雪默认增益监控，同时开启新条且身上存在463730
- **THEN** 独立新条仍按游戏管理的层数显示

#### Scenario: No buff or disabled

- **WHEN** 增益消失或关闭新条开关
- **THEN** 新条背景和填充均隐藏

#### Scenario: Display range

- **WHEN** 最大显示层数为100且实际层数为25、50或至少100
- **THEN** 分别显示约四分之一、二分之一或满条，不表示回血百分比

#### Scenario: Binding recovers

- **WHEN** 原生绑定临时失败后接口恢复可用
- **THEN** 新条自动恢复绑定，无需改变配置
### Requirement: Coagulated Blood keeps the approved full arc and independent colours

凝固之血条 MUST 使用已确认的完整圆弧，与血条同圆心、同起止角及对应填充方向，主体粗细为血条的一半。位置 MUST 固定在已确认的血条边界处，并随整体缩放，不提供独立位置或缩放。背景和填充 MUST 为分开的图层，颜色及透明度分别可配置，填充默认白色、100%，背景默认深灰、0%。

#### Scenario: Full buff arc

- **WHEN** 新条显示满条
- **THEN** 覆盖与血条相同的完整起止角，主体仍为半粗

#### Scenario: Change colour

- **WHEN** 仅修改新条背景或填充颜色及透明度
- **THEN** 只改变对应图层，不影响血条或另一个图层
### Requirement: Death Strike cost marker follows current cost and power capacity

灵打消耗刻度 MUST 有独立开关，关闭时始终隐藏。开启时 MUST 根据当前实际灵界打击所需最低符能与当前最大符能的比例，沿能量条填充方向确定位置，不固定费用或上限。刻度 MUST 为始终指向共同圆心的单根直线，平头，两端略超出能量条；位置变化时方向同时旋转。粗细、颜色及透明度 MUST 可配置，默认粗细2、白色、100%。费用或上限不可用或受限时 MUST 隐藏刻度，恢复后重新显示。

#### Scenario: Cost changes

- **WHEN** 灵界打击费用或最大符能变化且数值可用
- **THEN** 刻度位置和朝向随当前比例变化

#### Scenario: Marker disabled

- **WHEN** 关闭灵打消耗刻度
- **THEN** 刻度始终隐藏，包括解锁显示状态

#### Scenario: Unavailable cost

- **WHEN** 无法取得可用费用或符能上限
- **THEN** 隐藏刻度，恢复后重新显示，不猜测位置
### Requirement: New installations use the confirmed HUD defaults without replacing saved settings

新安装 MUST 默认位置居中、可见性总是显示且没有隐藏条件；整体缩放0.8、图层中、所有组成项开启。血条默认职业色、能量条默认能量色、职业资源默认资源色，准星及新增两项默认白色，填充浓淡100%。基础条背景 MUST 为深灰#313131、100%，凝固之血背景0%；阴影黑色80%、最大显示层数100、刻度粗细2。已有设置 MUST 保留，升级只补缺失默认项，不覆盖用户的位置、可见性或配色。

#### Scenario: Fresh installation

- **WHEN** 没有插件存档时首次加载
- **THEN** 使用上述默认值，位置居中，总是显示且没有勾选隐藏条件

#### Scenario: Upgrade existing save

- **WHEN** 已有个人设置时更新插件
- **THEN** 原配置保留，缺失项才补默认值
### Requirement: Three inline gears collect secondary settings and follow their switches

设置页 MUST 在总开关、凝固之血启用、灵打刻度启用旁各提供一个现有界面风格的齿轮。三个齿轮 MUST 分别收纳图层与HUD缩放、最大显示层数、粗细，不再为这些次要项占独立页面格。说明 MUST 各自对应并用大白话解释；总开关或该功能开关关闭时相关齿轮及弹窗控件 MUST 置灰不可操作，重新开启仅恢复可点击，不自动展开。

#### Scenario: Gear contents

- **WHEN** 分别点击三个可用齿轮
- **THEN** 看到对应的图层与缩放、最大显示层数或刻度粗细

#### Scenario: Gear disabled

- **WHEN** 总开关或对应功能开关关闭
- **THEN** 相应齿轮禁用，说明准确且不串用另一个功能的说明
### Requirement: The standard material workflow preserves source exports and verifies game outputs

仓库素材生产流程 MUST 保留设计原图与10倍透明导出图，并从导出图统一生成游戏成品及缩小图层。新增准星HUD素材 MUST 进入同一生产和检查流程，不临时替换原有组件参数。正式游戏素材 MUST 使用支持完整缩小图层的BLP格式，长宽各为2的幂，白色可染色模板与独立透明度保持一致；核对用PNG与源图 MUST 留在仓库，不随正式包部署。

#### Scenario: Add new media

- **WHEN** 制作或更新准星 HUD 素材
- **THEN** 保留源图，按同一流程生成并检查成品

#### Scenario: Reject nonstandard media

- **WHEN** 成品尺寸、透明度或缩小图层不符合标准
- **THEN** 素材检查失败，不以成功生成文件代替校验
### Requirement: Production packages contain only runtime files and deploy with verified backups

正式包 MUST 只包含最小运行代码、所需公共核心和已确认游戏素材，保留手动诊断，排除假数据、额外对照素材、独立测试插件及旧开发命令，仓库源码可保留。部署 MUST 先在游戏目录外备份本次准确修改范围并逐文件核对，再更新运行文件；备份 MUST 区分旧安装版本与新目标版本，旧版本未知时如实标注。部署 MUST 不修改WTF个人设置或无关插件文件，MUST 拒绝指向个人设置目录的部署目标。

#### Scenario: Build release

- **WHEN** 打包正式插件
- **THEN** 包内只有白名单运行文件和游戏素材，不含测试内容

#### Scenario: Deploy validated package

- **WHEN** 部署通过检查的正式包
- **THEN** 先完成备份和核对，再替换准确范围，个人设置与其他文件保持不变

#### Scenario: Invalid input

- **WHEN** 包校验失败、备份核对失败或目标位于个人设置目录
- **THEN** 停止部署，不清理现有游戏文件
