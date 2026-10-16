# 01：规则起点与合法导出

Parent: [总开发规格](../spec.md)
Status: in-progress
Triage: ready-for-agent
Assignee: Implementer
Blocked by: 无其他开发票。依据已确认规则及专精分层；缺必要静态字段或绑定参数须明确报告。

2026-10-16 用户已批准逐票串行实施，本票已开工；当前处于云端实现与独立审查前，尚未通过真实角色和 Windows 验收。02/03 未开始。

## What to build

让现有任务生成一个来自真实角色静态参数的规则起点，替换且只替换目录均匀来源，并经现有编译器导出GSE。

范围：最小静态快照；八类规则契约、通用生成过程与首批邪DK专精绑定；CD示范/符能累计骨架；八规则填充；现有起点入口和合法导出。邪DK骨架只统计符能，符文仍约束动作。Outbreak条件、过程选择和参数来源写入专精库，通用生成器无技能硬编码。具体持续秒数不得凭用户分层确认擅填。

复用原生目录及角色生命周期、initial_programs、现有程序表示、编译导出、行为身份和爆发保护。只为本批规则补字段，不写解释器、模拟器或新调度器。

## Acceptance criteria

- [ ] 真实角色参数来源及时点可核验；有效GCD不冒充基础trigger_gcd，必要多资源值不填假值。
- [ ] 原三个基础来源及训练/冠军边界不变，只替换均匀来源；确定输入产生确定初始化结果。
- [ ] 通用规则/通用过程/专精绑定职责可见；技能特例在专精库，不在通用生成分支。
- [ ] 骨架使用CD示范及累计符能一份容量；不加入满空、净收支平衡、下一轮CD就绪或45秒周期门槛。
- [ ] 真实GSE、合法导出、逐位置映射、参数来源及精确/近似/unknown清单可供审阅，取得初始化生成的实际证据。
- [ ] 固定爆发不变；单空点击、缺字段、结构超限明确失败，不扩语法或静默回退。
- [ ] 复用task.run_task集成接缝及现有程序测试；构造样例不冒充真实角色产物；检查与独立审查证据记录完整。

## Validation and budget

复用既有公开入口、自动发现及统一验证。云端开发，确依赖本机引擎/Windows/Lua/真实数据中心安装副本的正式验证另列获准动作。现有构建超时1200秒、整套正式验证预算60秒；单项检查上限不等于整套预算，未测耗时不作承诺。具体入口、真实输入及运行总上限在该动作开始前明确，不借本草案运行。

## Boundaries and stop conditions

本票不搜索、训练或进行新增候选收益比较。静态快照生命周期、动作特例、Outbreak低频参数来源及现有表示容纳性为实施核验项；需要改变政策时停止讨论，不另开抽象研究票。

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

- 已收到 Windows 三目标 C++ 构建成功及真实角色初始化→锁定 Lua 导出结果：123顶层节点、396展开点击，约0.64秒；有效 GCD 为 Festering Strike 827ms、其他动作1240ms，Putrefy CD30s、DND25s，初始符能0/100、符文6/6、符文重充8272.916ms/3槽，疾病持续18s。首次三目标构建实耗302.724秒；17项定向通过。该结果不代表正式验证通过。
- 固定基线快速 verify 首轮40.979秒退出1：523 passed、20 failed、150 subtests。已按20项映射修复：7项局部报告合并丢失race；2项WaitClicks旧目录缺生成动作及多Pause/GCD构造假设；2项不可用最高训练冠军夹具删除唯一生成动作；5项冠军评分/来源/冲突夹具依赖旧均匀起点；1项原生报告比较未扣除新增静态元数据。浏览器、硬退出和受控爆发序列三项保留原断言，需验证是否随原生长度缺陷修复恢复。
- 产品修正仅为既有长度合同：128约束源节点，4096约束每条独立宏的展开点击。controller接收普通/爆发展开计划，现分别检查每段1..4096，双段可合计8192；burst_offset仍限4096，输入时刻/来源/反馈一一对应、动作成员、施法序列索引等校验保留。Python公开sequence入口同步提前拒绝任一段超过4096；原顶层128、每宏4096及搜索预算未改。更新controlled源身份散列；需重建后验证。
- 冠军用例保持生产CAS、晋级和可信报告保护：恢复评分按明确行为身份固定100/200/300；不同赢家场景局部从真实生成列表选另一合法起点并断言行为不同；三来源合并使用公开initial_programs的实际规则起点，不再硬编码旧均匀排列。没有修改生产冠军逻辑。
- 本轮云端公开接缝红绿：race 1红→1绿；WaitClicks超限1红→1绿；sequence超限3子项红→2 passed/7 subtests；冠军5项原失败重现→7 passed/3 subtests（包含最高冠军不可用两项）。最终初始化/sequence/网页必要集合23 passed、7 subtests；冠军必要集合7 passed、3 subtests。证据见 `.local/tests/rule-initialization/native-review-*.txt` 及 `native-review-report.md`。
- 云端冠军诊断仅在忽略目录runner构造外部engine identity，复用原有Linux测试进程适配；不验证本机身份、锁、进程树或引擎。真正Windows仍须：重建controlled并核验身份；新增129普通点击及独立爆发的原生公开sequence测试；旧20失败组特别是300/600ms真实WaitClicks、浏览器、硬退出；原版/基准/禁用controller仅扣除新增静态元数据后所有战斗字段逐值一致。不能因去掉snapshot字段便宣称getter无副作用。票据仍in-progress，验收未勾选。
