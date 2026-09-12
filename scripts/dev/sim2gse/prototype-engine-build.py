"""Task-8 isolated upstream Make build; no installation or gear-planner writes."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '.local/sim2gse/execution-prototype'
TOOLS = ROOT / '.tools/sim2gse/execution-prototype'
COMMIT = 'b845947a34429874433d8e9362326894650dd20a'
ARCHIVE_HASH = '412fe6f536e181ef73fd4fcf6d27dbcd2e17d873511c545a1cea1138c44e8110'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    mode = sys.argv[1]
    assert mode in ('baseline', 'controlled')
    archive = ROOT / '.local/gear-planner-dk-validation/b845947-source.zip'
    assert digest(archive) == ARCHIVE_HASH, 'upstream archive changed'
    source = TOOLS / mode
    source.mkdir(parents=True, exist_ok=True)
    marker = source / 'prototype-source.json'
    identity = {'commit': COMMIT, 'archive_sha256': ARCHIVE_HASH}
    if not marker.exists():
        assert not list(source.iterdir()), 'refusing to overwrite unknown source'
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                relative = Path(*Path(entry.filename).parts[1:])
                target = source / relative
                assert target.resolve().is_relative_to(source.resolve())
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif relative.parts:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(entry))
        marker.write_text(json.dumps(identity))
    assert json.loads(marker.read_text()) == identity
    env = os.environ.copy()
    env['PATH'] = 'C:/msys64/mingw64/bin' + os.pathsep + env['PATH']
    # Archive provenance is explicit; never report the enclosing WoW repo's HEAD.
    env['GIT_CEILING_DIRECTORIES'] = str(TOOLS)
    patch = ROOT / 'scripts/dev/sim2gse/prototype-controller.patch'
    patch_hash = None
    if mode == 'controlled':
        patch_hash = digest(patch)
        applied = source / 'prototype-patch.sha256'
        saved_patch = source / 'prototype-applied.patch'
        if applied.exists() and applied.read_text() != patch_hash:
            assert saved_patch.exists() and digest(saved_patch) == applied.read_text()
            subprocess.run(['git', 'apply', '--reverse', '--check', str(saved_patch)], cwd=source, env=env, check=True)
            subprocess.run(['git', 'apply', '--reverse', str(saved_patch)], cwd=source, env=env, check=True)
            applied.unlink()
        if not applied.exists():
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, env=env, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=source, env=env, check=True)
            applied.write_text(patch_hash)
            saved_patch.write_bytes(patch.read_bytes())
        assert applied.read_text() == patch_hash, 'use a fresh source for changed patch'
    run_dir = OUT / mode
    run_dir.mkdir(parents=True, exist_ok=True)
    command = ['C:/msys64/mingw64/bin/mingw32-make.exe', '-j4', 'all', 'PATHSEP=/', 'SC_NO_NETWORKING=1',
               'CXX=g++', 'GIT=', 'MODULE=simc.exe']
    started = time.perf_counter()
    with (run_dir / 'build.log').open('w') as log:
        result = subprocess.run(command, cwd=source / 'engine', env=env, stdout=log, stderr=subprocess.STDOUT)
    evidence = dict(identity, mode=mode, command=command, patch_sha256=patch_hash,
                    source=str(source), exit_code=result.returncode,
                    elapsed_seconds=time.perf_counter() - started,
                    compiler=subprocess.check_output(['C:/msys64/mingw64/bin/g++.exe', '--version'], env=env, text=True))
    if result.returncode == 0:
        evidence['binary_sha256'] = digest(source / 'engine/simc.exe')
    (run_dir / 'build.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
