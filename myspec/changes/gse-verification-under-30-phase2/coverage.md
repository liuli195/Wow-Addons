# GSE <30秒：阶段2完整118契约承接矩阵（候选已实施，待真实验收）

> 历史资源门：旧main ea0e230/tree48c963同树6/8完整43项全过、0cache；真实118+19、普通410+130，8路37.61秒仍未达30。随后从已保存8路9676c51继续整组整改，并已正常整合新main3ee81b的诊断修复。实际受测新代码e0f42cc/treec469d12的普通结果为416 tests＋168 subtests，118 real仅deselected；真实与性能仍待完整验收。下表118真实库存仍适用，但普通源码/数量已变化，不能笼统称全部源码与旧对照相同。旧工作秒仅排优先级，不是当前收益。

## 固定读取身份与范围
- 只读树：`aba8e50c37747b121384185922f0b08f051fb0b0` / `b12bc41c4a503a90f830f0d62a4a90508cbfc1e2`；正式规格应用后须重新固定最终候选并复核清单。
- 实际pytest collect-only：528=410 ordinary（普通）+118 real（真实）；未运行用例，不是正式验证通过。
- 118真实参数实例全部登记；现有410普通及130子测试的独有断言保留，不改变自动发现选择；迁移/拆分必须指明新活节点与必要真实见证，透明报告新数量。
- 旧121真实→118：退役3个benchmark专属真实节点；search恢复节点仅budget→elapsed_time更名。通用replace_file重试仍在test_runtime普通层。
- 本矩阵是统一方案的完整边界清单：6/8资源门已完成，8路37.61秒未达标后已获整组实施授权；不逐个挑4例作试点，不将开发候选当性能收益。
- 下列工作秒是旧cb4d88单组诊断，不是退役候选实测，也不是与全仓墙钟可直接比较的加速数据。

## 分层总览
| 层 | 当前模块/真实实例 | 旧诊断工作秒 | 阶段2方向 |
|---|---:|---:|---|
| 编排、训练、网页、冠军 | 10 / 55 | 138.486 | 重复规则经现有memory_ga/直接生产函数；真实风险最小合法前置 |
| 原生语义、身份、编译 | 9 / 48 | 52.141 | 保真实，已核验不可变准备按worker复用；不共享可变状态 |
| 存储、checkpoint、诊断 | 3 / 15 | 5.317（旧18还含benchmark0.899） | 保独立风险与真实SQL/Parquet边界；低收益不再抽象 |

分层延用既有诊断口径：seed_training计编排层，retired_capabilities的原生scope/并发冻结计原生层，故模块工作秒与分层小计一致。这只是组织归类，不改变真实边界。

整体目标工作秒≤150只是工程控制目标，不预先承诺能够达到；最终必须全仓外4且GSE real<30、总时不退化、43全过。当前退役后尚无新工作秒测量。

## 逐模块承接
| 模块 | real实例 | 旧工作秒 | 准备/分层方向与不能削减的边界 |
|---|---:|---:|---|
| `population_training` | 8 | 34.541 | 保公共CLI、四模板真实共享上限、三取消/日志恢复参数、12报告组损坏与补发；规则组合进已有memory_ga，不改并发专测的4×5约束；registered_six只复用不可变材料描述，物理中心/登记逐例隔离。 |
| `interface` | 9 | 28.336 | 保9个HTTP/浏览器/并发/可靠可见性/共享存储恢复边界；真实浏览器双场与选中候选真实原生保留。仅复用现有_fast_*、_initialized_starts和固定合法起点；禁止模拟Handler或删真实剪贴板链。 |
| `search` | 12 | 23.825 | 保公共run/resume、SQLite/Parquet损坏恢复、真实交换文件和Windows进程所有权；纯GA组合用现有memory_ga(formal=True)。真原生首批/选中候选、硬退出、另owner存活不得替身。 |
| `burst` | 9 | 20.475 | 保9项审核门、真实药水/原生错误身份、双来源队列与跨战斗CD、历史适配HTTP、部分双场恢复、冻结定义点读。两条双来源模拟可研究worker内只读已核验爆发准备复用；每例自己的导出/controlled目录和中心。 |
| `formal_champion` | 5 | 9.473 | 保HTTP双场主路、真实CAS文件锁、pending公开resume、v1管理导入、取消后冻结冠军。已有formal_cohort/formal_publication_inputs只为合法来源证据准备；不新写恢复快照协议，不重复计此前少10场收益。 |
| `retired_capabilities` | 4 | 9.346 | 保无职业规则库的正式/GA公共链、两活跃组前台取消、两组prepare冻结爆发。规则身份/禁止旧键已在ordinary承接；并发Barrier/Event与实际共享中心不删。 |
| `formal_champion_recovery` | 4 | 6.531 | 保完整自然复测HTTP、发布失败补发不重评、首评失败仍可读reference、完成落盘失败恢复已验winner四风险；仅通过现有TaskStore/报告写入准备合法前置，不造checkpoint平台。 |
| `training_champion` | 2 | 6.012 | 保取消后新训练到达不换冻结冠军、真实v1历史经公共双场消费；completed_training本来构造完整证据不是运行训练，不能把它当省GA收益。可复用不可变history输入，中心和恢复文件隔离。 |
| `search_timeline` | 1 | 2.873 | 保一条文件/CLI生命周期，取消与恢复新段、旧曲线不可变、离线曲线零模拟、绘图失败不损成果、关闭开关和失败段；已共用一次完成任务，不能再次计算同一收益。 |
| `formal_champion_review` | 1 | 2.670 | 保4种物理checkpoint故障和可靠中心损坏优先级；同源完成任务已复用，若用TaskStore+既有完整证据替准备，必须保公开read_task/resume全部原断言与源字节未改。 |
| `sequence` | 24 | 20.358 | 24项全部保真实原生时序/队列/反馈/控制块语义；已有setUpClass准备不能重复算收益。只评估同一worker已知不可变参考的跨模块复用；每例候选与运行输出独立，不同模板/查询/输入事件不共享。 |
| `simulation_config` | 2 | 7.056 | 保两个公共任务的原始/有效字节、hash、冻结配置、篡改先于TaskStore、恢复不写污染；纯_effective_input/config组合可直调生产函数，但不能只造dict替公共恢复。 |
| `character_export` | 4 | 5.985 | 4项保真实Lua编译非战斗前缀、角色/背包和中文/ASCII临时路径、channel饰品、两主动饰品目录；不同真实素材不合并，已有小样不再缩参数。 |
| `dual_engine_identity` | 2 | 5.964 | 保每次start/resume身份读数1→5、两场独立runtime、取消时间和真实小产物篡改HTTP500；small_verified_engines和规则首扫已有，不共享被篡改可变产物，不把跨task identity缓存当优化。 |
| `seed_training` | 4 | 3.750 | 保前台锁阻止训练、准备上下文只重建变更源、公开CLI爆发准备/消费、物理坏历史不覆盖；memory_training_center/构造输入已用处不算新增收益。 |
| `native_compatibility` | 5 | 2.226 | 5项保original/baseline/disabled逐值战斗一致、真实构建身份、替换形态、急速与已执行战前占用、非DK完整引导、未执行战前不计占用；不同profile/模式必须真实执行。 |
| `engine` | 2 | 0.533 | 两真实查询保mage宠物初始化与未执行动作name查询；输入专属native probe不能用默认sample参考替代。 |
| `program` | 3 | 0.415 | 3项保真实上游Lua：Random两seed顺序不同且来源映射一致、六控制块集合、旧/新导出字节及编译顺序等价；纯结构已有ordinary，保真正上游编译。 |
| `combat_log` | 2 | 0.258 | 2项保任务指针→类型化中心同报告及真实CLI/文件选最新GSE会话；pure analyze组合已有ordinary，不重复计迁移收益。 |
| `data_store_connection` | 9 | 2.719 | 9实例全保：隔离安装connect成功/未接入、空HOME子进程、真实Parquet损坏HTTP、group/legacy寻址、两locator权限文件、三启动失败含optimize异步202。安装不可变副本已session复用；损坏/安装实例可变文件必须隔离。 |
| `checkpoint_changes` | 5 | 2.529 | 5实例保真实13=12+1分组部分提交镜像、原row位置回填、一次编码及跨Store隔离、same_object/reopen末组失败恢复；_new_checkpoint/_stage_checkpoint_reports现有最小真实前置，不缩12阈值，不改成内存Parquet假象。 |
| `diagnostic_logging` | 1 | 0.069 | 1实例保真实write_batch→read报告等价和两阶段调用/rows统计；纯计时故障/区间并集已ordinary，收益低不再造抽象。 |

## 全118实例逐项登记
每项默认保留真实节点及其全部源断言。若后续迁出某条纯组合，必须在同票写明新活断言节点；否则保留原断言。下面的“策略”引用上表同名模块，不表示可以整项删去。`contract-evidence.json`保留每项源函数、hash与直接断言，辅助函数/内嵌脚本仍须按源码复核。

| # | 原nodeid（最终退役读取树） | 源函数行 | 直接断言数量* | 策略 |
|---:|---|---:|---:|---|
| 1 | `tests/sim2gse/test_burst.py::test_public_burst_precheck_requires_a_reviewed_definition` | 70–74 | 1 | 保真实；见`burst` |
| 2 | `tests/sim2gse/test_burst.py::test_public_burst_precheck_roundtrip_and_real_potion` | 78–128 | 21 | 保真实；见`burst` |
| 3 | `tests/sim2gse/test_burst.py::test_public_burst_native_rejects_wrong_spell_id_with_a_real_action` | 172–181 | 1 | 保真实；见`burst` |
| 4 | `tests/sim2gse/test_burst.py::test_dual_source_castsequence_keeps_native_queued_origins` | 186–211 | 5 | 保真实；见`burst` |
| 5 | `tests/sim2gse/test_burst.py::test_dual_sources_share_cooldown_and_reset_between_battles` | 215–244 | 5 | 保真实；见`burst` |
| 6 | `tests/sim2gse/test_burst.py::test_reviewed_burst_training_rejects_unsafe_adaptation_and_preserves_old_training` | 287–332 | 10 | 保真实；见`burst` |
| 7 | `tests/sim2gse/test_burst.py::test_page_dual_scores_character_adapted_seed_without_changing_training[True]` | 379–449 | 11 | 保真实；见`burst` |
| 8 | `tests/sim2gse/test_burst.py::test_dual_keeps_completed_child_and_recovers_without_searching_it_again` | 453–520 | 13 | 保真实；见`burst` |
| 9 | `tests/sim2gse/test_burst.py::test_dual_children_reuse_the_frozen_definition_without_rediscovery` | 526–563 | 4 | 保真实；见`burst` |
| 10 | `tests/sim2gse/test_character_export.py::CharacterExportTests::test_native_catalogue_exports_both_active_items` | 264–281 | 3 | 保真实；见`character_export` |
| 11 | `tests/sim2gse/test_character_export.py::CharacterExportTests::test_native_precombat_buttons_and_item_keep_the_complete_nocombat_prefix` | 93–147 | 7 | 保真实；见`character_export` |
| 12 | `tests/sim2gse/test_character_export.py::CharacterExportTests::test_public_entry_preserves_real_character_and_bag_candidates` | 194–232 | 18 | 保真实；见`character_export` |
| 13 | `tests/sim2gse/test_character_export.py::CharacterExportTests::test_public_entry_simulates_native_channel_item` | 248–261 | 5 | 保真实；见`character_export` |
| 14 | `tests/sim2gse/test_checkpoint_changes.py::test_resume_after_partial_group_commit_uses_unused_group_number` | 142–230 | 20 | 保真实；见`checkpoint_changes` |
| 15 | `tests/sim2gse/test_checkpoint_changes.py::test_report_checkpoint_persists_original_locations_with_one_complete_comparison` | 234–247 | 6 | 保真实；见`checkpoint_changes` |
| 16 | `tests/sim2gse/test_checkpoint_changes.py::test_mixed_checkpoint_and_immediate_batch_encode_each_summary_once` | 296–342 | 8 | 保真实；见`checkpoint_changes` |
| 17 | `tests/sim2gse/test_checkpoint_changes.py::test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery[same_object]` | 363–395 | 12 | 保真实；见`checkpoint_changes` |
| 18 | `tests/sim2gse/test_checkpoint_changes.py::test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery[reopen]` | 363–395 | 12 | 保真实；见`checkpoint_changes` |
| 19 | `tests/sim2gse/test_combat_log.py::CombatLogToolTests::test_groups_damage_by_spell_id_owner_and_button_origin` | 184–200 | 2 | 保真实；见`combat_log` |
| 20 | `tests/sim2gse/test_combat_log.py::CombatLogToolTests::test_uses_latest_gse_session_and_compares_primary_dps_with_simulation` | 217–291 | 13 | 保真实；见`combat_log` |
| 21 | `tests/sim2gse/test_data_store_connection.py::test_connected_consumer_reads_writes_without_old_user_installation` | 29–55 | 3 | 保真实；见`data_store_connection` |
| 22 | `tests/sim2gse/test_data_store_connection.py::test_unconnected_consumer_fails_before_writing_data` | 59–70 | 3 | 保真实；见`data_store_connection` |
| 23 | `tests/sim2gse/test_data_store_connection.py::test_page_classifies_wrapped_storage_failure_from_the_real_target` | 97–121 | 3 | 保真实；见`data_store_connection` |
| 24 | `tests/sim2gse/test_data_store_connection.py::test_known_batch_groups_and_legacy_single_do_not_fallback_on_missing_keys` | 125–139 | 4 | 保真实；见`data_store_connection` |
| 25 | `tests/sim2gse/test_data_store_connection.py::test_page_classifies_report_locator_permission_error_as_storage_failure[.report-publish.lock]` | 144–172 | 4 | 保真实；见`data_store_connection` |
| 26 | `tests/sim2gse/test_data_store_connection.py::test_page_classifies_report_locator_permission_error_as_storage_failure[.report-locations.jsonl]` | 144–172 | 4 | 保真实；见`data_store_connection` |
| 27 | `tests/sim2gse/test_data_store_connection.py::test_page_reports_storage_startup_failure_before_native_compute[dual-api-version]` | 178–246 | 10 | 保真实；见`data_store_connection` |
| 28 | `tests/sim2gse/test_data_store_connection.py::test_page_reports_storage_startup_failure_before_native_compute[optimize-api-version]` | 178–246 | 10 | 保真实；见`data_store_connection` |
| 29 | `tests/sim2gse/test_data_store_connection.py::test_page_reports_storage_startup_failure_before_native_compute[dual-definition-file]` | 178–246 | 10 | 保真实；见`data_store_connection` |
| 30 | `tests/sim2gse/test_diagnostic_logging.py::test_public_report_write_records_only_opt_in_stage_totals[True]` | 11–27 | 7 | 保真实；见`diagnostic_logging` |
| 31 | `tests/sim2gse/test_dual_engine_identity.py::test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_runtimes` | 95–167 | 15 | 保真实；见`dual_engine_identity` |
| 32 | `tests/sim2gse/test_dual_engine_identity.py::test_dual_rejects_changed_engine_on_first_verification` | 171–193 | 6 | 保真实；见`dual_engine_identity` |
| 33 | `tests/sim2gse/test_engine.py::ImportQueryProfileTests::test_import_probe_action_is_initialized_for_mage_pet_setup` | 280–306 | 3 | 保真实；见`engine` |
| 34 | `tests/sim2gse/test_engine.py::ImportQueryProfileTests::test_import_probe_resolves_name_form_action_outside_executed_subset` | 310–328 | 3 | 保真实；见`engine` |
| 35 | `tests/sim2gse/test_formal_champion.py::test_http_dual_publishes_both_scenes_and_complete_export_collection` | 211–238 | 11 | 保真实；见`formal_champion` |
| 36 | `tests/sim2gse/test_formal_champion.py::test_concurrent_saved_formal_winners_use_real_lock_and_reject_stale_publication` | 263–366 | 15 | 保真实；见`formal_champion` |
| 37 | `tests/sim2gse/test_formal_champion.py::test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return` | 370–409 | 6 | 保真实；见`formal_champion` |
| 38 | `tests/sim2gse/test_formal_champion.py::test_management_imports_known_v1_source_without_reusing_old_score` | 569–634 | 14 | 保真实；见`formal_champion` |
| 39 | `tests/sim2gse/test_formal_champion.py::test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch[partial_first_batch]` | 639–693 | 13 | 保真实；见`formal_champion` |
| 40 | `tests/sim2gse/test_formal_champion_recovery.py::test_public_formal_search_naturally_retests_and_exports_one_champion_per_scene` | 50–76 | 11 | 保真实；见`formal_champion_recovery` |
| 41 | `tests/sim2gse/test_formal_champion_recovery.py::test_public_formal_publication_failure_is_recoverable_without_rescoring_saved_scene` | 80–116 | 10 | 保真实；见`formal_champion_recovery` |
| 42 | `tests/sim2gse/test_formal_champion_recovery.py::test_public_failed_first_score_keeps_reference_readable_without_search_columns` | 120–141 | 5 | 保真实；见`formal_champion_recovery` |
| 43 | `tests/sim2gse/test_formal_champion_recovery.py::test_public_formal_completed_save_failure_resumes_verified_winner_without_rescoring` | 164–200 | 9 | 保真实；见`formal_champion_recovery` |
| 44 | `tests/sim2gse/test_formal_champion_review.py::test_public_saved_result_remains_readable_when_optional_checkpoint_metadata_is_broken` | 13–69 | 14 | 保真实；见`formal_champion_review` |
| 45 | `tests/sim2gse/test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate` | 1108–1212 | 18 | 保真实；见`interface` |
| 46 | `tests/sim2gse/test_interface.py::InterfaceTests::test_completed_task_is_not_visible_before_its_result_is_reliably_saved` | 1067–1105 | 7 | 保真实；见`interface` |
| 47 | `tests/sim2gse/test_interface.py::InterfaceTests::test_dual_freezes_timeline_setting_and_preserves_storage_failure_recovery` | 1303–1354 | 12 | 保真实；见`interface` |
| 48 | `tests/sim2gse/test_interface.py::InterfaceTests::test_lost_report_locations_reject_duplicate_publication` | 819–867 | 11 | 保真实；见`interface` |
| 49 | `tests/sim2gse/test_interface.py::InterfaceTests::test_native_unsupported_specializations_fail_before_export` | 1268–1284 | 2 | 保真实；见`interface` |
| 50 | `tests/sim2gse/test_interface.py::InterfaceTests::test_public_search_reduces_wait_clicks_and_native_evaluates_selected_candidate` | 918–1063 | 29 | 保真实；见`interface` |
| 51 | `tests/sim2gse/test_interface.py::InterfaceTests::test_public_service_simulates_selected_import_and_returns_dps` | 654–678 | 5 | 保真实；见`interface` |
| 52 | `tests/sim2gse/test_interface.py::InterfaceTests::test_published_burst_report_group_is_reused_after_registration_interruption` | 728–811 | 20 | 保真实；见`interface` |
| 53 | `tests/sim2gse/test_interface.py::InterfaceTests::test_simultaneous_identical_tasks_keep_one_logical_report_per_batch` | 815–816 | 0 | 保真实；见`interface` |
| 54 | `tests/sim2gse/test_native_compatibility.py::NativeComparisonTests::test_original_baseline_and_disabled_controller_keep_native_combat` | 76–164 | 33 | 保真实；见`native_compatibility` |
| 55 | `tests/sim2gse/test_native_compatibility.py::NativeCatalogueTests::test_reference_collects_non_dk_cast_and_complete_channel_timing` | 227–261 | 18 | 保真实；见`native_compatibility` |
| 56 | `tests/sim2gse/test_native_compatibility.py::NativeCatalogueTests::test_reference_does_not_count_unexecuted_precombat_cast` | 263–276 | 3 | 保真实；见`native_compatibility` |
| 57 | `tests/sim2gse/test_native_compatibility.py::NativeCatalogueTests::test_reference_reads_audited_player_haste_and_executed_precombat_occupancy` | 204–225 | 7 | 保真实；见`native_compatibility` |
| 58 | `tests/sim2gse/test_native_compatibility.py::NativeCatalogueTests::test_reference_reads_initialized_replacement_forms_without_claiming_availability` | 169–202 | 15 | 保真实；见`native_compatibility` |
| 59 | `tests/sim2gse/test_population_training.py::test_public_run_uses_all_materials_ga_and_publishes_four_five_scene_results` | 161–234 | 24 | 保真实；见`population_training` |
| 60 | `tests/sim2gse/test_population_training.py::test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit[False]` | 314–419 | 18 | 保真实；见`population_training` |
| 61 | `tests/sim2gse/test_population_training.py::test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit[True]` | 314–419 | 18 | 保真实；见`population_training` |
| 62 | `tests/sim2gse/test_population_training.py::test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[foreground-on_to_on]` | 428–522 | 30 | 保真实；见`population_training` |
| 63 | `tests/sim2gse/test_population_training.py::test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[foreground-off_to_on]` | 428–522 | 30 | 保真实；见`population_training` |
| 64 | `tests/sim2gse/test_population_training.py::test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[interrupt-on_to_off]` | 428–522 | 30 | 保真实；见`population_training` |
| 65 | `tests/sim2gse/test_population_training.py::test_public_publication_failure_preserves_old_four_and_resume_repairs_only_missing_report_group[retest]` | 769–831 | 12 | 保真实；见`population_training` |
| 66 | `tests/sim2gse/test_population_training.py::test_public_failed_ga_exports_failed_timeline_and_compares_without_scoring` | 1049–1086 | 6 | 保真实；见`population_training` |
| 67 | `tests/sim2gse/test_program.py::ProgramTests::test_random_loop_repeat_maps_actual_upstream_order_across_seeds` | 124–161 | 7 | 保真实；见`program` |
| 68 | `tests/sim2gse/test_program.py::ProgramTests::test_search_program_keeps_export_and_compiled_order` | 287–303 | 8 | 保真实；见`program` |
| 69 | `tests/sim2gse/test_program.py::ProgramTests::test_upstream_compiles_six_control_blocks_in_one_collection` | 164–262 | 5 | 保真实；见`program` |
| 70 | `tests/sim2gse/test_retired_capabilities.py::test_public_formal_search_without_profession_rule_library_keeps_native_three_part_scope` | 33–58 | 7 | 保真实；见`retired_capabilities` |
| 71 | `tests/sim2gse/test_retired_capabilities.py::test_public_ga_without_profession_rule_library_publishes_native_scope` | 188–211 | 3 | 保真实；见`retired_capabilities` |
| 72 | `tests/sim2gse/test_retired_capabilities.py::test_public_foreground_cancel_stops_both_active_ga_groups_and_keeps_old_publication` | 215–266 | 6 | 保真实；见`retired_capabilities` |
| 73 | `tests/sim2gse/test_retired_capabilities.py::test_public_concurrent_prepare_uses_check_frozen_burst_identity_without_rediscovery` | 270–311 | 5 | 保真实；见`retired_capabilities` |
| 74 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_cold_cache_storage_failure_and_cancellation_do_not_resimulate` | 945–978 | 3 | 保真实；见`search` |
| 75 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_completed_search_removes_native_report_exchange_files` | 1192–1260 | 23 | 保真实；见`search` |
| 76 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_corrupt_parquet_cache_shard_is_recomputed` | 884–942 | 16 | 保真实；见`search` |
| 77 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_native_global_failure_stops_task` | 1263–1278 | 1 | 保真实；见`search` |
| 78 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_owned_process_tree_hard_exit_does_not_stop_other_owner` | 1144–1189 | 4 | 保真实；见`search` |
| 79 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_process_creation_failure_releases_thread_and_temporary_files` | 1305–1331 | 3 | 保真实；见`search` |
| 80 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_public_entry_runs_multi_start_search_with_isolated_validation` | 782–826 | 18 | 保真实；见`search` |
| 81 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_search_resumes_without_resetting_elapsed_time_or_batches` | 830–881 | 14 | 保真实；见`search` |
| 82 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_task_final_publish_failure_still_closes_connection` | 349–377 | 6 | 保真实；见`search` |
| 83 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_task_hard_exit_preserves_checkpoint_and_cleans_owned_engine` | 1010–1141 | 10 | 保真实；见`search` |
| 84 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_task_mutates_unexecuted_apl_button_and_scores_exports_it` | 410–470 | 17 | 保真实；见`search` |
| 85 | `tests/sim2gse/test_search.py::SearchAndValidationTests::test_valid_exchange_report_is_kept_when_center_write_fails` | 981–1007 | 4 | 保真实；见`search` |
| 86 | `tests/sim2gse/test_search_timeline.py::test_timeline_cli_file_lifecycle_preserves_results_and_frozen_resume` | 209–315 | 32 | 保真实；见`search_timeline` |
| 87 | `tests/sim2gse/test_seed_training.py::test_training_entry_rejects_an_active_foreground_search` | 363–377 | 2 | 保真实；见`seed_training` |
| 88 | `tests/sim2gse/test_seed_training.py::test_prepare_reuses_context_and_only_rebuilds_changed_sources` | 437–511 | 26 | 保真实；见`seed_training` |
| 89 | `tests/sim2gse/test_seed_training.py::test_training_prepare_keeps_formal_burst_through_public_cli` | 586–624 | 11 | 保真实；见`seed_training` |
| 90 | `tests/sim2gse/test_seed_training.py::test_training_prepare_keeps_corrupt_history_without_republishing` | 628–693 | 15 | 保真实；见`seed_training` |
| 91 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_failure_holds_member_and_success_wraps` | 399–428 | 6 | 保真实；见`sequence` |
| 92 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_repeated_clicks_do_not_replace_pending_member` | 430–456 | 6 | 保真实；见`sequence` |
| 93 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_reset_does_not_restore_old_queue_as_pending` | 336–366 | 4 | 保真实；见`sequence` |
| 94 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_reset_events_restart_first_member` | 368–397 | 2 | 保真实；见`sequence` |
| 95 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_reset_while_second_member_pending_keeps_old_identity` | 314–334 | 1 | 保真实；见`sequence` |
| 96 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_castsequence_timeout_refreshes_and_waits_for_next_client_update` | 286–311 | 3 | 保真实；见`sequence` |
| 97 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_cooldown_ending_inside_queue_window_executes_from_that_press` | 556–566 | 2 | 保真实；见`sequence` |
| 98 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_expanded_loop_over_128_clicks_runs_with_separate_burst` | 231–251 | 5 | 保真实；见`sequence` |
| 99 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_failed_steps_and_queue_replacement` | 534–554 | 7 | 保真实；见`sequence` |
| 100 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_failed_tentative_winner_promotes_earlier_candidate` | 678–693 | 2 | 保真实；见`sequence` |
| 101 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_failure_feedback_is_not_visible_before_its_event_time` | 654–676 | 5 | 保真实；见`sequence` |
| 102 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_long_search_castsequence_compiles_and_runs_with_member_limits` | 253–284 | 5 | 保真实；见`sequence` |
| 103 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_native_queue_replacement_advances_castsequence_as_issued_member` | 193–229 | 4 | 保真实；见`sequence` |
| 104 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_observed_gcd_transition_commits_previous_pending_action` | 615–633 | 4 | 保真实；见`sequence` |
| 105 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_observed_gcd_transition_rolls_back_when_snapshot_reverts` | 635–652 | 3 | 保真实；见`sequence` |
| 106 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_pending_queue_can_be_replaced_before_commit` | 568–581 | 3 | 保真实；见`sequence` |
| 107 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_phase_reset_and_replay` | 742–767 | 9 | 保真实；见`sequence` |
| 108 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_press_during_cast_queues_the_ready_button_variant` | 695–715 | 5 | 保真实；见`sequence` |
| 109 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_public_entry_simulates_imported_loop_and_empty_clicks` | 458–472 | 3 | 保真实；见`sequence` |
| 110 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_queue_locks_before_gcd_ready_and_executes_at_native_boundary` | 583–602 | 6 | 保真实；见`sequence` |
| 111 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_real_timeline_preserves_first_precombat_gcd` | 523–532 | 2 | 保真实；见`sequence` |
| 112 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_repeated_queue_commits_do_not_accumulate_clock_lead` | 604–613 | 2 | 保真实；见`sequence` |
| 113 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_same_block_item_order` | 717–740 | 6 | 保真实；见`sequence` |
| 114 | `tests/sim2gse/test_sequence.py::SequenceSimulationTests::test_single_evaluation_uses_interval_and_validates_phase` | 506–521 | 7 | 保真实；见`sequence` |
| 115 | `tests/sim2gse/test_simulation_config.py::SimulationConfigTests::test_task_entry_removes_only_valid_omnium_line_when_disabled` | 111–148 | 10 | 保真实；见`simulation_config` |
| 116 | `tests/sim2gse/test_simulation_config.py::SimulationConfigTests::test_task_records_effective_config_and_rejects_changed_resume` | 235–300 | 15 | 保真实；见`simulation_config` |
| 117 | `tests/sim2gse/test_training_champion.py::test_dual_resume_keeps_the_frozen_training_champion_after_new_training_arrives` | 281–325 | 4 | 保真实；见`training_champion` |
| 118 | `tests/sim2gse/test_training_champion.py::test_dual_reads_completed_v1_without_current_profession_rule_library` | 345–362 | 2 | 保真实；见`training_champion` |

*直接断言数量仅便于定位，参数展开重复源码会重复计；并不等于独有契约数。0项的节点可能经现有共享helper断言，例如并发HTTP调用；源码已保留。

## 全局承接与停止条件
1. 规则组合调用真实生产函数/现有memory_ga(formal=True)，不能用“自己实现期望值”的新fake来证明自己；ordinary必须通过官方2.7.1守卫，DuckDB内存不能冒充普通。
2. 全组共享的仅是不可变profile文本、已核验参考与能力描述；用pytest session/module fixture与每消费者deepcopy即可。真实请求、TaskRuntime、SQLite连接、ReportLocations、文件锁、任务目录、报告、写中心及故障注入均逐例隔离。
3. source/engine身份、有效profile、目标/场次、iteration/query不同即不可共用准备。身份篡改、hash计数、首次初始化/真实查询本身是被测行为时明确排除复用。
4. 现成class级prepare、每TaskRuntime身份缓存、session data-store安装、浏览器缩小候选、已有2候选/等分自然停滞均不计为新收益。
5. 非并发目的fixture仅在不改变被断言冻结配置时限制内层max_processes；并发专测保4模板×每组5/shared20、真实2组取消/冻结、HTTP双任务和CAS锁竞争、进程所有权。外层固定4、GSE真实固定8，不追加并发矩阵。
6. 先改最小合法前置和重复规则，不造快照平台、自定义调度器或原生常驻协议。若合法前置要求重写恢复协议，保留原准备并上报。
7. 单项定向仅调试，不能作性能验收；完成整个方案并独审后按最终固定树完整全仓正式60秒验证。性能失败不能删独有断言、放宽阈值、改生产默认或转CI/manual。
8. 批准范围8–16小时量级、总占用≤1.7GB（按root最新实际总账核算）；不复制tools/data；若新框架/削覆盖/超预算或仍无法达标，停止扩张并报告。

## 最终正式规格tree关联

2026-10-25：最终远端`9e73042d36eb2519c8965d58115f7de8f1ef2e58`（父协调给定tree`78ea2ec426fd13e921b1fd397b8b504d59353b80`）相对同树远端700仅9项myspec文档/正式规格变化，无测试源码或配置变化。因此上述118源函数/hash及实际collect库存适用最终提交；这是固定SHA差异证明，不是重新执行测试。细节见`final-tree-preflight.json`。

2026-10-25 18:02 UTC补充：b914acdb/tree48c963 CI修复相对9e没有GSE测试/产品源码变化，118矩阵仍适用；config普通层新增95个实际只读输入，守卫和完整执行范围未变。最终6/8须使用修复后同tree，见`ci-fixed-preflight.json`。

## 当前实施承接

候选从9676c51固定8路继续，完整118库存不变，变更接缝和每个风险如何继续被触发见`coverage-changes.md`；其中明确区分六个类型化内存中心编排实例与保原物理Parquet代表，不能把前者算成后者的通过。旧源码行号/工作秒仅定位参考，不是当前运行结果。
