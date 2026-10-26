# GSE 精简决策清单：原118 → 4真实、2迁移、112删除

用户最新范围主动减少边缘覆盖；**不再要求118全部等价承接**。本表按上一完整真实库存逐项登记，旧节点不藏入其它档位。迁移2项产生3个普通实例，因此当前收集 **418普通 + 4真实 = 422**，另有168普通子测试。四条真实的依赖与可观察结果、删除风险说明见 coverage-changes.md。

## 模块账本

| 原模块 | 保留真实 | 迁普通的原实例 | 删除 |
| --- | ---: | ---: | ---: |
| test_burst.py | 0 | 0 | 9 |
| test_character_export.py | 0 | 0 | 4 |
| test_checkpoint_changes.py | 0 | 0 | 5 |
| test_combat_log.py | 0 | 1 | 1 |
| test_data_store_connection.py | 1 | 0 | 8 |
| test_diagnostic_logging.py | 0 | 1 | 0 |
| test_dual_engine_identity.py | 0 | 0 | 2 |
| test_engine.py | 0 | 0 | 2 |
| test_formal_champion.py | 0 | 0 | 5 |
| test_formal_champion_recovery.py | 0 | 0 | 4 |
| test_formal_champion_review.py | 0 | 0 | 1 |
| test_interface.py | 1 | 0 | 8 |
| test_native_compatibility.py | 1 | 0 | 4 |
| test_population_training.py | 0 | 0 | 8 |
| test_program.py | 0 | 0 | 3 |
| test_retired_capabilities.py | 0 | 0 | 4 |
| test_search.py | 1 | 0 | 11 |
| test_search_timeline.py | 0 | 0 | 1 |
| test_seed_training.py | 0 | 0 | 4 |
| test_sequence.py | 0 | 0 | 24 |
| test_simulation_config.py | 0 | 0 | 2 |
| test_training_champion.py | 0 | 0 | 2 |
| **合计** | **4** | **2** | **112** |

## 保留与迁移

- **保留真实**：`tests/sim2gse/test_data_store_connection.py::test_connected_consumer_reads_writes_without_old_user_installation`
- **保留真实**：`tests/sim2gse/test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate`
- **保留真实**：`tests/sim2gse/test_native_compatibility.py::NativeComparisonTests::test_original_baseline_and_disabled_controller_keep_native_combat`
- **保留真实**：`tests/sim2gse/test_search.py::SearchAndValidationTests::test_owned_process_tree_hard_exit_does_not_stop_other_owner`
- **迁普通**：`tests/sim2gse/test_combat_log.py::CombatLogToolTests::test_uses_latest_gse_session_and_compares_primary_dps_with_simulation`
- **迁普通**：`tests/sim2gse/test_diagnostic_logging.py::test_public_report_write_records_only_opt_in_stage_totals[True]`

诊断原 `[True]` 迁为普通 `[False]` 与 `[True]`；combat 节点保持同名但直接调用内存输入的生产函数。原416普通中额外删除1个无消费者测试辅助自测（test_formal_champion_recovery.py::test_final_export_observer_excludes_candidate_and_other_task_compilations），保留415；加迁移3项为418。该自测原有2次断言，不是2个测试节点。不以重命名掩盖减少。

## 删除的112个原真实实例

### test_burst.py（9）

- `test_public_burst_precheck_requires_a_reviewed_definition`
- `test_public_burst_precheck_roundtrip_and_real_potion`
- `test_public_burst_native_rejects_wrong_spell_id_with_a_real_action`
- `test_dual_source_castsequence_keeps_native_queued_origins`
- `test_dual_sources_share_cooldown_and_reset_between_battles`
- `test_reviewed_burst_training_rejects_unsafe_adaptation_and_preserves_old_training`
- `test_page_dual_scores_character_adapted_seed_without_changing_training[True]`
- `test_dual_keeps_completed_child_and_recovers_without_searching_it_again`
- `test_dual_children_reuse_the_frozen_definition_without_rediscovery`

### test_character_export.py（4）

- `CharacterExportTests::test_native_catalogue_exports_both_active_items`
- `CharacterExportTests::test_native_precombat_buttons_and_item_keep_the_complete_nocombat_prefix`
- `CharacterExportTests::test_public_entry_preserves_real_character_and_bag_candidates`
- `CharacterExportTests::test_public_entry_simulates_native_channel_item`

### test_checkpoint_changes.py（5）

- `test_resume_after_partial_group_commit_uses_unused_group_number`
- `test_report_checkpoint_persists_original_locations_with_one_complete_comparison`
- `test_mixed_checkpoint_and_immediate_batch_encode_each_summary_once`
- `test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery[same_object]`
- `test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery[reopen]`

### test_combat_log.py（1）

- `CombatLogToolTests::test_groups_damage_by_spell_id_owner_and_button_origin`

### test_data_store_connection.py（8）

- `test_unconnected_consumer_fails_before_writing_data`
- `test_page_classifies_wrapped_storage_failure_from_the_real_target`
- `test_known_batch_groups_and_legacy_single_do_not_fallback_on_missing_keys`
- `test_page_classifies_report_locator_permission_error_as_storage_failure[.report-publish.lock]`
- `test_page_classifies_report_locator_permission_error_as_storage_failure[.report-locations.jsonl]`
- `test_page_reports_storage_startup_failure_before_native_compute[dual-api-version]`
- `test_page_reports_storage_startup_failure_before_native_compute[optimize-api-version]`
- `test_page_reports_storage_startup_failure_before_native_compute[dual-definition-file]`

### test_dual_engine_identity.py（2）

- `test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_runtimes[1]`
- `test_dual_rejects_changed_engine_on_first_verification`

### test_engine.py（2）

- `ImportQueryProfileTests::test_import_probe_action_is_initialized_for_mage_pet_setup`
- `ImportQueryProfileTests::test_import_probe_resolves_name_form_action_outside_executed_subset`

### test_formal_champion.py（5）

- `test_http_dual_publishes_both_scenes_and_complete_export_collection[1]`
- `test_concurrent_saved_formal_winners_use_real_lock_and_reject_stale_publication`
- `test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return[1]`
- `test_management_imports_known_v1_source_without_reusing_old_score[2]`
- `test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch[2-partial_first_batch]`

### test_formal_champion_recovery.py（4）

- `test_public_formal_search_naturally_retests_and_exports_one_champion_per_scene[1]`
- `test_public_formal_publication_failure_is_recoverable_without_rescoring_saved_scene[1]`
- `test_public_failed_first_score_keeps_reference_readable_without_search_columns[1]`
- `test_public_formal_completed_save_failure_resumes_verified_winner_without_rescoring[1]`

### test_formal_champion_review.py（1）

- `test_public_saved_result_remains_readable_when_optional_checkpoint_metadata_is_broken[1]`

### test_interface.py（8）

- `InterfaceTests::test_completed_task_is_not_visible_before_its_result_is_reliably_saved`
- `InterfaceTests::test_dual_freezes_timeline_setting_and_preserves_storage_failure_recovery`
- `InterfaceTests::test_lost_report_locations_reject_duplicate_publication`
- `InterfaceTests::test_native_unsupported_specializations_fail_before_export`
- `InterfaceTests::test_public_search_reduces_wait_clicks_and_native_evaluates_selected_candidate`
- `InterfaceTests::test_public_service_simulates_selected_import_and_returns_dps`
- `InterfaceTests::test_published_burst_report_group_is_reused_after_registration_interruption`
- `InterfaceTests::test_simultaneous_identical_tasks_keep_one_logical_report_per_batch`

### test_native_compatibility.py（4）

- `NativeCatalogueTests::test_reference_collects_non_dk_cast_and_complete_channel_timing`
- `NativeCatalogueTests::test_reference_does_not_count_unexecuted_precombat_cast`
- `NativeCatalogueTests::test_reference_reads_audited_player_haste_and_executed_precombat_occupancy`
- `NativeCatalogueTests::test_reference_reads_initialized_replacement_forms_without_claiming_availability`

### test_population_training.py（8）

- `test_public_run_uses_all_materials_ga_and_publishes_four_five_scene_results`
- `test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit[False]`
- `test_public_default_prepare_and_run_verify_four_real_template_groups_and_shared_limit[True]`
- `test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[foreground-on_to_on]`
- `test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[foreground-off_to_on]`
- `test_public_cancel_flushes_tail_and_resume_keeps_frozen_config_and_successful_batches[interrupt-on_to_off]`
- `test_public_publication_failure_preserves_old_four_and_resume_repairs_only_missing_report_group[retest]`
- `test_public_failed_ga_exports_failed_timeline_and_compares_without_scoring`

### test_program.py（3）

- `ProgramTests::test_random_loop_repeat_maps_actual_upstream_order_across_seeds`
- `ProgramTests::test_search_program_keeps_export_and_compiled_order`
- `ProgramTests::test_upstream_compiles_six_control_blocks_in_one_collection`

### test_retired_capabilities.py（4）

- `test_public_formal_search_without_profession_rule_library_keeps_native_three_part_scope`
- `test_public_ga_without_profession_rule_library_publishes_native_scope`
- `test_public_foreground_cancel_stops_both_active_ga_groups_and_keeps_old_publication`
- `test_public_concurrent_prepare_uses_check_frozen_burst_identity_without_rediscovery`

### test_search.py（11）

- `SearchAndValidationTests::test_cold_cache_storage_failure_and_cancellation_do_not_resimulate`
- `SearchAndValidationTests::test_completed_search_removes_native_report_exchange_files`
- `SearchAndValidationTests::test_corrupt_parquet_cache_shard_is_recomputed`
- `SearchAndValidationTests::test_native_global_failure_stops_task`
- `SearchAndValidationTests::test_process_creation_failure_releases_thread_and_temporary_files`
- `SearchAndValidationTests::test_public_entry_runs_multi_start_search_with_isolated_validation`
- `SearchAndValidationTests::test_search_resumes_without_resetting_elapsed_time_or_batches`
- `SearchAndValidationTests::test_task_final_publish_failure_still_closes_connection`
- `SearchAndValidationTests::test_task_hard_exit_preserves_checkpoint_and_cleans_owned_engine`
- `SearchAndValidationTests::test_task_mutates_unexecuted_apl_button_and_scores_exports_it`
- `SearchAndValidationTests::test_valid_exchange_report_is_kept_when_center_write_fails`

### test_search_timeline.py（1）

- `test_timeline_cli_file_lifecycle_preserves_results_and_frozen_resume`

### test_seed_training.py（4）

- `test_training_entry_rejects_an_active_foreground_search`
- `test_prepare_reuses_context_and_only_rebuilds_changed_sources`
- `test_training_prepare_keeps_formal_burst_through_public_cli`
- `test_training_prepare_keeps_corrupt_history_without_republishing`

### test_sequence.py（24）

- `SequenceSimulationTests::test_castsequence_failure_holds_member_and_success_wraps`
- `SequenceSimulationTests::test_castsequence_repeated_clicks_do_not_replace_pending_member`
- `SequenceSimulationTests::test_castsequence_reset_does_not_restore_old_queue_as_pending`
- `SequenceSimulationTests::test_castsequence_reset_events_restart_first_member`
- `SequenceSimulationTests::test_castsequence_reset_while_second_member_pending_keeps_old_identity`
- `SequenceSimulationTests::test_castsequence_timeout_refreshes_and_waits_for_next_client_update`
- `SequenceSimulationTests::test_cooldown_ending_inside_queue_window_executes_from_that_press`
- `SequenceSimulationTests::test_expanded_loop_over_128_clicks_runs_with_separate_burst`
- `SequenceSimulationTests::test_failed_steps_and_queue_replacement`
- `SequenceSimulationTests::test_failed_tentative_winner_promotes_earlier_candidate`
- `SequenceSimulationTests::test_failure_feedback_is_not_visible_before_its_event_time`
- `SequenceSimulationTests::test_long_search_castsequence_compiles_and_runs_with_member_limits`
- `SequenceSimulationTests::test_native_queue_replacement_advances_castsequence_as_issued_member`
- `SequenceSimulationTests::test_observed_gcd_transition_commits_previous_pending_action`
- `SequenceSimulationTests::test_observed_gcd_transition_rolls_back_when_snapshot_reverts`
- `SequenceSimulationTests::test_pending_queue_can_be_replaced_before_commit`
- `SequenceSimulationTests::test_phase_reset_and_replay`
- `SequenceSimulationTests::test_press_during_cast_queues_the_ready_button_variant`
- `SequenceSimulationTests::test_public_entry_simulates_imported_loop_and_empty_clicks`
- `SequenceSimulationTests::test_queue_locks_before_gcd_ready_and_executes_at_native_boundary`
- `SequenceSimulationTests::test_real_timeline_preserves_first_precombat_gcd`
- `SequenceSimulationTests::test_repeated_queue_commits_do_not_accumulate_clock_lead`
- `SequenceSimulationTests::test_same_block_item_order`
- `SequenceSimulationTests::test_single_evaluation_uses_interval_and_validates_phase`

### test_simulation_config.py（2）

- `SimulationConfigTests::test_task_entry_removes_only_valid_omnium_line_when_disabled`
- `SimulationConfigTests::test_task_records_effective_config_and_rejects_changed_resume`

### test_training_champion.py（2）

- `test_dual_resume_keeps_the_frozen_training_champion_after_new_training_arrives[2]`
- `test_dual_reads_completed_v1_without_current_profession_rule_library`

## 不作出的保证

本次移除的是持续自动验证，不是产品功能。普通内存层仍覆盖部分规则，但不证明已删物理损坏/锁/CAS/并发/阶段故障/复杂原生语义的所有风险。没有新增夜间套件或隐藏入口。旧代码和必要结果保留在Git历史；该清单不是“覆盖不减”证据。
