"""Only explicitly native tests prepare writable runtime directories."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def native_runtime_directory(request):
    if request.node.get_closest_marker('real') is None:
        return
    temporary = request.getfixturevalue('tmp_path') / 'runtime'
    temporary.mkdir()
    monkeypatch = request.getfixturevalue('monkeypatch')
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        monkeypatch.setenv(name, str(temporary))
    node = Path(__file__).resolve().parents[1] / '.local/verify-deps/node/node.exe'
    monkeypatch.setenv('PLAYWRIGHT_NODEJS_PATH', str(node))
