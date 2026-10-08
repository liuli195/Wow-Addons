"""Keep test results out of the user's shared simulation data center."""

from pathlib import Path
import os
import runpy
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects' / 'sim2gse'))


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
    # A freshly connected test center has an existing empty root for activity markers.
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    # Business tests use the real package copy; connection tests launch clean processes.
    monkeypatch.setattr(result_store, '_SKILL_API', installed_data_store_api)
    monkeypatch.setenv('DATA_STORE_TEST_SKILL', str(installed_data_store))
