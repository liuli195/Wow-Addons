"""引擎身份和页面错误映射的内存规则检查。"""
import hashlib
import io
import json
from pathlib import Path

import pytest

from engine import identity as REAL_IDENTITY


@pytest.mark.parametrize('mode', ['baseline', 'controlled'])
def test_identity_checks_complete_binary_with_bounded_reads_and_closes_it(monkeypatch, mode):
    import engine
    from native_build import build_identity, identity_digest

    root = Path('/memory-bounded-engine')
    lock = dict(build_protocol=2, upstream_commit='a' * 40, upstream_tree='b' * 40,
                build_options=[], baseline_patches=[], patches=[], sources=[])
    executable = root / '.local/sim2gse/build' / mode / 'simc.exe'
    contents = b'engine-prefix-' * 250000 + b'last-byte'
    build = build_identity(lock, mode, 'c' * 64)
    manifest = dict(build, identity_sha256=identity_digest(build), exit_code=0,
                    executable=executable.relative_to(root).as_posix(), command=['make', '-j4'],
                    binary_sha256=hashlib.sha256(contents).hexdigest())
    documents = {root / 'projects/sim2gse/compatibility/lock.json': json.dumps(lock),
                 executable.parent / 'build.json': json.dumps(manifest)}
    opened = []
    binaries = {executable: contents}
    faults = set()

    class Binary(io.RawIOBase):
        def __init__(self, data):
            self.data, self.position = data, 0
        def readable(self):
            return True
        def readinto(self, buffer):
            if executable in faults:
                raise OSError('constructed binary read failure')
            assert len(buffer) <= 1024 * 1024, 'binary verification must not allocate a whole-file buffer'
            count = min(len(buffer), len(self.data) - self.position)
            buffer[:count] = memoryview(self.data)[self.position:self.position + count]
            self.position += count
            return count

    real_text, real_bytes, real_open = Path.read_text, Path.read_bytes, Path.open
    monkeypatch.setattr(engine, 'ROOT', root)
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw:
                        documents[path] if path in documents else real_text(path, *a, **kw))
    def read_bytes(path):
        if path == executable:
            raise AssertionError('whole binary read is forbidden')
        return real_bytes(path)
    def open_binary(path, *a, **kw):
        if path != executable:
            return real_open(path, *a, **kw)
        assert a == ('rb',) and not kw
        source = Binary(binaries[path])
        opened.append(source)
        return source
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    monkeypatch.setattr(Path, 'open', open_binary)
    assert REAL_IDENTITY(mode) == (executable, manifest)
    assert opened[-1].closed and opened[-1].position == len(contents)
    from runtime import TaskRuntime
    runtime = TaskRuntime(float('inf'))
    assert REAL_IDENTITY(mode, runtime) == (executable, manifest)
    previous = list(opened)
    assert REAL_IDENTITY(mode, runtime) == (executable, manifest)
    assert opened == previous  # 同一已核验运行范围仍复用原有缓存。
    binaries[executable] = contents[:-1] + b'!'
    with pytest.raises(ValueError, match='独立引擎身份或构建状态不符'):
        REAL_IDENTITY(mode)
    assert opened[-1].closed and opened[-1].position == len(contents)
    faults.add(executable)
    with pytest.raises(OSError, match='constructed binary read failure'):
        REAL_IDENTITY(mode)
    assert opened[-1].closed
    manifest['exit_code'] = 1
    documents[executable.parent / 'build.json'] = json.dumps(manifest)
    with pytest.raises(ValueError, match='独立引擎身份或构建状态不符'):
        REAL_IDENTITY(mode)


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
    monkeypatch.setattr(Path, 'open', lambda path, mode: io.BytesIO(binaries[path]))
    assert REAL_IDENTITY('baseline') == (executable, manifest)
    binaries[executable] = contents + b'changed'
    with pytest.raises(ValueError, match='独立引擎身份或构建状态不符') as error:
        REAL_IDENTITY('baseline')
    assert interface._friendly_error(error.value) == '引擎计算失败，请检查本机模拟环境后重试。'
