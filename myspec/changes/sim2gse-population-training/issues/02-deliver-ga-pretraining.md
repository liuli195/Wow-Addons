# 02：打通GA预训练与四起点消费

**What to build（交付）:** 用户从现有独立训练公开入口完成A种群预训练、五场景复测、正常冠军与稳定代表四起点的可靠发布，正式搜索按成果版本复用，取消或故障可沿冻结配置恢复。

**Blocked by（前置）:** None（门禁一已确认，本票实施及两轴独立审查已完成）；01历史实验已有独立证据，不等待或改写其旧票据状态。当前整体候选最终官方本机fast待100代实验结束后执行，Gate2尚未完整展示并获批准。

**Status（分拣）:** ready-for-agent（实施及两轴Astra审查完成；既有构建／统一验证及真实隔离小验收按实际适用提交保留，后续三项性能实现／审查及03实际产品回放已完成，不能替代当前候选最终官方本机fast；100代实验不改正式2代早停，任务7／8暂停排除，Gate2未批准，整体交付未完成）

**Authorization（授权状态）:** 门禁一已确认：按已展示范围执行02→03、Sol串行实施及每票Astra独立审查；必要本机验证可拉取对应功能分支，整体变更真实隔离验收共享累计20分钟。未获门禁二、主干合并、发布、完整生产训练或具体对象不可恢复删除授权。

## 公开入口与最小接缝

沿用现有训练CLI的run／check／prepare命令及公共run_training；正式消费经公开run_task／resume_task。训练入口直接替换执行而非新增GA模式。内部定向深化已有训练评价接缝，统一冻结配置／五轨迹／可靠缓存／稀疏保存，不能复制实验硬阶段或落回旧screen／CI控制换代。公开测试接缝与本票粒度已随门禁一确认。

## Acceptance criteria（验收）

- [ ] 按既有标准模板和支持范围形成三条件独立组；实际从受检上游取得双英雄标准模板并验真，覆盖英雄×目标四组，不以现单模板加targets循环冒充四组，不新建模板注册表；同专精原料适配／合法性检查／行为去重后全部入初始N，N固定、每代N槽，无材料截断或凑数；正式completed winner回流沿既有路径并新条件重评。
- [ ] 实际执行A锦标赛3、独立交叉／变异0.8及实验动作块算子；合法重复保留槽并复用同完整身份评分，完整子代整批替换；无冠军回填／原始轮转。奇数末槽按原行为只尝试变异。
- [ ] 非法槽额外至多10次重生：每次重抽锦标赛父对，按既定算子固定取第一结果，不择合法／高分侧、不动合法邻槽；耗尽暂停留错。合法模拟／失败复测原条件种子最多重试1；已耗重试和重生次数持久化，恢复不清零。
- [ ] 初评／繁殖统一请求32，缓存仅完整身份相同复用；历史前K共享入围与早停参数，任一排名严格改善／补足清零、默认连续2完整代无改善停；不受旧600秒／三档控制，不将半代视完整代。
- [ ] 最多K默认8个粗分去重候选，以正常及既定四轨迹各3批×请求128独立复测；种子隔离／共同轨迹／有效样本均分、loss和四席规则与父spec一致，无额外实验终点或第五冠军。
- [ ] 第三类参数固定，第一二类白名单实际配置可调：4×5、32、3／128、2、共享K8、锦标赛3及交叉／变异0.8；启动冻结、恢复原值，跨字段范围和乘积≤20校验。初评／反馈／准备／复测共用组内额度，单引擎1线程，不共享跨组DEAP全局随机状态。
- [ ] 可靠报告按12组有界触发及尾刷；缓存命中不做完整检查点，同请求在途计算合并但保留槽。仅保存必要恢复状态和独立证据引用，不反复嵌入累计实验大报告；固定工作量读写／收尾可解释。
- [ ] 取消或故障只保存暂停、恢复原代原复测／候选／种子，不自动选优发布；每组自然早停、全部入围评估且四条合格才先验后写，独立替换同范围current。缺条／缺批不覆盖旧四，别组成功不回滚；极端情况按ROI显式报错，不吞错或暗补人。
- [ ] 成果契约v2消费最多4＋4＋1，旧／无版本按v1旧4＋4＋2读取，未知版本拒绝猜读；仅新GA省独立训练冠军，正式历史冠军原匹配契约及赢家回流保留，不跨条件借分、不新增历史库或新旧对决。
- [ ] 从上述最高公开接缝做有判别力的红绿构造验证，覆盖完整链、恢复／并发／缓存／失败及兼容；真实算法、登记／核验／发布不能整段mock；避免旧command helper默认附带legacy把验收带回旧训练。新测试纳统一入口，构造证据与真实报告不混称。
- [ ] 共享真实20分钟小验收的输入、隔离根、入口和可得计数已准备成可复核计划，不在本票重复烧预算。本票以完整公开链构造／定向验证及Astra独立审查收口；最终真实运行由03清理完成后一次执行，不作为02完成前置，不形成依赖环，也不冒称全70／大N验证。

## 失败恢复与预算

保留成功凭据和安全检查点；不可恢复身份冲突明确拒绝混接，变更业务／公开接缝返回需求路由。真实验收15分钟单组小链＋5分钟四组并发冒烟，包含准备／模拟／收尾；到限暂停并标未完成，构建／构造测试单列且不扩无关矩阵。不写正式数据根，缓存／索引／发布目标整体隔离；不自动扩大本机操作或生产发布。

## Comments（讨论）

2026-10-22：按已确认父spec形成纵向门禁草案，原01不改。推荐Sol串行实施、每票Astra独立审查；待完整门禁一展示后确认分支／开发／审查与票据粒度及接缝，未确认前不执行。

2026-10-22 最新授权：19:10 UTC门禁一已完整展示；用户 Sentinel_4ecb203be170819188a71ee173d434be 补充必要本机拉分支验证，Sentinel_759ece870e648191b5c92c67028a5ef0 明确确认进入开发。此前 Sentinel_c67ede7719f0819185c7a658899c73b3 为按方案开发请求，现以展示后的确认解除门禁阻塞；公开接缝与票据粒度同时获确认，原待答说明保留为历史。本票已进入实施，未声称完成、审查通过或验收通过；分支／基线、预算、隔离和范围沿父spec门禁记录，不扩大授权。


2026-10-22 02实施证据（待独立审查，不代表门禁二或原生验收通过）：

- 实施固定在 `codex/sim2gse-population-mvp`，基线 `2ec24f1bec120128b8be1d993ddad9ce9eca92da`。没有staging、commit、push或切分支；这些由父任务在停写后处理。没有编辑 `myspec/specs/`，没有改生产数据，没有执行真实模拟，也未开始03清理。
- 从公开 `seed_training.main check` 的 `KeyError: templates` 红证据开始（`.local/ga-pretraining-02/red-check.log`），转绿后逐个纵切：公开run旧结果没有algorithm（`red-run.log`）、正式消费者v2仍准备独立训练冠军（`red-consumer.log`）、真实核验拒绝合法压力0（`red-zero-stress.log`）、feedback首次失败没有原seed重试（`red-feedback-retry.log`）、发布失败恢复不能修复缺失证据组（`red-missing-group.log`），各自均有同入口对应绿色日志。没有沿用旧test command helper悄悄走旧算法。
- 实际执行仍复用既有prepare、search.optimize训练评价接缝、compiler、sequence.evaluate、完整request缓存、engine.check_report、TaskStore与共享data-store；仅原生执行/外部受检边界被构造。新 `population_training.py` 不是第二套模拟后端。新增测试自动纳入既有 `tests/sim2gse` 入口。
- 实际受检双英雄模板形成四组：默认prepare/run公开用例覆盖两英雄×单双目标、各N=6同专精全量输入、真实burst/rule绑定、组内<=5及全局<=20、单组持续失败不影响另外三组独立发布且保留失败组旧四份。此前集合暴露的并发新组sqlite初始化竞态已修复：扫描时先核对组manifest再读该组DB，不用单跑绕开；四组集合已复跑通过。
- DEAP 1.4.4与真实varAnd、锦标赛、动作块交叉、既有变异/feedback执行。独立组RNG不修改DEAP全局random；默认.8/.8公开run_training用例实际产生新交叉/变异候选。重复槽保留但完整请求只执行一次；非法固定第一子代而不挑合法第二侧，额外10次及失败原seed一次重试的余额在恢复后均不清零。
- 32粗评、rank topK任一提升清零/两完整代停止、五轨迹fresh共同种子3×128、minimax相对损失与正常/稳定双代表+正常补足四席，均由公开链检查；验证负loss、压力0=100%loss、nominal0显式排除、缺四不可发布。新完整四份直接替换当前范围，不对旧四份加决斗。
- 12-report有界组、完整代/阶段/正常取消刷尾；没有cache-hit逐分完整checkpoint。前台搜索取消和Ctrl-C取消均保存paused、没有自动final；恢复冻结原配置、候选、种子与代数，已持久化成功请求不重跑。Ctrl-C时尚未提交receipt的单个中断请求允许重算，没有冒称该次原生返回已成功保存。
- 发布写入失败保留旧四份；恢复重新验证所有冻结复测凭据，仅重算被删的单个12-report组，并修复被篡改的临时汇总；不能靠缺失报告或checkpoint伪成绩发布。结果v2只消费4+4+1、缺版本/旧v1保留4+4+2、未知版本拒绝；公开run_task/read_task/resume_task与completed winner回流prepare/list均覆盖，未借用旧条件分数。
- 最终定向集合命令：`DATA_STORE_TEST_SKILL="$PWD/.local/skills/data-store" PYTHONPATH="$PWD/projects/sim2gse:$PWD/.local/population-mvp/venv/lib/python3.12/site-packages" .venv/bin/python /workspace/scratch/0af43d0efb8f/cloud-native-pytest.py -q tests/sim2gse/test_population_training.py tests/sim2gse/test_simulation_config.py::SimulationConfigTests::test_training_section_is_independent_validated_and_bounded`。`final-public-suite-3.log` 已22 passed、19 subtests passed（102.16s）；同集合复跑 `final-public-suite-4.log` 再次22 passed、19 subtests passed（93.71s），两轮均exit0。较早不含新增Ctrl-C分支的集合 `final-public-suite-1.log` 为21 passed、19 subtests（146.53s），未把中间红日志删掉。
- 共享训练/正式冠军/恢复/双引擎构造回归 `.local/ga-pretraining-02/shared-regressions.log` 实际为1 failed、28 passed、15 subtests，不是全绿。唯一失败 `test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_budgets`：旧page_task_engine fixture把返回report targets改5却未改已落盘native.json（仍1），AOE恢复真实核验拒绝。完整固定基线只读重放脚本 `.local/ga-pretraining-02/verify-baseline-regression.py` 用git show加载六个原产品模块（保留原__file__），不改工作树；`DATA_STORE_TEST_SKILL="$PWD/.local/skills/data-store" PYTHONPATH="$PWD/projects/sim2gse" .venv/bin/python .local/ga-pretraining-02/verify-baseline-regression.py` 同样1 failed（`baseline-shared-regression.log`），保留完整trace供独立审查。未放宽正式报告核验或擅自扩修旧fixture。
- `python -m compileall -q` 定向产品/测试与 `git diff --check` 均exit0，正式规格diff及untracked检查为空。正式统一入口实跑 `build-and-verify verify --project . --base 2ec24f1bec120128b8be1d993ddad9ce9eca92da --execution-context cloud` 退出1 `baseline_worktree_not_clean`（`formal-verify-preflight.log`），只是提交前预期门禁，没有声称最终构建/验证已跑或通过；父任务干净提交后继续，不篡改Windows统一配置。
- 真实20分钟验收计划已写 `.local/ga-pretraining-02/native-smoke-plan.md`，列明全部隔离根、公开入口、身份冻结、15分钟单组+5分钟四组、准备/feedback/评价/报告/发布全计时、到限正常暂停与可得计数。云端只确认4份真实材料来源/版本/程序哈希，未找到含8份的registry；重复快照和构造输入不充数。现阶段不拉本机材料、不上传正式数据，待02/03与独立审查后按必要本机验证授权处理8份前置条件。真实预算尚未使用。
- 验收方框暂不代审查人勾选。实施完成后停止所有写入，等待父任务提交并组织Astra独立审查；03仍串行等待02审查结论。


2026-10-22 20:24 UTC 首轮审查修复证据（基于HEAD 73271be，等待两轴复审）：

- 按4项P2逐项公开红→绿修复，没有开始03、没有Git写操作、没有真实模拟或本机材料获取。没有新增注册框架/第二后端，没有放宽真实身份与共享报告核验。
- P2曲线：公开CLI启用后原先没有曲线（`review-red-timeline.log`：1 failed、1 passed）；接回既有Timeline、CLI/API共同起始时刻、已有成绩采集及完成/取消/失败结束导出。`review-green-timeline.log` 2 passed，后续CLI/API开关共4例及两种取消恢复纳完整集合；开/关实际native请求同为66，不新增评价。最终检查时间顺序start<=stop<=saved，导出标注真实GA算法/组seed，不改物理条件分图规则。
- P2 feedback稀疏保存：公开N70/seed0、锦标赛3、cx0/mut1、真实DEAP与真实变异链复现首个checkpoint缓冲44条feedback（`review-red-feedback-bounds.log`：1 failed，实际44对期望12）。成功feedback复用同一12-report阈值及时checkpoint，缓存命中不额外写；第12条在尚无pending整代计划时即提交。取消后从原代RNG重放，真实变异输入/输出及前后RNG与取消前前缀一致，已成功feedback不重新模拟，最终生成完整70槽。`review-green-feedback-macro.log` 包含该例通过。
- P2非法导出：公开真实block变异从合法宏变成>255字节，原先只报导出错误并永远卡槽（`review-red-macro-slot.log`：1 failed）；现复用codec.prepare_block/prepare_castsequence静态导出校验，目标源码核验放在重生catch之外。确定性非法仍固定第一子代，第二合法侧不替换，额外10次余额持久化；与4096点击超限合计两例通过，恢复不增加第11次尝试。该项和feedback合计 `review-green-feedback-macro.log` 3 passed。
- P2真实执行/报告失败：用真实engine.run非零退出、真实sequence.evaluate缺报告/坏JSON路径复现（`review-red-native-errors.log` 6 failed），不是只人工抛CandidateError。最小增加NativeEvaluationError(ValueError)区分明确单次运行/报告交换失败，仅正式GA原身份一次重试并持久化余额；普通搜索仍按ValueError通道报错。身份目标数不符、报告读取PermissionError直接报错、不消费重试。`review-green-native-errors.log` 8 passed；加入两项不重试守卫与CLI/API曲线后 `review-green-errors-and-timeline.log` 14 passed。
- 完整公开集合：与前次相同命令和两个测试路径，日志改为 `.local/ga-pretraining-02/review-final-public-1.log`（36 passed、19 subtests，151.88s）及 `review-final-public-2.log`（36 passed、19 subtests，139.49s）；两次exit0，最后一轮覆盖最终源码与曲线时间顺序断言。
- 共享组合明确排除已在固定基线复现的单个旧双引擎fixture失败：`review-shared-regressions.log` 为43 passed、1 deselected、15 subtests，62.86s，exit0。路径为test_search_timeline.py、test_engine.py::test_native_execution_timing_preserves_process_outcome、test_sequence.py::test_evaluation_timing_preserves_report_and_trace_contract，以及test_training_champion.py、test_formal_champion.py、test_formal_champion_recovery.py、test_formal_champion_review.py、test_dual_engine_identity.py；过滤项为 `-k 'not test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_budgets'`。没有把排除后的绿灯冒充完整双引擎全部通过；原完整失败trace、固定基线只读重放命令/脚本保留不动。
- 原生验收计划按审查纠正：仅只读消费核对，不额外真实run_task/resume_task；4+4+1为当前初始化4＋GA4＋历史冠军1；32与128各自记录数量级，不强求同seed配对/精密误差；五场景×三批共15 fresh seeds，同场景同批跨候选共享。仅4份真实来源、缺8份前置仍阻塞，未使用20分钟真实预算。
- 最终compileall与git diff --check exit0，myspec/specs/未修改。修复范围仅5个产品文件（population_training、seed_training、search、engine、sequence）、公开测试文件和本票证据；.local计划/日志是隔离证据。全部测试结束后停写，由父任务提交并组织复审，未自代勾选验收。


2026-10-22 第二轮审查残留修复（基于HEAD e11d4c4，未自行提交）：

- 对真实sequence.evaluate→engine.check_report链新增NaN/Inf/错误样本数各“失败一次后成功”和“失败两次恢复仍耗尽”用例，`review2-red-numeric.log` 六例全部失败：原先没有重试或恢复没有耗尽提示。成功重试同样经过真实sequence/check_report，不只用人工CandidateError或绕过成功报告核验。
- 产品最小修复仅engine.check_report四行差异：角色/目标/装备身份通过后，DPS非有限/负数及原既有样本数核验失败复用NativeEvaluationError；没有放宽任何数值判定，没有泛捕ValueError，没有新异常框架。spec62不混入失败/不完整批与既有实际样本数核验，支持将已验身份后的样本数错误同归不可靠数值报告；故合并覆盖。固定180秒战斗时长仍单独普通ValueError直接报错，避免把物理条件错误归为可重试数值。
- `review2-green-numeric-and-guards.log` 16 passed（37.51s），包括既有CandidateError、真实进程非零、缺报告、坏JSON、NaN/Inf/样本数及身份/存储不重试。另补时长不符直接报错守卫，纳最后完整公开集合。每次重试均原candidate/seed/input/compiled identity，失败两次后恢复不再执行第三次。
- 共享相关回归 `review2-shared-regressions.log`：28 passed、1 deselected、15 subtests（49.32s），exit0。仍只排除已固定基线复现的旧双引擎fixture目标数不一致，不放宽正式核验、不声称完整全绿；重放脚本和完整旧trace不变。
- 原生验收计划第6/33行已改为：只在隔离副本按记录规则固定选8条并记录来源/revision，prepare应有8个有效不同行为，正式registry材料不删不改，仍20分钟；不是要求全部材料N>=8。仅4份真实来源/缺8份前置仍明确阻塞，未运行真实模拟或拉取本机材料。
- 最后完整公开集合证据为 `.local/ga-pretraining-02/review2-final-public.log`，命令沿前两轮同一环境前缀与 `test_population_training.py`、`test_simulation_config.py::SimulationConfigTests::test_training_section_is_independent_validated_and_bounded`；最终43 passed、19 subtests（159.66s），exit0。前三项P2的曲线开关/取消恢复、12-feedback及时提交/RNG重放、非法宏固定第一子代10次重生继续在该集合内，不另改实现。

- 2026-10-22 20:34 UTC全部相关测试结束；compileall和git diff --check exit0，myspec/specs/ tracked/untracked均无变更。全部停写，等待父任务提交与最终复审；03未开始、真实20分钟预算未用。

2026-10-22 20:36 UTC：父任务确认02两轴Astra最终通过，HEAD 1f08058f06729a71e5b5ed51259ead784b481cb0；解除03实施依赖。此记录只确认02实现审查收口，不代表真实模拟验收、统一构建、门禁二或交付完成。
