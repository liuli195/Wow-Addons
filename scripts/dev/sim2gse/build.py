"""按项目兼容锁准备并构建独立引擎；不会改写研究或配装器缓存。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
    archive = ROOT / '.local/gear-planner-dk-validation/b845947-source.zip'
    if digest(archive) != lock['archive_sha256']:
        raise ValueError('固定源归档身份不符')
    env = os.environ.copy()
    env['PATH'] = 'C:/msys64/mingw64/bin' + os.pathsep + env['PATH']
    env['GIT_CEILING_DIRECTORIES'] = str(ROOT / '.tools/sim2gse')
    tool = Path('C:/msys64/mingw64/bin/mingw32-make.exe')
    for mode in ('baseline', 'controlled'):
        source = ROOT / '.tools/sim2gse/product' / mode
        output = ROOT / '.local/sim2gse/build' / mode
        output.mkdir(parents=True, exist_ok=True)
        patches = lock['patches'] if mode == 'controlled' else lock['baseline_patches']
        identity = dict(upstream_commit=lock['upstream_commit'], archive_sha256=lock['archive_sha256'], patches=patches,
                        build_options=lock['build_options'])
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
                if digest(path) != patch['sha256']:
                    raise ValueError('补丁散列与兼容锁不符')
                patch_bytes = path.read_bytes().replace(b'\r\n', b'\n')
                subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', '-'], input=patch_bytes, cwd=source, check=True, env=env)
                subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '-'], input=patch_bytes, cwd=source, check=True, env=env)
            marker.write_text(json.dumps(identity, indent=2), encoding='utf-8')
        if json.loads(marker.read_text()) != identity:
            raise ValueError(f'源码身份已变化，需要新的独立构建目录: {source}')
        with zipfile.ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                relative = Path(*Path(entry.filename).parts[1:])
                if entry.is_dir() or not relative.parts:
                    continue
                key = relative.as_posix()
                expected = lock.get('patched_files' if mode == 'controlled' else 'baseline_patched_files', {}).get(key)
                expected = expected or hashlib.sha256(zipped.read(entry)).hexdigest()
                if digest(source / relative) != expected:
                    raise ValueError(f'源码与固定归档/补丁不符: {key}')
        command = [str(tool), '-j4', *lock['build_options']]
        with (output / 'build.log').open('w') as log:
            result = subprocess.run(command, cwd=source / 'engine', env=env, stdout=log, stderr=subprocess.STDOUT)
        manifest = dict(identity, exit_code=result.returncode, command=command,
                        compiler_sha256=digest(Path('C:/msys64/mingw64/bin/g++.exe')))
        if not result.returncode:
            manifest['binary_sha256'] = digest(source / 'engine/simc.exe')
        (output / 'build.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(f'{mode}: exit={result.returncode}', flush=True)
        if result.returncode:
            print((output / 'build.log').read_text()[-5000:])
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
