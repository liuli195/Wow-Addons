"""校验准星 HUD 的成品纹理（与 build_crosshair_media.py 配对）。

这里断言的都是**染色能否正确**所依赖的性质，不是外观好不好看：

1. 尺寸与 `manifest.json` 一致（显示尺寸 × 导出倍率）——错了说明素材被换过或重导失败。
2. RGB 三通道处处相等（中性灰）——不中性则 `SetVertexColor` 染色会偏色。
3. 不透明像素恰好是纯白 (255,255,255)——这是"白色蒙版"的定义，偏暗会让染色结果发灰。
4. 边缘不做预乘 alpha——预乘会让抗锯齿边缘染色后发黑。
5. 遮罩的左半全不透明、右半全透明、中线单调过渡——镜像翻转会让所有填充方向整体反向，
   而这一条光看代码发现不了。

用法：python scripts/media/verify_crosshair_media.py
"""

from pathlib import Path
import json
import sys

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "assets" / "CrosshairHUDMedia"
MEDIA = REPO / "addons" / "MYUI" / "Media" / "CrosshairHUD"

MASK_NAME = "mask_half.png"
MASK_PX_PER_UNIT = 2
MASK_UNITS = 128

failures = []


def check(ok, message):
    if not ok:
        failures.append(message)


def load(path):
    check(path.exists(), f"{path.name}: 文件不存在")
    if not path.exists():
        return None
    return np.asarray(Image.open(path).convert("RGBA")).astype(int)


def verify_texture(name, want_size):
    image = load(MEDIA / name)
    if image is None:
        return
    h, w = image.shape[:2]
    check((w, h) == want_size, f"{name}: 尺寸应为 {want_size}，实际 ({w}, {h})")

    alpha = image[:, :, 3]
    opaque = alpha > 0
    check(opaque.any(), f"{name}: 没有任何不透明像素")

    r, g, b = image[:, :, 0][opaque], image[:, :, 1][opaque], image[:, :, 2][opaque]
    check(np.array_equal(r, g) and np.array_equal(g, b), f"{name}: RGB 三通道不相等（染色会偏色）")

    full = alpha == 255
    if full.any():
        check(np.all(image[:, :, :3][full] == 255), f"{name}: 不透明处不是纯白（染色会发灰）")

    half = (alpha > 10) & (alpha < 245)
    if half.any():
        # 预乘 alpha 的特征：半透明像素的亮度随 alpha 同步下降
        lum = image[:, :, 0][half].astype(float)
        a = alpha[half].astype(float)
        if lum.std() > 1:
            corr = float(np.corrcoef(lum, a)[0, 1])
            check(not (corr > 0.9 and lum.max() < 200), f"{name}: 疑似预乘 alpha（边缘染色会发黑）")


def verify_mask():
    image = load(MEDIA / MASK_NAME)
    if image is None:
        return
    side = MASK_UNITS * MASK_PX_PER_UNIT
    h, w = image.shape[:2]
    check((w, h) == (side, side), f"{MASK_NAME}: 尺寸应为 {side}，实际 ({w}, {h})")

    alpha = image[:, :, 3]
    mid = w // 2
    left = alpha[:, :mid - 1]
    right = alpha[:, mid + 1:]
    check(np.all(left == 255), f"{MASK_NAME}: 左半不是全不透明")
    check(np.all(right == 0), f"{MASK_NAME}: 右半不是全透明")

    # 中线必须是单调过渡，且整体从左(255)向右(0)下降；反转即方向错
    row = alpha[h // 2, max(0, mid - 4):mid + 5]
    check(np.all(np.diff(row) <= 0), f"{MASK_NAME}: 中线过渡不是从左侧不透明向右侧透明的单调下降（可能被镜像翻转）")
    check(row[0] > row[-1], f"{MASK_NAME}: 中线两侧明暗关系反了")


def main():
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    scale = manifest["exportScale"]
    for asset in manifest["assets"]:
        want = (asset["displaySize"][0] * scale, asset["displaySize"][1] * scale)
        verify_texture(asset["file"], want)
    verify_mask()

    if failures:
        print("FAIL: 准星 HUD 纹理校验未通过")
        for message in failures:
            print(f"  - {message}")
        print(f"诊断目录：{MEDIA}")
        return 1

    total = len(manifest["assets"]) + 1
    print(f"PASS: {total} 个准星 HUD 纹理的尺寸、中性度、蒙版纯度与遮罩方向")
    return 0


if __name__ == "__main__":
    sys.exit(main())
