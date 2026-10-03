"""通过现有素材构建入口检查游戏成品，独立读取文件保存的透明度。"""
from pathlib import Path
import json
import struct
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/media'))
from build_crosshair_media import build


def read_levels(path):
    data = path.read_bytes()
    assert data[:12] == b'BLP2' + struct.pack('<I', 1) + bytes([1, 8, 8, 1])
    w, h = struct.unpack_from('<II', data, 12)
    assert data[148:151] == b'\xff\xff\xff'
    levels = []
    expected_offset = 1172
    for index in range(max(w, h).bit_length()):
        offset = struct.unpack_from('<I', data, 20 + index * 4)[0]
        length = struct.unpack_from('<I', data, 84 + index * 4)[0]
        assert offset == expected_offset and length == w * h * 2
        assert data[offset:offset + w*h] == bytes(w*h)
        levels.append(np.frombuffer(data[offset + w*h:offset + length], dtype=np.uint8).reshape(h, w))
        expected_offset += length
        w, h = max(1, w // 2), max(1, h // 2)
    assert expected_offset == len(data)
    return levels


def test_build_produces_complete_game_materials_with_unchanged_base(tmp_path):
    build(tmp_path)
    pngs = sorted(tmp_path.glob('*.png'))
    manifest = json.loads((ROOT / 'assets/CrosshairHUDMedia/manifest.json').read_text(encoding='utf-8'))
    assert len(pngs) == len(manifest['assets']) + 3
    assert len(list(tmp_path.glob('*.blp'))) == len(pngs)
    with Image.open(tmp_path / 'mask_half.png') as mask:
        row = np.asarray(mask.getchannel('A'))[512]
        assert row[508:514].tolist() == [255, 191, 127, 63, 0, 0]
        assert np.count_nonzero((row > 0) & (row < 255)) == 3
    for png in pngs:
        levels = read_levels(png.with_suffix('.blp'))
        with Image.open(png) as source:
            assert np.array_equal(levels[0], np.asarray(source.getchannel('A')))
        assert levels[-1].shape == (1, 1)


def test_white_material_preserves_alpha_and_rectangular_chain(tmp_path):
    from white_blp import write_white_blp, verify_white_blp
    image = Image.new('RGBA', (4, 2), (255, 255, 255, 0))
    image.putalpha(Image.fromarray(np.array([[20, 40, 60, 80], [100, 120, 140, 160]], dtype=np.uint8)))
    path = tmp_path / 'rectangle.blp'
    write_white_blp(image, path)
    levels = read_levels(path)
    assert [x.shape for x in levels] == [(2, 4), (1, 2), (1, 1)]
    assert levels[1].tolist() == [[70, 110]]
    assert levels[2].tolist() == [[90]]
    verify_white_blp(path, image)
    original = path.read_bytes()
    damaged = bytearray(path.read_bytes())
    damaged[10] = 0
    path.write_bytes(damaged)
    with pytest.raises(ValueError, match='格式'):
        verify_white_blp(path, image)
    damaged = bytearray(original)
    damaged[1172 + 8] = 0
    path.write_bytes(damaged)
    with pytest.raises(ValueError, match='透明度'):
        verify_white_blp(path, image)
    path.write_bytes(original[:-1])
    with pytest.raises(ValueError, match='尺寸'):
        verify_white_blp(path, image)
    with pytest.raises(ValueError, match='2的幂'):
        write_white_blp(Image.new('RGBA', (3, 2), 'white'), path)
    with pytest.raises(ValueError, match='白色'):
        write_white_blp(Image.new('RGBA', (4, 2), 'red'), path)


def test_invalid_source_does_not_remove_existing_materials(tmp_path, monkeypatch):
    import build_crosshair_media
    from white_blp import MATERIAL_POLICY
    source = tmp_path / 'source'
    (source / 'Textures').mkdir(parents=True)
    (source / 'manifest.json').write_text(json.dumps({'gameMaterial': MATERIAL_POLICY, 'exportScale': 1, 'assets': [
        {'file': 'bad.png', 'displaySize': [2, 2]}]}), encoding='utf-8')
    Image.new('RGBA', (3, 2), 'white').save(source / 'Textures/bad.png')
    target = tmp_path / 'output'
    target.mkdir()
    old = target / 'existing.blp'
    old.write_bytes(b'keep existing material')
    monkeypatch.setattr(build_crosshair_media, 'SRC', source)
    with pytest.raises(AssertionError):
        build(target)
    assert old.read_bytes() == b'keep existing material'
