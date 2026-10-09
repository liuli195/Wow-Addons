"""按项目兼容锁准备并构建独立引擎；不会改写研究或配装器缓存。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile
import shutil

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'projects/sim2gse'))
from native_build import own_sources, build_identity, identity_digest, source_directory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def verify_upstream(upstream, lock):
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=upstream, check=True,
                            capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=upstream, check=True,
                          capture_output=True, text=True).stdout.strip()
    if commit != lock['upstream_commit'] or tree != lock['upstream_tree']:
        raise ValueError('固定上游提交身份不符')
    return commit


def main():
    lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
    if lock.get('build_protocol') != 2:
        raise ValueError('不支持的引擎构建协议')
    upstream = ROOT / '.tools/sim2gse-upstream/simc'
    commit = verify_upstream(upstream, lock)
    archive = ROOT / '.local/sim2gse/build/upstream.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', '-c', 'core.autocrlf=false', 'archive', '--format=zip', '--prefix=simc/', f'--output={archive}', commit],
                   cwd=upstream, check=True)
    env = os.environ.copy()
    msys2 = Path(env.get('MSYS2_LOCATION', 'C:/msys64'))
    toolchain = msys2 / 'mingw64/bin'
    env['PATH'] = str(toolchain) + os.pathsep + env['PATH']
    env['GIT_CEILING_DIRECTORIES'] = str(ROOT / '.tools/sim2gse')
    tool = toolchain / 'mingw32-make.exe'
    compiler = digest(toolchain / 'g++.exe')
    for mode in ('original', 'baseline', 'controlled'):
        sources = own_sources(ROOT, lock, mode)
        identity = build_identity(lock, mode, compiler)
        source = source_directory(ROOT, identity)
        output = ROOT / '.local/sim2gse/build' / mode
        output.mkdir(parents=True, exist_ok=True)
        patches = identity['patches']
        marker = source / 'source-identity.json'
        if not marker.exists():
            if source.exists() and any(source.iterdir()):
                raise ValueError(f'拒绝覆盖未知源码目录: {source}')
            source.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zipped:
                for entry in zipped.infolist():
                    relative = Path(*Path(entry.filename).parts[1:])
                    target = source / relative
                    if not target.resolve().is_relative_to(source.resolve()):
                        raise ValueError('源归档包含越界路径')
                    if not relative.parts or entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zipped.read(entry))
            for patch in patches:
                path = ROOT / patch['path']
                if patch_digest(path) != patch['sha256']:
                    raise ValueError('补丁散列与兼容锁不符')
                patch_bytes = path.read_bytes().replace(b'\r\n', b'\n')
                subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', '-'], input=patch_bytes, cwd=source, check=True, env=env)
                subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '-'], input=patch_bytes, cwd=source, check=True, env=env)
            for entry in sources:
                target = source / entry['destination']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / entry['path']).read_bytes().replace(b'\r\n', b'\n'))
            marker.write_text(json.dumps(identity, indent=2), encoding='utf-8')
        if json.loads(marker.read_text()) != identity:
            raise ValueError(f'源码身份已变化，需要新的独立构建目录: {source}')
        with zipfile.ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                relative = Path(*Path(entry.filename).parts[1:])
                if entry.is_dir() or not relative.parts:
                    continue
                key = relative.as_posix()
                patched = (lock.get('baseline_patched_files', {}) if mode == 'baseline' else
                           lock.get('patched_files', {}) if mode == 'controlled' else {})
                expected = patched.get(key)
                expected = expected or hashlib.sha256(zipped.read(entry)).hexdigest()
                if digest(source / relative) != expected:
                    raise ValueError(f'源码与固定归档/补丁不符: {key}')
        for entry in sources:
            if patch_digest(source / entry['destination']) != entry['sha256']:
                raise ValueError('复制的自有源码与兼容锁不符')
        command = [str(tool), '-j4', *lock['build_options']]
        with (output / 'build.log').open('w') as log:
            result = subprocess.run(command, cwd=source / 'engine', env=env, stdout=log, stderr=subprocess.STDOUT)
        manifest = dict(identity, exit_code=result.returncode, command=command,
                        identity_sha256=identity_digest(identity),
                        executable=(output / 'simc.exe').relative_to(ROOT).as_posix())
        if not result.returncode:
            manifest['binary_sha256'] = digest(source / 'engine/simc.exe')
            shutil.copy2(source / 'engine/simc.exe', output / 'simc.pending.exe')
            (output / 'simc.pending.exe').replace(output / 'simc.exe')
        (output / 'build.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(f'{mode}: exit={result.returncode}', flush=True)
        if result.returncode:
            print((output / 'build.log').read_text()[-5000:])
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
