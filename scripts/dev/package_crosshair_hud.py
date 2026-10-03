"""准星HUD正式打包、检查和备份部署；不接触WTF个人设置。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ('Logic.lua', 'NativeBlood.lua', 'Elements.lua', 'Config.lua',
           'Visibility.lua', 'Core.lua', 'Diagnostics.lua')
SCOPES = ('MYUI_CrosshairHUD', 'MYUI/Media/CrosshairHUD',
          'MYUI/MYUI.toc', 'MYUI/Series.lua', 'MYUI_CrosshairHUDEdgeTest')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_files(root):
    manifest = json.loads((root / 'assets/CrosshairHUDMedia/manifest.json').read_text(encoding='utf-8'))
    media = [Path(a['file']).with_suffix('.blp').name for a in manifest['assets']]
    media += ['mask_half.blp', 'death_strike_marker.blp', 'coagulated_blood_fill.blp']
    return sorted([f'MYUI_CrosshairHUD/{n}' for n in (*RUNTIME, 'MYUI_CrosshairHUD.toc')]
                  + ['MYUI/MYUI.toc', 'MYUI/Series.lua']
                  + [f'MYUI/Media/CrosshairHUD/{n}' for n in media])


def toc_files(path):
    return [line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def validate(package):
    package = Path(package)
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['files']
    expected = expected_files(ROOT)
    if sorted(e['path'] for e in entries) != expected:
        raise ValueError('安装清单与正式文件白名单不一致')
    actual = sorted(p.relative_to(package / 'AddOns').as_posix()
                    for p in (package / 'AddOns').rglob('*') if p.is_file())
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
           for p in (package / 'AddOns').rglob('*')):
        raise ValueError('安装包不能包含链接目录或文件')
    if actual != expected:
        raise ValueError('安装包存在缺失或多余文件')
    for entry in entries:
        path = package / 'AddOns' / entry['path']
        if path.is_symlink() or digest(path) != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError(f"安装包文件校验失败：{entry['path']}")
    if toc_files(package / 'AddOns/MYUI_CrosshairHUD/MYUI_CrosshairHUD.toc') != list(RUNTIME):
        raise ValueError('准星HUD加载清单含有非正式入口')
    if toc_files(package / 'AddOns/MYUI/MYUI.toc') != ['Series.lua']:
        raise ValueError('公共核心加载清单与预期不一致')
    return manifest


def build(root=ROOT, output=None):
    root = Path(root).resolve()
    output = Path(output or root / '.local/dist/crosshair-hud').resolve()
    if output.is_relative_to(root / 'addons') or output.is_relative_to(root / 'assets'):
        raise ValueError('安装包输出不能覆盖源码或原图')
    sys.path.insert(0, str(root / 'scripts/media'))
    from PIL import Image
    from white_blp import verify_white_blp
    names = expected_files(root)
    source_hash = hashlib.sha256()
    for name in names:
        path = root / 'addons' / name
        source_hash.update(name.encode() + b'\0' + path.read_bytes())
        if path.suffix == '.blp':
            with Image.open(path.with_suffix('.png')) as image:
                verify_white_blp(path, image)
    build_id = source_hash.hexdigest()[:16]
    output.mkdir(parents=True, exist_ok=True)
    destination = output / build_id
    if destination.exists():
        validate(destination)
        return destination
    with tempfile.TemporaryDirectory(prefix='hud-package-', dir=output) as directory:
        stage = Path(directory)
        for name in names:
            target = stage / 'AddOns' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / 'addons' / name, target)
        toc = stage / 'AddOns/MYUI_CrosshairHUD/MYUI_CrosshairHUD.toc'
        toc.write_text(f'## X-MYUI-Build: {build_id}\n' + toc.read_text(encoding='utf-8-sig'), encoding='utf-8')
        manifest = {'formatVersion': 1, 'build': build_id, 'files': [
            {'path': n, 'bytes': (stage / 'AddOns' / n).stat().st_size,
             'sha256': digest(stage / 'AddOns' / n)} for n in names]}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        validate(stage)
        # 压缩包只含可直接放入AddOns的运行文件，校验清单留在包外。
        with zipfile.ZipFile(stage / 'MYUI_CrosshairHUD.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(stage / 'AddOns' / name, name)
        shutil.copytree(stage, destination)
    return destination


def safe_scopes(addons):
    raw = Path(addons).absolute()
    if raw.name.lower() != 'addons' or raw.parent.name.lower() != 'interface':
        raise ValueError('部署目标必须明确指向游戏Interface/AddOns目录')
    if raw.is_symlink() or (hasattr(raw, 'is_junction') and raw.is_junction()):
        raise ValueError('游戏插件目录不能是链接目录')
    root = raw.resolve()
    targets = []
    for name in SCOPES:
        path = root / name
        # 拒绝目录联接或符号链接，避免清理跑到授权范围外。
        for node in (path, *path.parents):
            if node.is_symlink() or (hasattr(node, 'is_junction') and node.is_junction()):
                raise ValueError(f'部署范围含有链接目录：{node}')
            if node == root:
                break
        if not path.resolve().is_relative_to(root):
            raise ValueError('部署目标超出游戏插件目录')
        targets.append(path)
    return root, targets


def deploy(package, addons, backups):
    package = Path(package).resolve()
    manifest = validate(package)
    root, targets = safe_scopes(addons)
    backups = Path(backups).resolve()
    if backups.is_relative_to(root.parent.parent):
        raise ValueError('备份必须保存在游戏目录外')
    backup = backups / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:6])
    backup.mkdir(parents=True)
    records = []
    # 全部备份并逐文件核对完成后，才允许改动游戏文件。
    for name, path in zip(SCOPES, targets):
        if not path.exists():
            continue
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            # 子目录中的链接也不得跟随。
            if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in path.rglob('*')):
                raise ValueError('备份范围内部含有链接')
            shutil.copytree(path, target)
            files = [p for p in path.rglob('*') if p.is_file()]
        else:
            shutil.copyfile(path, target)
            files = [path]
        for file in files:
            name_in_backup = file.relative_to(root).as_posix()
            checksum = digest(file)
            if digest(backup / name_in_backup) != checksum:
                raise ValueError('备份核对失败，尚未部署')
            records.append({'path': name_in_backup, 'sha256': checksum})
    (backup / 'backup-manifest.json').write_text(json.dumps(
        {'installedBuild': manifest['build'], 'scopes': list(SCOPES), 'files': records},
        ensure_ascii=False, indent=2), encoding='utf-8')
    # targets已经逐个解析并限定在准确的授权目录内。
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    for entry in manifest['files']:
        target = root / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package / 'AddOns' / entry['path'], target)
        if digest(target) != entry['sha256']:
            raise ValueError(f"部署校验失败；可从备份恢复：{backup}")
    for name in ('MYUI_CrosshairHUD', 'MYUI/Media/CrosshairHUD'):
        actual = sorted(p.relative_to(root).as_posix() for p in (root / name).rglob('*') if p.is_file())
        expected = sorted(e['path'] for e in manifest['files'] if e['path'].startswith(name + '/'))
        if actual != expected:
            raise ValueError('部署后存在多余或缺失文件')
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/dist/crosshair-hud')
    parser.add_argument('--deploy', type=Path, metavar='GAME_ADDONS')
    parser.add_argument('--backups', type=Path, default=ROOT / '.local/game-deploy-backups')
    args = parser.parse_args()
    package = build(ROOT, args.output)
    print(f'已校验正式包：{package}')
    if args.deploy:
        backup = deploy(package, args.deploy, args.backups)
        print(f'部署完成；已核对备份：{backup}')


if __name__ == '__main__':
    main()
