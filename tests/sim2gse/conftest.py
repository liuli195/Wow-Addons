"""Keep test results out of the user's shared simulation data center."""

from pathlib import Path
import os
import runpy
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects' / 'sim2gse'))


def pytest_collection_modifyitems(items):
    """本次 Windows 实测长项优先；稳定排序保留全部收集项及未知项顺序。"""
    slow_prefixes = (
        'tests/sim2gse/test_training_champion.py::test_dual_chooses_all_67_final_results_and_keeps_four_selected_sources',
        'tests/sim2gse/test_formal_champion_recovery.py::test_public_cancelled_winner_can_advance_and_recover_without_invalidating_its_published_source',
        'tests/sim2gse/test_formal_champion.py::test_dual_deduplicates_sources_and_replaces_only_after_trusted_promotion',
        'tests/sim2gse/test_formal_champion.py::test_dual_retains_each_scenes_formal_champion_across_new_tasks',
        'tests/sim2gse/test_formal_champion.py::test_management_import_rechecks_one_known_formal_source_without_history_scanning',
        'tests/sim2gse/test_formal_champion.py::test_dual_saved_results_survive_publication_failure_and_resume_without_scoring',
        'tests/sim2gse/test_formal_champion.py::test_dual_stale_task_cannot_replace_a_newly_published_distinct_champion',
        'tests/sim2gse/test_formal_champion.py::test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch',
        'tests/sim2gse/test_formal_champion.py::test_dual_formal_champion_read_errors_remain_visible_and_do_not_overwrite_the_incumbent',
        'tests/sim2gse/test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate',
        'tests/sim2gse/test_burst.py::test_restarted_page_recovers_parent_after_real_process_exit',
        'tests/sim2gse/test_burst.py::test_public_task_runs_loop_and_burst_on_one_native_player',
        'tests/sim2gse/test_burst.py::test_page_runs_both_scenes_and_exports_three_independent_sequences',
    )
    items.sort(key=lambda item: not item.nodeid.startswith(slow_prefixes))


@pytest.fixture(scope="session")
def installed_data_store(tmp_path_factory):
    """The test runner provides a real installed package, never a user home link."""
    source = os.environ.get("DATA_STORE_TEST_SKILL")
    if not source:
        pytest.fail("请按 tests/README.md 提供独立 DATA_STORE_TEST_SKILL 测试安装副本")
    source = Path(source)
    if not (source / "scripts/project_binding.py").is_file():
        pytest.fail("测试安装副本缺少数据中心接入脚本")
    installed = tmp_path_factory.mktemp("data-store-install") / "skill"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    return installed


@pytest.fixture(scope="session")
def installed_data_store_api(installed_data_store):
    return runpy.run_path(str(installed_data_store / "scripts/data_store.py"))


@pytest.fixture(autouse=True)
def isolated_result_center(tmp_path, monkeypatch, installed_data_store_api, installed_data_store):
    import result_store
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'data')
    # Business tests use the real package copy; connection tests launch clean processes.
    monkeypatch.setattr(result_store, '_SKILL_API', installed_data_store_api)
    monkeypatch.setenv('DATA_STORE_TEST_SKILL', str(installed_data_store))
