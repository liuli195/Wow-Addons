# 云端实施核销（Windows组合验收待完成）

基线9b1a958；票01为80b511b＋291f997，票02为e6a844f，已审适配整合为6bb0b2e＋13a6d89，票03为2513b4f。每票及整合双轴独审最终均0发现；票01首轮P2已经返工关闭。未合并主干。

## 数量不是收益

按源代码AST逐函数及parametrize展开核对，非依测试名猜测：

| 四模块 | 原普通/真实函数 | 现普通/真实函数 | 原普通/真实参数实例 | 现普通/真实参数实例 |
|---|---:|---:|---:|---:|
| dual_engine_identity | 0/2 | 1/2 | 0/2 | 1/2 |
| checkpoint_changes | 4/4 | 5/4 | 9/5 | 10/5 |
| data_store_connection | 0/6 | 2/6 | 0/9 | 2/9 |
| formal_champion | 8/6 | 13/5 | 39/6 | 48/5 |
| 合计 | 12/18 | 21/17 | 48/22 | 61/21 |

原12个普通函数的原参数/断言保留；原18个真实函数为**1整项转普通、7拆规则保真实、1仅简化准备、9保留真实**。新增普通13实例、真实仅少1实例都不是提速证据。

## 原18个真实函数逐项去向

以下均指原nodeid；具体旧断言及新接缝见mapping.md，原断言逐表达式快照在云端ticket2证据目录。

| 原测试函数 | 实际处理 |
|---|---|
| identity::test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_runtimes | 保留真实。身份1→5读取、runtime独立、取消耗时与单场恢复及双场集合全保；不为移编排造调度器。 |
| identity::test_dual_rejects_changed_engine_on_first_verification | 拆规则保真实。普通真实identity内存SHA/文案；真实物理产物篡改、HTTP500及禁止_launch/Popen。 |
| data::test_connected_consumer_reads_writes_without_old_user_installation | 拆规则保真实。能力拒绝普通；安装/空HOME/CLI/真实读写与BLOB保留，启动次数未减。 |
| data::test_unconnected_consumer_fails_before_writing_data | 保留真实，空HOME未接入失败且无data写入。 |
| data::test_page_classifies_wrapped_storage_failure_from_the_real_target | 保留真实，实际坏Parquet→HTTP错误传播。 |
| data::test_known_batch_groups_and_legacy_single_do_not_fallback_on_missing_keys | 保留真实，分组/legacy寻址与无关坏分片隔离。 |
| data::test_page_classifies_report_locator_permission_error_as_storage_failure | 拆规则保真实。两文件实际读失败链保留，普通真实页面映射承接；撤JSONL唯一HTTP，锁文件分支原无HTTP。 |
| data::test_page_reports_storage_startup_failure_before_native_compute | 保留真实三参数，包括optimize 202/handle/GET生命周期；不造Handler调度框架。 |
| checkpoint::test_resume_after_partial_group_commit_uses_unused_group_number | 保留真实，13份11+legacy12+tail、精确中断镜像、分组/计数/完整性/清理/重开全保。 |
| checkpoint::test_report_checkpoint_persists_original_locations_with_one_complete_comparison | 保留真实，12份原引用位置回填/一次比较/重开仍验证真实flush接线。 |
| checkpoint::test_mixed_checkpoint_and_immediate_batch_encode_each_summary_once | 拆规则保真实。本对象计数/逐值规则进入内存SQL；物理flush、第二Store隔离、重开和编码交叉证明保留。 |
| checkpoint::test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery | 保留真实same_object/reopen两参数。事务失败与Parquet/locator跨边界不可由直接SQL替代，按停止条件不新造flush协议；未称已普通化。 |
| formal::test_dual_inherits_each_scenes_formal_champion_after_publication | 整项转普通两场参数，实际组装/GA重评分/冻结/发布/CAS。current_score字段及原DPS相同断言由取消恢复真实收尾承接；不再保原两轮HTTP交叉。 |
| formal::test_dual_preserves_legacy_ten_source_paths_and_replaces_champion_after_complete_retests | 拆规则保真实。十来源→真实内存GA→CAS300替换200；真实节点更名为双场发布/集合主路，仅一次双场。 |
| formal::test_dual_stale_task_cannot_replace_a_newly_published_distinct_champion | 拆规则保真实。普通版本/incumbent拒绝；完整已存赢家实际双线程争锁、公开生产发布、conflict及中心新读回。 |
| formal::test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return | 保留真实，pending合法任务准备及公开恢复全留；不重写合法checkpoint协议。 |
| formal::test_management_selects_the_highest_within_two_known_old_rule_sources_and_rejects_missing_proof | 拆规则保真实。明确v1组合/范围/65上限普通；两真实旧来源、公开profile拒绝与成功import及已有冠军不可覆盖保留。 |
| formal::test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch | 仅简化准备，首轮dual改真实单体。实际取消/冻结/外部版本更新/恢复全部保留并承接current_score精确字段。 |

## 实际减少与未减少

按原成功路径静态计算，冠军族带I/O任务场景流程少10次：两轮双场继承4次改内存、十来源首次单场准备1次、stale/fresh/inherited共4次、取消首轮多余AOE 1次。这不是实测进程次数，也不是原生C++模拟次数，更不等于节省10秒。另少一次JSONL HTTP搭建、一份foreign旧来源物理构造及其失败管理初始化；旧来源helper本不执行GA，不能算省训练/搜索。

身份成功链、启动三故障、公开pending恢复、checkpoint全部物理准备未减少。票03主要使SQL规则受普通内存约束，不宣称减少准备或墙钟。既有session安装、module素材、DK缓存均未重复算收益。

四模块中仅一条独立产品编排主路，另保身份/取消等风险链；范围外仍有HTTP/浏览器/真实引擎主路，不称全GSE唯一或全仓分层完成。规则迁移后不再执行原HTTP×两场×全部规则组合交叉，独有断言与风险按表承接。

## 待Windows串行验收

组合代码云端普通357＋108通过，inventory478=357普通+121真实；直接pytest不是官方守卫。Linux缺msvcrt的真实失败保留；全部必要边界必须在Windows实际通过后关闭。原适配分支单独通过不替代组合通过。父层在AB终态后安排：

```powershell
.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_dual_engine_identity.py tests/sim2gse/test_checkpoint_changes.py tests/sim2gse/test_data_store_connection.py tests/sim2gse/test_formal_champion.py --strict-markers --durations=20
build-and-verify verify --project . --full --performance-report --execution-context local
```

预期四模块82参数实例（61普通＋21真实），原子测试计数由实际输出记录。保全部43检查、17普通守卫、原配置及60秒预算，无缓存/无残留。与同适配修复基线工具59.8889秒/墙钟60.157秒比较；只有单轮时不作统计收益结论。未实施Lua，不自行启动本机重验证。
