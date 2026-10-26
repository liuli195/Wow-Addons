# 逐测试承接表

标记：M=可直接调用真实生产函数、显式内存输入；R=必须保独立真实边界；P=只能精简/复用前置准备，不能整项改标普通；S=需要本计划唯一的生产接缝抽取。名称均为现有完整test函数名（省略文件公共路径tests/sim2gse/）。表中“迁移”是拟议去向，非已实现结果。

## test_dual_engine_identity.py（2个函数）

| 原测试 | 分层与全部断言承接 |
|---|---|
| test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_runtimes | M+P：精确baseline/controlled读取1→2→3→4→5；两个训练冠军ID；两场预算None、runtime独立且inf；取消后elapsed>=17且单场恢复仍>=17；两次collection_ready。普通层直接执行dual_task.start/resume/_worker、engine.identity及formal runtime，外部读写/任务执行/导出只用局部显式响应，不能返回预设身份计数。实际小产物清单/SHA/真实启动恢复接线合到唯一双场主路；至少一次真实启动+恢复的两引擎读数仍被观察。若需大规模补齐_worker环境，停止迁其编排部分，保真实，不造调度器。 |
| test_dual_rejects_changed_engine_on_first_verification | M+R：identity真实SHA对内存变更bytes拒绝与_friendly_error映射分开普通化；保一个物理更改小引擎产物、HTTP500及中文错误的真实失败代表（当前只是read_bytes注入，不可称原先已有物理篡改），确认未开始计算。不得把构建清单核验mock掉。 |

## test_checkpoint_changes.py（8个函数，含参数组合）

| 原测试 | 分层与全部断言承接 |
|---|---|
| test_checkpoint_structural_changes_fall_back_without_losing_unmarked_nested_state | M已完成：reorder/delete/append/new_field/whole_archive五项、未标记嵌套reward、完整重开状态不变；不重写。 |
| test_scoped_checkpoint_deletes_an_explicit_field | M已完成：pending删除及重开一致，不动。 |
| test_scoped_checkpoint_failure_rolls_back_and_retry_persists_all_changes | M已完成：真实SQL触发器失败、完整回滚、同对象重试、reward=.75及samples=[2,4]，不动。 |
| test_resume_after_partial_group_commit_uses_unused_group_number | R+P：保13份、11+legacy第12+tail、确切中断SQLite镜像重开，11→13、组号1→2、请求/启动计数13、无重复、全部分组/分值/元数据/意图清空/临时报告清理及再次重开完整相等。已无HTTP/GA/native准备，不能再假称节省整链。 |
| test_report_checkpoint_persists_original_locations_with_one_complete_comparison | R+M：12份同组g0、调用者原row位置回填、计数12、buffer空和真实重开保R；state_write_count差1可直接用内存TaskStore._commit_report_group + checkpoint验证，但不以直接_commit替代原flush只比较一次接线；该断言留在R做交叉证明，额外内存仅覆盖规则。 |
| test_mixed_checkpoint_and_immediate_batch_encode_each_summary_once | M+R：批报告、cached/final/failed/immediate各编码1次、state_write_count2、完成数4、各batch精确相等移真实SQL内存组合；通过真实_commit_report_group和checkpoint/put_batch，显式metadata输入，不模拟flush返回值。独立第二TaskStore可见batch/cached/immediate、看不到final/failed、真实重开相等保一个R共享持久化代表。原flush→commit的每份一次编码断言在R暂保，直到普通层覆盖的是同一实际调用链而非人为拼接。 |
| test_empty_report_checkpoint_still_saves_nested_state_and_summary_count | M已完成：with_summary False/True、reward=.25、一次写及0/1计数、重开相等，不动。 |
| test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery | R+M：same_object/reopen原两参数。SQL最终提交失败、before状态、12已可靠/13缓冲/2意图、重试到13、next_group2移M事务规则；实际Parquet先提交而SQLite回滚的跨边界事实保R，reopen仍实际重开并recover_reports、保原archive和清理。same_object能否合进同一真实代表取决于故障时刻承接；不能用SQLite内存替代Parquet/locator一致性。 |

注：首项5参数、末项2参数、empty2参数；这里不以函数/参数数量减少作为验收。report_locations={}仅适用于不flush的SQLite接缝，flush_reports需要.locked()/entries/groups及data-store API；禁止偷偷扩成fake数据库框架。

## test_data_store_connection.py（6个函数，9个参数实例）

移除模块级pytestmark=real，逐个真实代表显式标记；普通项不能继承real。

| 原测试 | 分层与全部断言承接 |
|---|---|
| test_connected_consumer_reads_writes_without_old_user_installation | R+M：隔离安装/真实connect CLI/空HOME子进程/生产adapter读写、筛选命中与不命中、BLOB精确bytes、SQL嵌套part=4保主接入冒烟；缺binary-write-v1的文案及blocked_write未调用移M真实result_store.write，禁止为了规则再起子进程。 |
| test_unconnected_consumer_fails_before_writing_data | R：隔离复制真实adapter、空HOME、未接入子进程非零/中文接入错误/data目录不存在，独立发现与安装失败边界，不与成功冒烟混称等价。 |
| test_page_classifies_wrapped_storage_failure_from_the_real_target | R+M：真实runs parquet损坏→真实HTTP读任务→storage_unavailable/recoverable/中文错误保一个损坏传播代表；链式异常分类组合调用interface._is_storage_error/_friendly_error移M。 |
| test_known_batch_groups_and_legacy_single_do_not_fallback_on_missing_keys | R：真实group+legacy和无关损坏shard、missing None、投影/筛选不回退全表，属于真实存储寻址隔离，不只是dict查找。 |
| test_page_classifies_report_locator_permission_error_as_storage_failure | M+R：两个blocked_file原异常链TaskError→DataReadError→PermissionError与页面映射直接生产函数验证；保真实ReportLocations.locked和jsonl读取两个不同文件边界（每个只一次故障，不重复建HTTP/全任务）；物理locator能读到dps7/samples2仍先证。HTTP状态映射承接上一损坏代表+普通映射，明确不再重复每一权限文件×HTTP组合；若父任务对HTTP路径封装差异有独有断言不能证明，原组合保留。 |
| test_page_reports_storage_startup_failure_before_native_compute | M+R：dual/api-version、optimize/api-version、dual/definition-file三组合。API版本/中文同步与版本2、无data写入、Popen未调用规则M；真实接入产物加载API拒绝保1例，实际损坏definition parquet保1例；optimize的202/handle完成/GET storage_unavailable与dual的500区别必须分别调用真实处理/生命周期入口，不能只测_friendly_error；若直接HTTP Handler内存载体需新框架，保该异步真实例，不先减3→2。 |

## test_formal_champion.py（14个函数）

| 原测试 | 分层与全部断言承接 |
|---|---|
| test_dual_inherits_each_scenes_formal_champion_after_publication | M+P+S：两场published、中心source_run_id一致、正samples；第二轮selected/来源继承/targets/accepted/正score/同DPS/unchanged/source_kind全部保。formal_cohort分别绑定1/5，真实_freeze_formal_champion/新提取起点函数/publish_search_champion验规则；双场实际读写接线由唯一主路保，每场实际published后读回。取消为普通规则再次跑两轮dual；不得声称两轮完整HTTP跨轮组合仍实测。 |
| test_dual_preserves_legacy_ten_source_paths_and_replaces_champion_after_complete_retests | S+M+R：选作本四模块唯一HTTP双场编排主路的原载体。4/4/1/1十来源、空chains、stagnation/natural policy、300DPS、旧来源不同、v2/空promotion/完整代>=2/每finalist3批381样本分别通过真实起点提取函数+memory_ga(formal=True)+formal evidence/publish函数承接；R只保一轮双场、真实中心往返、两个结果和collection。旧冠军显式完整证据只作输入，不再为了规则先执行完整任务。来源数/复测规模不在生产或普通断言中缩水。 |
| test_dual_stale_task_cannot_replace_a_newly_published_distinct_champion | M+R+P：snapshot absent、同condition、旧任务conflict、有样本、新冠军source被后继读取保留。普通CAS组合调用真实publish_search_champion（只替换锁/读写边界）；独立R用两份完整formal_cohort证据，两个竞争发布者实际锁/存储CAS及再读，避免stale dual+fresh run+inherited run共四场搜索。实际线程/锁竞争必须发生，不用串行mock声称并发安全。 |
| test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return | R+M+P：真实可靠已存winner+pending意图、600 elapsed、resume发布、结果/批数不变、第二次幂等/原snapshot不变、evaluate禁止保R。用已有显式证据准备状态而非完整搜索；_publish_formal_champion顺序/失败分类可M。若合法保存状态必须重新实现_run_task协议，保原准备，不编造第二套checkpoint。 |
| test_dual_formal_champion_isolated_by_frozen_character_and_full_conditions | M已完成：equipment/cadence/engine/targets四组合、key不同/冻结input/目标/读取key不变。 |
| test_management_selects_the_highest_within_two_known_old_rule_sources_and_rejects_missing_proof | M+P：profile/source_batch_forged拒绝、零冠军写、旧来源行不变；明确low/high/high去重范围、最高300、来源条件与新条件不同、不复用旧DPS、publication published、已有冠军不覆盖、65拒绝、禁止runs/candidates全表扫描全部承接。真实_historical_formal_champion+import_formal_champion前置范围验证；在既有fixture补显式v1 run/candidate/request/report，不复用v2假称v1。不再运行三次旧引擎准备；若成功import完整入口接线无其他真实承接，保一条最小真实管理导入（风险代表，不第二双场主路）。 |
| test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch | R+M+P：中断首batch、旧冠军等于incumbent、版本与快照一致、无publication/search_result；外部version+1后恢复快照不变/publication unchanged。规则用memory_ga取消+formal_cohort冻结承接，保实际取消检查点/外部中心更新/恢复一个R；第一轮dual仅准备incumbent可用完整显式证据替换。 |
| test_dual_formal_champion_read_errors_remain_visible_and_do_not_overwrite_the_incumbent | M已完成：5种读取/程序错误可见、incumbent不变、write未调用，不动。 |
| test_formal_source_consumes_only_supported_explicit_contracts | M已完成：None/1/2真实校验completed，不动。 |
| test_formal_source_rejects_unknown_or_noninteger_contract_versions | M已完成：True/0/3/'2'契约版本拒绝，不动。 |
| test_formal_champion_requires_complete_request_reports_and_matching_source | M已完成：11种winner/samples/batch/request/score/report/profile/program损坏全保，不动。 |
| test_formal_champion_validates_all_six_original_reports_without_a_center | M已完成：6报告、200分、381样本及真实校验completed，不动。 |
| test_formal_snapshot_freezes_the_verified_published_version_without_rewriting_it | M已完成：selected/version/source/score/samples/finalists/原记录不变/零write全保，不动。 |
| test_formal_champion_rejects_changed_algorithm_or_incomplete_retest_contract | M已完成：10种契约/引擎/代数/停滞/promotion/duplicate/retests/sample/nonfinite错误全保，不动。 |

## 真实数量与承接约束

本四模块内目标完整HTTP双场编排主路1条，不是“全GSE仅1条主路”或“全GSE仅1个real”。该载体使用champion_engine/page_task_engine替代评分，不替代真实原生引擎产品冒烟。独立风险至少保：冠军真实CAS、pending发布恢复、取消快照恢复、引擎产物篡改拒绝；checkpoint部分提交镜像恢复、12份原引用回填、共享复用隔离、末组失败重开；存储安装成功/未接入、真实损坏传播、分组隔离、两种locator权限边界、启动失败跨API/definition。上述风险不能按数量指标强行合并。管理导入与异步启动代表是否可承接尚有明确停止条件；因此不承诺最终real参数实例数，交付按边界清单核销，不以未核实的最小数量签空白授权。

范围外保留：test_formal_champion_recovery.py:52–78、test_training_champion.py、test_burst.py仍有dual/HTTP流程，test_interface.py:1125浏览器真引擎链亦保留。本表只承诺四模块内去重，未逐项映射范围外断言，不宣称其已可删除或全GSE主路唯一。
