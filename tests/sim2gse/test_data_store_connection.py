"""Real consumer entry in an isolated connected project, without a user link."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[2]


def test_connected_consumer_reads_writes_without_old_user_installation(tmp_path):
    source = Path(os.environ.get("DATA_STORE_TEST_SKILL",
                                str(REPOSITORY / ".local/skills/data-store")))
    assert (source / "scripts/project_binding.py").is_file(), "请先接入项目或提供测试安装副本"
    installed = tmp_path / "installed"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    project = tmp_path / "project"
    adapter = project / "projects/sim2gse/result_store.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "projects/sim2gse/result_store.py", adapter)
    connected = subprocess.run(
        [sys.executable, str(installed / "scripts/project_binding.py"), "connect", "--project", str(project)],
        text=True, capture_output=True,
    )
    assert connected.returncode == 0, connected.stderr
    env = dict(os.environ, USERPROFILE=str(tmp_path / "empty-home"), HOME=str(tmp_path / "empty-home"))
    program = """import json,runpy,sys
m=runpy.run_path(sys.argv[1]);m['ensure_available']()
assert m['write']('measurements','one',[{'score':7,'parts':[{'value':4}]}])==1
print(json.dumps(list(m['iter_rows']('SELECT score,parts[1].value AS part FROM measurements'))))
"""
    result = subprocess.run([sys.executable, "-c", program, str(adapter)], env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{"score": 7, "part": 4}]


def test_unconnected_consumer_fails_before_writing_data(tmp_path):
    adapter = tmp_path / "projects/sim2gse/result_store.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "projects/sim2gse/result_store.py", adapter)
    env = dict(os.environ, USERPROFILE=str(tmp_path / "empty-home"), HOME=str(tmp_path / "empty-home"))
    result = subprocess.run(
        [sys.executable, "-c", "import runpy,sys;m=runpy.run_path(sys.argv[1]);m['ensure_available']()", str(adapter)],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "接入" in result.stderr
    assert not (tmp_path / "data").exists()
