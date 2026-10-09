# Sim2GSE Seed Training

## Purpose

让用户人工清洗一次外部材料后长期复用，人工启动独立训练，从同一共享数据中心提炼可供正常搜索使用的起点。

## Requirements

### Requirement: Sim2GSE registers cleaned seed materials in the existing shared store

系统 MUST 将人工清洗件及其来源、原件或引用、作者用法、清洗说明、结构家族、核心片段与可模拟程序保存在既有项目共享数据中心；不得为本流程建立第二套业务存储或向用户技能链接安装测试文件。清洗由人或代理逐项完成，登记入口不自动猜测原宏。

#### Scenario: A cleaned external material is registered

- **WHEN** 用户登记合法清洗件并指定已接入共享数据存储的项目
- **THEN** 同一中心保存程序及其可追溯来源，后续可重复读取和训练，登记不启动网络采集或原宏解释。
### Requirement: Sim2GSE retains seed sources and semantic boundaries

系统 MUST 区分语义保留、明确改写和当前不可表达材料，保留原件及逐项变化；待筛选来源、已处理、已入选和不可表达记录均可查询，未入选材料不得删除。已处理来源仍在可复用来源库中，不得将来源库列表冒称本轮未处理队列。成功施放日志不得被冒称原按键、等待指令或完整可循环宏；存在明确使用限制的材料必须保留限制和暂存原因。

#### Scenario: A material cannot currently be used as a program

- **WHEN** 用户登记没有可用程序的材料及其不可表达或使用限制原因
- **THEN** 来源和原因仍可查询，该材料不进入训练，不产生伤害成绩，也不被静默改写为支持状态。
### Requirement: Sim2GSE runs one manual training batch from a fixed input snapshot

系统 MUST 提供人工启动的一次处理入口，默认读取批次开始时的新清洗材料及同专精历史搜索最佳程序，处理后退出；不要求常驻服务。用户可明确限定已登记材料编号，仅处理该范围，不自动混入全库或历史成果。错误、非唯一编号及不支持的职业专精在计算前拒绝。训练期间新增材料不混入当前批次；历史来源可以跨角色，旧角色成绩不得直接用于标准角色下的排名。

#### Scenario: The user starts a training batch

- **WHEN** 用户启动训练且没有普通搜索正在运行
- **THEN** 系统固定本批输入，按场景处理可用来源及历史成果，保存状态并退出，不自行持续轮询或再次启动。

#### Scenario: The user restricts the material scope

- **WHEN** 用户明确指定少量已登记材料，或提供无效编号
- **THEN** 合法编号仅处理指定材料，保持正式收敛和独立复测标准；无效输入在实际计算前明确拒绝，不扩大训练范围。
### Requirement: Sim2GSE deduplicates seed training without losing source relationships

系统 MUST 在条件不变时复用可靠完成的训练及复测成果，保留各来源关系，不因重启重复计算。训练运行、预检查和查询默认使用同一独立爆发模式；历史无爆发模式须明确选择。标准角色、引擎、场景、爆发内容或按法改变后，旧成绩不得当作当前成绩，材料须重新评价。未完成任务及发布失败可恢复，不覆盖旧成果。

#### Scenario: The same sources or trained winner are encountered again

- **WHEN** 用户在条件未变时重复训练，或新历史记录含已经完整训练的同一程序
- **THEN** 系统关联来源而不重复搜索和复测；新行为候选继续处理，并如实显示新处理数。

#### Scenario: Training and query use the same default mode

- **WHEN** 用户未明确选择历史无爆发模式而运行、预检查或查询训练
- **THEN** 三个入口均使用独立爆发模式及其条件和记录；明确选择历史模式时只读取对应范围，不混入其他模式成绩。
### Requirement: Sim2GSE trains seeds with the locked standard character profile

系统 MUST 默认使用当前已核验引擎配套的完整标准角色进行训练，不使用旧版或私人角色冒充标准角色；明确指定其他模板时如实标明。所需模板缺失须在计算前报错。训练与页面模拟采用一致的角色检查、爆发兼容及动作限制，各自保留实际角色和训练或搜索规则。单目标与群体场景分别处理，不混用不同条件的成绩。

#### Scenario: A seed from another character is assessed

- **WHEN** 来源角色不同于本批标准角色
- **THEN** 系统在本批完整标准配置及实际参数下重新评价该程序，保留输入身份，不把来源旧成绩作为当前成绩。

#### Scenario: The engine changes or the standard template is missing

- **WHEN** 当前受检构建改变，或所需标准模板缺失
- **THEN** 默认训练定位当前构建配套模板；模板缺失则在模拟前失败，不能静默退回旧版本目录。
### Requirement: Sim2GSE gives each training path independent complete rounds

系统 MUST 为每个候选独立搜索至连续两个完整轮次没有确认改善后停止，确认改善全局最佳即清零，不设置固定五轮封顶。起点评分不算搜索轮次；不足一轮候选数量的轮次不增加无改善计数，但确认改善仍清零。每轮最多16候选，单条路径累计搜索上限600秒，候选总上限保持。沿用现有评分、动作空间、选择概率与缓存。现有生成机制无法提出新合法候选时也可正常结束；预算、候选上限或取消提前结束不得冒称收敛或发布新库。参考模拟与独立复测单独记录，不能把多候选整批冒称一次600秒普通搜索。新训练规则与旧固定五轮记录分开，旧成绩保留且不得冒称新规则验收。

#### Scenario: A training path has two complete unimproved rounds

- **WHEN** 一条候选路径连续两个完整轮次未确认改善
- **THEN** 该路径结束搜索，记录实际轮次、耗时、缓存和新增模拟量，完成独立复测后按既有规则筛选；其他候选独立处理。

#### Scenario: An improvement arrives after an unimproved round

- **WHEN** 已有无改善计数的路径确认找到更好的全局最佳，包括不足一轮候选数量的轮次
- **THEN** 无改善计数清零，继续搜索，持续改善时可以超过五轮；预算和其他上限仍有效。

#### Scenario: Training reaches a budget or candidate limit before convergence

- **WHEN** 训练尚未达到连续无改善或无新合法候选条件就耗尽预算、达到候选上限或被取消
- **THEN** 保存实际进度并报告未完成，旧入选库保持，不以旧五轮条件或部分结果冒称训练完成。
### Requirement: Sim2GSE selects retested performance and structural seed representatives

系统 MUST 在未参与搜索的三个固定随机条件下分别复测初始、优化后及现有代表，复用既有配对比较；成绩替换要求95%区间下限大于零，样本不足不得用于替换。另可保留少量合法、完整评分且可继续修改的不同结构家族代表；结构核心必须仍存在于被选程序中，来源标签不得盲目继承给已丢失核心的优化结果。后者可作为普通历史成果。每场景新增代表最多四个，不按作者或来源凑数量。

#### Scenario: Search improves damage but removes the registered core

- **WHEN** 优化后程序不再包含来源核心片段
- **THEN** 系统不将其当作该结构家族的保留证据；可将优化结果作为历史成果，并另行评价仍保留核心的初始结构代表。
### Requirement: Sim2GSE publishes seed snapshots automatically and preserves the old library on failure

系统 MUST 自动以同一逻辑键原子写入完整小型入选快照，不要求逐个确认入库，也不生成日常复测报告。成功前旧快照保持可用；发布失败允许基于可靠已完成结果重试。暂时不可读、明确损坏、模拟失败或预算不足应如实报告，不能静默置空库、伪造成功或把多键写入称为事务。

#### Scenario: Publication fails after training

- **WHEN** 训练结果已经可靠保存，但新快照写入失败
- **THEN** 旧入选库不变，入口报告失败，重新启动可继续发布而不重复可靠完成的计算。
### Requirement: Sim2GSE reads selected seeds once without running training in normal search

系统 MUST 在正常搜索初始化时只读取对应职业、专精、场景及引擎身份的小快照，按当前角色合法性和编译限制检查并去重，在原四类起点后追加最多四个代表；不更改用户角色配置、不扫描全历史、不启动训练或复测。快照固定到当前任务，恢复时沿用原快照，中途不刷新。空库沿用原搜索；身份不适用的候选跳过，读取异常不得掩盖为空库。

#### Scenario: A normal task starts with a usable library

- **WHEN** 用户启动正常搜索，且存在身份适用的入选快照
- **THEN** 任务读取一次快照，将合法且不重复的代表追加到原起点后，并通过原搜索继续评价和修改；搜索及归档不触发训练反馈计算。
### Requirement: Sim2GSE prioritizes normal search over manual seed training

系统 MUST 让普通搜索不等待训练：训练开始前发现普通搜索则退出；训练中普通搜索启动时，通过现有取消能力停止本批拥有的模拟并保留旧快照，不按进程名终止其他任务。允许短暂取消收尾窗口，不承诺物理零重叠；两个训练场景应由同一批次活动管理。

#### Scenario: A normal search starts during training

- **WHEN** 训练正在模拟而用户启动普通搜索
- **THEN** 普通搜索立即继续，训练取消自己的计算并保留可靠证据及旧库，其他进程不被终止。
### Requirement: Sim2GSE distinguishes batch seed evidence from original macro and game equivalence

系统 MUST 将来源方案、成员、来源版本、清洗程序、行为去重、实际完成路径及入选代表分别计数，保留初始与最终程序、核心保留、缓存和真实新增模拟证据。循环检查必须关注回绕及后期执行；请求迭代数与有效统计样本应区分。固定标准角色的改写件可运行不等于原宏完整复现、游戏验收或正常600秒搜索收益。性能比较应包含准备、搜索、归档和返回，新增起点评分成本应单独说明；缓存优势不得全部归因于起点。

#### Scenario: ABC and the existing full corpus are accepted

- **WHEN** ABC及已有社区、日志和插件材料完成清洗、批测与集中评审
- **THEN** 用户可核对实际数量、改写、去重、核心保留和入选原因；未通过或有使用限制的材料保留，不将其报成全数支持或全网穷尽，不将未测游戏与正常搜索收益报成通过。
### Requirement: Sim2GSE accepts long castsequences as searchable seed programs within macro limits

系统 MUST 在搜索起点入口接受含2至32个成员的受支持原生施法序列，同时遵守255字节宏文本、合法动作、重置、展开与导出一致性限制；不得仅因超过旧的短成员上限而拒绝。多个独立施法序列按各自成功施放推进状态处理，不能为接入而展平为不同推进规则。该能力不扩展其他原宏条件或高级控制结构。

#### Scenario: A cleaned seed contains more than four castsequence members

- **WHEN** 清洗起点含5至32成员的施法序列，且宏文本及其他编译模拟条件均合法
- **THEN** 起点可进入现有评分和搜索，不被旧短成员限制拦截；超过32成员或255字节时明确拒绝，不绕过限制。
