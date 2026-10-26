"""引擎身份和页面错误映射的内存规则检查。"""
import hashlib
import json
from pathlib import Path

import pytest

from engine import identity as REAL_IDENTITY


def test_changed_engine_bytes_fail_identity_and_map_to_page_error(monkeypatch):
    import engine
    import interface
    from native_build import build_identity, identity_digest

    root = Path('/memory-engine')
    lock = dict(build_protocol=2, upstream_commit='a' * 40, upstream_tree='b' * 40,
                build_options=[], baseline_patches=[], patches=[], sources=[])
    executable = root / '.local/sim2gse/build/baseline/simc.exe'
    contents = b'verified test engine: baseline'
    identity = build_identity(lock, 'baseline', 'c' * 64)
    manifest = dict(identity, identity_sha256=identity_digest(identity), exit_code=0,
                    executable=executable.relative_to(root).as_posix(), command=['make', '-j4'],
                    binary_sha256=hashlib.sha256(contents).hexdigest())
    documents = {
        root / 'projects/sim2gse/compatibility/lock.json': json.dumps(lock),
        executable.parent / 'build.json': json.dumps(manifest),
    }
    binaries = {executable: contents}
    monkeypatch.setattr(engine, 'ROOT', root)
    monkeypatch.setattr(Path, 'read_text', lambda path: documents[path])
    monkeypatch.setattr(Path, 'read_bytes', lambda path: binaries[path])
    assert REAL_IDENTITY('baseline') == (executable, manifest)
    binaries[executable] = contents + b'changed'
    with pytest.raises(ValueError, match='独立引擎身份或构建状态不符') as error:
        REAL_IDENTITY('baseline')
    assert interface._friendly_error(error.value) == '引擎计算失败，请检查本机模拟环境后重试。'
