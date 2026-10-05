"""Keep test results out of the user's shared simulation data center."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects' / 'sim2gse'))


@pytest.fixture(autouse=True)
def isolated_result_center(tmp_path, monkeypatch):
    import result_store
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'data')
