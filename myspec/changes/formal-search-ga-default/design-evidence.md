# 正式遗传搜索候选设计证据

## 当前状态和边界

- 核对时间：2026-10-24 UTC。唯一目标工作树为`/workspace/scratch/0af43d0efb8f/wow-addons-performance`。起始状态干净，登记在`codex/formal-search-ga-ab-mvp`，HEAD `0aa7a06aa6285c161733a5dacca24a8d35990df4`。
- GitHub分支API在本次准备重新核实main为`d08f1d6f540f3ced2496a59bdce6bd3badc7151a`，与此前`git ls-remote`一致；本次实施基线必须使用该主干，不把实验HEAD当生产基线。
- 拟建`codex/formal-search-ga-default`。按最新dev-flow需求步骤7，只能在完整门禁一展示并明确确认后同工作树创建；候选三文档现先保持未提交，不提前切分支。原实验分支和`.local/population-mvp`成果保留。
- 本次仅change文档，未修改业务、正式spec、工具配置或测试，未运行构建/测试/模拟，未操作用户本机。

## 实际Full技能使用

- 开发流程源：`cloud-skills/managed/sources/own-skills`，main `0cecf8a48865aab9483cfe21527f58ab2f98c930`；`plugins/my-spec/package.json`为2.7.1。实际读过dev-flow入口、requirements参考及subagent-policy，不用旧installed CLI写新schema。
- dev-flow入口SHA256 `92156d8e9640222294ef414747f8351c128704d91a78cc035698cdffbe400860`；requirements `a19afb36524a4006d1eded5cf25539ab592b2d80c6ae2c99fbd3793e47765aca`；subagent-policy `86fcdb83fe8e8ac3f70b2b5b3228999719c70c17b984a1b1986cab86fc316300`。
- Full理由：正式默认算法/停止、跨入口运行时、持久冠军与恢复契约变化，不满足Fast的单一已复现故障修复条件。
- Architect既有代理`design_formal_ga_replacement`被明确续派只读本次范围；其本次实际读取`managed/skills/codebase-design/SKILL.md`及`DEEPENING.md`，真实来源为`managed/sources/mattpocock/skills/engineering/codebase-design/`。入口SHA256 `2c20617f87ec8af6a434859f381b2f061a69b530444e74eb39e78bb016a6d1e2`；参考 `f3dd099ce99289bd213914d8ee3e2429b78309c3957ca4583f7659551b1d53c1`。其应用了共享深模块/小接口、最高真实入口和旧机制测试替换而非叠加原则。父线程已核创建记录：按本任务明确的GPT-6-A架构安排使用`gpt-6-astra`、`xhigh`、`fork_turns=none`；这是父调度证据，不声称子线程自检证明实际服务端模型。
- 实际读取并应用grill-with-docs→grilling及domain-modeling，来源同一mattpocock提交`24fe0ef7737efae15c87225755e9f6f5965e4888`。本change下节记录决策树、已确认产品选择、术语与边界反例，不把“仅看词汇表”冒称建模。项目要求不另建ADR/术语库，因此决策暂记change，正式规格后续受控处理。
- 实际读取并按模板应用to-spec与to-tickets，分别生成本change的spec和唯一纵向单票；最高测试接缝与票据粒度列入门禁一待用户确认。二者入口SHA256分别为`43ad9cf318e5e7d3d1fa360253a37021796dc87a0c2e595ad262661a10f85088`和`5c9fba69845c2519b9b35b9af42ae5142c21f8ca15ac2123dc2722002c8058ae`。

## 需求决策树和领域边界

1. 目标是产品正式替换，不是再调AB实验。已确认最大复用训练GA；因此共享繁殖/评价/缓存/早停，而不是复制遗传算法或套实验调度器。
2. 输入是实际角色的正式池，不是训练标准角色或全来源库。按原成果契约一次冻结：v2最多4原生＋4训练代表＋1角色正式冠军（4＋4＋1）；受支持v1或无版本保留独立旧训练冠军，最多4＋4＋2。冠军缺席或行为去重后N可减少，不复制补齐；未知或混合版本拒绝。旧训练冠军兼容是保留既有契约，不新增成果功能。
3. 停止是自然完整代早停，不是计时配额。用户最新确认原文如下。助手：“确认｜任务 2 新正式搜索的停止方式。既然目标是复用训练链，建议新正式 GA 搜索也按自然早停结束，再完成正常场景复测，不保留旧正式搜索的 600 秒总硬截止；手动取消和错误处理仍保留。影响是总耗时可能超过 600 秒。后续对比中，旧方案保持自己的原默认，新方案按这个新默认，分别记录自然耗时和 DPS。是否确认新正式搜索采用这个自然结束方式？”用户：“确认”。该产品确认不代替门禁一实施授权。
4. “正常场景复测”指流程内对冻结入围者完成原正常场景独立批次并择单冠军；不是把粗评赢家锁死后额外造共同端点评分，也不是保留训练全部扰动/四成果约束。
5. “共享训练链”不表示训练与正式输出、角色或资源拓扑相同。候选推荐保留正式单场2引擎×1线程、页面先单目标后群体与原按键/爆发；算法K/概率/早停/复测数复用现有训练默认，待门禁一整体确认。
6. “取消/故障”不同于自然完成：半代不提交，复测不完整不发布，成功批次保留；存储暂时不可读不是非法材料，发布失败不是重新评分理由。
7. “默认对照”是新旧各自完整自然输出的时间/DPS观察，不再强行统一预算/参数/独立端点。用户已明确输入一致、中间各自参数且功能保留；外部来源冻结、结果空间隔离是防污染，不是改算法。
8. 术语沿用项目“按键动作块”“空点击”“可按动作”“尝试频率”“纯序列模拟”。“自然停止策略”“入围名单”“正常复测”“单冠军”在本change分别绑定停止、候选集合、评分阶段和输出数量，不用“锁定”混淆粗评与复测择优。

当前没有待用户重新决定的总预算分配问题；门禁一仍需确认具体推荐、最高公开测试接缝和单票粒度。发现会改变产品输入、停止或测试接缝的新问题时回需求路由，不静默假设。

## 代码事实和最小接缝

- `projects/sim2gse/population_training.py`的`_stage_plan`、`_evolution`已有DEAP繁殖、反馈、完整代提交、历史前K无改善、成功凭据复核、有限重试/重生和复测。`run_group`使用无限总运行时，但`_selected`要求五场景和至少4条并写`seed_selected`，不能整个作为正式包装调用。
- `projects/sim2gse/search.py:1411`附近`optimize`已有`training_runner/training_stage_plan`真实评价接缝；正式适配应复用此深模块，不另建native_score。旧正式`search()`分支有32/128/256及CI晋级，不能包在新GA外继续执行。
- `projects/sim2gse/task.py`现有初始化负责真实角色、原生能力、训练代表适配、正式冠军冻结、去重、爆发和条件身份；正式适配应保留此入口。旧`_prepare_formal_publication`/冠军报告核验假设search/validation和CI链，新正式收据必须版本化，旧历史验证不放宽。
- `projects/sim2gse/dual_task.py:151`直接创建有限`TaskRuntime(total_budget_seconds)`；仅改`task.run_task`不足以去掉页面总截止。`interface.py:379–386`按elapsed/budget显示进度，也须最小适配自然阶段/代数/耗时。不要往旧有限校验和JSON塞入inf。
- `seed_training.ensure_prepared`仍有材料准备600秒局部运行时，普通单次原生故障还有局部超时；本票不顺手移除。运行时主体无限与这些局部约束须区分。
- `search_timeline.py`及`task curves`已有真实时刻、评分阶段、冻结物理条件分组和离线HTML输出，优先原样复用；新旧算法身份仅作标签，真实物理条件不符不能冒称同输入比较。
- 必要生产面预计为共享GA/评价模块、正式任务/冠军契约、页面双场运行时与进度适配，按实际纵向变更增补最少现有测试；不复制完整评价器，不开第二层策略框架，不直接承接实验分支819行改动。

## 最高公开测试接缝

采用现有HTTP生命周期：`POST /api/tasks`且`mode=dual`→`GET /api/tasks/{id}`→取消/继续。现成夹具是`tests/sim2gse/test_formal_champion_recovery.py:16–56`的`dual_page`，已穿过真实服务器、双场父任务、普通任务和结果读取；复用其形态更新到新公开契约，不保留夹具里的旧阶梯缩参作为新算法要求。

现有`test_population_training.py`、`test_formal_champion*.py`、`test_dual_engine_identity.py`、`test_search_timeline.py`及公开任务测试用于必要回归。只在原生/系统边界使用既有可替代依赖，不mock新业务状态机。快速构造通过不等于真实原生/Windows/游戏验收；新旧自然对照须等实施、对应环境与独立审查后执行。

## 门禁一展示必需项

- 工作树、固定main、拟新完整分支名及不继承实验代码；Full等级和技能/Architect证据。
- 用户输入→自然GA→正常复测→可靠单冠军→导出/读取的可观察成功主路，以及取消/故障/存储/旧契约恢复失败路径。
- 最高HTTP公开接缝、真实/替身边界、单纵向票据的范围与粒度；训练五场景四成果不变。
- 自然结束可超过600秒、不设新配额；准备和单次局部超时保留；页面不再展示假600秒百分比。
- 同输入新旧各自默认完整自然结果对照，无共同120秒/共同端点或新统计计划，不合并发布。
- 三组明确推荐：新建`codex/formal-search-ga-default`；单票串行子代理实施；单票完成后独立Reviewer审查。父线程须完整展示并取得当前确认，之后才创建分支和实施。
- 最新裸工具的可用性/身份后续核验；当前未运行旧CLI。正式规格冲突保留到受控增量与门禁二，不因候选文档ready-for-agent就改formal specs。
