# 实施中的契约承接：前置变小后仍能发现什么错误

状态：开发候选，**尚无修改后的Windows真实118或性能通过结论**。完整库存见`coverage.md`；此文专门解释发生变化的接缝，不用断言数量替代风险证明。未列出的契约保原实现和环境，不表示无需最终完整验证。

## 1. 公共训练编排：六实例改用已有类型化内存中心

仍标记real。`memory_result_center`运行真实DuckDB及既有数据中心的记录类型转换，并非ordinary或物理Parquet验收；每例新建独立连接/表。材料必须在该中心启用后注册，`memory_registered_six`明确建立这个依赖，不能注册在旧后端再读空的新后端。

| 原节点/参数 | 仍可触发原失败的链与断言 | 不再在本节点证明的物理部分及承接 |
|---|---|---|
| 四模板prepare/run，成功 | 公共CLI实际读取四个模板并建立四个真实任务目录/SQLite；六材料不减，prepare四组/六种群、24次coarse、五种轨迹、每组上限5/总峰值>5且≤20仍由真实线程和Event观察。若少开组、串行化、重复粗评分或来源场景串线，原计数/集合/峰值断言仍失败。 | 报告中心写入不落Parquet，不能据此声称四组Parquet写盘已验。正常真实发布由同模块`test_public_run_uses_all_materials_ga_and_publishes_four_five_scene_results`保留物理中心；共享报告发布竞争由interface的真实同时任务与位置清单用例保留。四组独立SQLite和真实评分重叠未替换。 |
| 四模板prepare/run，一组失败 | 原San'layn单目标coarse位置实际抛错；同一真实调度结束后必须恰好3组完成、25次尝试且24个唯一请求；失败组原冠军仍从同一独立类型化中心读出比较。错误影响其它组或覆盖旧冠军仍失败。 | 与上一行相同；物理报告损坏/补发另由下述原physical节点保留，内存中心通过不算持久性证据。 |
| 取消/恢复 foreground-on_to_on | 真实foreground文件锁和取消事件，任务SQLite实际关闭/重开；paused、retest、report_intents清空、successful>6都读真实SQLite。恢复从原目录加载，旧成功请求不得再评分，日志开关/配置冻结/两代/时间曲线文件及离线不评分断言仍执行。 | 中心报告是同进程独立DuckDB数据，不证明进程退出后的Parquet持久性。原物理正常发布、12条报告组损坏恢复，以及checkpoint部分提交/重开用例继续承担该风险。 |
| 取消/恢复 foreground-off_to_on | 与上一行同一真实取消/恢复链；原初始关闭、恢复开启的诊断状态断言不变，错误继承旧开关或刷新冻结配置仍失败。 | 同上；不把中心内存读成功当物理落盘。 |
| 取消/恢复 interrupt-on_to_off | 评分边界原位置实际抛KeyboardInterrupt；只有未提交请求可重试。真实SQLite记录及两次请求集合仍比较，因此误重评已成功请求/丢未完成请求仍失败。 | 同上；未改变真正中断位置、SQLite落盘或文件曲线。 |
| 失败GA曲线/离线比较 | 仍在首个评分位置抛NativeEvaluationError，公共CLI必须失败，真实task.sqlite3/identity及曲线文件仍存在；离线命令被禁止启动评分且源字节不变。 | 此路径本来无成功评分报告，中心后端变化不取消任何成功Parquet断言；它不承担Parquet持久性验收。 |

**明确保原的物理代表：**训练正常发布仍读实际分组，断言最大12/合计64/目录存在；训练publication failure节点仍保四个旧冠军，删除真实12条Parquet分组，篡改SQLite摘要后只补原12条并验真；全部9个连接、5个checkpoint及1个诊断真实节点不改。不得将以上6个内存中心实例计入“物理落盘实例通过”。

## 2. 冠军/网页恢复共同前置：四个默认原生来源缩到两个

仅`unchanged_champion_engine`消费者使用。先实际执行生产`initial_programs`，取前两个合法不同输入；不动外部训练/正式冠军注入和验真。原本已有的固定子代仍保两完整代、正常每finalist三份128请求，不减复测/样本。四来源行为由`test_retired_capabilities`的公共四起点节点及正式冠军十来源组装普通规则节点继续明确断言；不把下面最小入口说成四来源集成。

| 消费者 | 原风险仍由什么触发 |
|---|---|
| 正式冠军HTTP双场/完整集合导出 | 真实POST/GET、两场任务、编译/导出边界、三个导出成员和完整集合仍走原公共链；两个候选保胜者比较，不是预设完成结果。任一场不完成/少导出/无集合仍失败。 |
| 保存winner后公开resume补发布 | 仍在实际中心champion写入处抛错，真实任务完成并落盘后修改elapsed状态；resume两次禁止evaluate，比较既有成绩/批次/快照和发布状态。候选数不决定这条失败/恢复接线。 |
| 管理入口导入v1历史 | 原低/高分历史来源、目标、字节、验真、不能覆盖现有冠军及全部比较不变；只减少之后当前GA原生准备，历史候选不删。错误挑来源/旧成绩复用/覆盖原冠军仍被原断言发现。 |
| 正式冠军部分批次取消/外部更新 | 原先真实完成的单场冠军仍由当前公共run生成；新双场首评分实际取消，再由外部更新版本并公开resume。旧快照、不能发布半批、版本/分数保持与重新评分适配断言不变。 |
| 正常双场自然复测 | 真实HTTP生命周期仍运行生产GA，等分边界促成自然早停；每场381样本、3×128、natural_stagnation、三导出及发布状态都从结果读取，不手写完成状态。 |
| publication失败补发不重评分 | 真正的publish调用仍首次抛错，已完成场的评分调用列表必须非空；通过HTTP恢复后该场列表不得增加，pending转published。少候选不消除这个“先评分、后失败、再恢复”的顺序。 |
| 首评分失败保reference可读 | 真正第一个evaluate仍抛错，HTTP失败后读真实任务结果；batch_keys仅reference、无search records及原错误仍检查。候选数量与首评分前失败无关。 |
| completed保存失败保winner恢复 | 真正completed结果保存位置首次抛错；之前本场评分列表非空，恢复后不增加，物理TaskStore与公开read仍返回已验winner和发布状态。未将落盘失败或恢复替身化。 |
| 可选checkpoint四故障结果仍可读 | 先通过真实HTTP完成源任务；实际SQLite WAL合并、四种坏字节/字段、resume失败、可靠中心错误优先级和原源字节不变仍执行。两个候选只缩短制造正常源任务的前置。 |
| 双场start/resume引擎身份 | 小引擎文件与实际read_bytes计数仍独立；每次任务/恢复自己的TaskRuntime，两个scene的runtime不同，篡改/取消路径未改。候选数减少不能让错误身份检查次数通过。 |
| 新训练到来不更换冻结冠军 | 旧训练和更高新训练的完整凭据、单目标/aoe两来源均保留；原取消位置、冻结中心读取故障和HTTP恢复照旧。仍能发现重新挑新冠军、跨场串线或快照变化。 |

两处共同HTTP助手显式`max_processes=1`，只服务上述非并发目的链；四模板4×5和独立同时任务测试未改。双场仍逐场真实完成，不靠去掉外层竞争计时。

## 3. 模拟配置两真实节点：最短合法任务而非另跑宽搜索

复用已有`_fixed_search_population`，一个明确合法起点；原公开run/resume、真实输入/输出/SQLite、原断言全部保留。第一项仍检验omnium仅删除有效行、名字/注释保留、原始/有效bytes/hash、状态一致以及改配置恢复在SimC前拒绝。第二项仍检验目标2冻结配置、原始/有效文件、篡改两输入在TaskStore打开前拒绝、三个产物字节不变以及原配置恢复成功。这些风险由输入/恢复条件触发，不依赖四种候选；GA选择多样性不再在这两项重复执行，仍由其它独有规则/原生见证覆盖。

## 4. 两条双来源原生语义：每worker一次固定precheck

`reviewed_native_preparation`只有一个固定profile、审核定义及默认模拟配置，无通用缓存键或动态来源。每worker在专用pytest模块目录/独立临时中心真实完成一次公共precheck，之后仅供只读消费。每个用例deepcopy返回对象、重新写自己的profile、重新编译自己的loop、在独立controlled/quiet目录真实调用sequence.evaluate；新的TaskRuntime仍执行受控引擎身份核验。原queue source/member、跨战斗冷却/reset、native_execute/dispatch_failed、quiet无trace断言不变。

此共享不覆盖修改输入/定义的用例：缺审核、错误talent/有效输入、真实药水、错误spell身份、身份篡改及start/resume重验都继续各自独立运行。两个消费者不会向module准备目录传写输出；它们只读取capabilities、candidate及native identity，传出的对象已深拷贝。真实precheck先于两消费者是预备工作，而非对每例成功结果的缓存跳过。

## 5. 网页/冠军报告由三次重复写收敛为一次

旧链是`_fast_evaluate`写单目标文件→`_ui_score`改场景重写→`champion_engine`再写相同报告。现在第一层直接按simulation_config写最终场景报告；第二层仅补trace来源（不改report），第三层不再重复写。真实生产评分没有修改，文件内容与返回报告仍一致。

云端直接开发诊断已核两生产者×单目标/5目标四种组合：一次native.json写入、实际文件JSON等于返回报告、目标数正确。该诊断不冒充原生引擎/Windows验收；现有公开结果、历史报告验真和损坏/恢复断言仍由最终完整真实组运行。

## 首候选前的云端开发证据（历史）

- 云端普通层改前410+130通过；共同报告/候选修改后以及统一夹具整合后均410+130通过，118真实仅收集/未运行。
- 改动文件全部原assert/self.assert/pytest.raises的AST相同；这仅证明未删字面断言，上述触发链分析和最终Astra/真实验收才负责覆盖有效性。
- 当时尚无修改后GSE时间，不承诺节省>7.61秒；后续实测见第6节及`verification.md`，只有整个候选官方全仓无缓存通过且<30才可达标。

## 6. 实测后统一收窄非目标探索（第二候选，待正式全仓）

首候选并未达到全仓目标。修正独立单场/HTTP的`max_processes`身份不一致后，同8路单组对照证明工作量确有下降，但不证明全仓达标；详见`verification.md`。新证据显示准备/清理很短、worker无大偏斜，所以本次不再扩共享准备，也不改调度器，而是统一真实流程的最小合法工作量。

既有`_fixed_search_population`移至其依赖`_initialized_starts`所在的`test_search`，仍先调用生产初始化，再交明确合法输入；其它模块复用同一函数。它不替换生产GA、分代、评分、复测或持久化。浏览器原有自定义随机数类被该既有能力替代。全局产品默认值、随机变异专测及并发专测均不改。

### 每个变化后的风险触发链

| 节点（模块内唯一方法名） | 最小前置及仍实际触发的风险 | 本节点不再重复承担什么、承接在哪里 |
|---|---|---|
| burst `test_page_dual_scores_character_adapted_seed_without_changing_training[True]` | 一个普通合法起点；旧训练冠军仍通过生产适配和注入加入当前GA，HTTP双场均完成。仍逐项检查原程序/移除位置/移除原因/适配后程序确实进入search records、当前成绩不等于99999、源记录完全不变。若跳过适配、误用旧分、改坏来源或漏掉注入，原断言仍失败。 | 不是四默认来源或随机新候选测试；四来源真实入口与真实变异代表见下方。两场及其resume使用同一显式`max_processes=1`，没有独立默认2的同条件预建任务。 |
| burst `test_dual_keeps_completed_child_and_recovers_without_searching_it_again` | 一个起点、无无关子代。第一次真正完成single_target后在aoe的`run_task`入口抛错；公开HTTP恢复仍运行aoe，调用计数强制single_target恰好一次，最终三导出/说明一致。之后篡改真实input.original.simc，必须拒绝恢复。 | 不承担GA多样性。真实任务目录/SQLite和冻结字节保留；该节点原本已用内存报告中心，本次未进一步替换物理层。 |
| search `test_task_final_publish_failure_still_closes_connection` | 一个起点；最终实际写`progress.pending.json`仍在reservation释放后抛同一OSError，真实连接必须关闭且只记录该一次失败。报告中心改用现有typed-memory，SQLite连接和失败的物理文件接缝不变。 | 不再在此证明Parquet落盘；物理报告写入/重开由下方代表保留。不是随机候选或默认数量测试。 |
| search `test_public_entry_runs_multi_start_search_with_isolated_validation` | 明确两个不同合法起点，首个候选仍真实原生执行，其后构造评分边界不变。仍要求至少两起点、公开read一致、winner/locked一致、381样本、search与final种子互斥、独立验证完成。报告中心typed-memory，真实任务文件/SQLite保留。 | 不承担默认恰好四来源；独立retired_capabilities真实节点明确断言4。统计分离与样本断言不减；不把内存中心算Parquet持久性通过。 |
| search `test_search_resumes_without_resetting_elapsed_time_or_batches` | **保留两个起点**，第二次评分新增断言必须32场粗评，不能变成128场复测。仍在该点阻塞、通过公开入口观察0个已提交批次、拒绝运行中恢复、取消后真实重开SQLite并恢复；已成功key、累计时间/批次及诊断计数原断言全部保留。报告中心typed-memory。 | 不承担跨进程Parquet重新打开；真实硬退出、checkpoint重开和损坏分组代表不改。不能将这条内存中心结果声称为物理中心耐久证明。 |
| search `test_cold_cache_storage_failure_and_cancellation_do_not_resimulate` | 三次公开调用共享同一明确起点与配置；先真实写入物理中心，再在读取成功缓存时分别注入DataReadError或置取消事件。评分仍被禁止，第一份结果必须保持。 | 一个起点不再重复多样性；该节点**仍为物理中心**，未以内存替换冷读风险。 |
| search `test_valid_exchange_report_is_kept_when_center_write_fails` | 一个起点足以生成真实native.json；实际中心写search组时仍抛错，所有已成功交换报告必须仍存在且可解析。 | 不要求达到12条满组；12条边界由interface登记中断及population补报代表保留。此节点仍有真实文件和物理中心，未改失败位置。 |
| search `test_completed_search_removes_native_report_exchange_files` | 一个起点仍走完成和实际清理；文件全消失、伤害分布/宠物伤害数值和类型、read_task结果、候选引用、原始参考报告及只读指针断言保留。仍写入真实foreign.parquet坏分片并验证点读不扫坏片。 | 不承担候选多样性；**物理中心和坏片都保留**，不是内存清理模拟。 |
| interface `test_browser_computes_copies_and_clears_real_candidate` | 使用既有typed-memory报告中心；真实Edge、页面交互、诊断开关6次请求、一次真实POST双场任务、真实原生评分/上游编译/剪贴板/输入修改清空仍运行。任务SQLite和输入/结果文件仍真实，1候选两代、381样本、180ms输入、三导出和完整集合不变。 | 不再在浏览器一例重复Parquet持久性；下列物理发布/损坏/位置/锁代表承担。它仍不能被ordinary或构造HTTP代替。 |
| interface `test_public_service_simulates_selected_import_and_returns_dps` | 本用例显式iterations=2、max_processes=1；原生参考和受控执行均真实，选中THIRD_PARTY、目标5、DPS>0、无可复制搜索结果和diagnostic invocation文件全部保留。2次请求产生合法非空样本。 | 这不是100场精度/方差验收，原来也没有这种断言；正式GA统计仍保32场粗评与每finalist三份128、381样本。默认无覆盖参数的真实入口由character_export的原生引导饰品节点保留，不修改生产默认100/2。 |
| interface `test_dual_freezes_timeline_setting_and_preserves_storage_failure_recovery` | 仅该服务实例显式max_processes=1，两场和恢复都沿同一配置；仍在首评分时改真实配置文件、检查两曲线冻结/时序，实际rename物理中心引发storage错误，再恢复目录和完整集合。 | 不承担默认进程数或内层并发；物理中心不替换。四模板4×5和同时任务/进程所有权专测不动。 |

### 不变的明确代表，而不是按数量声称覆盖

- **四来源/默认入口：**`test_retired_capabilities::test_public_formal_search_without_profession_rule_library_keeps_native_three_part_scope`仍通过公共run/resume并明确`len(starts)==4`，不应用本次固定群体；`test_character_export::CharacterExportTests::test_public_entry_simulates_native_channel_item`仍不覆盖search_config，真实走参考/受控原生执行。数值默认值还由原普通配置测试直接约束。
- **变异/多样性：**`test_search::SearchAndValidationTests::test_task_mutates_unexecuted_apl_button_and_scores_exports_it`仍例外保真实变异门；interface的WaitClicks多候选选择和原生导出也不改。新最简通道不冒称这些风险已在自身重复覆盖。
- **统计：**原formal生产合同、32场粗评、两完整代、独立三份128及381样本不缩减；浏览器真实原生双场、正式冠军自然复测和multi-start原断言均保留。此次降低iterations只影响导入烟测，不降低正式复测合同。
- **物理报告/故障：**interface的12条发布后登记中断、丢失/截断.report-locations、两个任务真正同时写入；search的损坏Parquet精确补发、冷读失败、交换文件保留/清理；population的完整64条发布及12条损坏补报；全部checkpoint/连接节点继续物理执行。真实硬退出、真实进程所有权及四模板4×5不改。

云端使用现有`memory_ga`直接驱动生产formal_search得到反例：1起点的前两次评分为`32,128`，2起点为`32,32`；均两完整代。因此不能把暂停第二批的前置缩到1。该证据只证明阶段/采样链，不证明物理提交；实际SQLite的0→已提交/重开断言留在真实节点并等待最终全仓。
