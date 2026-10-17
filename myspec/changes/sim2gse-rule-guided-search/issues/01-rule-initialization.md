# 01：规则起点与合法导出

Parent: [总开发规格](../spec.md)
Status: draft
Triage: needs-info
Assignee: Implementer
Blocked by: 无其他开发票；本次配置化修订待确认总规格2节契约、10节决策及逐条规则review，旧实施授权不自动扩大。

2026-10-17 本票旧初始化已有实现和历史验收记录；本次仅更新两库配置化方案，新增范围未实施，回到draft/needs-info。02/03未开始；历史Comments保留，不代表新范围已批准。

## What to build

让现有任务生成一个来自真实角色静态参数的规则起点，替换且只替换目录均匀来源，并经现有编译器导出GSE。

范围：按[总规格2节](../spec.md#2-两个可编辑规则库与通用执行机制)迁移两个可编辑结构化规则库、通用数据执行及现有邪DK绑定；一次性安全静态动作采集补口；各CD及资源消费动作各一次示范骨架；按八规则契约的静态可判定范围填充（第4条保留绑定及unknown，动态优化交02/03）；现有起点入口和合法导出。邪DK骨架只统计符能，符文仍约束动作。Outbreak条件、过程选择和参数来源写入专精库，通用生成器无技能硬编码。具体持续秒数不得凭用户分层确认擅填。

复用原生目录及角色生命周期、initial_programs、现有程序表示、编译导出、行为身份和爆发保护。只实现已确认的有限数据操作，不写完整APL解释器、模拟器或新调度框架。保存、加载、合并、快照、摘要及原生事实边界统一依总规格2.1–2.5，不在本票另定义schema。

## Acceptance criteria

- [ ] 真实角色参数来源及时点可核验；有效GCD不冒充基础trigger_gcd，必要多资源值不填假值。
- [ ] 原三个基础来源及训练/冠军边界不变，只替换均匀来源；确定输入产生确定初始化结果。
- [ ] 两库为纯结构化数据；全部条件、次数、相对优先/依赖、阶段停止、unknown及映射可见。移除spending_decisions等业务callable及执行层固定类别/ID分支，不以回调注册换壳。
- [ ] 骨架使用各CD一次示范及绑定资源消费动作一次示范，不累计一份容量；消费总量只作报告，第二层不把示范次数硬锁为最终要求。邪DK单体按用户批准覆盖一次可用且对应天赋开启的枯萎凋零，原APL至少3目标条件与来源保留并明确初始化例外。
- [ ] 真实GSE、合法导出、逐位置映射、参数来源及精确/近似/unknown清单可供审阅；修复后以真实角色重跑初始化，完整列出每节点技能/WaitClicks、理由及编译输入映射，不混用构造样例。
- [ ] 第4条静态初始化保留完整绑定及unknown、未应用说明；不要求动态短窗口独立调序，不冒称该规则已经执行。
- [ ] 按2026-10-17用户批准，可用灵魂收割在单体和AOE中均纳入普通CD一次示范；使用真实静态参数，保留完整动态条件及unknown，不固定斩杀/黑暗突变时点。
- [ ] 固定爆发不变；单空点击、缺字段、结构超限明确失败，不扩语法或静默回退。
- [ ] 复用task.run_task集成接缝及现有程序测试；构造样例不冒充真实角色产物；检查与独立审查证据记录完整。

- [ ] 按总规格4.1逐条迁移8规则及23条现有APL绑定，保留完整来源和人工覆盖；未审表达不标已确认，AOE脓疮/天灾链不默认启用。
- [ ] 仅改配置优先/次数即可由现有task入口生成不同结果，原生binary/hash不变；重命名别名/ID及第二份synthetic专精配置证明无硬编码。
- [ ] 失效引用、循环、单位/类型、unknown、坏保存/直接编辑、并发版本及两库原子快照有小测试；热路径无读盘/重解析。
- [ ] rule_config_digest进入生成/搜索及训练语义身份，未被seed_training删除；原生构建身份不受配置变化影响，历史输出可查完整快照。
- [ ] 逐条按总规格10.1记录①保存②映射③顺序/次数/停止④诊断→候选→Coba的待实现接口。目标、表达、实现、验证分别记状态，不以单例批准整库。

## Validation and budget

复用既有公开入口、自动发现及统一验证。云端开发，确依赖本机引擎/Windows/Lua/真实数据中心安装副本的正式验证另列获准动作。现有构建超时1200秒、整套正式验证预算60秒；单项检查上限不等于整套预算，未测耗时不作承诺。具体入口、真实输入及运行总上限在该动作开始前明确，不借本草案运行。

## Boundaries and stop conditions

本票不实现02诊断或03选择器，不进行新增候选收益比较；但须接入训练/搜索的规则配置身份以避免旧缓存污染。新增事实需开发的边界和旧任务恢复语义先确认，不擅改正式规格。静态快照生命周期、动作特例、Outbreak低频参数来源及现有表示容纳性为实施核验项；需要改变政策时停止讨论，不另开抽象研究票。

发现受保护爆发变化、未知值被伪造、硬合法性越界、恢复不一致、超过获准预算或需要额外架构时停止相关动作并报告。不得把未运行验收勾选为完成。

## Traceability

当前完整设计、源码及必要研究证据均见[总开发规格](../spec.md)。原型验证复用实际开发实现，不另建一次性框架。

## Comments

### 2026-10-16 实施进度（待独立审查）

- 接入原生一次性静态快照（precombat_init 完成后、预战动作前），读取虚拟有效 GCD/CD、费用/ON_CAST 确定性收益、资源及邪 DK 参数；新增固定补丁 070，两套补丁适用及身份散列已核对。尚未在云端编译 C++，不将源码接出视为真实字段验收。
- 通用契约/有限静态过程与邪 DK 完整 APL 条目分开；骨架只累计符能，符文作可排性约束。保留高低位消费身份及完整 OR，未知 Army/CD/Buff 不填假值。低频间距来自原生疾病持续时间字段，通用过程没有 Outbreak 分支。
- 复用 initial_programs、program/codec、候选缓存和结果中心；只替换均匀来源。规则起点即使未作为赢家也保存实际编译输出和逐点击映射，页面/API可查看参数、来源及近似/unknown。无新增模拟批次。
- 定向红绿覆盖公开 task 和真实 HTTP POST/GET；最终必要集合 14 passed（约1.76秒）。构造输入经锁定 Lua 实际导出 48节点/120点击；生成约1.05–1.55ms，仅为构造样例耗时，不是实战或正式验收。
- 云端证据（忽略目录、需保留当前环境）：`.local/tests/rule-initialization/report.md`、`red-01.txt`至`red-05-source-priority.txt`、`final-targeted.txt`、`native-patch-check.txt`、`constructed-lua-export/`。
- 完整 test_search 模块的Linux诊断为79通过/11失败：4项为既有data-store query(tables=...)安装版本不匹配，7项为Windows/真实引擎依赖或测试锁适配不足；不作为产品回归定论或正式通过。依赖核对由环境检查处理。
- 待办：独立审查；既有Windows环境按授权重建；真实角色静态字段→初始化→GSE链路及固定基线统一verify。此处不勾选尚未完成的验收。

- 2026-10-16 环境补齐：项目连接已由官方固定源码更新到 data-store 2.4.0/API2；专用诊断runner现使用项目真实连接，旧tables参数失败项定向重跑为4 passed（2.14秒），见 `.local/tests/rule-initialization/data-store-corrected-regression.txt`。其中原缓存测试修正为按损坏批次身份核对，避免新任务冻结冠军导致索引0换位；实际损坏批次已重算。环境变化后14项必要契约集合再次通过。


### 2026-10-16 首审修复（待复审，未验收）

- 修正 AoE 低位消费的来源身份：Epidemic/Death Coil 低位填充保留 aoe.8/aoe.9，不再标为近满高位 aoe.4/aoe.7；动态条件及前序让位仍为 unknown。
- Putrefy 仅首次静态满充能证据标为静态分支估计；按静态 CD 间距安排的后续尝试明确记录充能消耗/恢复及窗口未知。固定源码 sc_death_knight.cpp:12244–12255 的 putrid_echoes 可额外消耗充能，不能用一次重充推断已满。不增加充能模拟器或跨轮就绪门槛。
- 两片公开 task.run_task 红绿：低位身份2项先失败后通过；重复充能1项先失败后通过。含既有HTTP和起点边界的定向集合17项通过，证据 `.local/tests/rule-initialization/review-red-01-low-spender.txt`、`review-green-01-low-spender.txt`、`review-red-02-repeated-charge.txt`、`review-green-02-repeated-charge.txt`、`review-final-targeted.txt`。
- 原生 getter 的嵌套观察副作用、传入空 action_state 的安全性与真实生命周期字段仍是 Windows 实际验证项；不凭函数签名或构造用例宣称纯读取安全。C++编译、真实角色验收和固定基线正式验证状态未改变。


### 2026-10-16 Windows 首轮验证回归修复（待复审及重跑）

- 已收到 Windows 三目标 C++ 构建成功及真实角色初始化→锁定 Lua 导出结果；角色参数和具体产物仅保存在本地实际验证目录，不作为仓库回归夹具。首次三目标构建实耗302.724秒；17项定向通过。该结果不代表正式验证通过。
- 固定基线快速 verify 首轮40.979秒退出1：523 passed、20 failed、150 subtests。已按20项映射修复：7项局部报告合并丢失race；2项WaitClicks旧目录缺生成动作及多Pause/GCD构造假设；2项不可用最高训练冠军夹具删除唯一生成动作；5项冠军评分/来源/冲突夹具依赖旧均匀起点；1项原生报告比较未扣除新增静态元数据。浏览器、硬退出和受控爆发序列三项保留原断言，需验证是否随原生长度缺陷修复恢复。
- 产品修正仅为既有长度合同：128约束源节点，4096约束每条独立宏的展开点击。controller接收普通/爆发展开计划，现分别检查每段1..4096，双段可合计8192；burst_offset仍限4096，输入时刻/来源/反馈一一对应、动作成员、施法序列索引等校验保留。Python公开sequence入口同步提前拒绝任一段超过4096；原顶层128、每宏4096及搜索预算未改。更新controlled源身份散列；需重建后验证。
- 冠军用例保持生产CAS、晋级和可信报告保护：恢复评分按明确行为身份固定100/200/300；不同赢家场景局部从真实生成列表选另一合法起点并断言行为不同；三来源合并使用公开initial_programs的实际规则起点，不再硬编码旧均匀排列。没有修改生产冠军逻辑。
- 本轮云端公开接缝红绿：race 1红→1绿；WaitClicks超限1红→1绿；sequence超限3子项红→2 passed/7 subtests；冠军5项原失败重现→7 passed/3 subtests（包含最高冠军不可用两项）。最终初始化/sequence/网页必要集合23 passed、7 subtests；冠军必要集合7 passed、3 subtests。证据见 `.local/tests/rule-initialization/native-review-*.txt` 及 `native-review-report.md`。
- 云端冠军诊断仅在忽略目录runner构造外部engine identity，复用原有Linux测试进程适配；不验证本机身份、锁、进程树或引擎。真正Windows仍须：重建controlled并核验身份；新增129普通点击及独立爆发的原生公开sequence测试；旧20失败组特别是300/600ms真实WaitClicks、浏览器、硬退出；原版/基准/禁用controller仅扣除新增静态元数据后所有战斗字段逐值一致。不能因去掉snapshot字段便宣称getter无副作用。票据仍in-progress，验收未勾选。

### 2026-10-16 二次规则审查修复（待固定提交复审及原生重采，未验收）

- 按已确认公共接缝逐片红→绿，复用网页/HTTP→`task.run_task`、既有 program/codec 和 NativeCatalogue/reference；实际再次读取 TDD `SKILL.md`、同目录 `tests.md`、`mocking.md`。未用私有生成函数测试替代交付合同。
- 移除第二层旧骨架时长硬下限；进一步恢复有限骨架编辑合同：第一层才要求一次 CD 覆盖与累计一份符能容量，第二层消费骨架已有动作条目，不再次补容量。只有已知同资源 ON_CAST 贡献、费用不增加且 GCD 不更慢时，维护动作才替代相应资源填充；未知收益不参与该替代。多余末次疾病尝试先撤销（必要时恢复被其替代的原条目），再复用同一排位账重算；单次疾病间距不足只补有规则7来源的等待。
- 原捕获样例的 `final < skeleton` 断言在修正 FS 分类后失效，失败事实保存在 `review2-current-length.json` 原公开任务产物及 `review2-obsolete-relative-assertion.txt` 失效断言复核，没有用放宽秒数阈值掩盖。保留独立手算公开回归：30符能容量，20符能维护替代两条10符能填充，骨架4秒→成品3秒；需要6秒维护间距时仍是同三动作，仅延长尾部 Wait 至6秒。尾部维护另由独立小mock检查有限条目、圆周间距和实际删除证据，不依赖个人角色参数。
- 初始化复用 Program 预战前缀和实际编译点击校验，Raise Dead 的输入计入时间；动作来源/点击位置与真实编译计划一致。跨爆发暂停使用已有墙钟输入槽，避免把暂停中已经经过的 GCD 又计成窗口后的空点击。
- 按用户新确认，FS 在邪 DK 绑定中归增益维护，SS 为符能填充；原生读取初始 `lesser_ghoul_ready->check()`。初始缺层时每循环保留一次 FS 维护示范，单体末位兜底与 AoE `<3` 分开，不承诺持续 Buff、不设 FS:SS 比例或固定刷新周期。通用流程不含专精252/天赋字段检查，检查已移至现有绑定。
- 原生收益增加 ON_HIT 时机和已知/已知零/未知区分；FS 读取 `composite_energize_amount(nullptr)`，不硬编码20。Scythe 从已注册的独立动作采集，不继承 FS 收益。保守排位只累计已知 ON_CAST；条件收益/未知收益金额仍保留，之后余额明确 unknown，不能据此宣称真实未溢出或资源条件满足。旧真实快照缺 `gain_timing` 的红证据不是新 C++ 执行证据；同一既有 NativeCatalogue/reference 测试已追加 FS/Scythe 契约，等待 Windows 旧 binary 红、新 binary 绿。
- 规则5实际调整普通顺序：冻结爆发编译内容含 DT 输入时，首次 Putrefy 对齐该尝试后的最近可表达普通输入；原混合输入对照仅留本地；替代的独立构造公开用例1秒→4秒，移除 DT 时仍1秒，冻结爆发逐值不变。只对齐输入尝试，不把它当成 DT 已成功或 Buff 已生效。
- 规则4仍未实现基于动态短窗口的独立调序：Vampiric Strike/Essence 的随机相位及剩余时长无法从初始化静态快照推出。撤销将普通 SS 填充贴成 `short_window` 的误导标签，保留完整绑定、明确 `unknown_not_applied`。各规则公开已应用位置与近似/未应用状态，不能据此把八规则全部勾为完成。
- 默认 HTTP 500ms 摘要只带初始化存在标记及行为/编译状态身份；同一 GET 的 `?details=rule_initialization` 才取完整详情。页面展开一次读取，任务或既有身份变化时失效，避免轮询反复传输/渲染整份详情。
- 云端最终必要集合26 passed（4.01秒）；旧20失败映射的可做回归15 passed、3 subtests（8.15秒）。两套原生补丁链适用及身份散列通过，Python编译和差异空白检查通过。构造样例锁定 Lua 实际导出38普通节点/120点击；旧 Windows 数值与构造字段混合的历史验证产物仅留本地，不作为仓库回归数据或新真实角色验收；新原生层数及有效 ON_HIT 值尚未重采。无新增搜索/收益模拟批次。
- 证据目录仍为 `.local/tests/rule-initialization/`：`review2-red/green-*`、`review2-final-targeted.txt`、`review2-prior-failure-regression.txt`、`review2-native-patch-check.txt`、`review2-captured-lua-export/`。真实快照仅留 `.local/tests/rule-initialization/real-windows/`；仓库测试使用独立构造的小数据，不将个人快照改几个字段后称为合成。
- Windows 待验：重建 baseline/controlled、原生新增收益/初始层数契约及真实角色生成/编译/时间映射；原版/基准/禁用控制器仅剔除新增项目元数据后逐值核对战斗字段，尤其 getter 副作用/空 state 安全性；既有真实浏览器、WaitClicks、硬退出及固定基线快速 verify。规则4缺口须用户审阅，01仍 `in-progress`，02/03未开始。

### 2026-10-16 摘要读取与详情恢复修复（待固定提交复审，浏览器待 Windows 红绿）

- 固定 `dff4d94` 的默认摘要虽然已删响应大字段，仍先读取完整初始化列。本次公开 HTTP 红灯观察真实外部 data-store 的 `read_key`：`runs` 投影为全列；修复后由 GET 的 details 需求沿既有双场/单场读入口传递，默认投影排除 `rule_initialization`，仅显式详情读取全文。存在/行为身份复用已有 `search_metrics` 小字段持久化，不新增表、缓存或服务。
- 单场与双场 HTTP 定向2项通过；单场用真实安装数据存储，双场复用已有内存 DuckDB 外部存储边界，均实际读取并观察列投影，不 mock 产品内部读函数。详情 GET 仍返回完整初始化。红灯 `review3-red-summary-storage.txt`，绿灯 `review3-green-summary-storage.txt`；含初始化合同的必要集合26 passed（4.82秒），`review3-final-targeted.txt`。
- 页面身份暂时消失时同步清除已载身份；详情 HTTP200 但 `storage_unavailable` 时进入既有失败处理，恢复后沿既有展开/轮询重新读取，不将空数组缓存为成功。新增两条真实 Playwright 页面回归，网络边界构造摘要或详情暂时不可读，验证恢复后再次请求且显示原身份详情，不启动 C++ 或收益模拟。
- 云端 Chromium 因沙箱本地 socket 权限未启动，提权尝试也因宿主 bwrap 初始化失败未执行；未绕过限制，不能声称浏览器红绿。Windows 用固定 `dff4d94:projects/sim2gse/interface.html` 的 `git show` 输出替换测试进程内的静态页面内容，可运行同一两条测试取得旧页面红；正常加载修后页面再取得绿。无需切换工作树或重建原生。其余原生待验及规则4未实现状态不变，01仍未验收。

### 2026-10-16 用户确认第4条阶段边界及真实序列复核

- 用户明确批准：静态生成无法复现的第4条动态短窗口优化留至后续诊断搜索。01保留完整绑定与unknown，不再以未独立调序阻断本票；02负责同次学生状态诊断及合法修改，03接入搜索。此决定覆盖上文“规则4缺口须用户审阅”的待决状态，不表示动态规则已实现或02/03已开工。
- 用户要求修复完成后重新运行真实角色初始化并完整列出序列供审查。待Windows现有线程用修后原生字段与真实角色生成，逐节点提供技能或WaitClicks、规则理由/unknown、编译点击及时间映射，同时保留真实快照和GSE；旧快照加构造字段的产物不能替代这次复核。当前尚未运行，不勾选验收。

### 2026-10-16 生成过程与专精绑定解耦（待固定提交独审）

- 按用户再次明确的通用化要求，现有 initial_programs 组合绑定并显式传入 generate；生成器不再导入邪DK模块、判断专精/天赋/技能名或读取原生符文字段。高低位消费的DK阈值、OR组合、来源身份及条件状态移入已有Python专精库纯判断函数，通用过程只消费结果；未增加条件解释器、注册器或新框架。
- 恢复过程显式选择 `parallel_discrete` 并提供资源身份、间隔、并行槽；仅这一模型验证满初值、整数资源及槽位。显式 `none` 不强求辅助资源，不读取符文参数；缺失或未知模型明确拒绝。疾病间隔和专精说明也由绑定转入，删除无消费者的 `short_window_action` 字段但保留第4条正式规则绑定与unknown。
- 保持已确认公开 task 接缝，不新增 generate 测试接缝、不 mock 内部 bind。同一资源状态仅切换现有单体/AoE绑定，消费来源依据原先缺失2红→相关6绿；显式恢复模型及手算等待原先缺字段1红→相关6绿。1单位/5秒恢复例实际输出动作0/5/6秒及对应WaitClicks 24/4/4，验证参数确实影响排位。
- 初始化/单场及双场HTTP/golden必要集合30 passed（5.84秒）；证据 `review4-red-binding-spending.txt`、`review4-green-binding-spending.txt`、`review4-red-recovery-model.txt`、`review4-green-recovery-model.txt`、`review4-final-targeted.txt`。新红灯针对公开来源/能力报告缺失，不能冒称此前两种消费选择或5秒恢复本身算错；隔离改动另由独立源码审查核验。真实行为覆盖仅邪DK单体/AoE，不声称所有职业已支持；无C++变更、无新增模拟批次，Windows真实初始化及浏览器待验不变。

### 2026-10-16 回归数据改为独立构造，真实快照不外发

- 按用户明确要求，删除此前尚未推送的真实角色快照夹具；真实数据只留忽略目录做实际验证。复用已有 `apl_pool_reference` / `static_snapshot` 工厂，分别仅补所需FS或Putrefy动作；没有复制装备、天赋或个人参数组合，没有新增采集、模拟或数据管线。技能身份来自已有公开绑定，边界数值为独立可手算mock。
- 尾病回归采用主资源容量30、一个辅助单位每5秒恢复、维护获得20、填充获得10、消费30：有限成品为维护0秒、填充5秒、消费6秒，循环7秒，WaitClicks为24/4/4（200ms输入）。分别验证3秒与4秒维护间隔，删除5秒处导致跨轮仅2秒的冗余维护并恢复被替代填充，不能再开一轮消费。保留另一组骨架4秒→成品3秒，以及需要6秒间隔时仅补尾Wait的完整预期。
- 预战映射用基础工厂与300ms输入；FS角色及ON_HIT/unknown用工厂加一个构造FS；爆发对齐用工厂加一个构造Putrefy与200ms输入，预期1秒→4秒，无DT时仍1秒。真实任务生成/编译和公开接缝保留，只在既有外部引擎数据边界使用mock。
- 为证明替代案例仍抓住旧缺陷，仅在忽略目录测试进程从Git读取固定 `3d0454c` 的 search/rule_initialization/unholy_rules 源码，不切换工作树：同一11例为10 failed/1 passed；旧失败分别覆盖额外尾病/资源工作、预战漏计、FS重复、未知收益缺失、DT未对齐和二层重补骨架。当前实现同11例全部通过。日志 `review5-red-synthetic-previous.txt`、`review5-green-synthetic-current.txt`；非Windows或原生引擎证据。
- 替代后初始化/单场与双场HTTP/golden必要集合31 passed（5.71秒），见 `review5-final-targeted.txt`；Python编译和差异空白检查通过。
- 本轮只调整测试数据与说明，未修改产品算法。发布须从此前远端提交构造不含真实快照的最终tree，不推送含该文件的未发布本地中间历史。真实角色修后重采、完整序列审阅与本机验证仍待执行。

### 2026-10-16 Windows 最后节奏隔离用例修正（产品不变）

- Windows固定 `cd3ba2e` 新构建、浏览器恢复红绿、新原生收益契约及原版/基准/禁用控制器战斗字段对照已通过；快速verify仍因正式冠军条件隔离的cadence子项失败，不能宣称整套通过。
- 云端公开HTTP重现同一失败。该用例使用构造1000ms GCD、200→400ms节奏，与真实角色FS或600ms无关：2400ms动作后仅有2800ms一个普通空输入，接着跨过固定3000–4000ms爆发暂停，于4000ms恢复，形成无法表达的WaitClicks=1。现有产品拒绝正确，未改初始化政策或合法性。
- 仅将该隔离用例改为200→250ms，两种节奏都可表达；新增公开返回节奏值断言，保留姓名/装备/节奏/引擎条件隔离及原冠军记录不变的全部断言。原用例2 failed（一个cadence子项及汇总）→修后连同既有单空/非法静态字段拒绝回归5 passed、4 subtests passed（1.81秒）。证据 `review6-red-champion-cadence.txt`、`review6-cadence-diagnosis.txt`、`review6-green-champion-cadence.txt`。
- 本轮仅测试与本票说明变化，Python编译、差异检查通过。待窄范围独审、Windows受影响用例及最终快速verify；无需因本轮重建C++或重跑真实角色初始化。

### 2026-10-16 未知余额后的已知维护贡献替代修复（待独审及真实重采）

- 原实现因较早的条件收益把余额标为unknown后，完全禁止后续已知ON_CAST维护收益替代骨架填充，有限工作清单因此残留多余资源动作；并非规则7删除末次维护后的恢复造成。
- 最小修复：只要求当前维护自身known/on_cast，复用既有同资源、候选已知收益、费用不增加、GCD不更慢及credit额度条件。credit仅表示保守静态账的本次贡献，先前未计入收益仍使余额及后续消费条件保持unknown；不将估计提升为实际收益或资源合规证明。不增unknown专用分支、不恢复第二遍容量门槛、不加技能特判。
- 公开task入口使用独立小mock：主资源容量60，填充与维护各10确定性收益，消费30，维护间隔3秒；先有一次20条件收益的维护示范。骨架6填充+2消费为8秒；最终预期9秒/45点击，动作依次为维护、增益示范、填充、维护、消费、填充、维护、填充、消费，每动作后4空点击。三次维护各替代一条原填充，条件收益之后所有余额继续unknown；最后维护到下轮首次恰3秒，最终允许长于骨架。
- 同条新回归旧实现红灯：多出末尾维护及两条填充（各带Wait），12秒；修后与unknown传播、规则7删尾、有限编辑/必要延长共7 passed（1.22秒）。初始化文件全部29 passed（4.81秒），Python编译及差异空白检查通过。证据 `review7-red-uncertain-replacement.txt`、`review7-green-uncertain-replacement.txt`、`review7-final-targeted.txt`，均在既有 `.local/tests/rule-initialization/`。
- 本轮为Python静态生成修复，无C++变化、无额外收益模拟批次。真实角色更新后的初始化需沿已有外部快照与公开生成/编译入口重采，不能用本mock替代；D&D场景策略未改。01仍待独审及最终Windows验证。

### 2026-10-16 用户改为单次消费示范及单体枯萎凋零覆盖（待独审与合并重采）

- 用户明确将骨架“消耗一轮资源”改为“消耗一次”，并确认单体初始化也示范一次枯萎凋零。本节及总规格3.2覆盖上文容量目标的历史记录：骨架只等各CD及绑定消费动作各示范一次；第二层仍消费有限工作清单，不把初始次数或消费总量硬锁为最终要求。
- 通用生成器按绑定spender是否尝试收尾，并在骨架阶段不重复示范它；资源消费总额仍报告，不硬写技能名、30费用或100容量。独立mock初始100、绑定费用35：同一task回归旧105/6秒红→35/1秒绿，证明采用实际绑定费用与一次尝试；长CD例仍验证CD一次和消费一次，2秒收尾，不等CD恢复。
- 邪DK绑定仅在能力可用且cycle_of_death开启时把D&D列入普通CD覆盖，单体不再被目标数排除；原完整APL的active_enemies>=3及固定L373来源不变。单体绑定另记initialization_coverage，明确用户批准的覆盖、原上游条件不适用及非上游单体推荐，不推断减CD或固定周期。正例原0次红→1次绿，缺天赋/不可用两例继续不安排；通用过程无D&D特判。
- 原3个容量断言按新批准合同改为一次30单位。未知收益替代回归保留严格完整期望，独立mock改为60费用消费一次：骨架6填充+1消费7秒，最终8秒，规则7撤回末次多余维护并恢复其替代条目。相同测试加载固定3f523e7旧生成器仍失败（多2动作及Wait），当前通过，未以删除或放宽断言掩盖原缺陷。
- 云端初始化33 passed（5.29秒）；冠军条件隔离、取消恢复及等价来源合并4 passed、4 subtests passed（4.26秒）。红绿日志为 `review8-red/green-single-spend.txt`、`review8-red/green-single-target-cooldown.txt`、`review8-red-retained-uncertain-credit.txt`、`review8-final-targeted.txt`、`review8-champion-regressions.txt`，仍在既有忽略证据目录。Python编译及差异空白检查通过。
- 未修改C++、正式规格或02/03实施。待本轮固定提交双轴复审后，一次同步Windows跑最终快速verify并重新生成真实角色的完整中文序列供用户审阅；不重复建立引擎，不用mock结果代替该序列。

### 2026-10-16 已确认天赋的腐化维护替代（待独审及Windows重建）

- 用户批准邪DK初始化可由腐化替代爆发维护疾病。固定SimC的putrefy_damage_base_t::trigger_blightburst及主目标/范围impact表明施病或延病依赖Blightburst；不是Cycle of Death或Scythe。固定APL:372仍保留Outbreak的开场及断病兜底，省略属于用户初始化选择，不声称上游推荐删除该技能。
- 复用原生070专精bool map增加blightburst=talent.unholy.blightburst.ok()。已有reference/capabilities没有解析后的该天赋值，talents只有编码串；未新增解码器、查询模拟或效果系统。两套补丁链适用通过，仅更新070及两个受影响DK文件的锁身份，未在云端构建C++。
- 专精绑定仅在明确true且Putrefy可用并在普通CD骨架时令periodic_action=None；false、缺失unknown或腐化不可用均保留Outbreak。通用生成器未改，自然不再插入Outbreak或为其周期补尾；腐化仍是CD/伤害动作，原CD、固定爆发及DT尝试对齐均未改。完整Outbreak绑定保留用户替代来源与coverage=unknown，明确不保证首次爆炸前或全程疾病覆盖。
- 同一公开task四条件回归：替代正例先红，修后4 passed；独立mock成品为腐化、填充、填充、消费，均1000ms动作及4空点击，共4秒，原疾病间隔6秒不再强加尾等。false/unknown/不可用仍保留疾病动作和6秒周期。全部初始化及必要目录/身份入口39 passed（5.82秒）；较宽目录组另有2项因云端缺原生build.json无法执行，50 passed、7 subtests，不把缺环境记为通过。
- 既有NativeCatalogue/reference测试新增明确bool契约。旧本地真实快照缺字段红只证明旧协议缺口，不是C++执行红；Windows须用旧binary的同一reference值先确认缺字段，再重建baseline/controlled并运行契约绿及原版/基准/禁用控制器战斗字段对照。证据位于原忽略目录：review9-red/green-alternative-maintenance、review9-red-native-field-captured、review9-native-patch-check、review9-final-targeted、review9-final-supported。
- Wowhead本轮仅核对只读索引，英雄切换与正文未全文核实，尚未接入完整指南规则。用户要求先列实际指南条目核对，后续另按确认范围处理；本片仅依据明确替代授权及固定源码。
- 独审后一次同步Windows重建、固定基线快速verify，并分别生成保存真实单体和AoE初始化，明确目标数，提供完整中文节点/等待/理由/映射供用户审阅；不新建训练批次，不用mock替代真实产物。01仍未最终验收。

### 2026-10-17 用户批准灵魂收割纳入CD示范（待独审及Windows重建）

- 用户明确要求灵魂收割即使不能动态处理，也必须作为CD技能放进初始化序列。本次只在角色能力可用时追加普通CD清单，单体/AOE共用现有排位；完整APL斩杀/黑暗突变条件、父入口和优先保留，并报告用户批准的静态示范及动态unknown。未增加固定施放时点或改冻结爆发，通用生成器不变。
- 原生070采集白名单只追加soul_reaper，复用既有有效GCD/CD、费用、充能及收益字段；没有猜数值。baseline/controlled两套补丁链适用，通过既有脚本更新070和受影响DK源码锁散列；尚未构建新C++。
- 公开task.run_task接缝使用独立构造数据：单体/5目标可用两例先因零次收割失败，不可用两例通过；最小修改后四例全部通过。另核对1200ms构造GCD对应200ms输入后的5空点击、完整源条件和unknown。初次绿灯尝试发现原24秒疾病尾等待合并影响GCD断言，将该独立mock疾病间隔设为3秒以隔离目标，未放宽5空点击断言，未改产品周期行为。最终同四例加载固定5c43c8de旧绑定仍为2 failed/2 passed，证据review10-red-final-case-fixed-base.txt。证据：review10-red-soul-reaper.txt、review10-intermediate-period-isolation.txt、review10-green-soul-reaper.txt，均在既有忽略目录.local/tests/rule-initialization/。
- 较宽初始化/目录集合53 passed、7 subtests；另外2项因云端缺baseline/build.json无法运行，不记为通过。日志review10-final-targeted.txt；排除这两项原生环境依赖后，同集合53 passed、7 subtests（24.66秒），review10-final-supported.txt。两套补丁链日志review10-native-patch-check.txt。原生reference既有契约已补可用收割必须提供静态参数的检查，等待Windows旧binary红、新binary绿，云端不冒称原生验证。
- 独审后需Windows重建baseline/controlled，核验新增原生字段及原版/基准/禁用控制器战斗字段一致，执行固定基线快速verify，再从现有入口生成真实单体和AOE初始化，逐步分别列出技能尝试和随后空点击。真实序列及01验收仍待完成，02/03未开始。

### 2026-10-17 两库可编辑配置方案修订（仅文档，待逐项讨论）

- 以总规格2节为唯一契约草案；旧Python业务分支、9动作名单及专精原生参数不是已满足配置化的证据。当前代码与真实序列均未因本次文档变化而改变。
- 下一步按总规格10节先讨论格式/保存，再逐条review通用规则和专精绑定；记录使用10.1模板。既有8目标、23源签名和人工策略不等于新的数据表达批量获准。
- 只修改本规格和三票据；没有创建可执行规则文件、运行新模拟或开始02/03。
