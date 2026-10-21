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

系统 MUST 对每场正常搜索遵守默认累计600秒计算上限，准备及评分均计入该场预算。页面依次运行两场，各自最多600秒；公共准备、两场计算及整理分别显示实际用时。停止和收尾未完成时不能显示已完全停止。人工种子训练按其独立停止规则执行，不套用此正常搜索总预算。

#### Scenario: Both scenes run

- **WHEN** 用户一次启动单目标和5目标
- **THEN** 第一场停止及收尾后才开始第二场，各自累计计算预算；页面如实显示公共准备、两场用时及整理时间。

#### Scenario: Budget expires during search

- **WHEN** 某场累计预算耗尽
- **THEN** 停止计算并保存完整结果，有有效候选时输出选中候选，否则报告没有有效结果；半份报告不计成功，清理未结束不能显示已完全停止。
### Requirement: Sim2GSE resumes without mixing results

系统 MUST 在取消后保留完整结果和已用预算，恢复时不重复计数或重置预算；不同角色、引擎、搜索规则、输入模型、编译顺序、重置或采样条件不得混用成绩。规则起点和自适应选择器两个独立选项 MUST 随任务及训练路径冻结并参与身份核验；缺少选项或规则身份不足的旧未完成任务不得按新默认值静默切换搜索方式。拒绝恢复不删除已保存结果，也不阻止符合来源核验要求的已完成成果作为新任务起点重新评分。

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

#### Scenario: A previous unfinished task has no explicit search mode

- **WHEN** 旧未完成任务缺少两个搜索选项或不能证明与当前搜索规则一致
- **THEN** 系统拒绝原地续跑并保留已保存结果可读；建立新任务时重新确定搜索方式和评分，不把旧成绩冒充新条件成绩。
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

系统 MUST 在正常搜索初始化后，将共用连续完整无改善停止门槛固定为实际合法、行为去重且成功评分建立的路径数；四条为四轮、八条为八轮、十条为十轮，非法、重复或评分失败输入不得虚增门槛。初始化评分不计搜索轮次；确认改善全局最佳，或非初始化候选经既有晋级核验确认改善所在路径，均算本轮有改善并清零同一个全局连续无改善计数。未通过晋级核验或仅建立初始起点不算改善；不足一轮候选数量的轮次不增加计数，但确认改善仍清零。此改善定义共用于正常搜索和人工训练，不受规则起点或选择器选项控制。正式冠军存在时，先核验并按当前条件评分建立保留基线，作为首条路径优先轮转和继续变异；其余原生、训练代表和训练冠军保持相对顺序。没有正式冠军时沿用既有起点顺序。一条路径无法产生新合法候选时标记并跳过，其他路径继续，只有全部路径均无法产生候选才按候选空间停滞结束。跳过路径不冒算完成轮次、不缩小已固定门槛；取消恢复沿用已保存的轮转位置、评分和累计预算。每轮最多16候选、累计32/128/256评分分档、候选总上限与正常任务600秒总预算保持，不增加逐路径无改善计数、资源权重或重启。预算和其他上限仍可能提前结束，不承诺无条件公平。旧规则任务不得绕过身份检查原地恢复，既有入选程序可进入新任务重新评分，不在正常搜索中现场重训。

#### Scenario: The task initializes four eight or ten valid starts

- **WHEN** 正常任务分别成功建立四条、八条或十条有效路径
- **THEN** 无改善门槛分别为四、八或十个完整搜索轮次；在预算和其他条件允许时，一圈轮转给每条可搜索路径一次机会，结果和保存后查询显示实际门槛。

#### Scenario: One path cannot propose a new legal candidate

- **WHEN** 当前路径无法产生新合法候选，而其他路径仍可搜索
- **THEN** 系统跳过该路径并保存下一路径位置，其他路径继续；全部路径均无法产生候选时才整体以候选空间停滞结束。

#### Scenario: Search is cancelled after skipping a path

- **WHEN** 跳过路径后取消任务并在相同条件下恢复
- **THEN** 保留原门槛和预算，从已保存轮转位置继续，不重复已保存评分，不因跳过路径提前停止全部搜索。

#### Scenario: A path improves without beating the global champion

- **WHEN** 非初始化候选经既有晋级核验改善所在路径，但仍未超过全局最佳
- **THEN** 本轮记为有改善并清零全局连续无改善计数；全局最佳不被较低成绩覆盖，正式搜索门槛仍为初始化时确定的实际有效路径数。

#### Scenario: A partial round has no verified progress

- **WHEN** 一轮不足规定候选数量且没有有效全局或路径晋升，或候选未通过既有晋级核验
- **THEN** 不把未完成轮次计为完整无改善轮，也不把未经核验的分数变化当作改善。
### Requirement: Sim2GSE verifies complete engine identity when upgrading

系统 MUST 使用适配已核实正式客户端、版本一致且可重新构建的引擎；版本或构建内容不匹配时拒绝计算和恢复。仅做内部整理时，同一版本和相同输入下的动作目录、报告中的战斗数据与战斗行为须保持一致，开关诊断记录不能改变技能执行。升级后以固定角色确认核心行为没有回归，并能恢复完整旧版本，保留历史任务和成绩；不同版本不混用成绩，不要求伤害、精确时刻或搜索路径相同。

正式任务 MUST 在每次启动或恢复时完整核验两套所需引擎，本次后续准备与双场计算可复用本次核验结果；新任务和下一次恢复必须重新核验，不能直接信任旧任务保存的身份。双场各自保留独立累计预算。角色、天赋、审核爆发、规则和报告核验仍保持。此范围不承诺在同次已验后的执行途中再次发现人为替换引擎文件；下次启动或恢复仍须拒绝不符产物。

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
- **THEN** 两套引擎各完整核验一次，本次双场复用该结果但不共享计算预算；以后新任务或恢复重新核验，旧身份不能绕过核验。
### Requirement: Sim2GSE provides a repository scoped engine upgrade entry

系统 MUST 提供本仓库专用、最小自包含的统一升级入口，供Codex（代码代理）和Claude Code（代码代理）使用同一份流程和核验能力。入口给出明确升级步骤及开发、验证、审查和交付要求；复用现有仓库能力，不依赖个人记忆，不注册公共市场。前后核验只读取必要的指定证据，不自行修改数据或启动计算；缺失、损坏或版本不符须明确失败。日常测试不增加重训练或提高预算，两端复用同一次真实训练至页面验收的证据。

#### Scenario: A maintainer starts an upgrade

- **WHEN** 维护者从本仓库升级入口更新引擎
- **THEN** 按明确五步及开发门禁执行一次升级，专项沿用正式训练规则；两端复核同一份真实证据，不重复训练。日常验证不加入重训练或增加预算，失败保留准确恢复位置。

#### Scenario: Upgrade evidence is incomplete or from an old engine

- **WHEN** 前后核验发现指定记录缺失、损坏或引擎及处理条件不一致
- **THEN** 返回非零结果并报告原因，不据文件存在判成功；两端实际调用不可用和游戏未测分别保留未完成事实。
### Requirement: Sim2GSE combines four native four selected and two champion sources

系统 MUST 在正式搜索保留四类原生起点与至多四个既有训练代表，并独立消费至多一个最终训练冠军与一个角色正式冠军；所有来源经过当前角色合法性、编译与行为去重后，最多形成十条真实有效路径。等价行为只建立一条路径，但保留全部来源，不能复制或补选凑数。新增来源不扩大每场600秒、样本、轮次候选数或并发上限，不改变独立训练入口。

#### Scenario: All ten sources are legal and behaviorally distinct

- **WHEN** 四类原生、四个代表及两个冠军均合法且行为不同
- **THEN** 十条实际路径参与当前角色评分及变异，无改善门槛按真实成功路径数确定。

#### Scenario: A champion coincides with another source

- **WHEN** 冠军适配后的行为与原生或代表相同
- **THEN** 只建立一条真实路径并保留各来源，不重复评分、不虚增路径数。
### Requirement: Sim2GSE retains and reliably advances the formal champion

系统 MUST 为相同冻结角色资料、职业专精及完整正式条件保留可追溯正式冠军；不同目标、装备、天赋、按法、引擎、评分或爆发条件隔离。常规任务只按对应条件读取冠军，不扫描全历史。继承只复用程序，先以当前条件核验评分建立保留基线；只有既有可信比较证明更优的完整候选才能接替，打平、部分挑战或未证明改善时保留原冠军。行为相同不更换原来源或递增版本，同一发布意图的恢复保持幂等。

系统 MUST 先可靠保存完整正式成果及其候选、报告、导出和晋级证据，再核验当前冠军版本发布；陈旧任务不能覆盖已变化冠军。结果与发布状态分别可查，发布失败保留可靠成果并允许恢复补发布。恢复沿用已冻结来源、已用预算和成功批次，不为补保存或补发布重复模拟；完成或预算耗尽的恢复亦须处理可靠待发布成果。取消只能发布已完成且具备合格证据的赢家，部分结果不能接班。附属发布状态损坏不得遮蔽已有可靠结果，也不得伪称发布成功。

#### Scenario: A new task inherits the same character champion

- **WHEN** 新正式任务具有同角色、专精和完整条件，且冠军证据可核验
- **THEN** 冠军程序在当前条件重新评分、保留并继续变异，原来源和当前成绩分别可查询。

#### Scenario: A stale task tries to publish after another task has advanced the champion

- **WHEN** 另一个任务已更新冠军版本，而旧任务完成挑战
- **THEN** 旧任务保留自身可靠结果并明确未接班，不覆盖新冠军。

#### Scenario: Publication was interrupted after reliable results were saved

- **WHEN** 可靠完整赢家已保存，但发布未完成，用户恢复任务
- **THEN** 按冻结条件和当前版本幂等补发布，不重复成功评分、不重置预算；来源不可靠或版本冲突时不冒称接班成功。
### Requirement: Sim2GSE imports bounded verified historical formal candidates

系统 MUST 通过明确管理操作接入最多64个去重的已知正式来源任务；不把历史接入作为每次网页搜索的全表扫描。仅在对应正式冠军缺席时接入，已有冠军不得被导入覆盖。每个来源的角色、专精、关键引擎/爆发/按法条件和完整正式程序及报告关联必须可证；无法证明时明确拒绝并保留原因。范围内旧成绩只用于选候选，旧规则程序须按当前规则重新评分并经正常可靠保存与发布建立冠军，不搬用旧缓存成绩。

#### Scenario: An explicit bounded source set contains a historical best program

- **WHEN** 管理操作提供可核验且去重后不超过64个来源，当前尚无对应冠军
- **THEN** 仅核验该范围并选择候选，按当前条件重新评分后正常保存发布；报告限定范围，不声称代表全部历史。

#### Scenario: The source set is too large or a champion already exists

- **WHEN** 去重来源超过64个、关键来源证据无法核验，或对应冠军已经存在
- **THEN** 拒绝超限或不可靠来源，已有冠军保持；未执行接入的真实历史不得标记为已迁移。
### Requirement: Sim2GSE independently controls rule starts and adaptive candidate selection

系统 MUST 在共用配置的 [search] 区域提供 rule_initialization_enabled 和 adaptive_selector_enabled 两个独立布尔选项，均默认关闭；正式搜索、双场入口和人工训练使用相同解析规则。显式调用或命令行选项优先于配置，配置优先于默认值；未传选项不覆盖配置，显式关闭可以覆盖配置开启，非布尔值必须明确拒绝。搜索选项不得混入物理模拟条件。

规则起点关闭时 MUST 保持均匀、频率、重复、种子打乱四类原生起点，不执行规则起点生成；开启时仅替换原均匀起点名额，其他原生起点、既有代表和冠军来源保持，不增加起点名额或暗中修改正式首次爆发时点。人工训练始终以当前材料本身为起点，不因规则起点选项替换材料或追加训练路径。

自适应选择器关闭时 MUST 使用既有随机变异及其候选生成、反馈和晋级路径，而非空模型的自适应路径；不读取、更新已有模型或产生选择器专用诊断，既有模型文件保持。开启时使用现有自适应选择和反馈能力。四种组合均保持共用评分、合法性、去重、保存及成果复用规则。选择器所需可选依赖未安装时，关闭模式仍可运行；显式开启则报告缺少依赖，不自动安装或静默退回其他搜索方式。

#### Scenario: Search starts with no feature options

- **WHEN** 用户未提供两个搜索选项，配置中也未设置
- **THEN** 正式搜索使用原四类原生起点和既有随机候选搜索，不生成规则起点，不触及模型或写选择器专用诊断；既有训练代表及冠军仍按各自条件复用。

#### Scenario: Either feature is enabled independently

- **WHEN** 用户分别选择全关、仅规则起点、仅选择器或两者全开
- **THEN** 每种组合仅启用对应能力；规则起点只替换一个原生名额，正式首次爆发时点和物理模拟条件不因开关改变。

#### Scenario: Explicit invocation overrides shared configuration

- **WHEN** 配置开启某选项但调用或命令行显式关闭，或未传对应选项，或提供非布尔配置
- **THEN** 显式关闭生效，未传时保留配置，非法类型明确失败；正式与训练入口结果一致。

#### Scenario: Training disables selection while keeping its material

- **WHEN** 人工训练关闭选择器，并分别开启或关闭规则起点
- **THEN** 两种设置都以当前材料为训练起点并完成既有搜索与独立复测，不读取或更新模型；两个选项仍按各自实际值记录到训练路径身份。

#### Scenario: Optional selector dependencies are missing

- **WHEN** 环境未安装自适应选择器可选依赖
- **THEN** 选择器关闭的搜索和训练可用，显式开启时给出明确依赖错误，不自动安装或静默改用另一搜索方式。
### Requirement: Sim2GSE provides independent lightweight search and damage curves

系统 MUST 提供独立布尔选项 search_timeline，默认关闭，可由 [search] 配置或显式调用及命令行覆盖，优先级与其他搜索选项一致。该选项控制任务运行时的自动采集与导出，关闭时不采集曲线事件、不写曲线文件、不自动绘图，也不为曲线额外模拟；显式离线查看已有资料不触发新搜索或模拟。开启曲线不改变候选、评分、缓存或恢复身份，不联动详细诊断、规则起点或选择器。

开启后 MUST 复用已有评分及结果，在真实调用开始的单调墙钟上记录首个可用成绩、全局与路径成绩变化、停止和保存时点；准备、排队及诊断自身耗时不得从曲线时间扣除，不额外评分或开启原生详细追踪。业务搜索和结果保存结束后才离线输出事件数据及可离线查看的曲线。曲线记录与导出失败不得破坏有效业务结果；事件数量有界，达到上限时标记截断而非停止搜索。异常终止导致数据缺失时不得伪造完整曲线。

曲线 MUST 从零开始按10秒网格取当时最后已知成绩，首个成绩之前留空，不用未来成绩回填；成绩重估下降如实显示。停止或取消后的已知值可延伸展示，但必须明确标记已停止，不伪装继续搜索；失败或截断后的未知区间留空。恢复调用形成新时间段，保留旧段不覆盖、不拼成未中断的一次搜索。人工训练各路径使用同一公开调用时间起点并分别展示，不混为一条成绩曲线。

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
