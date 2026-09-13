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
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def patch_bytes(path):
    return path.read_bytes().replace(b'\r\n', b'\n')

def patch_digest(path):
    return hashlib.sha256(patch_bytes(path)).hexdigest()

def apply_patch(source, path, env=None, reverse=False):
    command = ['git', 'apply']
    if reverse:
        command.append('--reverse')
    content = patch_bytes(path)
    subprocess.run([*command, '--check', '-'], input=content, cwd=source, env=env, check=True)
    subprocess.run([*command, '-'], input=content, cwd=source, env=env, check=True)

def verify_source(source, files):
    current = {path.as_posix(): digest(source / path) for path in files}
    manifest = source / 'prototype-source-files.json'
    if manifest.exists():
        assert json.loads(manifest.read_text()) == current, 'prototype source changed'
    else:
        manifest.write_text(json.dumps(current, sort_keys=True))

def main():
    mode = sys.argv[1]
    assert mode in ('baseline', 'controlled')
    lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
    upstream = ROOT / '.tools/sim2gse-upstream/simc'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=upstream, text=True).strip()
    assert commit == lock['upstream_commit'] and tree == lock['upstream_tree'], 'upstream source changed'
    archive = OUT / 'upstream.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'archive', '--format=zip', '--prefix=simc/', f'--output={archive}', commit],
                   cwd=upstream, check=True)
    with zipfile.ZipFile(archive) as zipped:
        files = [Path(*Path(entry.filename).parts[1:]) for entry in zipped.infolist()
                 if not entry.is_dir() and len(Path(entry.filename).parts) > 1]
    source = TOOLS / mode
    source.mkdir(parents=True, exist_ok=True)
    marker = source / 'prototype-source.json'
    identity = {'commit': commit, 'tree': tree}
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
    toolchain = Path(env.get('MSYS2_LOCATION', 'C:/msys64')) / 'mingw64/bin'
    env['PATH'] = str(toolchain) + os.pathsep + env['PATH']
    # Archive provenance is explicit; never report the enclosing WoW repo's HEAD.
    env['GIT_CEILING_DIRECTORIES'] = str(TOOLS)
    patch = ROOT / 'scripts/dev/sim2gse/prototype-controller.patch'
    patch_hash = None
    if mode == 'controlled':
        patch_hash = patch_digest(patch)
        applied = source / 'prototype-patch.sha256'
        saved_patch = source / 'prototype-applied.patch'
        if applied.exists() and applied.read_text() != patch_hash:
            assert saved_patch.exists() and patch_digest(saved_patch) == applied.read_text()
            apply_patch(source, saved_patch, env, reverse=True)
            applied.unlink()
        if not applied.exists():
            current_bytes = patch_bytes(patch)
            apply_patch(source, patch, env)
            applied.write_text(patch_hash)
            saved_patch.write_bytes(current_bytes)
        assert applied.read_text() == patch_hash, 'use a fresh source for changed patch'
    verify_source(source, files)
    run_dir = OUT / mode
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [str(toolchain / 'mingw32-make.exe'), '-j4', 'all', 'PATHSEP=/', 'SC_NO_NETWORKING=1',
               'CXX=g++', 'GIT=', 'MODULE=simc.exe']
    started = time.perf_counter()
    with (run_dir / 'build.log').open('w') as log:
        result = subprocess.run(command, cwd=source / 'engine', env=env, stdout=log, stderr=subprocess.STDOUT)
    evidence = dict(identity, mode=mode, command=command, patch_sha256=patch_hash,
                    source=str(source), exit_code=result.returncode,
                    elapsed_seconds=time.perf_counter() - started,
                    compiler=subprocess.check_output([str(toolchain / 'g++.exe'), '--version'], env=env, text=True))
    if result.returncode == 0:
        evidence['binary_sha256'] = digest(source / 'engine/simc.exe')
    (run_dir / 'build.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
