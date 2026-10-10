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

系统 MUST 直接输出搜索在用户指定场景和按键节奏下选中的可导出序列，报告搜索伤害、有效样本、自由选招参考伤害及二者比例；不再强制最终五节奏独立复测，也不因该复测回退到初始序列。搜索成绩 MUST 与独立复测及实际游戏验收明确区分，不承诺收益比例或全局最优。

#### Scenario: Search completes with a valid candidate

- **WHEN** 搜索结束且存在完整评分并通过导出一致性检查的已选候选
- **THEN** 系统导出该候选，显示搜索结果与参考比例，明确未进行最终独立复测、游戏效果尚待验证，不启动最终五节奏复测或其回退。
### Requirement: Sim2GSE respects the confirmed runtime budget

系统 MUST 对每场优化遵守默认累计600秒计算上限，准备及评分均计入该场预算。页面依次运行两场，各自最多600秒；公共准备、两场计算及整理分别显示实际用时。停止和收尾未完成时不能显示已完全停止。

#### Scenario: Both scenes run

- **WHEN** 用户一次启动单目标和5目标
- **THEN** 第一场停止及收尾后才开始第二场，各自累计计算预算；页面如实显示公共准备、两场用时及整理时间。

#### Scenario: Budget expires during search

- **WHEN** 某场累计预算耗尽
- **THEN** 停止计算并保存完整结果，有有效候选时输出选中候选，否则报告没有有效结果；半份报告不计成功，清理未结束不能显示已完全停止。
### Requirement: Sim2GSE resumes without mixing results

系统 MUST 在取消后保留完整结果和已用预算，恢复时不重复计数或重置预算；不同角色、引擎、搜索规则、输入模型、编译顺序、重置或采样条件不得混用成绩。

#### Scenario: User cancels a running evaluation

- **WHEN** 用户发出取消请求
- **THEN** 系统停止派发并终止本次所属模拟，保留完整已完成结果，不终止其他任务或配装器的模拟。

#### Scenario: Resume a cancelled search

- **WHEN** 同条件搜索任务在取消后恢复
- **THEN** 系统沿用已用预算、候选和已完成批次继续搜索，不启动最终复测，也不重复汇总样本。

#### Scenario: Resume conditions change

- **WHEN** 待恢复任务的引擎、搜索规则、角色或模拟条件与原记录不一致，或缺少核验规则所需的历史记录
- **THEN** 系统拒绝原地续跑，保留旧结果并要求按新条件建立任务。

#### Scenario: Simulation report is incomplete

- **WHEN** 引擎失败、超时或只留下损坏及部分报告
- **THEN** 系统不将该批次纳入成功排名或成功缓存，也不把它记为正常零分结果。
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

系统 MUST 在候选进入原生模拟前按实际逐次点击行为识别等价候选，使同一任务中的等价行为只执行一次候选编译和一次评分；非法或无有效动作的候选不得进入原生模拟。诊断日志总开关 MUST 默认关闭并优先于细分开关；关闭时不保存详细过程、持久化动作轨迹、诊断报告和性能统计，不仅为收集记录额外运行模拟，只保留搜索、位置修复、避免重复模拟、取消后继续所必需的数据及最终结果。算法临时需要的详细轨迹计算结束后 MUST 清理，不作为诊断历史保留。

#### Scenario: Two candidates have the same click behavior

- **WHEN** 两个候选的来源结构不同，但映射后的动作、顺序、动作块边界、空点击和重置行为相同
- **THEN** 系统将它们视为同一行为，复用已经成功编译的候选，不再次启动候选编译或原生评分。

#### Scenario: Diagnostics are not requested

- **WHEN** 用户按默认配置运行搜索，或关闭总开关但细分开关仍请求详细记录
- **THEN** 系统不产生额外诊断记录或仅用于诊断的模拟；轻量进度仍更新，必要结果与累计预算可靠保存，不为统计或进度每半秒保存完整历史。

#### Scenario: Diagnostics are enabled

- **WHEN** 用户显式打开总开关并启用相应细分记录
- **THEN** 系统允许相应诊断和统计；开关不改变候选身份、评分方式、合法性判断及位置修复，在同一候选、样本和随机条件下成绩与选择保持一致，不要求固定时间内两侧完成候选数相同。
### Requirement: Sim2GSE 按需要追加候选评估并复核晋级

系统 MUST（必须）在同轮可评估且不重复的方案中，只停止计算已有成绩明确落后的方案，不固定淘汰比例；默认按累计32、128、256次请求检查；仍允许调用方明确指定512上限，复用已完成成绩，仅给仍难分清的方案追加计算，判断不得读取尚未获得的后续成绩。更新原赢家前 MUST（必须）核对双方相同计算量的已完成成绩并通过独立晋级复核，不能把同轮胜出或计算量不同的平均伤害直接当成晋级依据。成绩缺少合法的伤害波动统计时 MUST（必须）拒绝将其作为有效筛选依据，并在有其他有效方案时继续任务。

#### Scenario: 同轮有明确落后的方案

- **WHEN** 同轮方案完成当前层评估，其中某方案考虑已观察伤害波动后仍明确落后
- **THEN** 系统停止给该方案追加计算，其他方案复用当前层成绩；没有固定保留一半的要求，也不读取该方案未计算的后续成绩。

#### Scenario: 当前成绩仍难分清

- **WHEN** 同轮方案或挑战原赢家的双方，在当前层仍难分清
- **THEN** 系统只追加缺少的下一层计算，并按双方相同计算量核对；达到上限后才按同层平均成绩决定是否发起独立晋级复核。

#### Scenario: 本轮只剩一个方案

- **WHEN** 同轮筛选只剩一个方案，但尚未完成与原赢家的核对及独立晋级复核
- **THEN** 系统继续保留原赢家，该方案不能仅凭本轮胜出替换原赢家。

#### Scenario: 伤害波动统计残缺

- **WHEN** 某批成绩的伤害波动统计缺失、非法或与用于评分的伤害统计不一致
- **THEN** 系统不把该批成绩作为有效筛选依据；若任务还有其他有效方案，继续搜索并保留其结果。

#### Scenario: 晋级期间取消后恢复

- **WHEN** 用户在新方案与路线或全局原赢家的补算或晋级复核期间取消，再以相同条件恢复
- **THEN** 系统保留此前有效赢家及已完成成绩，补完尚缺的核对和复核，不重复已成功批次，不重置预算；新方案只有完成入档及晋级复核后才能成为赢家。

#### Scenario: 默认上限及显式原上限

- **WHEN** 用户未指定加测档位，或明确指定原512上限
- **THEN** 默认按累计32、128、256检查；明确指定512时仍按累计32、128、512检查，双方均沿用独立晋级复核、预算及按本次实际有效起点数确定的完整无改善停止规则。
### Requirement: Sim2GSE preserves complete checks while reducing redundant search work

系统 MUST（必须）在模拟或编译已结束后及时返回，不为等待下一次固定检查而延迟完成；普通搜索同层最多同时评估两个单线程候选；人工起点训练使用其明确配置的同层并发上限，仍按原顺序使用结果，并在整层完成后筛选，不跨层提前取得成绩。导出所需的完整检查 MUST（必须）一次启动完成而不删除任何检查；调用方已指定报告目标时，一次模拟只生成该份完整交换报告，未指定时保留原默认报告。晋级判断与保存摘要 MUST（必须）使用同一次比较结果，不重复计算相同比较；评分、样本、随机条件、比较方法、晋级门槛、报告字段和类型保持原规则。取消、超时及失败仍有效，完整成功结果须保存且恢复不重算，部分结果不得作为成功。

#### Scenario: Simulation or compilation has already exited

- **WHEN** 本任务的模拟或编译程序已经退出，包括退出与取消或超时同时发生
- **THEN** 系统及时取得结束结果，不继续固定等待；取消、超时和本任务所属程序的收尾仍按原规则执行。

#### Scenario: Two candidates complete in the opposite order

- **WHEN** 普通搜索的同层两个候选同时评估且后一个先完成
- **THEN** 系统最多使用两个单线程引擎，按原顺序使用完整成绩，整层结束后筛选；停止时保留已完整完成的成绩，不派发新候选，也不重算已成功结果。

#### Scenario: A candidate is checked for export

- **WHEN** 系统核验某个候选的完整导出
- **THEN** 一次启动完成校验码、真实导入、动作顺序和篡改拒绝检查，仍执行最终编码往返核验；任一检查失败时不发布导出。

#### Scenario: Caller supplies a complete report destination

- **WHEN** 调用方已指定一次模拟的完整交换报告目标，或沿用未指定目标的原调用方式
- **THEN** 指定时只生成该份完整报告，未指定时保持默认报告；字段和类型保留，解析核验成功后才发布，失败或部分报告不能登记为成功。

#### Scenario: A promotion decision is recorded in the summary

- **WHEN** 系统完成一次晋级比较并保存其摘要
- **THEN** 晋级判断与摘要复用该次比较的相同结果，不重复计算该比较；种子、重采样次数、比较方法和晋级门槛保持原规则。

#### Scenario: Manual training candidates complete out of order

- **WHEN** 人工起点训练明确使用4并发，且同层候选按不同顺序完成
- **THEN** 系统最多同时使用4个单线程评分引擎，按预先固定的候选顺序使用完整成绩，整层结束后筛选；保留可靠成功结果，不改变评分、样本、随机条件或复测规则。
### Requirement: Sim2GSE rotates valid search starts with a matching stagnation limit

系统 MUST 在正常搜索初始化后，将共用连续完整无改善停止门槛固定为实际合法、行为去重且成功评分建立的路径数；四条为四轮、八条为八轮，非法、重复或评分失败输入不得虚增门槛。初始化评分不计搜索轮次，任何确认改善全局最佳的轮次清零；不足一轮候选数量的轮次不增加计数，但确认改善仍清零。路径依现有顺序轮转，一条路径无法产生新合法候选时标记并跳过，其他路径继续，只有全部路径均无法产生候选才按候选空间停滞结束。跳过路径不冒算完成轮次、不缩小已固定门槛；取消恢复沿用已保存的轮转位置、评分和累计预算。每轮最多16候选、累计32/128/256评分分档、候选总上限与正常任务600秒总预算保持，不增加逐路径无改善计数、资源权重或重启。预算和其他上限仍可能提前结束，不承诺无条件公平。旧规则任务不得绕过身份检查原地恢复，既有入选程序可进入新任务重新评分，不在正常搜索中现场重训。

#### Scenario: The task initializes four or eight valid starts

- **WHEN** 正常任务分别成功建立四条或八条有效路径
- **THEN** 无改善门槛分别为四或八个完整搜索轮次；在预算和其他条件允许时，一圈轮转给每条可搜索路径一次机会，结果和保存后查询显示实际门槛。

#### Scenario: One path cannot propose a new legal candidate

- **WHEN** 当前路径无法产生新合法候选，而其他路径仍可搜索
- **THEN** 系统跳过该路径并保存下一路径位置，其他路径继续；全部路径均无法产生候选时才整体以候选空间停滞结束。

#### Scenario: Search is cancelled after skipping a path

- **WHEN** 跳过路径后取消任务并在相同条件下恢复
- **THEN** 保留原门槛和预算，从已保存轮转位置继续，不重复已保存评分，不因跳过路径提前停止全部搜索。
### Requirement: Sim2GSE verifies complete engine identity when upgrading

系统 MUST 使用适配已核实正式客户端、版本一致且可重新构建的引擎；版本或构建内容不匹配时拒绝计算和恢复。仅做内部整理时，同一版本和相同输入下的动作目录、报告中的战斗数据与战斗行为须保持一致，开关诊断记录不能改变技能执行。升级后以固定角色确认核心行为没有回归，并能恢复完整旧版本，保留历史任务和成绩；不同版本不混用成绩，不要求伤害、精确时刻或搜索路径相同。

#### Scenario: Engine artifacts have mixed identities

- **WHEN** 引擎程序与其版本记录不一致
- **THEN** 拒绝执行或恢复并保留旧结果，不能将不一致产物当作通过验证。

#### Scenario: A client matched engine is upgraded

- **WHEN** 新引擎匹配已核实客户端且固定角色行为回归通过
- **THEN** 按新身份创建任务；旧记录不混入新成绩，实际游戏及未覆盖专精另记未验证。

#### Scenario: The engine is reorganized without a version change

- **WHEN** 仅整理同一版本引擎，并使用相同角色、序列和运行条件
- **THEN** 用户得到一致的动作目录、报告中的战斗数据和战斗结果；版本说明及其他非战斗记录按事实变化，开启或关闭诊断记录不改变序列执行。
### Requirement: Sim2GSE provides a repository scoped engine upgrade entry

系统 MUST 提供本仓库专用、最小自包含的统一升级入口，供Codex（代码代理）和Claude Code（代码代理）使用同一份流程和核验能力。入口给出明确升级步骤及开发、验证、审查和交付要求；复用现有仓库能力，不依赖个人记忆，不注册公共市场。前后核验只读取必要的指定证据，不自行修改数据或启动计算；缺失、损坏或版本不符须明确失败。日常测试不增加重训练或提高预算，两端复用同一次真实训练至页面验收的证据。

#### Scenario: A maintainer starts an upgrade

- **WHEN** 维护者从本仓库升级入口更新引擎
- **THEN** 按明确五步及开发门禁执行一次升级，专项沿用正式训练规则；两端复核同一份真实证据，不重复训练。日常验证不加入重训练或增加预算，失败保留准确恢复位置。

#### Scenario: Upgrade evidence is incomplete or from an old engine

- **WHEN** 前后核验发现指定记录缺失、损坏或引擎及处理条件不一致
- **THEN** 返回非零结果并报告原因，不据文件存在判成功；两端实际调用不可用和游戏未测分别保留未完成事实。
