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

系统 MUST 在当前正式GA自然收敛后，冻结全程成功粗评的不同行为前K入围者（默认K为8），让全部入围者完成正常场景3批×请求128次的独立复测，再按正常DPS均值及稳定行为身份选出一个可导出冠军。报告实际有效样本、自由选招参考及比例，区分粗评、正常独立复测和实际游戏验收；不承诺全局最优或收益比例，不执行训练的五场景四代表发布或旧复测回退。

#### Scenario: Search completes with a valid candidate

- **WHEN** 全部冻结入围者完成正常独立复测且冠军通过导出一致性检查
- **THEN** 导出该冠军，显示正常复测DPS、有效样本与参考比例，明确游戏效果尚待验证。

#### Scenario: A finalist retest is incomplete

- **WHEN** 任一冻结入围者缺少完整有效正常复测
- **THEN** 保留可靠进度并报告未完成，不用粗评、部分复测或临时补入候选冒充正式完成冠军。

### Requirement: Sim2GSE stops formal GA by natural stagnation

系统 MUST 对正式搜索采用明确版本化的自然停滞策略，不设置600秒搜索总截止、固定代数或1000候选封顶。共用GA在每个完整代后检查历史不同行为前K榜，任一名次严格提高或不足K时补入新行为均清零停滞计数，连续两个完整代无提高后转入正常复测；半代、取消、失败不冒充完整代。初始化实际合法且成功评分的起点决定有效种群槽数，不以分支数量决定停止阈值。

页面 MUST 依次运行单目标和5目标，两场分别显示实际代际/阶段、累计用时，公共准备与整理单列；不得按elapsed/600制造有限终点进度。不承诺有限总收敛时间。手动取消、所属进程清理、单次原生超时及单次/导入模拟既有安全上限保持，无限总额度不写入标准JSON或旧有限预算字段。

#### Scenario: Both scenes run

- **WHEN** 用户一次启动单目标和5目标
- **THEN** 第一场及其收尾完成后才开始第二场，每场自然收敛并正常复测，如实显示公共准备、各场和整理耗时。

#### Scenario: A partial generation is interrupted

- **WHEN** 一代尚未完成即取消或失败
- **THEN** 保存可靠进度而不累加完整代停滞；恢复同一冻结随机计划和原阶段，不自动转入复测。

### Requirement: Sim2GSE resumes without mixing results

系统 MUST 在取消后保留可靠结果、冻结配置、随机状态、代际位置、评价计划与已耗重试，恢复不重复计算或汇总可靠成功批次。角色、引擎、全部源码规则、输入模型、编译、Reset或采样身份不同必须拒绝混接；不放宽已有完整版本保护，退役前未完成的新GA也可能因代码变化拒绝跨版本恢复。

旧正式chain/neighbour任务 MUST 仅可读取、验真及提取合法程序进入新GA重新评分，不恢复旧搜索、旧晋级或旧冠军待发布意图，不把旧配置补成新默认，不重写历史身份。当前GA的同版本搜索、正常复测、可靠结果补保存与v2冠军补发布继续支持；训练恢复沿用原冻结分组、候选和种子。拒绝不删除旧证据。

#### Scenario: User cancels a running evaluation

- **WHEN** 用户取消计算
- **THEN** 停止派发并终止本次所属模拟，保留可靠完成结果，不终止其他任务或配装器进程。

#### Scenario: Resume a cancelled current GA task

- **WHEN** 当前GA任务在同版本同条件下恢复
- **THEN** 继续原代或原正常复测阶段，只补缺少的可靠请求，不重新选择起点或重复汇总成功样本。

#### Scenario: Resume conditions change

- **WHEN** 输入、引擎、源码或评价条件不符，或必要历史证明缺失
- **THEN** 拒绝原地续跑，旧结果仍可读，要求新建任务。

#### Scenario: An old formal task contains a pending champion intent

- **WHEN** 旧正式任务或v1发布意图尝试恢复、补保存或补发布
- **THEN** 明确拒绝旧执行，不重新模拟、不补写结果或冠军，保留原始证据。

#### Scenario: Simulation report is incomplete

- **WHEN** 报告损坏、部分完成或执行失败
- **THEN** 不将其记为成功缓存、正常零分或完成复测；仅当前正式粗评显式版本化的候选评分失败政策可排除初始失败槽或保留对应已验真父槽，其他失败继续报错。

### Requirement: Sim2GSE independently replays timestamped inputs

系统 MUST 能按提供的按键时间逐次运行已选序列，并仅用模拟到该时刻已知的状态决定排队与执行；独立对照不得把实测施法成功、失败、资源或冷却状态作为模拟输入。

#### Scenario: Two recorded click timelines are compared

- **WHEN** 同一序列在两场各自记录的按键时间线上分别复测
- **THEN** 每场独立产生模拟轨迹，轨迹冻结后才能与对应实测成功技能对照；不同场次的按键和实测状态不会混用。

#### Scenario: Observed state is supplied for diagnosis

- **WHEN** 测试者另外提供实测状态或失败事件做事后定位
- **THEN** 该次结果与只输入按键时间的独立模拟结果可区分，不能充当独立预测的验收成绩。
### Requirement: Sim2GSE distinguishes queue handling from native execution

系统 MUST 在受控模拟轨迹中区分输入、排队处理与原生技能执行，使测试者能按输入序号追查被替换或拒绝的动作，不把排队请求当成施法成功。当前受控引擎已接入的原生队列替换路径 MUST 保留派发原按钮的完整命令签名及实际原生动作身份；成功、中断及失败反馈按同一原按钮身份核验，施法序列只在该成员确认成功后推进。仅共享输入来源的派生效果 MUST 不冒充原按钮执行或清除其待确认状态；不一致及重复终结仍须明确拒绝。

#### Scenario: A queued input does not execute

- **WHEN** 某次输入进入队列后被后续输入替换或在执行时被原生规则拒绝
- **THEN** 轨迹保留该输入的排队处理记录，但成功执行序列不包含该技能。

#### Scenario: Native queue replaces an issued button

- **WHEN** 已派发按钮通过该已接入的原生队列替换路径成功执行或中断
- **THEN** 轨迹保留原按钮完整签名和实际动作身份，匹配该次派发而不误报缺少执行；施法序列成功推进原成员，中断不推进，失败反馈仍能识别原按钮。

#### Scenario: Derived effect shares an input origin

- **WHEN** 派生效果共享某次输入来源，但没有该按钮的真实原生替换执行
- **THEN** 不把派生效果作为原按钮完成，不清除待确认成员，也不放宽派发与完成一致性核验。
### Requirement: Sim2GSE labels offline validation accurately

系统 MUST 把离线模拟与正式服游戏内验收区分开；输出独立模拟成绩时不得把未达到的时序差异目标或借助实测反馈取得的成绩标作已达成。

#### Scenario: Offline result is produced without a new game test

- **WHEN** 只有自动测试和既有实测数据对照，而没有改后正式服游戏内验收
- **THEN** 结果标明游戏内验收未运行，并如实保留频率与时序差异，不声称达到未证实的精度目标。
### Requirement: Sim2GSE exposes supported engines only

系统 MUST 仅提供 baseline（基准）与 controlled（受控）引擎；序列模拟使用受控引擎，并拒绝未知引擎模式。

#### Scenario: Unsupported mode is selected

- **WHEN** 测试者请求已移除或未知的引擎模式
- **THEN** 系统拒绝该模式，不启动模拟或构建。
### Requirement: Sim2GSE searches scores and exports castsequence candidates

系统 MUST 能在现有自动搜索中生成并评价成员顺序和 Reset（重置）规则不同的 `/castsequence` 候选，按真实受控模拟成绩参与选择，并将选中候选导出为可导入 GSE 的 `/castsequence` 宏；不同规则或可观察重置场景不得混用成绩。

#### Scenario: A castsequence candidate reaches selection

- **WHEN** 搜索生成可模拟的 `/castsequence` 候选并完成评分
- **THEN** 系统使用该候选的受控战斗成绩参与搜索内选择与比较，导出结果保留宏成员顺序和 Reset 规则。

#### Scenario: Two reset scenarios differ

- **WHEN** 相同成员序列分别在不同可观察 Reset 事件条件下评价
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

系统 MUST 在候选进入原生模拟前按实际逐次点击行为识别等价候选，使同一任务中的等价行为只执行一次候选编译和一次评分；非法或无有效动作的候选不得进入原生模拟。详细诊断日志总开关 MUST 默认关闭并优先于其细分开关；关闭时不保存仅供事后分析的详细过程、持久化动作轨迹、详细诊断报告和性能统计，不仅为收集记录额外运行模拟。搜索、位置修复、避免重复模拟、取消后继续以及显式启用的自适应选择所必需的数据和最终结果仍保留。轻量搜索与伤害曲线由独立选项控制，不受详细诊断总开关联动启停，也不得借此打开详细追踪。算法临时需要的详细轨迹计算结束后 MUST 清理，不作为诊断历史保留。

#### Scenario: Two candidates have the same click behavior

- **WHEN** 两个候选的来源结构不同，但映射后的动作、顺序、动作块边界、空点击和重置行为相同
- **THEN** 系统将它们视为同一行为，复用已经成功编译的候选，不再次启动候选编译或原生评分。

#### Scenario: Diagnostics are not requested

- **WHEN** 用户按默认配置运行搜索，或关闭详细诊断总开关但其细分开关仍请求详细记录，且未单独开启轻量曲线
- **THEN** 系统不产生额外诊断记录或仅用于诊断的模拟；轻量进度仍更新，必要结果与累计预算可靠保存，不为统计或进度每半秒保存完整历史。

#### Scenario: Diagnostics are enabled

- **WHEN** 用户显式打开详细诊断总开关并启用相应细分记录
- **THEN** 系统允许相应诊断和统计；开关不改变候选身份、评分方式、合法性判断及位置修复，在同一候选、样本和随机条件下成绩与选择保持一致，不要求固定时间内两侧完成候选数相同。
### Requirement: Sim2GSE exposes only the current formal GA execution

系统 MUST 仅执行当前正式GA，复用现有训练的选择、交叉、变异、位置反馈、评价与可靠保存。原四类初始化、合法历史起点和当前角色条件保持，不另建策略框架。旧局部链、分档筛选、配对区间晋级及Git历史源码提取执行工具必须退役，不能通过选择开关、旧检查点或隐藏工具重新启动。

新配置 MUST 明确拒绝total_budget_seconds、search_budget_seconds、candidate_limit、round_candidate_limit、no_improvement_rounds、batch_targets、validation_batches、final_batches、final_iterations、trace_search、scenarios十一键，即使值为false也不静默接受。iterations仍控制自由选招参考；并发、随机种子、输入间隔、Reset及既有日志/曲线保留。正式评分场景固定正常，scenarios不再可配置，但修饰键Reset仍须对齐正常点击；训练多场景不接受该修饰键事件。历史只读解码继续按旧字段解释，不能取得旧运行能力。

#### Scenario: A caller sends a retired setting

- **WHEN** 当前配置、API、CLI配置或HTTP请求携带任一退役键
- **THEN** 计算和任务创建前明确报退役错误，不因false或旧默认值而忽略。

#### Scenario: A valid modifier reset is requested

- **WHEN** 当前正式任务请求与固定正常点击对齐的修饰键Reset
- **THEN** 保留该语义；不对齐或用于训练五场景时明确拒绝，不靠删除scenarios绕过验证。

### Requirement: Sim2GSE preserves complete checks while reducing redundant search work

系统 MUST 在模拟或编译已结束后及时返回，不因固定轮询延迟完成。正式搜索最多两个单线程候选调用，训练使用冻结组内并发；都按冻结槽位和请求顺序消费完整结果，不因完成先后改变随机计划。完整代后才换代，可靠请求复用不虚增样本。

导出所需完整检查 MUST 一次启动完成而不减少校验码、真实导入、动作顺序、篡改拒绝和编码往返检查。调用方指定交换报告目标时只产生该份完整报告，未指定时保留默认；字段与类型保持。取消、超时、失败和所属进程清理有效，可靠完整报告才可入库及恢复复用，不保留旧CI晋级计算或摘要分支。

#### Scenario: Simulation or compilation has already exited

- **WHEN** 模拟或编译进程已退出，包括与取消或超时同时发生
- **THEN** 及时取得结果，按原所有权规则清理，不额外固定等待。

#### Scenario: Candidate calls finish out of order

- **WHEN** 同组候选完成顺序变化
- **THEN** 遵守本组并发上限，按冻结槽位消费结果，不改变种子、随机计划或完整代边界。

#### Scenario: A candidate is checked for export

- **WHEN** 系统核验可导出候选
- **THEN** 完整检查保持，任一失败不得发布导出，不能以退役旧搜索为由删除通用校验。

#### Scenario: Caller supplies a complete report destination

- **WHEN** 调用方指定完整交换报告目标
- **THEN** 只生成该报告，完整解析核验后才发布，部分结果不登记成功。

### Requirement: Sim2GSE verifies complete engine identity when upgrading

系统 MUST 使用适配已核实正式客户端、版本一致且可重新构建的引擎；版本或构建内容不匹配时拒绝计算和恢复。仅做内部整理时，同一版本和相同输入下的动作目录、报告中的战斗数据与战斗行为须保持一致，开关诊断记录不能改变技能执行。升级后以固定角色确认核心行为没有回归，并能恢复完整旧版本，保留历史任务和成绩；不同版本不混用成绩，不要求伤害、精确时刻或搜索路径相同。

正式任务 MUST 在每次启动或恢复时完整核验两套所需引擎，本次后续准备与双场计算可复用本次核验结果；新任务和下一次恢复必须重新核验，不能直接信任旧任务保存的身份。双场各自保留独立GA进度与累计耗时。角色、天赋、审核爆发、规则和报告核验仍保持。此范围不承诺在同次已验后的执行途中再次发现人为替换引擎文件；下次启动或恢复仍须拒绝不符产物。

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
- **THEN** 两套引擎各完整核验一次，本次双场复用该结果但不共享GA进度；以后新任务或恢复重新核验，旧身份不能绕过核验。
### Requirement: Sim2GSE provides a repository scoped engine upgrade entry

系统 MUST 提供本仓库专用、最小自包含的统一升级入口，供Codex（代码代理）和Claude Code（代码代理）使用同一份流程和核验能力。入口给出明确升级步骤及开发、验证、审查和交付要求；复用现有仓库能力，不依赖个人记忆，不注册公共市场。前后核验只读取必要的指定证据，不自行修改数据或启动计算；缺失、损坏或版本不符须明确失败。日常测试不增加重训练或提高预算，两端复用同一次真实训练至页面验收的证据。升级后核验 MUST 只读指定GA清单/检查点与真实五场景报告，复用现有四代表选择，再核对页面冻结来源、当前派生适配和新GA评分；不接受旧逐材料processed索引，不初始化会写盘的任务存储。

#### Scenario: A maintainer starts an upgrade

- **WHEN** 维护者从本仓库升级入口更新引擎
- **THEN** 按明确五步及开发门禁执行一次升级，专项沿用正式训练规则；两端复核同一份真实证据，不重复训练。日常验证不加入重训练或增加预算，失败保留准确恢复位置。

#### Scenario: Upgrade evidence is incomplete or from an old engine

- **WHEN** 前后核验发现指定记录缺失、损坏或引擎及处理条件不一致
- **THEN** 返回非零结果并报告原因，不据文件存在判成功；两端实际调用不可用和游戏未测分别保留未完成事实。
### Requirement: Sim2GSE combines four native four selected and two champion sources

系统 MUST 在正式搜索保留四类原生起点与至多四个既有训练代表，并按冻结成果契约版本消费冠军来源：v1或无版本保留独立最终训练冠军及角色正式冠军，最多4＋4＋2；v2四条已含正常DPS冠军／稳定代表，只增加原契约正式冠军，最多4＋4＋1，不另取训练冠军。未知或混合版本明确拒绝。所有来源经过当前角色合法性、编译与行为去重并重新评分，旧分不冒充当前成绩。等价初始行为只建立一个有效起点，但保留全部来源，不能复制或补选凑数。新增来源不改变冻结GA评价、自然停止或并发上限，不改变独立训练入口。

#### Scenario: All ten sources are legal and behaviorally distinct

- **WHEN** 四类原生、四个代表及两个冠军均合法且行为不同
- **THEN** 合法起点在当前角色重新评分，成功槽进入当前GA，停止仍为历史topK连续两个完整代无提高。

#### Scenario: A champion coincides with another source

- **WHEN** 冠军适配后的行为与原生或代表相同
- **THEN** 只建立一个合法初始行为并保留各来源，不重复评分或复制凑数。

#### Scenario: A version two pretraining snapshot is consumed

- **WHEN** 新正式任务读取可核验的v2四条预训练成果
- **THEN** 冻结该快照且不再读取独立训练冠军，保留原四类起点及原条件正式冠军，行为去重后最多九条；当前GA恢复不因库变化重新选择来源或切换算法。
### Requirement: Sim2GSE retains and reliably advances the formal champion

系统 MUST 为相同冻结角色、专精和完整正式评价条件保存可追溯冠军，按对应条件点读，不扫描全历史。继承只复用程序并按当前GA重新评分，不把旧成绩作为本次基线或强制精英；本次冠军来自全部冻结入围者完整正常复测，不能伪造旧CI或global_validation晋级链。

系统 MUST 仅新写v2正式冠军，先可靠保存完整任务、候选、导出及全体入围复测证据，再按预期冠军版本更新；陈旧任务不能覆盖已变化版本，行为相同不虚增版本，同一意图幂等。当前GA发布失败仍可同版本恢复补保存/补发布，不重做可靠评分；取消、半代或部分复测不发布。旧v1完整冠军仅按原契约只读验真，其旧pending意图不补写或补发布。附属发布状态损坏不得遮蔽可靠结果或伪称成功。

#### Scenario: A new task inherits a verified champion

- **WHEN** 当前角色条件下存在可核验正式冠军
- **THEN** 程序作为当前合法起点重新评分，旧来源与当前成绩分别可查，不保证单调超过旧分。

#### Scenario: A stale task tries to publish after another task

- **WHEN** 另一个任务已经改变当前冠军版本
- **THEN** 陈旧任务保留自身成果并报告冲突，不覆盖新版本。

#### Scenario: Current v2 publication is interrupted

- **WHEN** 当前GA完整赢家已可靠保存但发布中断
- **THEN** 同身份恢复核验全体入围证据并幂等补发布，不重复可靠评分；旧v1意图不适用。

### Requirement: Sim2GSE imports bounded verified historical formal candidates

系统 MUST 通过明确管理操作接入最多64个去重的已知正式来源任务；不把历史接入作为每次网页搜索的全表扫描。仅在对应正式冠军缺席时接入，已有冠军不得被导入覆盖。每个来源的角色、专精、关键引擎/爆发/按法条件和完整正式程序及报告关联必须可证；无法证明时明确拒绝并保留原因。范围内旧成绩只用于选候选，旧规则程序须按当前规则重新评分并经正常可靠保存与发布建立冠军，不搬用旧缓存成绩。

#### Scenario: An explicit bounded source set contains a historical best program

- **WHEN** 管理操作提供可核验且去重后不超过64个来源，当前尚无对应冠军
- **THEN** 仅核验该范围并选择候选，按当前条件重新评分后正常保存发布；报告限定范围，不声称代表全部历史。

#### Scenario: The source set is too large or a champion already exists

- **WHEN** 去重来源超过64个、关键来源证据无法核验，或对应冠军已经存在
- **THEN** 拒绝超限或不可靠来源，已有冠军保持；未执行接入的真实历史不得标记为已迁移。
### Requirement: Sim2GSE provides independent lightweight search and damage curves

系统 MUST 提供独立布尔选项 search_timeline，默认关闭，可由 [search] 配置或显式调用及命令行覆盖，优先级与其他搜索选项一致。该选项控制任务运行时的自动采集与导出，关闭时不采集曲线事件、不写曲线文件、不自动绘图，也不为曲线额外模拟；显式离线查看已有资料不触发新搜索或模拟。开启曲线不改变候选、评分、缓存或恢复身份，不联动详细诊断或已退役的规则／选择器能力。

开启后 MUST 复用已有评分及结果，在真实调用开始的单调墙钟上记录首个可用成绩、全局与路径成绩变化、停止和保存时点；准备、排队及诊断自身耗时不得从曲线时间扣除，不额外评分或开启原生详细追踪。业务搜索和结果保存结束后才离线输出事件数据及可离线查看的曲线。曲线记录与导出失败不得破坏有效业务结果；事件数量有界，达到上限时标记截断而非停止搜索。异常终止导致数据缺失时不得伪造完整曲线。

曲线 MUST 从零开始按10秒网格取当时最后已知成绩，首个成绩之前留空，不用未来成绩回填；成绩重估下降如实显示。停止或取消后的已知值可延伸展示，但必须明确标记已停止，不伪装继续搜索；失败或截断后的未知区间留空。恢复调用形成新时间段，保留旧段不覆盖、不拼成未中断的一次搜索。独立预训练各组使用同一公开调用时间起点并分别展示，不混为一条成绩曲线；预训练仅提供时间DPS曲线，不新增伤害桶适配，以下战斗伤害曲线契约继续适用于正式搜索。

多次运行 MUST 仅在角色配置、引擎及模拟条件、输入节奏、重置和爆发条件一致且可核验时归入同一可比组；算法选项和随机种子作为对照标签，路径按已有标识区分，不借此混用物理条件。条件缺失或不同的运行分别展示。战斗伤害曲线仅复用已确认来源和统计口径的原生1秒伤害时间桶，保留含宠物在内的原生统计口径，不重复叠加宠物、不强行归一到最终评分；缺少或无法证明适用的时间桶时明确说明不可用，不自动补跑模拟。

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

- **WHEN** 完成结果没有可确认统计口径的原生1秒伤害桶
- **THEN** 明确说明伤害曲线不可用，不自动补模拟；有合格时间桶时按原生口径绘制，不重复加入宠物伤害或归一为最终评分。
### Requirement: Sim2GSE rejects retired rule and selector execution

系统 MUST 移除自适应选择器及规则化起点能力和开关，连同专属职业规则执行库、四套优先规则／八模板解释、规则编辑、手动单步与专属原生观察执行链，不保留闲置第二执行路径。旧配置键及CLI参数即使为关闭值也须明确提示已移除，不静默忽略或退回旧算法。

正式搜索 MUST 仍使用原四类起点、既有随机变异及基础位置反馈，保留合法性／编译／评分／缓存／存储、材料适配、固定独立爆发、原预算及正式冠军与赢家回流。新任务不依赖当前职业规则库来识别专精、真实英雄及目标类型；旧完整v1内嵌规则声明、报告及冠军仅保留必要只读验真，不生成、解释、编辑或补采旧规则。旧不兼容未完成任务明确拒绝恢复，不改写历史身份。混合历史任务／报告、材料及冠军不可整库删除，专属数据对象的永久删除须另按具体对象授权，不把源码移除冒称数据全清。

#### Scenario: A retired option is supplied

- **WHEN** 用户通过配置或CLI传入退役选择器、规则起点或规则专属诊断选项，包括显式关闭值
- **THEN** 明确提示能力和开关已移除，不加载模型、不生成规则起点或专属观察，也不默默忽略。

#### Scenario: A default formal task runs without the profession rule library

- **WHEN** 用户从原公开入口启动普通正式搜索，当前职业规则库已不存在
- **THEN** 原四起点、基础随机变异／位置反馈及已核验起点和冠军仍可按原条件工作，正式完整诊断能力不降级。

#### Scenario: A complete old result is inspected

- **WHEN** 用户读取可核验的旧完整任务、v1代表或冠军证据
- **THEN** 按必要只读兼容核验原证据，不重启旧规则执行、不迁移身份，也不删除混合历史。
