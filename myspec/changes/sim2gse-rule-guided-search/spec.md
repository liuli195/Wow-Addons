# Sim2GSE 规则初始化与自适应搜索开发规格

Status: planning
Triage: needs-info

日期：2026-10-16。本文件合并完整开发方案、可观察契约和必要源码证据，是三张开发票共同遵循的规范入口。交付文件仅本规格及 issues/01、02、03；不依赖旧讨论票或单独研究目录。当前方案设计已讨论，产品实现及真实原型验证尚未开展；整体审阅和真正的开始开发门禁仍须按流程完成。

## 问题与用户结果

当前一个基础起点来自目录均匀排列，后续修改依赖随机选择和固定启发式，未将已研究的APL规则、实际学生状态及跨任务学习贯通。目标是复用现有模拟和搜索能力，生成有依据的起点，并用可解释诊断指导值得模拟的合法修改。


1. 用户提交真实角色资料后，得到可合法导出的规则起点及来源说明。
2. 用户能区分静态估算、明确近似、未知条件与真实模拟证据。
3. 用户保留原有其他起点、训练代表、冠军、缓存、预算和晋级能力。
4. 用户看到实际学生状态对应的问题及具体对象、位置、改量，不接受教师状态代替学生诊断。
5. 用户的全部规则问题同时交给选择器，候选一次只做一个操作，不人工先挑一条规则。
6. 不同角色和专精可积累通用经验；继续旧任务不能回滚其他任务的新经验。
7. 非法表示、缺字段、未知条件及恢复问题明确报告，不静默删条件或改爆发。
8. 用户按三张开发票逐票讨论、实施、审查和验收，最终同条件新旧各600秒直接比较输出DPS。


## 1. 最终交付什么

用户从现有任务入口提交角色资料，得到合法可导出的 GSE 和既有搜索成绩。内部改两处：

1. 四个基础起点中，只将“目录均匀排列”改为“通用规则＋专精绑定生成的起点”。另三个来源保留；训练代表最多四个，训练冠军与正式搜索冠军各一个；去重后最多 4＋4＋2，不保证一定有十个。
2. 所有起点及新启动的既有训练统一使用：学生模拟诊断→合法修改候选→Coba 选择一个操作→既有模拟和晋级→积累经验。整体替换旧随机算子选择、固定启发式和搜索中的洗牌兜底。随机初始化仍保留。

保留已有模拟、缓存、行为去重、预算、晋级和冠军机制。旧任务不原地换算法、不自动重训；兼容的旧结果可作新任务起点，旧分数不冒充新验证。

本轮不做：完整 APL 解释器、战斗实时调度器、自动改爆发宏、片段/特征挖掘、新增预训练种群或遗传算法、新数据库/常驻经验服务、多算法评测。通用能力首批落地已审核的邪 DK 绑定，不声称所有专精已经配置或验证。

## 2. 三类库如何配合

| 部分 | 放什么 | 不放什么 |
| --- | --- | --- |
| 通用规则库 | 下文八类意图、适用/让位/未知边界、可诊断与可修改方向 | 不写具体技能名、职业专属数值或固定45秒周期 |
| 通用过程库 | 复用的静态快照读取、CD与资源消费各一次示范、按机会排位、低频/间隔安排、资源填充、GSE编译和局部编辑过程 | 不含 if outbreak 等专精特判，不新增DSL或插件平台 |
| 专精规则库 | 把通用规则及过程绑定到实际按钮、完整APL条件、父列表与优先、资源类型、窗口/持续效果及有来源的参数 | 不删除动态条件，不把未知参数填成经验常数 |

“库”只表示清晰的数据与函数职责，不要求三个框架或服务。规则采用六项契约：范围、完整条件、期望动作、优先/让位、来源/所需状态、初始化/诊断/修复用途与表达能力。同一按钮在不同 APL 条目中的规则身份保留。

邪 DK 的骨架周转资源绑定为符能；符文仍约束执行和可排性，不与符能相加。Outbreak 的技能身份、疾病条件、低频过程选择及参数来源写在邪 DK 专精规则库；通用生成器只执行配置引用的过程。这一分层由用户 2026-10-16 15:13:31 的决定明确，具体持续时间数值并未因此自动批准。

### 2.1 已确认的邪 DK 简明循环规则

2026-10-17 用户确认以下十条，作为面向人的专精循环概述；编号不是固定 1→10 的 GSE 施放顺序，也不替代第4节的八类通用规则及其完整绑定条件。

1. 疾病不断，具备相应天赋并可用时优先腐化，爆发兜底。
2. 黑暗突变前用脓疮打击准备小食尸鬼层数。
3. 亡者大军、黑暗突变遵循爆发节奏。
4. 灵魂收割兼顾斩杀与黑暗突变配合。
5. 瘟疫降临安排在合适的爆发收尾。
6. 腐化兼顾爆发窗口和充能，禁断知识内保留对应优先级。
7. 镰刀增益快结束时补上。
8. 单体和 AOE（群体伤害场景）都允许枯萎凋零，利用其腐化联动并考虑目标留在地面。
9. 缺层用脓疮打击，有层用天灾打击，吸血鬼打击属于同一按键。
10. 单体死缠、AOE 扩散，优先利用触发并防符能溢出，替换形态归同一按键。

来源与保存边界：

- 本节保存用户确认的简明口径。[Wowhead 邪 DK 循环指南](https://www.wowhead.com/guide/classes/death-knight/unholy/rotation-cooldowns-pve-dps)是来源线索；此前仅检索索引可读，正文与英雄天赋切换未完整核验，不能称为已抓取或已核验的完整指南。
- 程序资料继续保留单体、AOE、英雄天赋、完整条件及优先级的结构化区别，源码依据仍固定为 SimC `eed909156d8eccbfca0f284cc271c080949d6a20`。简明口径不删除已有条件，不新增未核验的数值或硬阈值；枯萎凋零的单体初始化覆盖与原 APL 条件仍按3.2和第4节区分。
- 本次仅保存规则概述，不据此修改运行时优先级、冻结爆发宏或其节奏，不表示动态条件已实现或01已验收，也不启动02/03。

## 3. 初始 GSE 怎样生成

### 3.1 真实静态数据

按角色装备、急速、天赋和常驻加成取得动作的有效静态 GCD/CD、费用、确定性收益、资源初值/容量及必要恢复信息。不能统一假设1.5秒，也不能把目录基础 trigger_gcd 当成有效GCD；不要求预测所有战斗触发。

复用引擎已有动作和资源实现，只增加本批绑定需要的字段。数据必须具有明确采集时点和来源，不能从战后平均值倒推非战斗静态值。生命周期与最小导出接口仍须实现核验。

### 3.2 两层生成

1. 先考虑受保护爆发窗口的配合，再安排普通 CD/Buff，最后按资源规则填充。
2. 骨架沿一次生成路径排位：普通循环负责的各 CD 完成一次示范，绑定的资源消费动作完成一次示范，在最早完成这两类示范的位置收尾。按绑定动作及其实际静态费用判断，不累计一份资源容量；消费总量仅作报告。邪 DK 消费动作绑定符能，符文仍只约束动作可排性。
3. 这是起点估算，不要求资源先满后空、收支平衡、首尾所有状态恢复或下一轮CD就绪。长CD允许轮空，不以最长CD、最小公倍数或爆发45秒间隔强行拉长骨架。
4. 再在骨架上按八规则契约及其静态可判定范围调整顺序、频次、间隔和长度，形成初始GSE；第4条动态短窗口的初始化边界见下文。同一CD一轮尝试两次允许，最终序列无需维持最初覆盖计数；不为重复演示骨架而无依据铺长排列。

2026-10-16 用户最新确认：骨架由“消耗一轮资源”改为“消费动作示范一次”，覆盖此前容量目标；第二层仍为有限规则编辑，不把一次示范次数重新锁成最终序列要求。用户另批准邪DK单体初始化也示范一次枯萎凋零，前提为能力可用且对应天赋开启；此初始化覆盖策略写在专精绑定，保留原APL至少3目标条件和来源，明确不是上游单体推荐，不虚构减CD或固定周期。

2026-10-17 用户明确补充：灵魂收割在当前角色能力可用时，单体和AOE初始化都作为普通CD加入一次示范，不再以动态斩杀或黑暗突变条件未知为由排除。复用既有CD排位和真实静态GCD/CD/费用；不硬定施放时点，不修改冻结爆发。完整APL条件与优先保留为后续诊断依据，本次静态覆盖明确标为用户批准的示范，动态适用性仍为unknown。此决定不要求一次尝试成功，也不启动02/03。

2026-10-16 用户明确确认：第4条动态短窗口优化交由后续学生诊断与搜索处理。01静态初始化保留完整规则/专精绑定及 `unknown_not_applied`（未知、未应用）说明，不要求据此独立调序，也不将普通填充贴成该规则已执行；该边界不再作为01缺口阻断。02按学生实际窗口诊断和提出修改，03接入既有后续搜索流程，三票结构与执行顺序不变。

静态消耗账表示预计成功时的消费，失败尝试不能称为已实际消费。资源预留仅在源规则要求时采用；预计接近上限时选择适用消费，否则依据源优先及必要多资源账安排。未知疾病、伤口或随机触发条件仍标未知，不造第二个战斗模拟器。

### 3.3 从时间到点击

普通瞬发占GCD动作先采用已确认的保守初值：点击跨度＝ceil(该动作静态有效GCD／实际按键间隔)，动作尝试本身占一次，空点击数＝跨度−1。一次尝试后仍按现有语义推进，不默认增加重试。

该做法每机会可能多等不足一个按键间隔，累计代价由第8规则及搜索检查；不保证施放成功或最优。off-GCD、施法/引导及特殊动作另按引擎语义处理。空点击为0可省略，为1时现有搜索表示存在缺口，不能自动改成0或2。

CD除以静态GCD只用于估算施放机会间距，不能直接当GSE步骤数。多个动作争同一占GCD机会时按适用APL优先，其他顺延；越窗、越界或无法表达要报告，不挤入同槽或无限顺延。

### 3.4 Outbreak 与爆发边界

低频或间隔安排是通用过程。需要Outbreak时由专精绑定调用该过程，具体条件与参数来源在专精绑定中；不以短骨架每轮一次来决定频率，也不把“全场无病”伪装成GSE实时判断。可以使用顶层Action/WaitClicks平铺；仅不含等待的重复动作片段可用现有Loop。具体间距需来自已核验绑定参数，尚无被批准的固定秒数。

2026-10-16 用户批准邪DK初始化维护替代：仅当原生明确导出 `blightburst=true`，且Putrefy可用并纳入普通CD骨架时，专精绑定令 `periodic_action=None`，省略普通起点中的Outbreak及其周期尾等。Blightburst为false、缺失未知或Putrefy不可用时保留原Outbreak安排。Putrefy仍按原CD/伤害动作处理，不改为疾病固定周期；省略是用户初始化策略，不保证首次爆炸前或全程疾病覆盖，完整APL开场及断病兜底来源继续保留。

来源边界：固定SimC `sc_death_knight.cpp:12103–12130,12153–12157,12184–12188` 明确由Blightburst控制Putrefy的施病/延病；APL:372仍有Outbreak开场及断病兜底。Wowhead仅核对到只读索引，未全文核实；指南作为人工来源线索，不以简化描述覆盖上述固定源码及完整条件，不引入自动抓取规则系统。

当前独立爆发宏内容与节奏不变，Army/DT/Blightfall不加入普通循环搜索。当前邪DK配置在3/48/93/138秒安排爆发输入，各1秒；这是当前绑定配置，不是通用周期。普通输入暂停、位置保留，墙钟和资源/CD仍继续。按键尝试不等于施放成功，静态普通循环不保证每轮对齐真实Buff窗口。

## 4. 八条规则及可提出的修改

下表是实施范围。每条仍须保留专精绑定的完整条件、父入口、前序让位和例外；表内摘要不能替代完整源条件。硬GSE合法性、可优化规则事实和学习经验参数分开。

| 规则 | 通用含义与当前邪DK绑定 | 有证据时的合法修改 | 不能误判的边界 |
| --- | --- | --- | --- |
| 1 窗口或满充能释放 | AoE Putrefy：DT开启 **或** 当前满充能；至少3目标及前序优先保留。单体条目独立绑定 | 前移、补一次尝试、缩短关联间隔 | 非DT满充能可合法使用；被高优先占用不自动违规 |
| 2 低优先消费预留资源 | 单体低位Death Coil：Army剩余>5 **或** 符能缺口<50；只约束此低位条目 | 后移/减少该低位消费，或提前有依据的前置动作 | 不改成固定留50符能，不禁止其他高位Death Coil；5目标案例不能证明单体行为 |
| 3 近满资源时及时消费 | 高位Epidemic的完整OR条件及epidemic_prio；deficit<15只是其中一支 | 提前或补消费；仅在证据明确时减少冗余生成 | 近满不等于已溢出；不能越过预留/窗口的源优先 |
| 4 短窗口及时用指定动作 | Scourge Strike：Vampiric Strike.up且Essence.up且Essence.remains<gcd×3，保留基础按钮替换身份 | 提前/分散指定按钮尝试，缩短关联等待 | 01保留绑定及unknown，不要求独立调序；动态优化由02/03承接。不泛化为所有Buff不断档，不新增独立吸血按钮，不保证随机触发相位 |
| 5 普通循环配合固定爆发 | 只诊断普通排列对既定爆发的资源、等待和受益动作影响 | 仅改普通循环动作/等待 | 爆发宏内容、时点、来源和排除策略均受保护 |
| 6 普通CD在源允许时及时尝试 | D&D完整APL仍保留至少3目标、天赋、镰刀增益、Putrefy充能、战斗/小怪剩余及数量、自身充能组合；单体初始化另按用户批准覆盖一次 | 前移/补尝试；有证据时降低过早重复密度 | 单体覆盖不称为上游单体推荐；不是CD好就放；源允许等待不违规；裸duration不能换成地面持续时间 |
| 7 必要持续效果按条件补齐 | Outbreak保留天赋、Putrefy剩余/开场、玩家全场Dread Plague计数为0、战斗/小怪剩余等条件 | 补漏时前移/补尝试；已证重复时减少或拉开 | active_dots=0不是当前目标没病；低频初始化是显式近似 |
| 8 尽量减少可避免GCD空闲 | 实际有可用且符合相关前七项/APL的具体动作，却未及时尝试 | 减少已证多余等待、前移或插入合法填充 | 低于前七项；合理等待和unknown不据此删等待；动作数差不是理论损失GCD数 |

第8项分三类：已证可避免空闲；有源依据的合理等待；证据不足的unknown。正常GCD、施法/引导占用不算空闲。优先汇总已证空闲时长，合理/未知分列；不把教师动作总数当绝对天花板，不从用户举例生成全职业硬阈值。

完整绑定源以固定[邪DK APL](https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/apl/apl_death_knight.cpp#L349-L406)为准；本规格附录直接收录取值入口与必要证据。第二条单体Death Coil与第六条D&D已获准进入验证范围，尚无新学生诊断验收。

## 5. 诊断、候选和模拟如何连接

诊断只读取本次候选的学生实际状态，不用教师轨迹补缺。每项最小记录为：规则/绑定身份，场景和时间/来源位置，适用性及结论，原因与让位关系，证据/缺口，次数或时长及分母摘要。

先区分适用、不适用、适用性未知；只有证据完整时判断符合、违反或合理让位。动作不可用本身不证明整条规则通过或违反。上层条件、react历史或前序优先无法证明时保留unknown。

候选模块把全部已知问题转成统一有限候选池。每个候选只有一个具体操作，带生成父身份、原对象/位置、改前改后参数和影响范围。复用已有插入、删除、移动、交换、替换、块内命令、Loop/次数、WaitClicks和CastSequence/Reset能力；不增加多组合枚举。

- 修改Loop身体会影响全部相应重复，不能伪装为只改日志中一次发生。
- CastSequence成功推进/Reset与普通序列失败仍推进不同，不能无成本互换。
- 不从unknown编造修改原因；有限合法探索须标明探索，不能恢复旧随机兜底。
- 候选经过既有硬合法性与行为去重，再模拟。改后状态必须重新产生，不能套用改前资源或Buff结论。
- 规则改善不直接晋级，仍以原模拟评分与现有晋级机制决定保留。

## 6. Coba怎样选择和积累

沿用Coba现成LinUCB＋NumPy，直接调用predict/learn，不引入其整套实验框架，不自写替代算法。

输入是全八条诊断摘要（含unknown）和当前跨规则合法操作列表，不人工先挑一条规则、不分成八个选择器。固定维度数值列按通用语义编码：规则状态、操作类别、对象机制属性、资源类型及归一化量、位置/方向/改量。角色差异是上下文，不是经验分区；不能把技能ID当连续大小或让同一列换职业就换含义。

适配层保留完整候选与选择时数值快照。返回值映射回准确对象和位置；相同数值摘要的不同候选不误去重，不声称模型能区分摘要没有表达的差异。

一次predict选一个操作及probability。现有一轮仍可反复选择、不放回地形成多个独立候选；它们不叠加成一条组合程序。整轮已入队后收到的反馈影响后续选择，不宣称已经排好的同轮候选会即时重排。

**反馈唯一口径：** 使用生成父与候选已有的共同search批次，分别按实际samples加权求DPS，reward＝(候选均值−父均值)／父均值。升正降负，不额外模拟，不加人工评分权重。匹配场景、种子/输入计划及执行配置，不能要求包含不同程序身份的完整data_key相等。没有可比共同批次或分母无效则记录缺口、不learn；正常早筛退出仍可使用其已完成共同批次。取消、预算截断和引擎错误不造零奖励。保留原晋级判断，晋级对手可能是处理时最佳，不偷换生成父。

**共享与恢复：** 同一宿主进程的正式任务和训练共享原生learner，短锁保护predict、learn及必要快照，不持锁跑模拟。不建立每任务副本或结束归并；原生learn持续累积，每个有效反馈只学一次。经验跨角色、专精和任务通用，候选合法性仍由各角色自己的绑定保障。

复用任务检查点与结果中心，保存模型、Coba随机进度、版本、决策快照和反馈去重所需状态。恢复某个旧任务不能回滚其他任务已经积累的全局经验。官方序列化尚不能证明精确随机恢复，必要薄适配、原子提交和崩溃一致性留实现验证；不另建数据库或共享学习服务，不承诺一定正迁移。

## 7. 性能与复用边界

性能从设计开始约束：不新增诊断专用完整模拟、不额外调用有副作用的ready、不逐点击扫描完整APL；复用同次事件和已经计算的状态，默认少量聚合与有界样本，不默认全量trace。无法在限定字段与候选范围内证明的条件保留unknown。

静态绑定按实际依赖身份缓存：有效输入、引擎/数据/规则版本及相关场景/爆发配置；程序位置映射还依赖程序身份。动态资源、Buff和就绪不能跨模拟缓存。候选与输出设有界实现，不引入全排列或无限特征列。

LinUCB成本随编码维数增长，默认交互项d=1+q+p×q；预测约O(C×d²)，学习及模型约O(d²)。这是源码推导，尚无实测开销。生成、诊断、选择、学习、保存及锁等待全部计入原搜索600秒，不借日志开关暂停算法计时。

| 既有位置 | 直接复用与必要补口 |
| --- | --- |
| 原生catalogue、controller及engine/sequence适配 | 复用动作/状态/输入来源；补最小静态字段与同次学生聚合，不造新模拟器 |
| search.initial_programs | 只替换均匀目录来源，保留其余起点 |
| search.mutate内实际编辑体 | 参数化对象/位置/改量；替换旧随机和启发式选择，不全面重构 |
| program、codec、burst | 现有合法性、行为身份、导出和受保护爆发检查 |
| search.optimize、TaskStore、result_store | 现有批次、缓存、晋级、预算、检查点与结果中心；接Coba与必要恢复 |

既有硬限制为顶层128节点、展开4096点击、WaitClicks 2–4096、Loop仅动作等，来源在program.py，不能为生成成立自动扩容。单空点击、缺字段、非法对象或无法导出必须明确失败，不静默丢条件或退回旧来源。

## 8. 三张开发票，逐票完成

| 顺序 | 独立开发票 | 交付及验收 | 真实依赖 |
| --- | --- | --- | --- |
| 1 | [规则起点与合法导出](issues/01-rule-initialization.md) | 真实静态参数→三类库→骨架与八规则填充→真实GSE和来源映射；只替换一个基础来源，复用编译导出，取得初始化生成的真实证据；第4条静态保留unknown | 无其他开发票；字段和绑定参数须有来源 |
| 2 | [学生诊断与合法修改](issues/02-diagnostic-edits.md) | 同次学生状态→八规则结论→一个明确合法修改→原生评分；验证unknown、爆发保护及观察不改变行为，取得诊断修改的真实证据 | 可用现有GSE，不假造对第1票的硬依赖；使用第1票产物时才等待它 |
| 3 | [统一自适应搜索与共享恢复](issues/03-adaptive-search.md) | 所有起点和训练进入Coba同一机制；已有反馈只学一次、共享及恢复可靠；贯通演示并完成最终两组DPS对比 | 完整交付依赖第1、2票 |

三票只是划分，执行顺序明确为1→2→3，每票讨论清楚、实施、验证并独立审查后再推进下一票。三票均为草案，尚未获产品门禁授权。初始化、诊断修改和选择器的原型验证沿实际开发实现产出，同一真实产物贯通复用，不另写一次性demo框架；一个成功例子不能替代各票边界检查。

## 9. 验证及最终对比

环境准备首先使用[统一云端初始化入口](../../../docs/cloud-environment.md)：技能仓库 `scripts/cloud_bootstrap.py` 读取 `scripts/cloud-environment.json` 的项目配置，Linux 使用 `scripts/project_environment.py` 准备依赖，Windows 调用项目 `scripts/dev/setup.ps1`。它不等于原生引擎已构建或正式入口验收通过。其他环境说明：[环境说明](../../../docs/environment-setup.md)、[本机任务与数据中心连接](../../../docs/sim2gse/local-task.md)、[构建验证配置](../../../.build-and-verify/config.json)、[固定兼容版本](../../../projects/sim2gse/compatibility/lock.json)。`.tools/`、`.local/` 属于忽略的缓存/运行目录，clone 只保证取得受版本管理的代码和版本锁，不保证完整 SimC 源码/构建产品、GSE 缓存、实际 data-store 安装连接、私有角色输入或历史报告就绪；按上述现有入口准备并核验。外部 data-store 安装副本存在不等于当前项目已连接。Coba 依赖安装和版本锁属于第03票尚待实施内容。

复用最高现有入口网页→任务API→task.run_task及相关任务恢复，内部复用sequence.evaluate与共享编译接缝。构造样例验证分支与失败路径，真实角色产物验证实际数据和导出，两者区分。测试加入现有自动发现，不建第二测试框架。

云端完成开发。正式引擎构建、固定Windows/Lua及真实数据中心安装副本相关验证依仓库现有环境要求执行；缺环境明确报告，不用mock或Linux定向结果冒称正式通过。本机具体动作和路径须列入授权，未经允许不在仓库外创建文件。

现有命令与预算依据（带 --base 的正式验证在提交后、干净工作树运行）：build-and-verify build --project .；build-and-verify verify --project . --base 5d7165b798d8a7555a74006a1206bd60d8db4331 --execution-context cloud（本机实际执行时地点改为 local；默认快速验证，完整模式仅按技能允许场景执行）。构建配置中Sim2GSE构建超时1200秒；整套正式验证预算60秒，单项Sim2GSE检查另有600秒上限，不能把单项上限当整套可用时间。以上均为既有上限，不是耗时预测，也不是新增模拟成本阈值。首票真实静态读取/导出的具体执行入口及总限时需在开始该动作前列清。

**最终收益验收只有一项：同样条件下旧方案和新方案各跑600秒，直接比较输出DPS。** 不加额外复测、四组消融、统计门槛、最低提升百分比或5%开销门槛。现有内部晋级机制仍保留。历史100份180秒五目标报告用于研究，不能机械变成本次必须再跑100次的规定；真实战斗按约定完整时长，不人为截短成有利结果。

## 10. 尚待实际核验的事项

- 真实静态有效GCD/CD、费用/确定收益、符能容量与必要符文恢复的原生采集时点；目录现有基础值不够。
- 专精绑定中Outbreak低频参数的有效来源和合法表达；用户没有批准任意固定持续秒数，也不能回到每45秒周期或每短骨架一次。
- 八规则在学生状态中的覆盖、有限条件推导、合理让位和unknown；react、gcd.max及D&D duration等语义不能偷换。
- 现有结构限制下的导出、单空点击缺口、off-GCD及替换形态；不静默扩语法。
- 固定Coba发行版、数值编码、随机进度恢复、共享模型去重与持久一致性；源码可用不等于接入通过。

这些是实施和验收必须公开的缺口，不是假设已经完成，也不自动授权扩大架构。若需要改变已确认政策，应明确影响后再讨论；其余有来源的字段由实现核验，不让用户猜引擎事实。

## 11. 开发状态与流程边界

三张开发票保持draft/needs-info，依01→02→03逐票讨论、开发、验证和独立审查，绝不同时开工。02可使用已有GSE，不虚构对01的技术依赖；03完整交付依赖01及02。初始化、诊断修改和选择器的真实原型验证依实际开发产物贯通，不另写一次性demo框架，设计确认不等于验收通过。

原研究基线为80cb3a8b67ca5b86a23b95cec7f6256e79d70b18；后续源码核验基线为5d7165b798d8a7555a74006a1206bd60d8db4331。拟用于此变更的功能分支为codex/sim2gse-rule-guided-search；实际Git状态以交付时证据为准。

用户要求将本规格及三张开发票保存到远端仓库，供本机拉取；这是四文件文档交付，不代表产品实施已获授权。不存在独立的“文档入库门禁”。整体审阅后，核对规格与全部开发票，完整展示真正的“门禁一——开始开发”：范围、固定基线、工作树、流程等级、证据、阻塞和验证安排，并确认功能分支完整名称、开发方式及独立审查安排。方案认可或文档交付不代替该门禁确认。后续还有“门禁二——规格与交付”。

## 12. 必要源码与研究证据

以下为既有只读核验结论，用于本机定位实现；没有新增研究、模拟或接口实现。原始大报告和私人角色输入不随本四文件交付，实际验收必须使用获准的有效角色输入及匹配引擎。

### 12.1 项目复用位置与官方选择器

固定 SimC：`eed909156d8eccbfca0f284cc271c080949d6a20`。原项目研究基线：`80cb3a8b67ca5b86a23b95cec7f6256e79d70b18`；后续源码核验 HEAD：`5d7165b798d8a7555a74006a1206bd60d8db4331`。两者不混写。

历史教师研究来自多目标场景，不能充当单体或学生证据。本规格只保留公开源码中的字段结构与推断边界，不保留私人报告标识、运行参数或实际数值摘录；开发不依赖这些报告，也不以历史样本规模强制新增接口实验或最终复测。

#### Coba 原生接入和共享

固定只读核验提交：`0abed4d9779d254b0501f8be10632765c1ce718a`，源码版本 8.1.0；尚未安装或锁定发行依赖。

- [LinUCB](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/learners/linucb.py)：现成 predict(context, actions) / learn(context, action, reward, probability)；稠密数值输入、动态候选列表；learn 持续更新模型，可接受负反馈，不按任务自动清空。
- [预测器](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/learners/utilities.py#L6-L25)、[随机状态](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/random.py#L237-L238)：Coba 有独立随机进度；原生序列化仅保存初始 seed，不能当作精确续跑证据。
- [库内序列化工具](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/pipes/multiprocessing.py#L107-L142) 用于对象运输；模型持久恢复仍需薄适配验证。不得由此自建第二套学习算法。
- 项目 `projects/sim2gse/task.py:1700–1725` 与 `seed_training.py:1100–1104,1164–1172` 使用线程/线程池，支持同宿主复用实例；原生模拟子进程不构成按任务复制 learner 的理由。
- 项目 `search.py:1688–1690,1824–1833` 保留评分批次；`TaskStore` 和 `result_store.py` 提供存储接缝。原子保存、一次反馈去重及不同进程同时访问的行为尚未验证。

#### GSE 与静态字段边界

项目 `program.py:134–181,264–287`：顶层最多 128 节点、展开最多 4096 点击；WaitClicks 为 2–4096，Loop 身体仅动作；并非此次新增限制。现有编译导出接缝在 `program.py:435`、`codec.py:125`。

`native/src/catalogue.cpp:100,158,184` 当前 gcd_ms 为 trigger_gcd 基础值，不能冒充角色静态有效 GCD。原生动作、资源和 Buff 对象可复用，但纯静态快照的采集生命周期与最小字段还需接入核验。

固定 GSE 外层按钮有独立步进状态，停止普通输入本身不重置；现有固定爆发采用普通序列暂停、原位续接。其独立按钮状态与暂停续接属于已有源码核验，用户当前实机绑定、手动重置和全局设置未实测，不声称游戏验收通过。



#### 项目最高入口、编辑与反馈接缝

下列项目路径相对本仓库根目录，行号对应固定核验基线 `5d7165b798d8a7555a74006a1206bd60d8db4331`；实施后优先按函数名定位，并核对当前行号。全文省略的项目 Python 模块（search.py、task.py、engine.py、program.py、codec.py、result_store.py、burst.py、seed_training.py、sequence.py）位于 `projects/sim2gse/`；task.py 明确指该目录的任务模块，不是同名开发命令脚本。TaskStore 定义在 `projects/sim2gse/search.py:788`；controller.cpp、catalogue.cpp 位于 `projects/sim2gse/native/src/`。S1–S13 中的 `engine/...` 则是 SimC 官方仓库路径，须从对应固定提交链接读取，不是本仓库根目录。

- projects/sim2gse/search.py:144–188为initial_programs，均匀来源在160附近；projects/sim2gse/task.py与projects/sim2gse/search.py均有调用，须统一替换这一个来源。
- projects/sim2gse/search.py:209–472为现有mutate选择及实际编辑体；1898–1904还有调用侧洗牌，不能只换函数内部而留下旧兜底。
- projects/sim2gse/search.py:1688–1690、1824–1833保留request、dps、samples、variance及batches；545–561、2042–2045为现有配对晋级数据。学习反馈按本规格使用共同search批次，不要求新增配对模拟。
- projects/sim2gse/search.py:34定义32/128/256累积目标；score_batch在1761–1764按target−previous形成32/96/128增量；projects/sim2gse/engine.py:348–354读取实际count并核验其为max(1, iterations−1)，samples取该count，必须使用存档实际samples加权。
- projects/sim2gse/search.py的pending尚需保存生成父身份与选择快照，不能依赖可关闭的observability字段；整轮先入队，后续学习不伪称实时重排已排候选。
- 现有TaskStore使用SQLite检查点，save/flush有既有缓存和事务边界；共享模型与反馈去重原子性仍须验证，不能假定不同存储天然跨库原子。
- tests/sim2gse/test_search.py已有run_task/fast_evaluate接缝，适合契约检查，不能代替真实角色静态参数或正式引擎产物。

### 12.2 补充精确绑定与按钮身份

低位单体消费原文：`death_coil,if=cooldown.army_of_the_dead.remains>5|runic_power.deficit<50`。父入口`active_enemies<3`，保留默认high_priority/trinkets/cooldowns及单体更高位Death Coil的让位。不能将其套到同按钮的所有规则。

普通CD原文：`death_and_decay,if=active_enemies>=3&talent.cycle_of_death&(buff.festering_scythe_tt.up|!talent.festering_scythe)&(cooldown.putrefy.charges<cooldown.putrefy.max_charges&(raid_event.adds.exists&raid_event.adds.remains>=duration*0.75|!raid_event.adds.exists&fight_remains>=duration*0.75)&(raid_event.adds.exists&raid_event.adds.count<active_enemies|!raid_event.adds.exists|charges=max_charges))`。位于cooldowns中Outbreak之后、Army/DT之前；默认入口仍先处理high_priority和trinkets。实际条件以固定APL:373为准。

基础按钮、可替换形态及实际执行身份分开：已核验示例包括脓疮85948→镰刀458128、天灾55090→吸血433895、DT1233448→Blightfall1271967；替换依赖天赋或Buff。按钮DT1233448与玩家DT Buff1235391不能混为同一对象。来源为固定SimC职业模块8739–8746、10482–10491、12676–12684及项目catalogue.cpp:53–68,118–161；具体实际形态以同次学生事件为准。

静态费用与动态费用不同，资源收益不能由两张快照相减反推；符文并非通用线性regen。必要费用/恢复复用固定action.cpp:1192–1252,3272–3276、player.cpp:4950–4957,12619–12660及职业模块。静态天赋谓词只解析本批绑定所需项；available不等于当时ready。

### 12.3 八规则数据可获取性与已有数值

以下直接保留已完成的数据来源研究，作为本规格证据附录。这里的历史教师数据不代表本次学生诊断已实现或验收通过。

#### 研究结论

八项规则引用的资源、冷却、充能、Buff、疾病、GCD 和场景表达式，均已找到固定版本 SimC 的取值入口。主要缺口是项目尚未导出这些数据、需绑定正确对象与时点，以及诊断本身尚未计算；不是需要重新制造一套战斗状态。

最小方向是复用现有报告、控制器事件及 SimC 原生状态/表达式，只补规则实际需要的取值。无需为证明这些入口存在运行新模拟。本次仅阅读源码和已有报告，没有修改接口，也没有新模拟或性能测量。

需要特别区分三件事：
1. 项目已有渠道可读取；
2. SimC 已有数据，但项目需补接或指定上下文；
3. “是否违反规则”“是否合理让位”“可避免空闲区间”是根据事实计算的诊断结论，不是一个等着导出的原始字段。

研究基准：SimC eed909156d8eccbfca0f284cc271c080949d6a20。项目源码核验 HEAD 为 5d7165b798d8a7555a74006a1206bd60d8db4331。以下结论针对这些固定版本，不把接口存在等同于接入已实现、已证明无干扰或性能达标。

#### 现成取值渠道

项目控制器已有：时间、输入来源 origin/step、原按钮签名、实际动作身份、GCD 就绪时刻、主资源当前值、当前动作 CD 剩余、普通循环/爆发来源。见项目 controller.cpp:598–664；sequence.py:323–335 解析，380–387 返回报告/轨迹。[P1、P2]

SimC 自带动作快照已有：各资源 current/max；活动 Buff 的对象、层数和剩余。JSON 默认有资源及 Buff 层数；Buff remains 由 full_states 控制输出。见 player_collected_data.cpp:33–79、report_json.cpp:502–515,553–559。[S1、S2]

这些渠道有明确限制：
- 默认动作快照过滤 quiet/constant Buff，未出现不能一律解释为没有该 Buff。
- full_states 的 cooldowns 仅收 c->down() 的对象，stacks 写的是最大充能 c->charges，不是当前充能。打开 full_states 不能解决满充能诊断。
- Buff 汇总 duration 是观察到的平均持续长度，不是当时的 remains。
- 当前项目 trace 只输出主资源，不能因此说已输出符文和符能双资源。
- native_execute 通知位于 execute 调用之前，不是执行后扣资源或上 Buff 的快照。[P3]

#### 八项规则取值矩阵

1. 窗口或满充能释放
需要：Putrefy 当前/最大充能、CD/重充信息，玩家 Dark Transformation Buff；单体源条目另需符能缺口。
怎么取：从绑定的 cooldown_t 对象复用 charges/max_charges/remains/recharge 原生表达式；多充能当前值来自 current_charge，最大值来自 charges；单充能 charges 表达式按就绪情况返回 0/1。DT 对象为玩家 buffs.dark_transformation；符能缺口为 max-current。[S3、S4、S5]
现状/补法：现有报告已有符能和部分 Buff 层数，项目当前动作 trace 有 CD remains；需补接指定 Putrefy 充能及 DT 实时状态，不能使用 full_states.stacks 代替当前充能。
源绑定：AoE Putrefy 是 DT.up OR charges=max_charges；单体其他 Putrefy 条目独立保留。[S6:363,388,391]

2. 特定低优先消费预留
需要：单体低位 Death Coil 条目的 Army 实际 CD 剩余、符能 current/max/deficit、目标数量及源优先上下文。
怎么取：绑定 Army 的 cooldown.remains；资源复用 resources.current/max；目标数复用原生 active_enemies。[S1、S3、S7]
现状/补法：资源渠道已存在，指定其他动作的 CD 需要项目接出。源条件是 Army.remains>5 OR runic_power.deficit<50，不能改写成固定“保留 50 符能”。前序让位属于诊断判断，不是 SimC 缺一个字段。[S6:394]

3. 近满资源消费
需要：符能缺口、可用符文；Sudden Doom.react；Essence 层数、最大层数、剩余；Vampiric Strike.react；epidemic_prio。
怎么取：资源 current/max；Buff 层数/剩余及 max_stack()/stack_react()；epidemic_prio 的完整右侧为：
active_enemies>=3 & !buff.forbidden_knowledge.up | active_enemies>=4 & buff.forbidden_knowledge.up
因此还需 Forbidden Knowledge Buff，而不是一个静态天赋开关。[S6:365,406；S8]
现状/补法：符能、符文和部分 Buff 层数在原生报告已有；max_stack、react、实时剩余需指定对象接出。受控模式不执行原 APL 选招，不能盲读可能未被赋值的 variable.current_value_；最小做法是绑定上述有限右侧表达式，复用现成目标数和 Buff 状态，不重建 APL 解释器。[S9、P3]

4. 短窗口内及时使用指定动作
需要：Vampiric Strike.up、Essence.up/remains，以及该条动作上下文中的 gcd；基础按钮与实际替换动作身份。
怎么取：绑定 Buff 对象；APL gcd 直接复用 action_t::gcd()，实现由动作及角色状态计算；原按钮和实际动作关联沿用控制器。[S8、S10、P1]
适用阶段：按2026-10-16用户确认，以下实时取值与独立调序属于后续02/03；01只保留绑定及unknown，不预测动态相位。
现状/补法：身份关联现成；Buff 实时剩余和对应动作 gcd 尚需接出。catalogue 的 trigger_gcd 是基础值，gcd_ready 是绝对就绪时刻，均不能代替该谓词的 gcd。原条件保留 Vampiric.up AND Essence.up AND Essence.remains<gcd*3。[S6:360]

5. 普通循环配合受保护爆发
需要：普通/爆发输入计划、来源位置、暂停与续接、实际尝试/执行，以及相关增益状态。
怎么取：复用 sequence.py 的输入计划与来源映射、controller 的事件与动作关联；实际增益用对应 Buff 对象读取。[P1、P2、S5]
现状/补法：输入和来源主要已有，不需要新造时间调度器；需明确状态读取阶段。爆发按钮被尝试不能证明已成功施放，也不能从 execute 前通知推断增益已生效。本项不改变固定爆发内容或节奏。

6. 普通 CD 在源条件允许时使用
需要：D&D 自身 CD/当前及最大充能、Putrefy 充能、Festering Scythe TT.up、active_enemies、raid_event.adds.exists/remains/count、fight_remains、源谓词的 duration 及静态天赋条件。
怎么取：CD/Buff 使用上述对象；场景量复用 SimC 原生表达式，完整入口见下一节。[S3、S5、S7、S11、S12]
现状/补法：原生取值入口都存在，项目需只接出该绑定需要的值。重要区别：APL 的裸 duration 是通用 DoT 表达式，不是 D&D 地面区域持续时间；不能以另一字段替换源条件。[S10、S12、S5]
源条件的目标数、天赋、镰刀、Putrefy 充能、战斗/小怪剩余以及小怪数量组合，均保留，不改成 CD 好就放。[S6:373]

7. 必要持续效果按条件补齐
需要：玩家自己全场 Dread Plague 的 active_dots、Putrefy CD、当前 time、gcd.max、fight_remains 和 adds 相关条件。
怎么取：active_dots 由 dot.internal_id 索引玩家的 active_dots 计数；time、gcd.max 和场景量复用原生表达式。[S10:3632–3640；S7:14382–14389；S11]
现状/补法：全场计数已经存在，无需为判断“全场为零”在每次输入自行遍历所有目标；项目需接出。它不是“当前目标没有病”。保留 Outbreak 的天赋、Putrefy 剩余/开场、小怪及剩余时长完整条件。[S6:372]

8. 减少可避免 GCD 空闲
需要的原始事实：GCD 就绪、执行/引导占用、控制状态、实际输入/空点击/排队、当前动作已计算的 ready_now，以及有限候选所需的资源/CD/Buff 等条件。
怎么取：控制器已有 gcd_ready、输入/队列事件、执行/引导剩余及当前实际动作检查结果。[P1:302–322,702,812–835]
现状/补法：复用已经算出的事实，不为盘点或诊断重新调用有副作用的 ready。其他动作虽存在 ready 接口，但不能把“有这个函数”当成免费且安全的全动作探测器。
真正尚缺的是诊断推导：哪个具体动作在当时满足完整相关规则、空闲何时开始/结束、是否应让位。它们不是缺失的 SimC 原始数据字段。状态、反应历史或前序条件不足时保留 unknown，不把一个时点外推为整段可用。

#### 表达式准确入口

gcd：action.cpp:3284–3285 绑定 action_t::gcd；1285–1326 为计算逻辑。随具体动作及角色状态计算。[S10]

gcd.max：action.cpp:3764–3793；使用 player.base_gcd、attack_haste/spell_haste 与 action.min_gcd，min_gcd 为零时采用 750ms 下限。应复用原生表达式并保留动作上下文，不自行统一用 1.5 秒或另一技能 GCD。[S10]

Buff max_stack：buff.cpp:450–455 读取 max_stack()。Buff react：485–503 读取 stack_react()，2004–2015 根据 current_stack、逐层 stack_react_time 和当前时间计算可反应层数。表达式初始化会设置 reactable，影响触发时反应时刻的记录（491–499、2697–2708）。数据原生可算，但依赖正确初始化和反应历史；缺历史不能用 up 顶替。[S8]

epidemic_prio：原变量读取入口 player.cpp:11939–11970；赋值入口 variable.cpp:260–267。受控模式不跑原 APL 时，使用已绑定的源右侧和原生状态，不能假设缓存变量曾被更新。[S6、S7、S9、P3]

fight_remains：sim.cpp:3582–3585 为 expected_iteration_time-event_mgr.current_time，是当时引擎已有的计划状态，不需读取最终战斗结果。[S11]

adds：sim.cpp:3718–3749 构造 raid_event 表达式；raid_event.cpp:3045–3084 匹配事件和 exists，3087–3094 的 remains 取活跃匹配事件的最长剩余，3179–3187 的 count 取对应 adds 事件 count，pull 则取 spawn_parameters.size。无匹配事件时 exists/remains/count 为 0，in/cooldown 为极大值（3068–3077）；不是一律 unknown。count 不是当前 active_enemies。[S11、S13]

D&D duration：action.cpp:3372–3373 转入 dot_t::create_expression；dot.cpp:448–456 在无 dot state 时返回 0，否则读取 composite_dot_duration(dot->state)。D&D 实现将 dot_duration/base_tick_time 设为 0（sc_death_knight.cpp:9628），实际地面事件 duration 使用 data().duration()（9640–9654）；地面剩余还有 death_and_decay.remains→active_dnds.back()->remaining_time()（14595–14609）。源 APL duration 与地面持续时间是两个不同的原生值，均能找到入口，不得静默互换。本次未跑数值验证，不断言所有状态下裸 duration 恒为零。[S10、S12、S5]

#### 公开报告字段结构与推断边界

字段依据固定公开源码 `player_collected_data.cpp:33–79` 与 `report_json.cpp:474–559`（S1、S2），不使用私人报告摘录。动作记录位于 `sim.players[].collected_data.action_sequence`。

- 动作条目可输出 `time`、`id`、`name`、`target`、`spell_name`、`queue_failed`；等待条目输出 `wait`。资源快照由 `resources` 与 `resources_max` 按相关资源类型输出，不能将教师动作记录当作新GSE学生轨迹。
- Buff记录包含 `id`、`name`、`stacks`；仅启用 `full_states` 时输出该记录的 `remains`。采集会过滤未激活、quiet或constant的Buff，因此缺项不能一概等同于不存在；层数也不能代替react及反应历史。
- 启用完整状态时还可输出冷却的 `id`、`name`、`stacks`、`remains` 及目标debuff记录；采集冷却时只记录 `down()` 的对象。读取前须核对对应配置、采集时点及对象身份，不能把未记录状态补成已知值。
- 这些动作快照不包含完整动作ready证据或GCD表达式求值。Buff汇总的持续时间或覆盖率不能替代指定时刻的剩余时长；同名对象须按身份区分。缺少动态状态时保留unknown，不由汇总量或相似字段倒推。

#### 可用结论与未实施事项

可确认：八规则所需主要原始数据与指定表达式均有源码入口；现有报告可复用资源和部分 Buff 快照，现有控制器可复用输入/队列/动作来源。满充能、react、GCD 语义、全场疾病计数及 D&D duration 都不能从相似字段猜出。

项目待补：指定对象的少量实时值及明确时点；受控状态下有限变量表达式的正确绑定；从原始事实到前序让位和空闲区间的诊断计算。

尚未声称：接口已接入、观察不改变模拟、任何性能阈值通过、八条规则在学生轨迹上全部可判定。上述属于后续接入与诊断工作，不妨碍本次数据可获取性盘点凭源码完成。上述字段盘点依据公开源码，不依赖私人报告或新增模拟。

#### 可复核来源

项目来源 P1–P4 均相对仓库根目录，固定 HEAD 5d7165b798d8a7555a74006a1206bd60d8db4331：
P1 projects/sim2gse/native/src/controller.cpp:302–322,598–664,702,812–835。
P2 projects/sim2gse/sequence.py:180–188,323–335,380–387。
P3 projects/sim2gse/native/hooks/040-control-connections.patch:106–112,465–469。
P4 projects/sim2gse/native/src/catalogue.cpp:71–100,118–161。

SimC 官方固定提交源码：
S1 engine/player/player_collected_data.cpp:33–79
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/player/player_collected_data.cpp#L33-L79
S2 engine/report/json/report_json.cpp:474–559
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/report/json/report_json.cpp#L474-L559
S3 engine/sim/cooldown.cpp:553–599
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/cooldown.cpp#L553-L599
S4 engine/sim/cooldown.hpp:31–51,78–82
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/cooldown.hpp#L31-L82
S5 engine/class_modules/sc_death_knight.cpp:9628–9654,14595–14609,15363,15389,16235–16236,16263–16264
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/sc_death_knight.cpp
S6 engine/class_modules/apl/apl_death_knight.cpp:349–406
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/apl/apl_death_knight.cpp#L349-L406
S7 engine/player/player.cpp:11939–11970,14382–14389
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/player/player.cpp
S8 engine/buff/buff.cpp:450–455,485–503,2004–2015,2697–2708
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/buff/buff.cpp
S9 engine/action/variable.cpp:260–267
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/variable.cpp#L260-L267
S10 engine/action/action.cpp:1285–1326,3266–3285,3372–3373,3632–3640,3764–3793
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/action.cpp
S11 engine/sim/sim.cpp:3576–3585,3718–3749
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/sim.cpp
S12 engine/action/dot.cpp:448–456
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/dot.cpp#L448-L456
S13 engine/sim/raid_event.cpp:3045–3094,3179–3187
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/raid_event.cpp

开发不依赖私人报告或特定云端路径；上述固定公开源码足以定位字段、采集条件及推断边界。仓库回归使用公开数据或独立构造的最小mock；真实角色报告仅在获准的本地验证范围内保留，不随仓库交付，不将其缺失误报为仓库文件丢失。
