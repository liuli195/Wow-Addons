# 门禁一——阶段三最小方案（待确认）

## 核心摘要

推荐两张独立小票串行实施、每票完成后独立审查；先试可减少实测慢项工作量的票01，再处理既有benchmark计数偶发的票02。当前仅写计划，不改生产或测试代码；不会为了等确认而停止只读方案准备。

### 身份、范围与流程

- 同工作树 `/workspace/scratch/0af43d0efb8f/wow-addons-performance`，现分支 `codex/formal-search-ga-default`。
- 固定云端基线 `8f2d25ec9b2e4b3e4ab3b9f16127ce59dda1a0d5`，树 `183634213bdb48fc05ad91a6777027a65bbde5d3`；父层已核远端同树文档头 `bc5efe72527f9d4407fada215b6353424307f361`。阶段二实际验收代码为 `ae8063b`，之后仅文档。
- 阶段二同提交完整复验43通过，工具57.4255589秒/外层57.672秒，17普通守卫齐。此前一次42通过/1旧benchmark失败仍有效；不宣称稳定性能或偶发已修。
- 当前未跟踪Lua计划目录保留，不纳入本票；正式配置、正式规格、预算均不改。
- 流程Full：涉及真实证明的覆盖分配，必须完整展示本门禁后确认。已读当前dev-flow、subagent-policy、to-spec、to-tickets，grill-with-docs路由grilling/domain-modeling；沿既有“正式冠军、双场、恢复、普通/真实”术语，不新增架构/领域概念。

### 票01：保第二次HTTP双场十来源，仅减少旧冠军准备

**唯一代码文件：** `tests/sim2gse/test_formal_champion.py`，目标 `test_dual_preserves_legacy_ten_source_paths_and_replaces_champion_after_complete_retests`。预计约15–25行新增/调整；不改共享dual_result辅助函数。

推荐：第一次 `dual_result` 改成公开 `task.run_task` 单体真实任务，写同一raw字节（显式UTF-8、newline=''），`use_burst=True`；保 `target_count=1, scene=single_target` 与原参数 `input_interval_ms=200,candidate_limit=10,batch_targets=(2,),iterations=2,validation_batches=2,final_batches=1,final_iterations=2,scenarios=('nominal',)`。`burst.publish`返回新行而非修改原定义，若显式冻结爆发身份须取其返回值，不能读原定义缺失的definition_id。确认首轮completed且冠军published，再引用其 `search.formal_champion_publication.source_run_id`。

第二次 `dual_result` 原封不动：真实POST dual、单体和AOE、GET结果。两次completed_training、评分映射、4个selected及候选/正常复测规模均不动。

| 原证明 | 新落点 |
| --- | --- |
| 真实旧冠军供后续替换 | 第一次公开单体run_task实际执行，补completed/published断言，禁止直接造冠军凭据 |
| HTTP双场十来源交叉 | 第二次HTTP dual全链仍存在，不改成单场 |
| 单体10来源与native/selected/training/formal=4/4/1/1 | 原second.scenes[0]和start_sources断言不变 |
| 无旧chains、自然stagnation、stop_policy | 原task.read_task公开读取断言不变 |
| 新冠军300DPS、published且来源不等旧冠军 | 原断言保留，仅旧来源读取结构改为单体返回结构 |
| v2、空promotion_evidence、至少2完整代、每finalist3批/381样本 | 原实际中心读取与全部断言不变 |

**覆盖退让：** 本用例不再执行第一次HTTP双场、第一次AOE搜索/发布，也不再交叉证明第二次AOE继承第一轮AOE冠军。第二次HTTP双场本身仍必须完成；目标十来源只在单体原本就有明确断言。既有 `test_dual_inherits_each_scenes_formal_champion_after_publication` 保两场初次发布、各自继承的完整真实证明，但不是原所有交叉完全等价。

**ROI与选项：** 推荐从4次场景搜索减到3次、从2个HTTP服务/双场父任务准备减到1个，候选/样本不减。10.18秒是历史整项call，不能推算净省几秒。若必须保本测试AOE跨轮继承，则保持原样，不做此优化。另选首次HTTP单场需要改/加helper却不恢复AOE交叉，成本更高，不推荐。旧“第二次也改单场”方案撤回，不在本票内。

### 票02：重试次数规则与真实目录IO分开

**唯一代码文件：** `tests/sim2gse/test_benchmark.py`。预计约30–45行新增/调整，无生产重试改动。

- 普通层直接调现有 `runtime.replace_file`，`os.replace`提供两次固定PermissionError后成功响应；严格断言相同源/目标、总3次、sleep调用恰为2次0.02秒。这是原精确规则的迁移，不用>=3替代。
- 真实materialize仍注入恰两次权限错误，再调用真实os.replace；保每次相同pending、源码/manifest内容、原源码不变、pending清理及后续源码变化拒绝。用标准库 `patch(..., wraps=原time.sleep)`观察并实际等待，不把等待变成空操作。
- 真实回调另外记录非注入的PermissionError（保异常对象/WinError用于诊断），注入计数与总attempts分开；若额外真实权限错误为N，断言总调用精确为3+N、sleep列表精确为(2+N)次0.02秒、注入计数恰2。捕获后原样抛出，由生产重试决定是否继续；其他异常不得转成权限错误或吞掉。验证回调文件读出现权限异常也须如实记为非注入错误，不错归os.replace。
- 永久权限失败11次、其他异常1次、原异常对象保留及失败清理原用例不动。生产最多11次、重试异常类型/等待时长不变。

**覆盖与收益：** 精确无环境噪声的“2失败→第3成功”移普通守卫；真实IO仍经两次注入故障恢复且保完整内容/清理证明。允许实际OS发生额外权限错误，不再硬称真实总调用必为3；每一个额外重试均必须有对应真实异常证据及等待，不能无理由放宽。此票主要降低错误报警、落实普通规则内存化，不承诺提速；真实等待可能比旧空sleep多约0.04秒。若本机额外异常是别的缺陷，应保失败并继续调查，不能拿本分层掩盖。

### 验证与停止条件

1. 门禁通过后逐票串行：固定基线/身份、定向收集；只按所属文件实现，记录测试灵敏度与红绿证据，不冒称产品缺陷修复。
2. 票01定向原目标及双场继承承接测试，实际核HTTP dual仍执行、十来源完整、首轮真发布；云端遇Windows锁依赖不造假替代，交本机。
3. 票02普通重试规则在官方内存守卫下执行；实际目录两相关真实用例保内容/故障/清理断言，两次注入开启、sleep真实执行；非注入异常对象与精确计数保存在现有验证报告或断言信息，不新增持久诊断框架。
4. 每票限定已提交差异做独立规范/需求双轴审查，inventory确认全收集与普通/真实互补。普通pytest不冒称官方守卫。
5. 由父层同Windows官方入口运行无缓存全部43组，17普通守卫、60秒预算、恢复后的配置不变。报告单项/各组/端到端实测，首次失败和重复结果分别保留，不以总和推墙钟、不挑最快结果。
6. 无明确收益或发现独有覆盖无法承接时停止该优化并如实报告，需扩大生产/测试范围返回本门禁。阶段四Lua仍须后续独立安排，本阶段不实现。

### 独立准备审查

Architect已只读源码确认票01可行：dual worker亦调用公开run_task；冠军按target_count/完整条件隔离，第一AOE冠军不参与第二单体十来源。首次HTTP单场成本较高，无额外AOE覆盖。具名入口不可用，按策略通用回退gpt-6-sol/xhigh，无写入/测试。票02独立只读审查及最终完整计划Reviewer均已完成，无技术阻断：同文件增加普通重试规则可行，计数与真实等待分层保覆盖。具名入口不可用，通用回退gpt-6.1-sol/high、只读未改代码未运行测试。审查提出的等待文字歧义已改为两次注入开启/sleep真实执行，明确不新增持久诊断框架。计划可展示，用户Gate1尚未确认。

## 确认后进入的下一步

一次确认整套推荐或逐票选择：①沿现有完整分支 `codex/formal-search-ga-default`、同树；②两票串行、子代理实施；③每票完成后独立子代理Reviewer审查。票01/02无技术依赖，顺序是控制范围而非虚假阻塞。

也可答“分支：现有/新建＋完整名称；开发：串行＋主/子代理或并行＋子代理；审查：每票/最后”。推荐不新建分支、不并行写代码。确认时同时接受上述票01跨轮AOE交叉退让和票02计数分层；此前阶段二批准不覆盖本两票。本计划审查结束后由父层展示完整门禁，未确认不实施。

## 授权更新

2026-10-25父层完整展示两票范围、覆盖退让、验证与执行限制后，用户明确回复“确认”（Sentinel_c2e71b706cc48191b723958ffc887e40）。本两票门禁通过；以上待确认描述保留为历史计划。
