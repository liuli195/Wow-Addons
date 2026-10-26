# Sim2GSE Sequence Evaluation

## Purpose

对用户角色的可导出按键序列进行真实、可复查的战斗评估，并如实报告搜索与复测结论。

## Requirements

### Requirement: Sim2GSE evaluates the exported action order

系统 MUST 对与导出产物编译后相同的动作块、顺序和起始规则进行原生按键模拟；合法同块动作不得被一律拆成额外按键，暂时不可用的动作不得触发隐藏自主选招。

#### Scenario: Middle step is unavailable

- **WHEN** 序列依次为 A、B、C，当前输入对应不可用的 B
- **THEN** 该次输入按声明的步进与队列规则处理，不在同次输入自主扫描并补放 C；下一有效输入再处理下一步。

#### Scenario: Item and skill share a block

- **WHEN** 一个合法动作块依次包含主动使用物品与技能
- **THEN** 一次输入按块内顺序尝试动作，使用成功与拒绝遵守原生限制，导出后顺序保持一致。

#### Scenario: Export compilation differs

- **WHEN** 导出后编译的动作顺序与受测程序不一致
- **THEN** 系统拒绝将该导入产物标记为已验证，并说明差异。
### Requirement: Sim2GSE retains native combat behavior

系统 MUST 使用固定身份的原生引擎处理资源、冷却、伤害、宠物和被动效果，不自行补算或删除被动机制；未启用按键控制时不得产生相对同版本原版的非预期结果差异。

#### Scenario: Control is disabled

- **WHEN** 使用相同版本、角色、场景及随机条件关闭按键控制进行回归
- **THEN** 角色结果与对应原版保持一致，已有上游模型提示仍可追溯。

#### Scenario: Baseline engine lacks control support

- **WHEN** 运行入口收到没有所需按键控制能力的引擎
- **THEN** 系统报告不兼容，不能回退为自由选招模拟并称为序列结果。
### Requirement: Sim2GSE reports independently tested improvements

系统 MUST 在当前正式遗传算法自然收敛后，从全程成功粗评且行为不同的候选中，按粗评均分降序取不超过冻结上限的候选（默认最多8条），同分时按稳定的候选行为顺序确定入围名单，让全部入围者完成正常场景3批×请求128次的独立复测，再按正常每秒伤害均值及稳定行为身份选出一个可导出冠军。报告实际有效样本、自由选招参考及比例，区分粗评、正常独立复测和实际游戏验收；不承诺全局最优或收益比例，不执行训练的五场景四代表发布或旧复测回退。

#### Scenario: Search completes with a valid candidate

- **WHEN** 全部冻结入围者完成正常独立复测且冠军通过导出一致性检查
- **THEN** 导出该冠军，显示正常复测每秒伤害、有效样本与参考比例，明确游戏效果尚待验证。

#### Scenario: A finalist retest is incomplete

- **WHEN** 任一冻结入围者缺少完整有效正常复测
- **THEN** 保留可靠进度并报告未完成，不用粗评、部分复测或临时补入候选冒充正式完成冠军。
### Requirement: Sim2GSE resumes without mixing results

系统 MUST 在取消后保留可靠结果、冻结配置、随机状态、代际位置、评价计划与已耗重试，恢复不重复计算或汇总可靠成功批次。角色、引擎、软件版本、按键方式、重置规则或评价条件与原任务不兼容时必须拒绝继续；保留原有版本兼容限制，退役前未完成的新遗传算法任务也可能因软件变化无法继续。

旧正式搜索任务 MUST 仅可读取、验真及提取合法程序进入新遗传算法重新评分，不恢复旧搜索、旧晋级或旧冠军尚未完成的发布，不改写旧设置或历史记录以制造兼容。当前遗传算法的兼容任务可继续搜索、完成正常复测、保存可靠结果并补完当前冠军发布；训练恢复沿用原冻结分组、候选和种子。拒绝不删除旧证据。

#### Scenario: User cancels a running evaluation

- **WHEN** 用户取消计算
- **THEN** 停止派发并终止本次所属模拟，保留可靠完成结果，不终止其他任务或配装器进程。

#### Scenario: Resume a cancelled current genetic algorithm task

- **WHEN** 当前遗传算法任务在同版本同条件下恢复
- **THEN** 继续原代或原正常复测阶段，只补缺少的可靠请求，不重新选择起点或重复汇总成功样本。

#### Scenario: Resume conditions change

- **WHEN** 输入、引擎、软件版本或评价条件不兼容，或必要历史证明缺失
- **THEN** 拒绝原地续跑，旧结果仍可读，要求新建任务。

#### Scenario: An old formal task contains a pending champion intent

- **WHEN** 旧正式任务或旧版冠军尚未完成的发布尝试恢复、补保存或补发布
- **THEN** 明确拒绝旧执行，不重新模拟、不补写结果或冠军，保留原始证据。

#### Scenario: Simulation report is incomplete

- **WHEN** 报告损坏、部分完成或执行失败
- **THEN** 不将其记为成功缓存、正常零分或完成复测；仅当前正式粗评明确支持的失败处理可排除失败起点或保留原已验真候选，其他失败继续报错。
### Requirement: Sim2GSE independently replays timestamped inputs

系统 MUST 能按提供的按键时间逐次运行已选序列，并仅用模拟到该时刻已知的状态决定排队与执行；独立对照不得把实测施法成功、失败、资源或冷却状态作为模拟输入。

#### Scenario: Two recorded click timelines are compared

- **WHEN** 同一序列在两场各自记录的按键时间线上分别复测
- **THEN** 每场独立产生模拟轨迹，轨迹冻结后才能与对应实测成功技能对照；不同场次的按键和实测状态不会混用。

#### Scenario: Observed state is supplied for diagnosis

- **WHEN** 测试者另外提供实测状态或失败事件做事后定位
- **THEN** 该次结果与只输入按键时间的独立模拟结果可区分，不能充当独立预测的验收成绩。
### Requirement: Sim2GSE distinguishes queue handling from native execution

系统 MUST 在受控模拟轨迹中区分输入、排队处理与原生技能执行，使测试者能按输入序号追查被替换或拒绝的动作，不把排队请求当成施法成功。受支持的按键排队替换 MUST 可追溯到原按钮及实际执行动作；成功、中断及失败反馈不得错记到其他按钮，施法序列只在该成员确认成功后推进。仅共享输入来源的派生效果 MUST 不冒充原按钮执行或清除其待确认状态；不一致及重复终结仍须明确拒绝。

#### Scenario: A queued input does not execute

- **WHEN** 某次输入进入队列后被后续输入替换或在执行时被原生规则拒绝
- **THEN** 轨迹保留该输入的排队处理记录，但成功执行序列不包含该技能。

#### Scenario: Native queue replaces an issued button

- **WHEN** 已派发按钮在受支持的按键排队替换过程中成功执行或中断
- **THEN** 轨迹明确显示原按钮及实际执行动作，不误报缺少执行；施法序列成功推进原成员，中断不推进，失败反馈仍能识别原按钮。

#### Scenario: Derived effect shares an input origin

- **WHEN** 派生效果共享某次输入来源，但没有该按钮的真实原生替换执行
- **THEN** 不把派生效果作为原按钮完成，不清除待确认成员，也不放宽派发与完成一致性核验。
### Requirement: Sim2GSE labels offline validation accurately

系统 MUST 把离线模拟与正式服游戏内验收区分开；输出独立模拟成绩时不得把未达到的时序差异目标或借助实测反馈取得的成绩标作已达成。

#### Scenario: Offline result is produced without a new game test

- **WHEN** 只有自动测试和既有实测数据对照，而没有改后正式服游戏内验收
- **THEN** 结果标明游戏内验收未运行，并如实保留频率与时序差异，不声称达到未证实的精度目标。
### Requirement: Sim2GSE exposes supported engines only

系统 MUST 仅提供原版基准引擎与按键受控引擎；序列模拟使用受控引擎，并拒绝未知引擎模式。

#### Scenario: Unsupported mode is selected

- **WHEN** 测试者请求已移除或未知的引擎模式
- **THEN** 系统拒绝该模式，不启动模拟或构建。
### Requirement: Sim2GSE searches scores and exports castsequence candidates

系统 MUST 能在现有自动搜索中生成并评价成员顺序和重置规则不同的 `/castsequence` 候选，按真实受控模拟成绩参与选择，并将选中候选导出为可导入 GSE 的 `/castsequence` 宏；不同规则或可观察重置场景不得混用成绩。

#### Scenario: A castsequence candidate reaches selection

- **WHEN** 搜索生成可模拟的 `/castsequence` 候选并完成评分
- **THEN** 系统使用该候选的受控战斗成绩参与搜索内选择与比较，导出结果保留宏成员顺序和 重置 规则。

#### Scenario: Two reset scenarios differ

- **WHEN** 相同成员序列分别在不同可观察 重置 事件条件下评价
- **THEN** 两次评价各自使用对应的重置行为与成绩，不复用另一场景的结果。
### Requirement: Sim2GSE advances castsequence only after confirmed success

系统 MUST 在逐次按键模拟中将 `/castsequence` 保持在当前成员，直到该成员确认成功才前进；失败、中断及等待结果期间的重复点击不得提前前进。最后一个成员成功后回到第一个成员。数字超时按客户端统一更新时钟及每次有效使用刷新，目标变化、脱战、修饰键和死亡按对应规则重置；重置前仍在途的旧施法结果不得推动重置后的新一轮序列。

#### Scenario: A member fails or is still pending

- **WHEN** 当前成员失败、中断，或施法结果未确认时再次点击
- **THEN** 下一成员不会提前执行；后续有效输入仍按当前成员及原生按键队列处理。

#### Scenario: Reset occurs while an older spell is pending

- **WHEN** 重置事件发生时旧成员已有待确认施法
- **THEN** 旧施法仍可按原生战斗规则完成，但其结果不推进重置后的序列；后续输入从第一个成员开始。

#### Scenario: The final member succeeds

- **WHEN** `/castsequence` 的最后一个成员确认成功
- **THEN** 下一次有效使用从第一个成员开始。
### Requirement: Sim2GSE avoids repeated equivalent candidate work

系统 MUST 在候选进入原生模拟前按实际逐次点击行为识别等价候选，使同一任务中的等价行为只执行一次候选编译和一次评分；非法或无有效动作的候选不得进入原生模拟。详细诊断日志总开关 MUST 默认关闭并优先于其细分开关；关闭时不保存仅供事后分析的详细过程、持久化动作轨迹、详细诊断报告和性能统计，不仅为收集记录额外运行模拟。搜索、序列改进、避免重复模拟和取消后继续所需的可靠结果仍保留。轻量搜索与伤害曲线由独立选项控制，不受详细诊断总开关联动启停，也不得借此打开详细追踪。未请求详细诊断时，计算结束后 MUST 不留下仅供诊断使用的详细历史。

#### Scenario: Two candidates have the same click behavior

- **WHEN** 两个候选的来源结构不同，但映射后的动作、顺序、动作块边界、空点击和重置行为相同
- **THEN** 系统将它们视为同一行为，复用已经成功编译的候选，不再次启动候选编译或原生评分。

#### Scenario: Diagnostics are not requested

- **WHEN** 用户按默认配置运行搜索，或关闭详细诊断总开关但其细分开关仍请求详细记录，且未单独开启轻量曲线
- **THEN** 系统不产生额外诊断记录或仅用于诊断的模拟；轻量进度仍更新，必要结果与累计耗时可靠保存，进度刷新不得反复保存完整历史。

#### Scenario: Diagnostics are enabled

- **WHEN** 用户显式打开详细诊断总开关并启用相应细分记录
- **THEN** 系统允许相应诊断和统计；开关不改变候选身份、评分方式、合法性判断及位置修复，在同一候选、样本和随机条件下成绩与选择保持一致，不要求固定时间内两侧完成候选数相同。
### Requirement: Sim2GSE preserves complete checks while reducing redundant search work

系统 MUST 在模拟或编译已结束后及时返回，不因固定轮询延迟完成。新正式搜索默认最多五个单线程候选调用，可在一至五个范围内选择并随任务冻结；训练使用自身冻结组内并发；同输入和既定随机条件下，结果不因候选完成先后而改变。完整代后才换代，可靠请求复用不虚增样本。

导出所需完整检查 MUST 一次启动完成而不减少校验码、真实导入、动作顺序、篡改拒绝和编码往返检查。调用方指定交换报告目标时只产生该份完整报告，未指定时保留默认；报告内容及其数值含义保持。取消、超时、失败和所属进程清理有效，可靠完整报告才可入库及恢复复用，不再以旧配对置信区间规则决定晋级。

#### Scenario: Simulation or compilation has already exited

- **WHEN** 模拟或编译进程已退出，包括与取消或超时同时发生
- **THEN** 及时取得结果，按原所有权规则清理，不额外固定等待。

#### Scenario: Candidate calls finish out of order

- **WHEN** 同组候选完成顺序变化
- **THEN** 遵守本组并发上限，候选完成先后不改变既定随机条件、结果或完整代边界。

#### Scenario: A candidate is checked for export

- **WHEN** 系统核验可导出候选
- **THEN** 完整检查保持，任一失败不得发布导出，不能以退役旧搜索为由删除通用校验。

#### Scenario: Caller supplies a complete report destination

- **WHEN** 调用方指定完整交换报告目标
- **THEN** 只生成该报告，完整解析核验后才发布，部分结果不登记成功。
### Requirement: Sim2GSE verifies complete engine identity when upgrading

系统 MUST 使用适配已核实正式客户端、版本一致且可重新构建的引擎；版本或构建内容不匹配时拒绝计算和恢复。仅做内部整理时，同一版本和相同输入下的动作目录、报告中的战斗数据与战斗行为须保持一致，开关诊断记录不能改变技能执行。升级后以固定角色确认核心行为没有回归，并能恢复完整旧版本，保留历史任务和成绩；不同版本不混用成绩，不要求伤害、精确时刻或搜索路径相同。

正式任务 MUST 在每次启动或恢复时完整核验两套所需引擎，本次后续准备与双场计算可复用本次核验结果；新任务和下一次恢复必须重新核验，不能直接信任旧任务保存的身份。双场各自保留独立遗传算法进度与累计耗时。角色、天赋、审核爆发、规则和报告核验仍保持。此范围不承诺在同次已验后的执行途中再次发现人为替换引擎文件；下次启动或恢复仍须拒绝不符产物。

#### Scenario: Engine artifacts have mixed identities

- **WHEN** 引擎程序与其版本记录不一致
- **THEN** 拒绝执行或恢复并保留旧结果，不能将不一致产物当作通过验证。

#### Scenario: A client matched engine is upgraded

- **WHEN** 新引擎匹配已核实客户端且固定角色行为回归通过
- **THEN** 按新身份创建任务；旧记录不混入新成绩，实际游戏及未覆盖专精另记未验证。

#### Scenario: The engine is reorganized without a version change

- **WHEN** 仅整理同一版本引擎，并使用相同角色、序列和运行条件
- **THEN** 用户得到一致的动作目录、报告中的战斗数据和战斗结果；版本说明及其他非战斗记录按事实变化，开启或关闭诊断记录不改变序列执行。

#### Scenario: A dual task starts or resumes

- **WHEN** 用户新建或恢复正式双场任务
- **THEN** 两套引擎各完整核验一次，本次双场复用该结果但不共享遗传算法进度；以后新任务或恢复重新核验，旧身份不能绕过核验。
### Requirement: Sim2GSE provides a repository scoped engine upgrade entry

系统 MUST 提供本仓库专用、最小自包含的统一升级入口，供Codex（代码代理）和Claude Code（代码代理）使用同一份流程和核验能力。入口给出明确升级步骤及开发、验证、审查和交付要求；复用现有仓库能力，不依赖个人记忆，不注册公共市场。前后核验只读取必要的指定证据，不自行修改数据或启动计算；缺失、损坏或版本不符须明确失败。日常测试不增加重训练或提高预算，两端复用同一次真实训练至页面验收的证据。升级后核验 MUST 能证明指定新训练确已完成五场景复测、产生正确四代表，并证明页面采用这些来源、按当前角色适配并重新评分。旧逐材料训练证据不能冒充新训练验收；核验本身不得启动计算、补写或改写成果。

#### Scenario: A maintainer starts an upgrade

- **WHEN** 维护者从本仓库升级入口更新引擎
- **THEN** 按明确五步及开发门禁执行一次升级，专项沿用正式训练规则；两端复核同一份真实证据，不重复训练。日常验证不加入重训练或增加预算，失败保留准确恢复位置。

#### Scenario: Upgrade evidence is incomplete or from an old engine

- **WHEN** 前后核验发现指定记录缺失、损坏或引擎及处理条件不一致
- **THEN** 返回非零结果并报告原因，不据文件存在判成功；两端实际调用不可用和游戏未测分别保留未完成事实。
### Requirement: Sim2GSE combines four native four selected and two champion sources

系统 MUST 在正式搜索保留四类原生起点与至多四个既有训练代表，并按冻结成果契约版本消费冠军来源：版本1或无版本保留独立最终训练冠军及角色正式冠军，最多4＋4＋2；版本2四条已含正常每秒伤害冠军／稳定代表，只增加原契约正式冠军，最多4＋4＋1，不另取训练冠军。未知或混合版本明确拒绝。所有来源经过当前角色合法性、编译与行为去重并重新评分，旧分不冒充当前成绩。等价初始行为只建立一个有效起点，但保留全部来源，不能复制或补选凑数。新增来源不改变冻结遗传算法评价、自然停止或并发上限，不改变独立训练入口。

#### Scenario: All ten sources are legal and behaviorally distinct

- **WHEN** 四类原生、四个代表及两个冠军均合法且行为不同
- **THEN** 合法起点在当前角色重新评分，成功候选进入当前遗传算法，停止仍按历史领先榜达到任务冻结的连续无提升轮数判断，新正式任务默认八个完整代。

#### Scenario: A champion coincides with another source

- **WHEN** 冠军适配后的行为与原生或代表相同
- **THEN** 只建立一个合法初始行为并保留各来源，不重复评分或复制凑数。

#### Scenario: A version two pretraining snapshot is consumed

- **WHEN** 新正式任务读取可核验的版本2四条预训练成果
- **THEN** 冻结该快照且不再读取独立训练冠军，保留原四类起点及原条件正式冠军，行为去重后最多九条；当前遗传算法恢复不因库变化重新选择来源或切换算法。
### Requirement: Sim2GSE retains and reliably advances the formal champion

系统 MUST 为相同冻结角色、专精和完整正式评价条件保存可追溯冠军，按对应条件点读，不扫描全历史。继承只复用程序并按当前遗传算法重新评分，不把旧成绩作为本次基线或强制精英；本次冠军来自全部冻结入围者完整正常复测，不能用旧配对置信区间或不完整的历史晋级证明冒充当前完整复测。

系统 MUST 仅新写版本2正式冠军，先可靠保存完整任务、候选、导出及全体入围复测证据，再按预期冠军版本更新；陈旧任务不能覆盖已变化版本，行为相同不虚增版本，重复尝试同一次发布不得重复生成成果。当前遗传算法发布失败仍可同版本恢复补保存/补发布，不重做可靠评分；取消、半代或部分复测不发布。旧版本1完整冠军仅按原契约只读验真，其未完成发布不再补写。附属发布状态损坏不得遮蔽可靠结果或伪称成功。

#### Scenario: A new task inherits a verified champion

- **WHEN** 当前角色条件下存在可核验正式冠军
- **THEN** 程序作为当前合法起点重新评分，旧来源与当前成绩分别可查，不保证单调超过旧分。

#### Scenario: A stale task tries to publish after another task

- **WHEN** 另一个任务已经改变当前冠军版本
- **THEN** 陈旧任务保留自身成果并报告冲突，不覆盖新版本。

#### Scenario: Current version two publication is interrupted

- **WHEN** 当前遗传算法完整赢家已可靠保存但发布中断
- **THEN** 通过兼容检查后继续核验全体入围证据并幂等补发布，不重复可靠评分；旧版本1意图不适用。
### Requirement: Sim2GSE imports bounded verified historical formal candidates

系统 MUST 通过明确管理操作接入最多64个去重的已知正式来源任务；不把历史接入作为每次网页搜索的全表扫描。仅在对应正式冠军缺席时接入，已有冠军不得被导入覆盖。每个来源的角色、专精、关键引擎/爆发/按法条件和完整正式程序及报告关联必须可证；无法证明时明确拒绝并保留原因。范围内旧成绩只用于选候选，旧规则程序须按当前规则重新评分并经正常可靠保存与发布建立冠军，不搬用旧缓存成绩。

#### Scenario: An explicit bounded source set contains a historical best program

- **WHEN** 管理操作提供可核验且去重后不超过64个来源，当前尚无对应冠军
- **THEN** 仅核验该范围并选择候选，按当前条件重新评分后正常保存发布；报告限定范围，不声称代表全部历史。

#### Scenario: The source set is too large or a champion already exists

- **WHEN** 去重来源超过64个、关键来源证据无法核验，或对应冠军已经存在
- **THEN** 拒绝超限或不可靠来源，已有冠军保持；未执行接入的真实历史不得标记为已迁移。
### Requirement: Sim2GSE provides independent lightweight search and damage curves

系统 MUST 提供默认关闭的独立轻量曲线开关，可通过配置、显式调用或命令行选择；新任务本次显式选择优先于配置，未指定时沿用配置或默认值；恢复任务本次明确选择优先，否则沿用该任务保存的曲线设置。该选项控制任务运行时的自动采集与导出，关闭时不采集曲线事件、不写曲线文件、不自动绘图，也不为曲线额外模拟；显式离线查看已有资料不触发新搜索或模拟。开启曲线不改变候选、评分、缓存或恢复身份，不联动详细诊断或已退役的规则／选择器能力。

开启后 MUST 复用已有评分及结果，在真实调用开始的单调墙钟上记录首个可用成绩、全局与路径成绩变化、停止和保存时点；准备、排队及诊断自身耗时不得从曲线时间扣除，不额外评分或开启原生详细追踪。业务搜索和结果保存结束后才离线输出事件数据及可离线查看的曲线。曲线记录与导出失败不得破坏有效业务结果；事件数量有明确数量上限，达到上限时标记截断而非停止搜索。异常终止导致数据缺失时不得伪造完整曲线。

曲线 MUST 从零开始按10秒网格取当时最后已知成绩，首个成绩之前留空，不用未来成绩回填；成绩重估下降如实显示。停止或取消后的已知值可延伸展示，但必须明确标记已停止，不伪装继续搜索；失败或截断后的未知区间留空。恢复调用形成新时间段，保留旧段不覆盖、不拼成未中断的一次搜索。独立预训练各组使用同一公开调用时间起点并分别展示，不混为一条成绩曲线；预训练仅提供时间每秒伤害曲线，不提供预训练战斗伤害分布曲线，以下战斗伤害曲线契约继续适用于正式搜索。

多次运行 MUST 仅在角色配置、引擎及模拟条件、输入节奏、重置和爆发条件一致且可核验时归入同一可比组；算法选项和随机种子作为对照标签，路径按已有标识区分，不借此混用物理条件。条件缺失或不同的运行分别展示。战斗伤害曲线仅复用已确认来源和统计口径的原生按每秒统计的伤害明细，保留含宠物在内的原生统计口径，不重复叠加宠物、不强行归一到最终评分；缺少或无法证明适用的逐秒伤害明细时明确说明不可用，不自动补跑模拟。

#### Scenario: Lightweight curves are not requested

- **WHEN** 用户按默认配置运行搜索或训练
- **THEN** 不产生曲线事件、文件、自动绘图或仅为曲线执行的模拟；业务进度和必要结果继续正常保存。

#### Scenario: Curves are enabled without detailed diagnostics

- **WHEN** 用户单独开启轻量曲线但保持详细诊断关闭
- **THEN** 在不新增评分或原生追踪的情况下记录真实调用时间，业务保存完成后输出离线事件和曲线；诊断异常不改变已保存业务结果。

#### Scenario: Known scores change between grid points

- **WHEN** 首个成绩晚于调用开始，或后续已知成绩被修订为较低值
- **THEN** 首个结果前留空，每个10秒网格仅采用该时点已知值，修订下降如实显示，不进行未来回填。

#### Scenario: A run stops truncates or resumes

- **WHEN** 搜索停止或取消、曲线被截断、调用失败，或用户恢复同一业务任务
- **THEN** 已停止段明确标记，失败或截断后的未知区间留空；恢复产生新段并保留原段，曲线开关变化不阻止同一合法业务任务恢复。

#### Scenario: Multiple runs have different or incomplete comparison conditions

- **WHEN** 用户查看多个运行的曲线，且其物理或输入条件不同或无法证明一致
- **THEN** 不将它们归入同一可比组；同条件下算法选项和随机种子只作为对照标签，路径按已有标识区分，训练路径仍分开展示。

#### Scenario: Existing damage buckets are unavailable

- **WHEN** 完成结果没有可确认统计口径的原生按每秒统计的伤害明细
- **THEN** 明确说明伤害曲线不可用，不自动补模拟；有合格逐秒伤害明细时按原生口径绘制，不重复加入宠物伤害或归一为最终评分。
### Requirement: Sim2GSE rejects retired rule and selector execution

系统 MUST 不再提供自适应选择、规则化起点、职业规则编辑、旧模板解释、手动单步或其专属运行观察功能。通过配置或命令行请求这些已移除能力时，即使明确关闭也须提示已移除，不静默忽略或退回旧算法。

正式搜索 MUST 仍使用原四类起点、既有随机变异及基础位置反馈，保留合法性检查、导出一致性、评分、可靠结果复用和保存、材料适配、固定独立爆发、适用安全时限、正式冠军及赢家复用。新任务不依赖当前职业规则库来识别专精、真实英雄及目标类型；旧版完整报告及冠军仍可按原记录只读核验，但不能恢复旧规则功能或补采旧规则证据。旧不兼容未完成任务明确拒绝恢复，不改写历史身份。混合历史任务／报告、材料及冠军不可整库删除，专属数据对象的永久删除须另按具体对象授权，不把功能退役冒称历史数据已删除。

#### Scenario: A retired option is supplied

- **WHEN** 用户通过配置或命令行传入退役选择器、规则起点或规则专属诊断选项，包括显式关闭值
- **THEN** 明确提示能力和开关已移除，不运行已移除功能，也不产生旧规则起点或其专属观察结果，也不默默忽略。

#### Scenario: A default formal task runs without the profession rule library

- **WHEN** 用户从原公开入口启动普通正式搜索，当前职业规则库已不存在
- **THEN** 原四起点、基础随机变异／位置反馈及已核验起点和冠军仍可按原条件工作，正式完整诊断能力不降级。

#### Scenario: A complete old result is inspected

- **WHEN** 用户读取可核验的旧完整任务、版本1代表或冠军证据
- **THEN** 按必要只读兼容核验原证据，不重启旧规则执行、不迁移身份，也不删除混合历史。
### Requirement: Sim2GSE stops formal genetic algorithm search by natural stagnation

系统 MUST 对正式搜索采用明确版本化的自然停滞策略，不设置600秒搜索总截止、固定代数或1000候选封顶。共用遗传算法在每个完整代后检查历史不同候选在冻结入围上限内的领先榜，任一名次严格提高或未达到入围上限时补入新行为均清零停滞计数，达到冻结的连续无提升轮数后转入正常复测，新正式任务默认八个完整代；半代、取消、失败不冒充完整代。初始化实际合法且成功评分的起点决定有效候选数量，不以分支数量决定停止阈值。

页面 MUST 依次运行单目标和5目标，两场分别显示实际代际/阶段、累计用时，公共准备与整理单列；不得把已用时间除以旧600秒预算，伪造可到达终点的进度。不承诺有限总收敛时间。手动取消、所属进程清理、单次原生超时及单次/导入模拟既有安全上限保持，结果和进度不得虚构有限搜索截止时间。

#### Scenario: Both scenes run

- **WHEN** 用户一次启动单目标和5目标
- **THEN** 第一场及其收尾完成后才开始第二场，每场自然收敛并正常复测，如实显示公共准备、各场和整理耗时。

#### Scenario: A partial generation is interrupted

- **WHEN** 一代尚未完成即取消或失败
- **THEN** 保存可靠进度而不累加完整代停滞；恢复同一冻结随机计划和原阶段，不自动转入复测。
### Requirement: Sim2GSE exposes only the current formal genetic algorithm execution

系统 MUST 仅提供当前正式遗传算法搜索，保持原四类起点、合法历史程序、当前角色评价及可靠结果保存能力。旧正式搜索、旧分档筛选和配对置信区间晋级不再可执行；任何现行入口、恢复操作或附带工具均不得重新启动旧算法。历史来源和已保存成果仍可查看与核验。

系统 MUST 在计算和创建任务前拒绝已退役的搜索设置：总预算、搜索预算、候选总上限、每轮候选上限、旧无改善轮数、旧累计批次目标、旧晋级复核批数、旧最终复测批数、旧最终复测迭代数、旧搜索过程追踪及自定义评分场景。显式关闭或沿用旧默认值也必须说明已退役，不能静默接受。

参考评价请求迭代数仍控制自由选招参考，不被误解为正式搜索采样设置；并发、随机种子、输入间隔、重置规则及既有日志/曲线保留。正式评分场景固定正常，不再允许用户另选正式评分场景，但修饰键重置规则仍须对齐正常点击；训练多场景不接受该修饰键事件。历史结果仍按产生时的规则解释，但不因此获得继续运行旧搜索的能力。

#### Scenario: A caller sends a retired setting

- **WHEN** 调用者通过任一受支持入口提交上述任一退役设置
- **THEN** 计算和任务创建前明确报退役错误，不因显式关闭或旧默认值而忽略。

#### Scenario: A valid modifier reset is requested

- **WHEN** 当前正式任务请求与固定正常点击对齐的修饰键重置规则
- **THEN** 保留该语义；不对齐或用于训练五场景时明确拒绝，不能因评分场景已固定而跳过重置合法性检查。

### Requirement: Sim2GSE keeps formal search configuration independent from training

角色按键序列优化器 MUST 分别使用正式搜索与训练各自的计算配置。正式搜索提供九项算法设置：评分并发、粗评请求次数、复测批数、每批复测请求次数、连续无提升轮数、用于比较提升和最终复测入围的候选名额（不限制整个搜索累计评估的候选数量）、竞争参与数量、交叉概率及变异概率；另提供八项运行设置：参考模拟次数、随机种子、搜索曲线、诊断日志总开关、诊断详细程度、搜索过程记录程度、按键间隔及重置事件。模拟目标、场景与既有天赋开关仍按原功能独立选择。

新正式任务默认参考模拟请求128次、评分并发五个、连续八个完整代无榜单改善后复测；粗评32次、正常场景复测三批且每批128次、领先榜及入围上限八个、竞争参与数量三个、交叉及变异概率各0.8，随机种子20260912保持原值。参考次数不代替粗评次数；连续无提升轮数不是总运行代数，也不只是观察第一名。

新任务 MUST 按页面明确选择、直接运行参数、所属配置文件、程序内置默认值的顺序取值；明确关闭是有效选择。页面和双场任务未提供按键间隔时沿用200毫秒，单场任务沿用300毫秒；配置和明确运行参数均可覆盖这些内置默认。关联参数以最终有效组合校验，不因较低优先级默认组合不适用而拒绝合法的页面选择。

诊断日志总开关仍默认关闭，关闭不新增仅供诊断的记录。正式任务保留期望的记录程度，重新开启时不丢失；未另行指定细分程度时，仅开启总开关仍提供既有性能摘要与过程记录。明确选择关闭或摘要程度不得被强制升级为完整记录；切换观测程度不改变计算条件，不补采过去记录。

恢复 MUST 沿用保存的全部计算条件，本次未明确提供的观测设置也沿用保存值；明确改变计算条件须新建任务。旧完整成果按其原规则只读验真，不因当前默认改变而失效；代码、引擎或其他必需身份不兼容的旧未完成任务仍拒绝继续，不迁移或绕过身份检查。

#### Scenario: A new formal task uses independent settings

- **WHEN** 用户创建新正式任务，正式配置未另行覆盖默认值
- **THEN** 实际参考请求128次，同场评分最多五路，达到连续八个完整无提升代才复测；训练原计算配置不变。

#### Scenario: A higher priority page choice makes the combination valid

- **WHEN** 页面明确选择的按键间隔与重置事件相容，而较低优先级默认间隔不相容
- **THEN** 使用页面选择校验和运行；最终选择不相容时明确拒绝，不静默更改条件。

#### Scenario: A frozen task resumes after configuration changes

- **WHEN** 已保存任务通过原版本和身份核验，配置文件后来已有变化
- **THEN** 恢复仍使用保存的计算条件；本次明确观测选择生效，省略时保留保存值，明确计算冲突被拒绝。
