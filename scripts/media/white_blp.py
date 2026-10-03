"""白色可染色素材的 BLP2 保存适配器；缩小算法复用 Pillow BOX。

只处理白色和透明度，不做彩色量化或有损压缩。格式沿用实机验收的
颜色表模式、8位独立透明度、格式提示8和完整缩小链。
格式依据：https://skarndev.github.io/wowlib/python/blp/
"""
from pathlib import Path
import struct

import numpy as np
from PIL import Image

MATERIAL_POLICY = {
    'format': 'BLP2', 'encoding': 1, 'alphaBits': 8, 'preferredFormat': 8,
    'mipmaps': 'full', 'downsample': 'BOX', 'filterMode': 'TRILINEAR',
    'pngReferencePreserved': True,
}


def _levels(image):
    alpha = image.convert('RGBA').getchannel('A')
    yield alpha
    while alpha.size != (1, 1):
        alpha = alpha.resize(tuple(max(1, n // 2) for n in alpha.size), Image.Resampling.BOX)
        yield alpha


def write_white_blp(image, path):
    """保持基本层透明度，写入完整层级；拒绝错误尺寸及非白色可见内容。"""
    image = image.convert('RGBA')
    w, h = image.size
    if any(n <= 0 or n & (n - 1) for n in (w, h)):
        raise ValueError('素材宽高必须是2的幂')
    pixels = np.asarray(image)
    if np.any(pixels[:, :, :3][pixels[:, :, 3] > 0] != 255):
        raise ValueError('只支持白色可染色素材，不能自动改变可见颜色')
    levels = list(_levels(image))
    if len(levels) > 16:
        raise ValueError('BLP2最多保存16级图片')
    header = bytearray(1172)
    header[:12] = b'BLP2' + struct.pack('<I', 1) + bytes([1, 8, 8, 1])
    struct.pack_into('<II', header, 12, w, h)
    header[148:152] = bytes([255, 255, 255, 255])
    payloads = []
    offset = len(header)
    for index, alpha in enumerate(levels):
        count = alpha.width * alpha.height
        payload = bytes(count) + alpha.tobytes()
        struct.pack_into('<I', header, 20 + index * 4, offset)
        struct.pack_into('<I', header, 84 + index * 4, len(payload))
        payloads.append(payload)
        offset += len(payload)
    Path(path).write_bytes(bytes(header) + b''.join(payloads))


def verify_white_blp(path, source):
    """检查实际文件头、每级尺寸、白色和透明度；基本层须与PNG完全一致。"""
    data = Path(path).read_bytes()
    if len(data) < 1172 or data[:12] != b'BLP2' + struct.pack('<I', 1) + bytes([1, 8, 8, 1]):
        raise ValueError(f'{path}: BLP保存格式错误')
    if struct.unpack_from('<II', data, 12) != source.size:
        raise ValueError(f'{path}: 原始层尺寸不一致')
    if data[148:151] != bytes([255, 255, 255]):
        raise ValueError(f'{path}: 白色模板不一致')
    offset = 1172
    levels = list(_levels(source))
    for index, expected in enumerate(levels):
        actual_offset = struct.unpack_from('<I', data, 20 + index * 4)[0]
        length = struct.unpack_from('<I', data, 84 + index * 4)[0]
        count = expected.width * expected.height
        if actual_offset != offset or length != count * 2 or offset + length > len(data):
            raise ValueError(f'{path}: 第{index}级尺寸或位置错误')
        if data[offset:offset + count] != bytes(count):
            raise ValueError(f'{path}: 第{index}级不是白色模板')
        if data[offset + count:offset + length] != expected.tobytes():
            raise ValueError(f'{path}: 第{index}级透明度或缩小处理不一致')
        offset += length
    if offset != len(data) or any(data[20 + len(levels)*4:84]) or any(data[84 + len(levels)*4:148]):
        raise ValueError(f'{path}: 多余或缺失的缩小层')
    return len(levels)
