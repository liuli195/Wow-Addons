"""构建和运行共用的固定源码身份；不管理产物切换或清理。"""
from pathlib import Path
import hashlib
import json


def content_digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def own_sources(root, lock, mode):
    entries = []
    destinations = set()
    for entry in lock.get('sources', []):
        if mode not in entry['modes']:
            continue
        source = (root / entry['path']).resolve()
        destination = Path(entry['destination'])
        if (not source.is_relative_to((root / 'projects/sim2gse/native').resolve())
                or destination.is_absolute() or '..' in destination.parts
                or destination.parts[:2] != ('engine', 'sim2gse')
                or destination.as_posix() in destinations):
            raise ValueError('自有源码路径或复制目标无效')
        if content_digest(source) != entry['sha256']:
            raise ValueError('自有源码与受检引擎不符')
        destinations.add(destination.as_posix())
        entries.append(entry)
    return entries


def build_identity(lock, mode, compiler):
    patches = [] if mode == 'original' else lock['patches' if mode == 'controlled' else 'baseline_patches']
    return dict(protocol=2, source_line_endings='lf', mode=mode, upstream_commit=lock['upstream_commit'],
                upstream_tree=lock['upstream_tree'], patches=patches,
                sources=[entry for entry in lock.get('sources', []) if mode in entry['modes']],
                build_options=lock['build_options'], compiler_sha256=compiler)


def identity_digest(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_directory(root, identity):
    return root / '.tools/sim2gse/build' / identity['mode'] / identity_digest(identity)
