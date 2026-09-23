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

系统 MUST 在候选锁定后使用未参与选优的样本进行最终比较，提供可追溯的有效样本数、对照和差异区间，并分别记录名义、扰动、慢按、暂停及起始相位情景；最终复测不完整时须保留锁定候选作为证据不足的临时结果，只有完整复测未证实改善时才保留有效初始序列。

#### Scenario: Candidate reaches final evaluation

- **WHEN** 已锁定候选进入最终复测
- **THEN** 使用未参与搜索或验证选优的数据评估候选及相应对照，记录各情景结果，不将试验结果倒用于同轮候选选择。

#### Scenario: Complete evaluation does not establish improvement

- **WHEN** 全部规定的最终复测完整结束，但无法证实锁定候选优于有效初始序列
- **THEN** 系统导出有效初始序列，报告尚未证实改善，不承诺收益比例或全局最优。

#### Scenario: Final evaluation is incomplete

- **WHEN** 最终复测缺少任一规定情景、批次或样本而未完整结束
- **THEN** 系统导出锁定候选作为临时结果，明确显示复测未完成和证据不足，不把该结果标记为验证通过。
### Requirement: Sim2GSE respects the confirmed runtime budget

系统 MUST 在一次优化中遵守累计 10 分钟计算上限，搜索最迟累计第 7 分钟结束以预留复测时间，最多同时运行两个单线程引擎进程；停止后的必要清理须如实显示。

#### Scenario: Budget expires before final validation completes

- **WHEN** 累计计算预算耗尽而必需的最终复测尚未完成
- **THEN** 系统停止计算并保存完整中间结果，显示验证未完成；清理未结束时不能显示任务已完全停止。
### Requirement: Sim2GSE resumes without mixing results

系统 MUST 在取消后保留完整结果和已用预算，恢复时不重复计数或重置预算；不同角色、引擎、输入模型、编译顺序、重置或采样条件不得混用成绩。

#### Scenario: User cancels a running evaluation

- **WHEN** 用户发出取消请求
- **THEN** 系统停止派发并终止本次所属模拟，保留完整已完成结果，不终止其他任务或配装器的模拟。

#### Scenario: Resume a locked candidate

- **WHEN** 同条件的已锁定候选任务在取消后恢复
- **THEN** 系统沿用已用预算和已完成批次，继续该候选复测，不重新选择候选或重复汇总样本。

#### Scenario: Resume conditions change

- **WHEN** 待恢复任务的引擎、角色或模拟条件与原记录不一致
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

系统 MUST 在受控模拟轨迹中区分输入、排队处理与原生技能执行，使测试者能按输入序号追查被替换或拒绝的动作，不把排队请求当成施法成功。

#### Scenario: A queued input does not execute

- **WHEN** 某次输入进入队列后被后续输入替换或在执行时被原生规则拒绝
- **THEN** 轨迹保留该输入的排队处理记录，但成功执行序列不包含该技能。
### Requirement: Sim2GSE keeps the TC queue comparison opt-in

系统 MUST 保持现有受控控制策略为默认，并允许测试者显式选择 TC（社区服务端）队列对照策略；切换策略不得改变序列步进或原生战斗结算，且不得将对照策略标称为正式服完整复刻。

#### Scenario: Comparison mode is selected

- **WHEN** 同一序列、角色条件和按键时间分别使用默认策略与 TC 对照策略运行
- **THEN** 两次结果标明所用控制策略，并各自输出可比较的原生执行轨迹；未显式选择时仍运行默认策略。
### Requirement: Sim2GSE labels offline validation accurately

系统 MUST 把离线模拟与正式服游戏内验收区分开；输出独立模拟成绩时不得把未达到的时序差异目标或借助实测反馈取得的成绩标作已达成。

#### Scenario: Offline result is produced without a new game test

- **WHEN** 只有自动测试和既有实测数据对照，而没有改后正式服游戏内验收
- **THEN** 结果标明游戏内验收未运行，并如实保留频率与时序差异，不声称达到未证实的精度目标。
