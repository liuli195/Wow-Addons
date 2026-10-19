# 03：单操作自适应搜索与共享恢复

Parent: [总开发方案](../spec.md)
Status: in-progress
Triage: ready-for-agent
Assignee: Implementer（实施者）
Blocked by: 01/02既有依赖已满足；B按需真实采集与收尾1已明确批准，公共TDD与5原生功能已有下述限定通过，不再等待方案选择。父predict前ensure、最终输出不强补；正式全套60秒已通过，已完成2.5消费者接入/受控迁移和同条件单次性能实测；游戏与交付仍待。

## Current progress（真实进度）

2026-10-20（UTC+08）最新：测试精简支线已收尾，Windows正式37检查/413测试＋103子测试全过、54.082秒。数据中心2.5.0已发布并同步双模式，实际模块具binary-write-v1；云端本工作树入口已由随包脚本从旧性能测试副本更新至正式2.5，本机保开发市场2.5。用户确认继续GSE消费者接入，最小物理合同为新theta_bytes/a_inv_bytes列＋旧数组NULL、state_version3、原锁内仅当前模型三阶段迁移；算法/身份/经验版本/即时保存不变，详见总方案当前状态节。本机兜底实现及追加守卫已由云端独审通过，实际2.5正式完整验证与单次真实搜索结果见下方新增收尾；下列2026-10-19记录属于历史证据，不再据旧段声称2.5未发或正式60秒未过。

### 2026-10-20二进制接入实测收尾（UTC+08）

消费者公共写入、正式v3矩阵快照及原锁内受控迁移已实施，限定红绿/恢复验证完成；云端GPT-6-A累计双轴审查0/0。产品固定本机提交`91903c579c40bbe9ad1a62deb137ddde27baa627`，未修改算法、MODEL_KEY、逻辑经验版本、学习频率或停止条件。实际开发市场data-store 2.5.0，模块摘要`a3a636c325dc718f7c59854a1f2429df3ff68eda04a801745ba84b1e7ddfd0ca`。正式完整验证37检查/413测试＋103子测试全过，工具51.217秒、外层51.318秒，原外4/内20及60秒预算不变；证据`.local/verify-binary-91903c5-20261019/`。

同一成熟模型192版/1072维、同实际2.5公开接口、各3次配对暖态小测：编码/公开写入/点读/恢复/完整往返中位数，旧typed数组分别15.671/366.154/183.892/22.888/589.943ms，新正式BLOB分别1.998/41.679/23.361/1.979/81.226ms。编码包含正式快照的形状、float64及有限值检查，读写包括原子持久化；一次隔离迁移另计514.813ms。完整矩阵字节、逻辑元数据、下一预测/RNG及一次学习全等，来源散列不变。纯公开写入每次少324.475ms乘98约31.80秒；含编码写入路径每次少338.147ms乘98约33.14秒，两者是替代口径，不能累加，均非整轮搜索实测收益。证据`.local/model-public25-study-20261019/{summary.json,console.log}`；第一次清单定位准备错误在任何计时/写样本前发生，保留`preparation-failure.log`，修正后仅完成一轮样本。

随后仅一次真实公开`run_task`搜索：`binary-ondemand-20261019T215307Z`，对照原`ondemand-20261019T140341Z`。新建仓库内空center/task/model/cache，不迁移或复用成熟经验；同1560字节公开萨莱因邪DK输入（SHA256 `fa1ae07e2f0e6b027b6e67f6063147c60f02d323cabf65431eb60c7bfa3418d1`）、相同原生二进制/身份、规则摘要、爆发ID、种子20260912、原4起点和冻结配置逐项一致。预算仍600/600秒、上限1000、每轮16、连续5轮无改善、batch32/128/256、100迭代、validation4、max_processes2、输入200ms、五场景及on_demand/summary日志不变，未请求额外独立最终复测。

| 同口径指标 | 原typed数组运行 | 正式BLOB运行 |
| --- | ---: | ---: |
| 外层公开调用及原结果序列化尝试 | 137.658秒 | 107.913秒 |
| 产品保存时elapsed快照 | 136.515秒 | 106.782秒 |
| 首次评分/完整归档/唯一候选 | 100/100/100 | 100/100/100 |
| 轮数/停止原因 | 6/no_improvement | 6/no_improvement |
| predict/learn | 96/96 | 96/96 |
| 完整模型写入98次，model.full_write | 32.887秒 | 3.833秒 |
| 快照194次，model.snapshot（与full_write分开） | 1.177秒 | 0.166秒 |
| 轻控制写入97次 | 1.428秒 | 1.455秒 |
| 模型加载192次 | 5.385秒 | 5.451秒 |
| 独立诊断6次/6唯一父 | 9.234秒 | 9.366秒 |
| 搜索DPS/样本 | 134389.77826135626/253 | 134389.77826135626/253 |

外层少29.746秒（21.61%），新纯公开调用单列107.304秒，原样结果序列化尝试约0.609秒，后续读取/导出不纳入。两轮同为204个原生进程＝reference1＋search153＋validation44＋diagnostic6，批请求223、缓存命中20，pending/inflight均0。最终模型同逻辑192版，全部theta/A_inv字节和RNG一致；原成熟来源SHA256仍`b63110df18dcf7b7db4a566e48368aff1fd6d679d533cb6ac3bb345801c1a653`。两轮`model.full_write`均不包含外部`model.snapshot`，故32.887→3.833是相同埋点比较；写入内部JSON/参数绑定/Parquet/原子替换未再细分，不伪造嵌套编码耗时。嵌套/并发阶段不能相加解释整轮墙钟。

这是同条件单次早停搜索的时间改善，不是400–500候选/600秒实证，也不改变原旧方案141201.9448 DPS较高的历史结论；新data-store版本与二进制接入一起改变，不能将整体29.746秒全归因于单一编码语句。原先游戏验收及最终交付仍待。原始配置、起点等价核对、阶段/计数、公开结果与GSE仅保存在`.local/performance/binary-ondemand-20261019T215307Z/{run.json,compact-summary.json,public-result.json,task/diagnostics.json,candidate.gse.txt}`，不提交模型、数据库或全量日志。

功能实施与云端有限定向验证已完成：完整合法池→真实Coba8.1.0单选→原pending评分→生成父共同批次学习→同一中心权威记录保存/恢复均已接通。C50/A21缺失位、原生learner/RNG下一预测roundtrip、111项完整池成本、共享两任务及可靠恢复已逐切片独审；pending/跨任务缓存同报告诊断重放至f192dbb已通过。真实自动链保4起点、82项完整可评分池一次预测、1项实际操作及学习；最终原验证保初始化父。原stale cancelled停止字段已红271→绿272，并通过b43dfe2独审；原失败实证保留，不重算或改写旧任务。训练CLI/dual公开代表及10项旧搜索生成接缝已有构造外部评分证据；最后两条旧训练接缝273红→276同3例38.31秒绿（9598405，增量独审已通过），保停滞/并发/缓存/实际轨迹归属，不恢复index99额外模拟。

用户指定的官方SimC MID2萨莱因邪DK单体样本，新旧完整方案各给600秒预算且各仅运行一次：旧输出141201.9448 DPS，新输出134389.7783 DPS，新比旧低4.8244%。旧按原无改善条件自然早停，新按原搜索时限停止；这是原选中搜索结果，未额外独立最终复测。功能链完成，当前样本未获性能收益，不据结果私改策略或声称优化收益通过。精确输入、原始结果、真实进程及边界见下方Comments。

当前Status in-progress保留至统一正式验证和交付。A四项修复已完成：效果查询内存索引、保typed数组的权威版本点读/同成功版本缓存、诊断单份持久化/引用及已证报告空映射/稀疏资源键原义往返；模板、评分与学习策略未改。随后仅迁移旧测试接缝并修正真实检查点/故障注入设置，GPT-6-A独立双轴通过。Windows功能分支 `1ca05fce96781f6855f43a27d206c5d6245bedb4` 的树与云端 `543715173248be194eab27507268a82d95d9001b` 相同：两个剩余单点2 passed/6.97秒，完整 `tests/sim2gse` 869 passed、0 failed、0 skipped，另165子测试通过，95.25秒。用户明确延后60秒预算问题；调试全绿不代表该正式预算门禁通过，也不代表游戏验收或最终交付完成。

在上述完整调试全绿后，沿同公开样本、输入、原4起点和固定爆发计划，仅新增一次优化后新方案600秒预算运行，复用旧组，不补样本、不额外最终复测。原获选DPS仍为134389.77826135626、253 samples，获选GSE与修前新版相同，较旧141201.94479487446低4.8244%。同口径结果如下：

| 方案 | 完整归档候选 | 有完成评分的候选 | 搜索及验证批次 | 获选DPS |
| --- | ---: | ---: | ---: | ---: |
| 旧方案 | 148 | 148 | 262 | 141201.9448 |
| 修前新版 | 66 | 68 | 112 | 134389.7783 |
| A优化后 | 68 | 82 | 136 | 134389.7783 |

A包含104个search批次、32个validation批次及另1个reference进程，137个native均exit0；80次选择中78 learned、2 no_learn，反馈完整。终态pending16（其中14已评分但未归档），不能将82称为完整归档。纯公开调用632.1104秒，结果读取0.1921秒、轻量导出0.1178秒，未导出巨量run-return；配置仍600/600，预算到期后处理与收尾实耗未截断。首末native跨度593.3161秒、运行区间并集60.2505秒、内部无native空档533.0656秒，另末尾38.3680秒单列。旧两组wrapper墙钟含完整导出，不与本次纯调用直接计算加速倍数；无native空档也不等于磁盘IO。A未解决核心性能问题，不宣称达标。261项边界及702个旧产物摘要保持，未重跑旧组。

后续只读复核确认82份完整诊断池中仅5个不同父候选被用于80次选择，其余77池未用于本轮选择。一次隔离存储报告重放剖析、零native发现报告预处理全树遍历及整组保存有明显成本；带剖析开销、存储STRUCT补null和原运行数据形态不同，不能外推成533秒的完整归因或提速承诺。重放诊断的完整语义等价性尚未证明，不能忽略该缺口。当时“按实际父需求生成完整诊断/池”尚待确认；随后用户已批准下方B与收尾1，旧待确认状态不再阻塞实施。此前B（base64模型数组存储）仍未授权、不执行，与本次B不同。

2026-10-19保语义整套方案已获用户批准（`Sentinel_a1870b1f0e948191906e80cdc1d538e1`），替代此前暂停根因调查/等待旧性能A或B选择的状态。本票承接状态脏项保存、模型轻量控制状态与统一日志开关，并核02受限前序汇总及源头裁剪后的完整池、特征、反馈与恢复；准确范围及审查条件见[总方案](../spec.md#2026-10-19已批准的保语义性能收口)。70–120秒只为当时整体估算，不能当已省时间或整任务墙钟；状态finally（最终处理）恢复屏障/errors（错误）脏字段、模型NULL（空值）空v0、active control（活动控制）守卫与旧writer（写入端）拒绝等原收尾历史保留。原聚合日志版已完成下述实际运行，不再沿用“原生构建中、最终600秒未跑”的过期状态；原600秒比较、869项调试通过及历史失败证据不改写。当时未批准按需跳过候选、大缓存、base64矩阵和任务末内存攒报告；其后仅下方B按需采集获得新授权，其余仍不实施。

2026-10-19后续实测与恢复记录（原始摘要 `performance-root/whole-run-final/run-summary.json`，运行提交fc77fe7753efc2c1f66b033be51e543fee986aa2）：

| 口径 | 真实结果 |
| --- | --- |
| 600秒预算运行的公开调用墙钟 | 631.5945秒；不同于结果发布快照或runtime（任务运行计时） |
| 首次评分/完整归档/待处理 | 94/84/16；pending中10已评分、6未评分 |
| 搜索/验证批次与选择 | 178批次，96次选择 |
| 获选结果 | 134389.7783 DPS、253样本，与修前新版相同；未达到400–500候选 |
| 完整诊断实际消费者 | 94份完整诊断中6父供96次选择，96次父身份/池操作归属均匹配 |
| 未供后续选择的诊断 | 88份累计412.1362秒，占429.5831秒诊断累计的95.94%；不是可省任务墙钟 |

上一轮Windows回传远端81cee19e/tree b967：963项＋165子测试、约111秒通过；原本机日志 `.local/windows-short-temp-verify-08ecde5618d04994bb36d1a244e13acc/{stdout.log,execution.log}`，本次恢复未复跑。正式60秒预算仍延后，调试通过不代表游戏验收或交付完成。

后续细日志一份真实报告22规则/82有序操作，off/on（关闭/开启）均值2.0767/2.1906秒，业务输出与特征相同；64项/45.88秒绿是该历史切片。公开resume（继续任务）阶段墙钟并集漏计修补的24项logging（日志）绿仍为历史回传；本次恢复另有64项/56.93秒通过（包含24项日志及前序规则/检查点），证据 `performance-root/recovered-logging-prefix-checkpoint-green.log`，本地提交24a0582。runtime/rule_diagnostics/search与保留恢复清单SHA逐字相同。该64项只覆盖原恢复切片；后续流水线补点另有下述43项＋7子测试及真实小测，不混用验证范围。计时同时保留两种里程碑：`first_score_published` 只表示评分报告group（报告组）可靠提交，`screening_archived` 表示内存筛选归档完成，二者并列、不得混计；时间从runtime起算，不借外层公开调用时间冒充。12候选/180秒安全预算归因小测已唯一完成，结果如下。

按需采集32迭代ABBA有效31样本、完整战斗/DPS/方差/37,664轨迹一致，四个已测串行阶段1.997→0.552秒；存储仅NULL补列且readback_exact仍false、632,649既有观察叶值相同及87,665 NULL差异均已核。尚未验证重放Python诊断/池/特征、按需来源与奖励契约或任务恢复，不能以微测代替策略设计和验收。这是B批准前的日志/研究阶段；现已获B与收尾1批准，诊断时点与独立来源按下方新合同实施，完整池和原评分/学习保持。完整实证与限制见[总方案](../spec.md#2026-10-19后续实测与本次恢复状态)。

### 唯一12候选归因小测（2026-10-19）

固定运行提交 `7b69d593e7f93751b9082d73efc4b47b7d0652a3`，仅一次、未重跑；证据 `performance-root/twelve-candidate-probe/{analysis.md,analysis.json,run-summary.json,diagnostic-consumer-audit/summary.json}`。公开调用 **80.632秒**，12首评分可靠发布、12最终持久归档、pending0，4初始＋8子。candidate_limit（候选上限）正常终止，轮上限仍16，partial_round=true不意味着遗留待处理项。搜索结果 **122798.143 DPS、126样本**；保存结果 `final_status=not_requested`、`independent_validation_complete=false`，不是独立最终复测。

| 归因层 | 实测与边界 |
| --- | --- |
| 完整诊断 | 累计42.005秒/并集26.632秒；12份仅1父供8次选择，身份及操作归属均匹配，11份未供后续选择累计40.079秒（95.41%）。这是诊断累计占比，不是可省任务墙钟。 |
| 原生调用 | native.execute累计33.036秒/并集26.431秒；30实际调用全部成功：首批12＋追加评分9＋配对验证8＋参考1，缓存0。 |
| 发布与等待 | report.publish 15.851秒包含report.write 14.960秒；main.wait 37.021秒仅筛选轮future.result重叠等待，不计覆盖并集。 |
| 覆盖与差额 | 粗阶段跨阶段并集70.823秒，公开墙钟未覆盖9.809秒；现有日志不能将差额精确拆项，不是全CPU时间。嵌套/并发阶段不能相加。 |
| 原生计时边界 | invocation elapsed累计23.293秒，和native.execute差9.743秒，包含外层前置及清理/回调等待，不能全称cleanup；已在覆盖阶段内，不是未覆盖9.809秒。 |

两里程碑仍以TaskRuntime.started起算：首次评分可靠发布须等group事务提交，筛选归档只标内存完成、检查点可能缓冲；首候选内存入档7.358秒、发布17.287秒这种顺序合法。最终持久归档12个由任务状态另核，不能用内存事件替代持久完成。

新容器真实重建binary SHA（可执行文件摘要）改变，engine/compiler identity（引擎/编译器身份）与whole-run-final相同；预算/日志和工作量也不同，只作归因，不能当作前后收益验收或将固定初始化/配对验证成本线性外推400–500候选。尚无该候选量实证。流水线定向43项＋7子测试/61.67秒通过（`performance-root/pipeline-combined-green.log`），Astra独立双轴0项问题；不替代正式60秒门禁或游戏验收，也不据运行提交号声称远端同步完成。此小测未改变eager合同；随后B与收尾1已批准，具体覆盖及待验范围见下节，不拿该小测当B已实现；详见[总方案归因记录](../spec.md#2026-10-19唯一12候选归因小测)。

### B按需采集与收尾1（最新已批准，实施中）

用户 `Sentinel_9838d5f47eb88191ae20bf5b25a5f4e6` 选B，`Sentinel_bd5d76067ea48191a1901d5de1344c63` 选收尾1：新任务普通评分薄数据，仅父predict前或明确单候选诊断请求ensure；搜索结束直接输出原最佳GSE/DPS，有诊断显示，无则未诊断。不最终强补、不预留/追加诊断收尾预算、不新增完成/导出/冠军或训练完成守卫。当前产品与限定验证见下文，已有5原生功能复验，尚无B新600秒收益结果；400–500候选目标不降，约2.00→0.55秒报告链与2.08秒Python诊断不是整轮墙钟保证。本次B与旧未批准base64矩阵备选B不同，后者仍不执行。

最新产品 `ea38c8067fc175cab074531874618982f22ca715` 的针对性测试25项59.04秒通过、301项未选，日志 `performance-root/on-demand-final-repairs-narrow.log`；最终Standards（规范）/Spec（规格）独立审查均0项问题。该59.04秒不构成正式全套验证或正式60秒预算门禁通过。首轮5原生功能发现state字典恢复排序漂移；复用冻结bindings顺序修复后，同一真实报告0新增原生离线核查的有序规则/池、50维context及action_features一致，仅两处typed NULL观察摘要不同，原失败与离线核查保留在 `performance-root/b-native-functional-20261019-1302/`。

修后新HEAD另一次公开功能复验已passed：`performance-root/b-native-functional-ea38c80-20261019-1319/summary.json`，5次SimC、公开功能步骤22.7094秒；B薄评分→独立补采后取消→恢复/read/repeat零新增原生，公开读回程序、归档原程序与实际编译行为相同。三路B评分/补采/eager的DPS 99688.53352317847、samples31、variance30301640.969619744严格相等；按真实双批出处精确映射后，22规则/82完整有序池、50维context与操作特征业务差异0，632,649既有叶值/类型相同、87,665仅新增NULL、0旧值/数组顺序变化，两处evidence/parent observation_digest差异仍披露。验证脚本后置分析的export/归档程序参数误用以禁用原生的只读verifier修正、另1.4425秒，原error/diff保留，未重跑公开或原生步骤。

本次两个任务candidate_limit=1、batch_targets=(32,)，只验证补采/取消恢复/复用与eager对照；真实原生自动predict/learn及搜索收益未由这5进程覆盖，不能把既有公开构造评分边界测试替代该实证。B新600秒、400–500候选、正式全套/游戏/最终交付仍未完成，详见[总方案限定验证](../spec.md#2026-10-19-b限定验证与真实功能复验)，原B验收不整体勾选通过。

旧148基线只读复核为真实工作量：源80cb3a8b有148不同首批、262原生启动/成功另参考1；旧无完整规则观察/逐候选诊断/Coba，有9次两迭代轨迹反馈与报告写入。输入/seed/并发/阶梯相同，但首爆3000/5000毫秒、行为v1/v2、初始序列/native来源不同，不能当完全等价或400–500保证，不能说旧靠cache。原123.9494秒仅原票历史墙钟证据，改过elapsed的副本不能回推它。

2026-10-19 Windows收尾：`491bd2d` 完整调试1011项＋167子测试/107.44秒通过，规范轴/规格轴各0项；`7de4e0e` 固定公开样本核对后，以全新中心/任务/模型/缓存运行唯一600秒预算B实验 `ondemand-20261019T140341Z`。6轮按no_improvement（无改善）早停，外层137.658秒、100首次评分/100归档、待处理0，独立诊断父6；真实predict/learn（预测/学习）各96次，DPS134389.7783。模型完整保存98次累计32.887秒、该阶段墙钟并集同值；阶段含子阶段且有并发，不相加。未跑满600秒，约436只是等速估算，非同机旧新加速倍数。包装脚本返回值序列化失败后只读恢复，未重跑；冻结配置及机器可读证据位置见[本轮收尾](../spec.md#2026-10-19-windows修复与b性能实跑收尾)。正式60秒门禁、最终独立复测、游戏及最终交付仍未完成。

2026-10-19后续模型存储方案已选：受控一次迁移；Python通用BLOB先行、CLI保普通字段查询并拒直接BLOB输出。保持学习算法/特征/奖励/版本/RNG（随机状态）/回执/水位及每次学习即时提交，二进制格式校验与迁移均在Wow层；通用技能不知模型或NumPy。本机Codex原生列表与配置已确认本地开发市场直接以技能仓库为来源，安装副本及项目入口指cache不改变此来源；此前仅凭realpath判模式不符的结论撤回。保留本机现有开发市场原生形态及云端正式市场，不换源码软链，不为同版本切市场；新版本能力安装后单独核摘要/能力并重启消费者。中心需求准备与开发交回云端，本机只保四文档待审及后续必要Windows验证，除非再次实际额度失败。后续适配包括能力透传、控制记录隔离、受控迁移/恢复、两种市场安装形态及未授权切来源拒绝，尚未开工。54ms小测不是生产写入口承诺；证据及顺序见[后续方案](../spec.md#2026-10-19二进制存储后续方案已选设计与双模式边界)。

## Shared workflow（共用开发流程）

最新确认：两个A继续有效；通用数据中心2.5.0已发布和同步，当前沿原门禁进入Wow适配/受控迁移的串行TDD。两端市场模式不切换，迁移成功及性能收益须由后续实际证据确认。

本票沿01/02/03共用的已批准门禁一、同一功能分支、串行TDD及每票独立审查实施；不重复开工确认。三票完成后统一正式验证、规格与交付，不设独立最终验收门禁。完整契约及自包含JSON在[总方案](../spec.md)，正式规格本轮不改。真正新增业务或未批准具体默认单列确认，不将其扩大为公共能力开发暂停。

## What to build（交付）

原多起点调度先确定当前父候选；B先ensure来源正确、统计严格一致的完整诊断/池/context，随后才创建selection_intent（选择意图）、调用reserve（保留回执）/predict。把全部适用诊断作为context（上下文）、完整合法具体单步池作为actions（备选操作），交Coba LinUCB选一个，沿原编译/共同批次评分，再按真实相对DPS反馈学习。未诊断、不完整或不一致不创建意图/回执，已有意图/回执不换父、换报告或重抽。跨角色、专精及任务共享兼容通用经验，可靠保存恢复，不用规则优先级决定修哪条。

只替换随机算子、固定启发式及洗牌兜底的操作选择。原起点轮转/父选择、4＋4＋2来源、训练入口、批次、早筛、晋级、冠军、缓存、预算和停止条件保持；随机初始化保留，旧任务不原地换算法或自动重训。复用既有TaskStore、pending、结果中心和锁，不新建经验平台/数据库/服务。

## Features and learning（特征与经验）

| 来源 | 初版通用字段 | 规则 |
| --- | --- | --- |
| 全部适用诊断 | 问题种类、事实/假说/未知计数比例、未知比例 | 所有适用诊断参与，不只取最高规则。 |
| 窗口/资源 | 相对窗口位置、资源/上限比例、支持机会/观察输入比例，数量/均值/适用极值 | 分母无效/缺失有valid位，不造0。 |
| 尝试 | 失败/实际尝试比例 | 零分母有缺失标记。 |
| 具体操作 | 操作类型、全部贡献模板、源/目标相对位置、带方向移动量、加减次数 | 路径经已有展开映射转相对序号；每个具体操作保留身份，不因同特征误去重。 |
| 定位身份 | 技能/角色/三键配置ID | 仅报告定位，不作连续数值、规则权重或分模型隔离键。 |

一个兼容feature/reward版本共享学习器。配置摘要不同不自动重建模型，字段含义/维度/反馈版本不兼容明确拒绝混用。具体编码与库输入做最小验证，不另手写权重算法。

反馈＝(同共同批次候选样本加权DPS－同共同批次生成父样本加权DPS)/父均值。相同场景/种子/输入等条件匹配；只使用原已完成共同评分批次，不为奖励额外跑模拟；B独立diagnostic_batches绝不进入成绩、共同批次或reward，不能删除rule_observations凑配对。无共同证据/分母无效不learn，早筛已有真实完成共同批次可学，失败/取消/半报告不造0；学习父始终是生成父，不偷换全局最佳。

真实Coba learner状态及必要随机进度存入现有存储，按task/decision反馈去重并与模型可靠保存关联。短锁不跨模拟；旧任务恢复读取最新共享模型，不能用旧任务快照覆盖其他任务的新经验。已核官方8.1.0没有原生save/load；本轮仅以已审状态/RNG薄适配完成predict/learn→保存/重读→下一预测/更新roundtrip，不能称库开箱支持全部恢复。复用原store事务/版本能力，两任务交错和崩溃恢复有用例，不新建服务。

## Public seams and TDD（公开接缝）

复用现有task启动/运行/读取/恢复、dual_task及训练入口；03向02提交同一种operation身份。明确单候选诊断只薄增resume_task(diagnostic_candidate_key=..., diagnostic_budget_seconds=正数)，无默认额外预算，不新增演示/平台，read_task始终零模拟。该显式分支即使原任务额度耗尽也仅按单独额度诊断，不恢复普通搜索。原pending可靠保存再评分/学习。先在公开任务入口用现有评分边界替身验证完整诊断/全部池→单选→实际单操作→评分→反馈→重读，再核库调用和持久化；最后贯通真实产物，不以私有learner测试代替全链。

## Acceptance criteria（验收条件）

以下最终勾选保留至三票统一正式验证；Current progress及Comments分别记录有限功能证据和未完成范围。旧eager通过证据不替代B新增验收。

- [ ] B普通评分不采完整观察/不diagnose；父selection_intent/reserve/predict前ensure完整池/context后真实Coba选择，原score/batches/common_key/reward不变，补采旁链不计分、不增候选。
- [ ] B来源双键与真实evidence、严格DPS/samples/variance核验、mismatch保原分不供selector；可靠采集恢复只补Python，取消/缓存/发布中断及训练共用路径有公开红绿。
- [ ] 最终原GSE/DPS直接输出，无诊断准确标记；read_task零模拟，不新增完成/导出/冠军守卫，不预留或追加最终补诊断预算。
- [ ] 明确单候选诊断必填正diagnostic_budget_seconds，独立有界Runtime/记账；原额度耗尽后可诊断但不恢复搜索，无默认额外预算，不改原600秒、elapsed、DPS/奖励；新B与旧无字段eager冻结且严格身份门禁不放宽。

- [ ] 全部适用诊断和完整合法池一起输入一个LinUCB，不人工先挑模板/高位规则、不按职业/技能/角色/配置拆模型。
- [ ] 一次predict只选一个可追溯具体操作；同父多次选择仍各自一步，不叠成组合、不冒称在途选项实时重排。
- [ ] 原多起点/父选择/训练及评分晋级/冠军/停止保持；无池沿原停滞处理，其他路径继续，不回退随机搜索。
- [ ] 通用特征/缺失位/维度与版本明确，兼容配置跨角色/专精/任务共享，未知不会成为隐式0或人工加权。
- [ ] 共同批次实际样本加权相对DPS一次反馈；取消/错误/无共同证据/无效分母不造零或新实验。
- [ ] 真实学习器保存重读与随机进度已用最小roundtrip验证，依赖版本锁定；API缺能力只补薄适配，不重选算法。
- [ ] 反馈去重、保存失败、崩溃、旧任务恢复、两任务交错有公开结果证据；旧恢复不回滚新全局经验，锁不持有跨模拟。
- [ ] 配置/实际输入计划/引擎/特征及反馈版本纳入原身份与缓存，变规拒恢复，旧结果可读；固定burst机制不变。
- [ ] 贯通01初始化、02同次事实/完整池、一次单操作与真实评分，所有现有搜索/新训练入口不藏旧随机兜底。
- [ ] 最终仅按同条件旧方案与新方案各600秒比较输出DPS；不加100场、消融、统计门槛、最低提升或额外收益指标。

2026-10-19状态脏项保存仍在同一TaskStore（任务存储）和SQLite事务内：显式标记变动字段/归档，覆盖原地修改和删除；事务成功后才确认已保存，回滚/失败仍保脏并可重试，归档重排或未识别形态全量回退。公开暂停/恢复、冻结反馈、完整重读与原状态逐值相同，不允许为减少保存遗漏可靠意图。唯一 `--diagnostic-logging` 默认关闭，恢复/重启需本次显式开启；页面分级/请求不能越过它，旧训练身份兼容不等于继承开启。性能日志不控制业务诊断/池/学习/回执或真实预算。总开关及四路产品聚合已接入diagnostics.json.performance.stages，scope=current_invocation（仅本次调用）、timing=inclusive_wall_seconds（含子阶段墙钟秒），每阶段calls/seconds/units（次数/秒/工作量）；默认off无额外perf_counter（性能计时器），仍待联合验证。诊断total/read_validate（内存取数）/preprocess/rules/finalize、报告prepare/write、状态persist.full/partial/transaction/progress、模型load/predict/learn/snapshot/full_write/control_write已接入；嵌套并发不能相加，data-store（数据存储）内部序列化/Parquet细分未实现。

## Budget and boundaries（预算与边界）

父用补采、诊断、池生成、选择、学习、保存及锁等待计入原预算；显式单候选诊断仅用调用方正diagnostic_budget_seconds的独立有界Runtime和记账，原额度耗尽后仍可仅做此诊断，无默认额外预算、不恢复搜索、不改原预算/elapsed/DPS，最终输出不强补、不新增收尾预算。日志开关不改变执行/伤害或算法计时。云端优先，确依赖本机的动作另给授权路径和总限时。不同宿主/进程共享如超出现有能力先报告，不新建常驻学习服务。共享经验不保证正迁移，真正结果仍由原评分晋级。

## Comments（讨论）

下列2026-10-18 A性能修复记录中的“B不实施/未执行”均指当时base64矩阵备选B；保留原始进度与证据，不作为本次已批准B按需采集的阻塞。

初稿阶段记录：当时仅同步需求文档，未安装新库或修改产品；当前已锁定安装依赖并通过下述有限真实库探针，公开实现按Current progress继续。三组使用时机默认已分别确认，不再保留此类待决或重开选择器选型/项目门禁。固定爆发按法/周期/宏保持，各专精引用自身定义。正式规格/最终交付随三票完成后统一处理。

2026-10-18定向证据：训练251（1例7.87秒）、dual259（1例7.71秒）；核心恢复最终265（7例36.10秒），独审f82612f双轴0/0。旧生成接缝最终267/268各5例22.30/54.32秒，涵盖并行、取消、晋级、批次恢复、编译延后、空池轮转及真实生成父共同反馈。pending诊断红264保留，其同报告重放沿现archive/pending首批有限视图及公开replay标记，不更改原报告/评分/取消点。以上引擎评分均为已存在外部边界构造，非真实战斗或新旧收益实验，未声称整个test_search文件/项目测试全绿。


2026-10-18真实自动链（产品f192dbb，公开SimC MID2萨莱因邪DK单体样本）：最终保留初始化父，自动子未晋级。自动操作为灵魂收割完整动作块从0基路径[19]移至[18]；普通同条件批父89869.3401、子93694.1444，原生learn实际reward=0.0425596121；原验证父97881.0696、子102411.7496，单批paired-bootstrap的ci95为空、not_proven_better，故不能称已证收益。4起点全部保留，5唯一候选、9真实评分批、10native进程（1参考＋5普通＋4验证）全部exit0，无额外诊断模拟，中心发布elapsed为43.5114秒、当次checkpoint实际累计45.9706秒。评分前取消后恢复沿同decision与具体operation；完成后同任务公开恢复在禁止新评分/进程/选择/学习的边界下通过，共享完整模型和原评分/验证/最终结果不变。证据位于云scratch rule-selector-automatic-acceptance/evidence（原报告、选项、程序、GSE、模型、single-step-proof及保留的failed summary），两个mask批次均已原SHA还原。真实脚本发现的stale stop_reason另列为产品缺陷，271构造公开恢复红后仅在实际继续search时清除旧cancelled，再沿原停止原因生成；272恢复与普通选择关联3例8.27秒绿。真实任务不改写成修后版本、不再模拟。


2026-10-18最终限定比较：同一公开输入SHA256 `fa1ae07e2f0e6b027b6e67f6063147c60f02d323cabf65431eb60c7bfa3418d1`，身份/装备/共同配置与适配差异见 `.local/tests/old-new-comparison/inputs/sanlayn-input-manifest.json`。旧80cb完整方案（与固定5d旧项目树一致）及新b43dfe2完整方案各600秒预算各一次；原输出141201.94479487446 / 134389.77826135626 DPS，相对-4.8244140995%。旧中心发布elapsed为122.9247秒、整次调用及结果保存墙钟123.9494秒、no_improvement早停、263个native进程；新中心发布elapsed为597.1335秒、progress累计608.989秒、整次调用及结果保存墙钟617.3696秒、search_deadline、113个native进程。617.3696秒包含wrapper的save(run-return.json)额外结果落盘，不能当成纯公开run调用或纯产品处理时长。新侧首个原生开始至最后原生结束跨度547.092秒，合并原生运行区间51.196秒，内部无原生处理空档为495.896秒；跨度外首尾70.277秒单列，含初始化、结果输出/保存等尚待分解部分，不全归产品开销。两方均final_retest_status=not_requested，不偷加收益复测；首爆分别3000/5000ms，后续45秒周期/固定宏保持，属于已批准初始化差异。结果未显示新方案胜过旧方案，不等于功能链或共享学习未执行，也不构成自行变更策略的授权。两侧完整原始证据各在 `.local/tests/old-new-comparison/final-run/{old,new}/`：`summary.json`（版本/预算/停止/数量）、`public-result.json`、`native-processes.jsonl`、`final-candidate.json/.gse`；两侧mask及冻结边界已原样还原。

2026-10-18最后训练接缝迁移：仅 `tests/sim2gse/test_seed_training.py`，273原红3例1.41秒，276同命令3例38.31秒绿。保原7/4轮、no_improvement=2及15/8归档，真实Coba/配置解释器/中心并发、第三材料成功缓存零重评分、各实际trace原run/batch及native/cache请求计数；撤销的仅旧mutate强塞多编辑目标与index99额外两迭代诊断批假设；旧第三任务命中带trace的index99具体场景随额外批撤销，不称该场景原样保留。当前分别核每个实际首批trace来源与共同无trace评分缓存不可冒轨迹。未改产品、无真实native，mask原SHA恢复；未声称整个训练/搜索文件或统一正式验证全绿。


2026-10-18用户明确选择A并授权执行（Sentinel_b40b9eb423088191b2ee3270621ea83e）。范围限上述四项性能/原义修复，按原共同门禁TDD及小切片独审，不新增每票门禁、框架或600秒实验；typed矩阵查询能力保留，base64备选B不实施。9598405最后训练接缝迁移独审已通过；性能修复后以同一原raw报告、成熟模型及已有恢复边界复核全部输出/实际计时，未测前不承诺回到旧吞吐或正收益。


A性能修复首切片：同次效果状态按object/sample/input建立保全部匹配值的内存索引；重复、缺项、null、非布尔仍沿原UNKNOWN。279公开run/read两个代表原整表扫描1804次/900输入而红；最小索引后280关联5例3.99秒绿（其中索引2例、原公开2例、模型缓存首测1例，范围分列）。同一保留raw报告（900输入/4500效果，SHA3b197ccfe03b36d25684d0124304fb2e41dd8afc46b1467157ad4af0844797af）对固定ae24f46函数与当前产品完整诊断/有序池逐值相等：22规则、2698 findings、165操作，一次测量3.1482→2.3843秒；0native，非整个任务吞吐指标或达标承诺。证据 `.local/tests/general-initialization/279-selector-effect-state-index-red.txt`、`280-selector-effect-index-and-version-cache-green.txt`、`281-selector-effect-state-index-raw-comparison.txt`。其余A范围仍实施中，矩阵保持typed，B不执行。


A性能修复续片（均0native、不重跑600秒）：效果索引d45f121已双轴0/0。模型8be35a1已双轴0/0，沿同一成功版本缓存原生learner及reservations/settled，短锁内只点读11个身份/版本/兼容列；同来源权威丢失、版本回退、兼容变化及读写异常均拒绝/失效，不忘已确认版本，不读全矩阵哈希。同源连续两次故障及换根真冷启动、原写前后故障/RNG代表见286/287、289/292、294/296；完整selector为19例34.52秒。成熟真实v128/d1072²、同165项全池的3轮公共reserve/settle对照，6阶段回执/操作/概率、完整theta/A_inv/RNG/水位逐值相等，至v134；全读6→1、11列点读0→5、必要typed原子写均6。3轮累计5.106→3.787秒；仅2个热轮每轮中位1.694→1.163秒，冷reserve0.859→0.875秒基本未降。reward=.01是相同构造对照值，不是战斗收益；所有oracle全读/初始克隆在计时外单列。原模型与mask SHA均保持。证据为云scratch `performance-root/approved-selector-version-cache-{probe.py,probe.log,summary.json}`；不据小样本宣布整体任务达标。

诊断去重首片仅去checkpoint内顶层与首批的等价重复：保留当前任务完整诊断在首batches/score_batches，顶层持版本/父/evidence本地引用；保存前浅投影，原比较缓存也保同投影，不先深拷贝双份。恢复核身份后还原同一对象；旧inline只在load时一次确等才alias，同身份不同内容保留两份，未知版本/缺源/错父拒绝。中心原批是来源证据，当前rebound/replayed可不同，仍保留原中心诊断；不称全体系只有一份。公开物理份数首红283→首绿285，旧inline/拒错引用及重放恢复见290/295/301（11例9.52秒绿）；公开评分仍为构造外部边界，重放/存储/配置/选择器与中心均真执行。原66archive实际状态只读离线对照298：全状态恢复逐值相等，archive JSON94,041,361→48,594,798字节（UTF-8），66双份→0双份；首次完整save3.362→1.913秒，含浅投影和原深比较的两次未变化save0.092/0.094→0.053/0.051秒，进度字段save0.093→0.051秒，一记录变化save0.115→0.063秒。旧inline首次load1.243→1.345秒（一次确等成本），新compact恢复3.403→1.281秒。原DB SHA不变，保存成本包含真实SQLite事务，非只量磁盘；原始日志`.local/tests/general-initialization/298-selector-checkpoint-reference-mature-comparison.txt`及云scratch `performance-root/approved-checkpoint-reference-summary.json`。既有search保存计数测试在299另失败于旧fixture缺rule_snapshot，固定8be35a1同例300亦失败；这是本性能切片前已存在的03测试接缝缺口，留统一验证收口，不永久排除。尚余报告原义适配；B不实施。


A报告原义续片只处理已证观察字段：state_observations[].value 的空record新增明确version2/empty_record，现v1及missing/null/布尔/数值/已支持record保留，未来版本3仍DataReadError且不使成功缓存invalid。action_observations与真实action_events（qualification及其它事件的cost presence）逐行resource_costs_storage仅保version/kind/原唯一字符串键；record+空键可从物理null还原{}，非空原键必须存在，只删除原未声明且实际null的STRUCT补键；额外非null/缺原键/坏键拒绝。unknown/null与missing分开，旧无标记不猜。one/read_records/read_many在原_restore_batch解码，flush/recover直接API保持存储态，二次prepare幂等；typed成本列可查询，其他统计{}→NULL及_report_columns不变，不建全报告空路径或变体平台。

302原义首红1例0.46秒（{}读成None），303首绿；307旧无state数组分片混读的None边界红后保原兼容，最终308为15例8.14秒绿，含最高run/read新任务缓存、未来版本成功缓存不重模拟、往返/幂等/旧分片/缺键及冲突拒绝、既有重放与checkpoint。引擎评分是构造外部边界，0真实native；mask原SHA还原。306同一保留raw通过真实typed中心新写/读取，state值和cost presence/值完全复原，2344个已知空费用均恢复；raw165池、旧adapter读回重算0池、修后165池。全部rules/findings、有序具体操作及贡献证据相同；只observation_digest及其parent/operation_id派生变化来自已有其它可选字段STRUCT补null，完整payload不是逐字相等，未改旧身份或原native文件，不据本修扩全字段presence平台。

306单次真实中心写1.411→1.308秒、读0.667→1.212秒，Parquet494065→499783字节；这不是纯性能优化。按同一既有分片仅补一轮热读309，整读0.927→0.840秒，方向不稳定，故不把前次差值确定归因I/O热点；每份report还原调用均仅1次，适配还原本身0.006→0.102秒是新增原义成本。309当前最终产品完整诊断与306修后逐值相等（165池），不含额外引擎；原始证据`.local/tests/general-initialization/302/303/305/307/308/309`对应具名日志及云scratch `performance-root/approved-observation-shape-{summary,hotread-summary}.json`，完整诊断样本在该summary标注的隔离目录。该原义切片7635888已双轴0/0；A合并验证见下一条，无新600/收益/达标承诺，B不执行。


A限定合并验证310：冻结7635888后，原同次云测试批次26例40.74秒全部通过，0native。完整selector19例与公开效果索引2例、两任务共享/旧恢复1例、checkpoint恢复1例、mixed state/新任务缓存2例、空/稀疏费用往返1例在同进程验证，Coba和中心均真实执行，任务评分仅用既有外部边界构造。mask已还原SHA256 6de539a9e5cdca5fe7a0f853b7fe548d85d37ae7b21b04ac2fb73c7413e5bcd2，保留raw SHA3b197ccfe03b36d25684d0124304fb2e41dd8afc46b1467157ad4af0844797af；未修改原报告/旧任务或再次运行600秒。四项A分片均独审通过，局部改善与正确性成本已分列；剩余同样本诊断约2.4秒/父、成熟热reserve+settle约1.16秒/轮、codec还原约0.10秒/报告，不能相加外推整搜索结果或声称恢复旧吞吐。正式固定基线verify、已知旧fixture接缝迁移、最终规格/交付和Windows/游戏验收尚待，B未执行。日志 `.local/tests/general-initialization/310-selector-approved-a-combined-green.txt`。


## Implementation contract（已审最小技术接线）

以下接线保留既有选择器/共享恢复；B只按下节新增诊断时点、独立来源及显式诊断预算覆盖旧eager接缝，不改变模板策略。C50/A21初版已完成有限实际成本探针，之后成本继续计入原预算；记录当前一次learn后的25,078字节分片不等于长期稠密矩阵上界保证。

### 0. B最小接线与来源合同（当前有效）

- 冻结 `config.rule_diagnostics_policy=on_demand/eager`；新任务B，旧无字段eager，不默认迁移旧任务。规则源码、真实binary、profile/input及任务身份检查不放宽；selector特征/奖励版本、MODEL_KEY与共享学习状态保持。
- B普通评分（首次及后续批次）不传完整观察请求、不diagnose；父子评分request按同策略统一，原score/batches/common_key/reward不变，尤其不删除rule_observations强凑共同批次。补采完整复制所引用原评分program/profile/times/seed/input_seed/iterations/reset/burst/trace/binary等输入，仅替换冻结fullrequest及独立诊断用途/来源字段，不按新默认重推；独立purpose=diagnostic/source_scoring_batch_key/真实digest/data_key，放record.diagnostic_batches旁链，绝不算入评分批次、候选或奖励。
- record.rule_diagnostic_source保存scoring_batch_key/diagnostic_batch_key/kind=on_demand_replay；诊断本体evidence指向真正补采批，不伪称same_scoring_batch。rule_diagnostic_status为not_diagnosed/incomplete/complete/mismatch；只有来源有效、补采与所引用原评分批的DPS/samples/variance逐项严格一致且完整池/context成立才可创建selection_intent、调用reserve/predict。mismatch保原分/奖励与来源证据，不发明容差，不能供selector。
- ensure只位于父predict前或明确单候选诊断入口。父完整诊断及池/context可靠保存后再建选择意图/回执，不在reserve后换来源/重抽；已有共享回执按原恢复合同消费。已可靠补采报告只重放未完Python，B恢复不扫全部未诊断归档/待处理候选，read_task永远零模拟。
- 父用ensure计入原搜索预算；显式单候选诊断复用resume_task(diagnostic_candidate_key=..., diagnostic_budget_seconds=...)，必须提供正diagnostic_budget_seconds，无默认额外预算。原额度耗尽后仍可仅做此诊断，独立有界Runtime与记账，不恢复搜索，不动原600秒、原elapsed/DPS/奖励。复用现任务/中心/发布，不建新调度或恢复平台；若手动入口膨胀须报告。
- 收尾1不调用ensure：完成/耗尽/停止时直接输出原最佳GSE/DPS；有诊断显示，没有标未诊断。无最终强补、预算预留或追加诊断收尾额度，无新完成/导出/冠军/训练guard；原30秒反馈结算窗口仅结算已有反馈，不可挪作补采预算。

### 1. 文件与真实 API

新增一个小 `projects/sim2gse/selector.py`，只做特征编码、Coba 状态薄适配及本业务的决策/反馈协调；既有 `result_store.py` 增加同数据中心的权威记录读/原子发布薄入口；`search.py` 接原生成/评分，`task.py`及训练既有恢复点在报告恢复后、终态/预算提前返回前补发冻结反馈；`requirements.txt` 锁 coba==8.1.0、numpy==2.4.4。沿仓库现 .venv/pip -r 准备，不装 full/VW/scipy/torch/cloudpickle，不修改原生/build/runtime。测试进现有 test_rule_diagnostics/test_search/test_seed_training 公开接缝，必要新增 learner roundtrip 定向文件。

固定官方发布 commit 0abed4d9779d254b0501f8be10632765c1ce718a：LinUCBLearner(alpha=1,features=[1,'a','ax'],seed=1)，predict(context,actions)->(原动作对象,p)，learn(context,selected_action,reward,p)。保原生权重/矩阵/交叉编码，不另写学习公式。完整池每项单独新建 dense list，以 `is` 回映 operation_id；同特征不同操作不得值相等误映。空池不调用 predict，沿原 lane 停滞处理。池长度可变，单项维数固定。

### 2. 固定特征 v1（已审初版；编码不含业务权重）

全为 finite 数值 dense list，context 非空。C=50，A=21，原生 InteractionsEncoder 默认模型维度 d=1+A+A*C=1072。字段顺序写为固定 schema；角色、技能、三键、规则 ID、配置摘要仅报告，不作连续特征/模型分区。

Context：
- 当前声明的22种 finding.kind 各计数/全部finding数，另1个other_kind同比例；全部适用规则的findings一起计入，共享一个分母valid位，明确控制这23值：24维。不得除规则数变为随点击增长的无界量。
- observed_fact / hypothesis / unknown 三种 certainty 占全部 findings 比例及共享 valid 位：4维。
- 含未知项规则比例及valid：2维；status unknown或unknown_conditions/unknown_evidence非空均计入，diagnosed不代表全部分支已知。
- 窗口位置有效样本占比/mean/min/max，各value+valid：8维。样本按同sample/input/窗口身份去重；占比分母是全部声明窗口关联样本（含缺字段），均值/极值仅用真实有效相对位置。
- 资源/上限比值有效样本占比/mean/min/max，各value+valid：8维。同sample/input/resource去重；占比分母为本次声明资源的观察样本（含缺字段），无实时上限的比值invalid，不借初始化容量。
- 支持机会按同sample/input去重后/已观察inputs比例+valid：2维，多个规则指同input不得重复计数超1。
- 实际失败/已知实际尝试比例+valid：2维。
总50。计数/身份来自全部适用诊断，集合不挑高位；时间/资源只用同一次已采字段及明确分母，缺上限、窗口/输入关联或尝试完整性时保持 invalid。未知数值占位0仅与对应valid一起使用，不能被当成真实0。默认报告没有实时资源上限的项仍invalid，不拿初始化容量补学生事实。

Action：move/insert/reduce_wait/remove_wait 4维独热；贡献模板8类+other 9维multi-hot（只表示类别，不决定资格、候选或权重）；源相对位置、目标相对位置、有向位移、有符号加减量，各value+valid 8维。有符号加减量以受影响展开点击数/原程序展开点击数表示（insert为正、wait减少/删除为负、move为0），不是混用裸块数/点击数。总21。类别词表固定于feature版本，不随当前配置排序改含义。路径沿现有展开映射转序号，同Loop多次出现采用全影响位置的平均相对序号；无唯一可解释映射则invalid，不用path字典序。每个具体operation身份仍单独保留。

同一实际采集报告的诊断结束时一次编码context；eager随原评分批次，B随diagnostic_batches及rule_diagnostic_source旁链可靠保存，恢复/缓存复用，不在每个备选操作重读报告或解析整包。当前诊断不暴露的窗口/资源数值优先用现报告必要字段；没有证据就invalid，不新增观察。完整池action编码只遍历现操作/映射，不编译/模拟池项。

模型维度导致 A_inv 最多1072²个float，约9.2MB未压缩。第一轮trip同时记录predict/编码/原子保存成本，计入任务预算；不增加引擎实验、不截池。如该实际成本妨碍600秒任务，先报告实测，再缩通用表达，不擅改算法。

### 3. 真正的状态及 O(1) RNG 薄适配

LinUCB无save/load。保存原生 `_theta`、`_A_inv` 的None或完整float数组（按DOUBLE[]/DOUBLE[][]有类型存储），alpha、有序features、原始seed、Coba版本、feature/reward/state版本和维数。构造同learner恢复encoder/predict辅助绑定，不序列化numpy模块；恢复后对原生字段形状/finite检查，失败拒绝。固定非空dense避免初始化删x/动态类别编码分支。

RNG薄适配已按固定源核准，实际持久化仍须公开验收：CobaRandom.__reduce__只存初始seed，不能pickle冒充进度；只读取原生 `_randu` generator的GEN_CREATED/GEN_SUSPENDED frame中整数s（核同版LCG参数、类型/范围/frames），用原生CobaRandom(s)构造后只移植 `_randu`，保留原始seed元数据。无自写RNG/矩阵公式；不逐历史predict O(n)重放。未知版本/解释器帧形态拒恢复，不吞错重置。

最小真实roundtrip包括未初始化、已learn、0/多次predict、同特征不同operation及变长池：同snapshot恢复两份，比较下一具体operation/p，再同reward learn比较theta/A_inv及再下一predict。本轮真实库探针已验证初始None/已learn状态、下一具体动作与概率、下一learn矩阵、变长池及同特征独立对象；产品共享恢复仍待公开TDD。

### 4. 共同数据中心逻辑权威版本，短锁+CAS

不使用每任务 `destination.parent/cache.sqlite3` 冒充全局模型，不依赖双WAL ATTACH崩溃原子性。复用 `result_store.DATA_ROOT` 与既有data-store原子同键write/read_key，以及现正式冠军短文件锁/CAS写法。

原v1在 `search_learners` 的同MODEL_KEY完整记录含矩阵、逻辑版本、RNG、reservations/settled（待结算回执/结算水位）。本次批准的v2保留此完整键，新增同中心 `search_learner_controls` 的同MODEL_KEY轻量键，不含theta/a_inv（模型向量/矩阵），以base_version绑定完整键版本；不是新数据库、服务或经验平台。逻辑权威由持原共享锁、校验成功后的完整键与控制键合成，task不存能回写的模型快照，配置digest仍不分模型。矩阵保持有类型数组，少量身份/回执元数据允许JSON，不把报告整包字符串化。

v2读取/选择/结算必须持现有全局共享锁。正常active（活动）状态的完整键或控制键缺失/损坏、坏形状或已知版本回退均停止，不静默重置；只允许下述可核验的bootstrap/migrating（引导/迁移）阶段继续未提交步骤。控制版本新于完整键时，仅base_version等于完整键版本才合成；控制旧于完整键时，采用已吸收控制状态的完整记录，不逐次删旧文件。reserve（选择）及no_learn（不学习）只原子替换小控制键；首次predict（预测）初始化矩阵例外，仍全量保存。有效反馈在最新合成模型上原生Coba.learn（学习），只原子替换包含最新控制状态的完整键；旧控制自然失效。任一发布异常都按原契约持锁重读提交版本/回执，不盲重试或重复学习，不假称两文件同时原子替换。

state_version升为2，但feature/reward（特征/反馈）版本及MODEL_KEY不变，不按角色或任务分经验。迁移前必须停旧写入器；旧writer在原参数校验处拒绝v2，不能把该拒绝当作可与旧writer继续并写的许可。

首次初始化按bootstrap→active（引导→活动）推进：先发布phase=bootstrap、逻辑版本0/空经验/RNG初值的控制键，再发布矩阵为None（未初始化）的空v2完整键，最后原子切换控制phase=active；active之前不调用predict（预测）。重启遇合法bootstrap且完整键尚缺，可在同锁内幂等补建同一空版本0记录，不重预测、不重置已有经验；首次实际predict仍完整保存初始化单位矩阵/零向量。正常active后完整键缺失则拒绝，不与未完成bootstrap混为一谈。

v1迁移按migrating→active（迁移→活动）推进：持同锁核旧完整键可读/控制一致，先发布phase=migrating且与旧完整键同逻辑版本的控制键，再原子写同版本v2完整键，最后切换active，不虚增逻辑决策版本。旧完整键仍v1时以它为权威；完整键已v2而控制尚未active时，只补完成一致阶段，准备控制键不算新决策。

异常必须同锁重读权威阶段/版本/回执；已提交步骤不重做，只对明确未提交步骤有界重试，不重复predict/learn（预测/学习）。正常每次决策仍只有一个权威键原子替换，不是每轮双写或多文件事务。完整/轻量版本关联、三阶段各中断点、写前/后异常、旧控制残留、跨任务交错及旧任务恢复按原TDD门禁核验；目前阶段回归与诊断小样本不等于本次整套完成、整任务收益或最终验收。

每task decision单调递增，沿原pending顺序结算。只保尚未结算reservations（每任务受原round limit限制）+各task已结算水位，不保O(历史predict次数) RNG重放日志。若现原pending存在逆序结算路径，先调整为原head退队边界结算，不另造调度。

reserve(intent)：先调用现flush_reports，再将(task_run_id,decision_id,parent_identity,pool_digest,完整具体操作身份/特征schema)意图可靠存原TaskStore.save（不能在report_buffer非空时误称save已存state）。短共享锁内读最新权威记录；先查decision是否≤已连续结算水位，已结算不得重predict；已有同intent receipt则原样返回，身份不同拒绝；否则原生predict一次，原子保存新RNG+该receipt+递增model版本，释放锁，再立即将该work存原pending并可靠保存，不能整round生成完才落盘。receipt含intent摘要/选中operation_id/context及action特征/p/选择时版本，崩溃在共享发布后、pending保存前仍先消费这个intent/原receipt并接续同父生成，不重新抽样/换父/重开轮。最少复用现pending和一个生成中round标记；reserve后的apply/行为检查失败也保该decision有界终态pending，按序no_learn，不continue留水位洞。

feedback(receipt,evidence)：原head候选有完整共同批次后，短锁内读最新模型；水位/receipt去重，已结算不再learn。合法reward则调用原生learn一次；无有效共同证据只记no_learn原因而非reward0。原子保存最新状态+receipt结算/水位+版本，再补task本地状态。already_seen恢复分支也先补冻结反馈，不能先覆盖为duplicate。共享write异常后必须重新读取同key：若receipt/水位证明已提交则补本地状态，若明确仍旧版才从重读的原生状态重试；不可复用已learn内存盲重试。无法读取则停止并保意图。task保存失败再恢复读共享水位，零重复learn/零重评分。锁绝不跨模拟；不同任务反馈更新最新模型，不拿旧快照覆盖其他任务。

### 5. 现搜索接缝及 reward

search.optimize保lane/base轮转；B在已选base的predict前ensure完整诊断/池/context并核真实来源，eager沿原同次诊断。将mutate/160尝试及1/16洗牌替成：基于base的全部诊断与完整池，仅先按原seen/本轮已选结果行为过滤后，把剩余全部可评分操作一次交Coba，生成同父若干独立一操作pending（每个predict恰一操作），仍受原round_candidate_limit/候选预算/已见行为过滤。每个选择都复用02 apply/行为检查及父/operation身份，保持原多起点。原02完整池与被seen过滤的原因仍报告，不按特征相等或模板筛选；不能先predict后反复拒掉同一最优行为制造假停滞，不随机兜底。旧随机初始化保留；生成后原pending/screen_round/早筛/挑战/晋级/冠军逻辑不重写。

reward只比较生成父与该候选的已完成共同search批次。共同身份按原request仅剔除program、behavior_identity及纯观察trace后，全部场景、seed/input/times/iterations/计划/engine等核对，不拿同batch_index替相同条件。各自用实际samples加权DPS，(child-parent)/parent；parent>0且finite才learn。父没有的批次不补跑；取消/错误/半报告不造0。早筛有共同完成可learn。验证/全球冠军不是生成父，不偷换反馈对象。

task/dual/training均共用optimize；版本纳入现算法/条件/缓存身份，旧结果可读，旧任务不得静默转新算法。日志开关不控制选择/学习/预算，只控制性能字段持久化。

### 6. 顺序表与恢复点

| 时点 | 原任务存储 | 共享逻辑权威版本发布（v2按上节选完整键或控制键） | 恢复/失败 |
| --- | --- | --- | --- |
| 父诊断准备 | B仅目标父ensure，独立diagnostic_batches及来源/状态可靠保存；eager复用原评分诊断；完成后才进入selection_intent/reserve | 尚无模型变更 | 可靠报告只重放Python；来源/统计不一致或池/context不完整不创建选择意图/回执，不覆盖原分 |
| 选择前 | 原seen/同轮结果去重；完整父池/context后flush_reports→save完整intent | 尚无模型变更 | 未提交intent不启动predict/子候选评分；B补采已在前一阶段 |
| 选择 | 继续持有原任务运行锁，未开原生进程 | 短共享锁重读最新→先水位/receipt检查→原生predict→RNG+receipt+version同写 | write报错须重读提交身份；只明确未提交才从重读旧状态重做 |
| 入队 | receipt和恰一操作放原pending，可靠save后评分 | 不持共享锁 | 共享已提交、本地未入队时同intent取回原receipt，不再抽样 |
| 已完成评分 | 原head保候选/生成父共同search样本及请求，flush_reports→save冻结反馈意图 | 尚不learn | 中断后复用现完整成绩，不重新模拟 |
| 反馈 | pending尚可重试，不提前记learned | 最新模型learn＋该decision结算水位＋receipt退场＋version同写 | 替换后异常从重读水位识别，不能再learn；任务只补发 |
| 退队/恢复 | 原归档/晋级/退队；task及训练phase done在recover_reports后首先调用同一reconcile冻结反馈，再允许completed/预算早返 | 只补尚未结算的已冻结反馈 | 暂取消pending不封no_learn；最终预算终止仅已有完整共同证据可learn，无证据记no_learn，不补场 |

同task结算只在原head顺序，不在screen_round并发future回调结算；连续水位无洞，未结算receipt保留。共同批次request只剔除原候选特有的program、behavior_identity及纯观察trace，其余字段全部相同才配对。rule_observations不删；日志开关须以同数据、同初始模型的公开reward/learn数正反核验，仅已审MVP观察边界，不推广全职业getter纯度。父与子都按实际samples加权，不用validation替换。

最终预算终止时，先按原pending顺序可靠冻结全部已选decision的反馈，再有限结算；临时取消仍保留待继续项。整批采用既有锁等待上限30秒作为收尾截止（线程锁与进程锁同受约束），不增加搜索预算，不调用预测/评分；已开始的同步原子写允许完成，实际耗时照计，不声称硬30秒抢占I/O。到期/取消后保留未结算intent及selection_feedback_incomplete供原公开恢复补发。活任务沿原墙钟计时，无活runtime的恢复累加实际补发耗时；恢复penalty仅自身受原剩余额度限制，真实累计超过总预算不得截回上限。

已完成任务也须在恢复后补发中心结果：读取原完整runs，仅更新rule_steps、selection_feedback_incomplete及elapsed_seconds，有差异才写；其余候选、DPS、验证、最终结果逐值保留，发布失败下次可补发而不再learn/评分。中心elapsed沿原_store_run的发布时快照（已含本次模型锁等待/学习/补发准备耗时），末次同步原子写尾段实耗finally保存在原SQLite账，后续预算按该真实账处理；不循环回写自身写耗时，不改read入口。

同一有限结算入口还用于预算恢复早返前，幂等补齐半批冻结中断后余下pending的真实成绩意图；任务及训练透传原取消信号。创建/删除intent与incomplete布尔标记同次可靠保存，空入口纠正旧假True。dual外传已启动runtime时，仅从其墙钟段消去已经计入used的补发实耗，避免双计，其他原准备耗时保留。

补发前未耗尽、但补发实耗跨总预算时，也在同一次入口内补齐其余pending意图；继续使用原整批截止，不另开30秒。截止/取消已到仍保存余intent/incomplete，未到则按原顺序结算，不增加评分。

### 7. 最小 TDD 顺序

B新增公开TDD先核薄多候选/read零补采、父完整诊断→真实Coba→原评分奖励；再核typed NULL混合组、缓存重复resume/取消与发布中断、mismatch保原分、eager冻结、训练共享路径和显式正预算独立记账。随后小真实链验证；本次未跑新600秒，不凭旧测试或单样本外推400–500。以下原序列保留为已有选择器/eager门禁证据，B不得据“零重评分”误禁止独立诊断补采，也不能把补采计为评分。

1. 先锁定依赖、最小实际库成本/roundtrip，记录真实predict/learn/状态写读/RNG下一predict；不做新增模拟实验。矩阵成本用当前最大111项完整真实池的dense表示测predict/learn/模型中心写读（无引擎），不只小池roundtrip；先看成本再冻结v1，未过不铺全搜索接线。
2. 公开run_task/read/resume构造既有外部评分边界，完整池→真实Coba选一项→原pending/评分→共同批次reward→中心保存重读，先红后绿；不mock learner/解释器。库验证不替代该公开链红绿。
3. 两任务交错、共享发布前/后保存失败、task补发失败、已评分恢复零重模拟/零重复learn，CAS版本冲突；不新建恢复框架。
4. 原多起点/预算/早筛/取消/缓存与训练公开代表回归；池空停滞不随机。
5. 01→02→03冻结后最小真实连通，最后按票据只旧/新各600秒，不100场或额外收益门槛。旧完整方案固定5d7165b；80cb3a8/a6ca951与其projects/sim2gse树均为d83c33c2803620e4880199c84fd8965c4633dd42且scripts无差。旧包含均匀初始化＋旧随机/启发式，新包含本次新初始化＋规则单步学习，不能只换选择器。外部角色/场景/输入节奏/宏与45秒周期保持；旧首爆3000ms、新按获批起手对齐first_burst_ms，各自实际锚点必须披露，不能把新锚覆盖旧方。


真实库准备证据：231依赖安装，232首轮因元数据字段二次JSON编码在恢复断言失败；按现typed schema直接传dict/list修探针输入后233绿。证据`.local/tests/rule-selector-probe/summary.json`，0native；实际中心API原子单key读写，未实现共享事务或公开搜索，不能以探针冒称03交付。


03首核心实施切片（历史首次冻结，后续独审见Current progress）：234最高run_task/read_task红为原路线没有自动selection，235首绿1项4.53s；236日志开/关2项8.97s，均核同生成父共同search批次reward及learn；237两任务共享最新模型/旧任务恢复不回滚、自动选择评分前取消后同decision恢复2项9.73s；238诊断取消后报告重放丢选择context红，复用同报告编码后239绿1项3.19s。240冻结核心代表为5项公开＋2项特征7 passed/23.71s；独立原生learner/真实中心/写前后异常及完整特征边界另7 passed/16.63s，来源分列不重复计成新增业务验收。公开评分仅替换既有外部引擎边界，Coba/解释器/中心均真调用；没有新原生修改或战斗模拟。50维生产编码真实源在selector.CON-TEXT_SCHEMA及定向证据，窗口关联/资源current+实时maximum/实际尝试均按缺证valid=false，已观察缺值与完全无观察分母分开，非probe末20维常量占位。云受控mask适配已原SHA还原。首核心冻结后再收其余恢复/训练/真链及两组600秒，不以本轮构造绿标整票完成。
