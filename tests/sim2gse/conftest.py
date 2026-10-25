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
    source = Path(__file__).resolve().parents[2] / '.local/verify-deps/data-store'
    supplied = os.environ.get('DATA_STORE_TEST_SKILL')
    if supplied and Path(supplied).resolve() != source.resolve():
        pytest.fail('DATA_STORE_TEST_SKILL 必须指向已登记的 .local/verify-deps/data-store')
    if not (source / "scripts/project_binding.py").is_file():
        pytest.fail("测试安装副本缺少数据中心接入脚本")
    installed = tmp_path_factory.mktemp("data-store-install") / "skill"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    return installed


@pytest.fixture(scope="session")
def installed_data_store_api(installed_data_store):
    return runpy.run_path(str(installed_data_store / "scripts/data_store.py"))


@pytest.fixture(autouse=True)
def isolated_result_center(request):
    if request.node.get_closest_marker('real') is None:
        return
    tmp_path = request.getfixturevalue('tmp_path')
    monkeypatch = request.getfixturevalue('monkeypatch')
    installed_data_store_api = request.getfixturevalue('installed_data_store_api')
    installed_data_store = request.getfixturevalue('installed_data_store')
    import result_store
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'data')
    # Business tests use the real package copy; connection tests launch clean processes.
    monkeypatch.setattr(result_store, '_SKILL_API', installed_data_store_api)
    monkeypatch.setenv('DATA_STORE_TEST_SKILL', str(installed_data_store))
