"""把 Figma 的高倍导出加工成仓库里的成品纹理。

    python scripts/media/prepare_crosshair_media.py <导出目录> [--scale 8] [--out 暂存目录]

- `<导出目录>`：Figma 里选中 18 个画板、Export 倍数填 10x、导出的那个目录。
  画板名必须与清单里的文件名（去掉扩展名）一致。
- `--scale`：成品密度，与 `manifest.json` 的 `exportScale` 同义（成品像素 = 显示尺寸 × 它）。
- `--out`：成品写到哪。缺省直接写 `assets/CrosshairHUDMedia/Textures/`。

## 为什么不能直接用 Figma 的导出

**Figma 的导出不带过渡**。这不是配置问题，是它的渲染结果——形状边缘落在整数像素网格上
时，硬边就是那个分辨率下的正确渲染。所以要先按 10 倍导出，再降到成品密度，**降采样本身
留下的那圈过渡就是抗锯齿**。实测（准星）：直接导出 0.08 像素，降采样后 2.4 像素。

## 为什么画布要补成 2 的幂

**这是"缩小显示不出锯齿"真正依赖的一条。** 魔兽的 `SetTexture` 只在过滤模式给
`TRILINEAR`**且贴图边长是 2 的幂**时才用得上 mipmap；少任何一条就只能双线性采样，
缩小显示时每屏幕像素只读 4 个纹素、高频全丢。2026-09-19 实机逐条验过：

    密度 8 + 边长非 2 的幂 + TRILINEAR  → 缩到 0.8 档锯齿明显
    密度 8 + 边长 2 的幂   + TRILINEAR  → 锐利且无锯齿

**不能靠"把边缘抹软"来绕**：软边确实也消锯齿，但那是拿锐度换的。补边才是既锐利又不锯的路。

补边**四周对称**，所以圆心偏移不变、内容位置与大小不变，只有透明边变多；
`displaySize` 跟着变成新画布的尺寸（它按显示尺寸 × 密度算像素，不跟着改就错位）。

**阴影**额外做两件事：把 RGB 统一成纯白（染色是乘法，颜色由顶点色给），
并把 alpha 峰值归一化到 255（"最重档"＝通道上限，游戏内只能往下调）。
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "assets" / "CrosshairHUDMedia"
DEFAULT_OUT = SRC / "Textures"

# Figma 端的导出倍率。这个值是给**人**在 Figma 里填的，脚本只拿它核对源图尺寸。
#
# 两边差一个系数：Figma 画板用的是**预览单位**，1 预览单位 = 0.5 设计稿单位
# （设计稿是 2 倍预览）。所以「画板宽 140 预览单位」对应「显示尺寸 70」，
# 在 Figma 里导 10 倍得到 1400 像素，而不是 700。忘了这个系数就会把尺寸核对错一倍。
FIGMA_SCALE = 10
PREVIEW_PER_DESIGN = 2

SHADOW_SUFFIX = "_shadow"


def load_manifest():
    return json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))


def white_rgb(image):
    """把有内容的像素的 RGB 一律置为纯白，alpha 原样。

    染色是乘法：形状是白色蒙版，颜色由顶点色给。RGB 只要偏一点，游戏里就会偏色。
    """
    data = np.asarray(image).copy()
    opaque = data[:, :, 3] > 0
    for channel in range(3):
        data[:, :, channel][opaque] = 255
    return data


def normalize_peak(alpha):
    """把 alpha 峰值缩放到 255。最重档就是通道上限，游戏内只能往下调。"""
    peak = int(alpha.max())
    if peak == 0:
        raise ValueError("阴影贴图整个是空的，导出可能没成功")
    if peak == 255:
        return alpha
    return np.rint(alpha.astype(np.float64) * 255.0 / peak).astype(np.uint8)


def next_pot(n):
    return 2 ** math.ceil(math.log2(n))


def pad_to_pot(image):
    """四周**对称**补透明边到 2 的幂。返回 (新图, 新尺寸)。

    对称是必须的：圆心偏移不变，内容位置与大小不变，只有透明边变多。
    """
    w, h = image.size
    pw, ph = next_pot(w), next_pot(h)
    if (pw, ph) == (w, h):
        return image, (w, h)

    data = np.asarray(image)
    canvas = np.zeros((ph, pw, 4), dtype=np.uint8)
    ox, oy = (pw - w) // 2, (ph - h) // 2
    canvas[oy:oy + h, ox:ox + w] = data
    return Image.fromarray(canvas, mode="RGBA"), (pw, ph)


def prepare(source, name, want_size, is_shadow):
    path = source / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在——Figma 那边导出了吗？画板名对得上吗？")

    with Image.open(path) as image:
        image = image.convert("RGBA")

    # 用 LANCZOS 降采样：它按缩放比例放大滤波核的支撑，这正是"带权重"的含义，
    # 也是那圈过渡的来源。NEAREST/BOX 会原样保留硬边（见模块文档的实测）。
    resized = image.resize(want_size, Image.LANCZOS)

    data = white_rgb(resized)
    if is_shadow:
        data[:, :, 3] = normalize_peak(data[:, :, 3])
    return Image.fromarray(data, mode="RGBA")


def main():
    parser = argparse.ArgumentParser(description="把 Figma 高倍导出加工成成品纹理")
    parser.add_argument("source", nargs="?", default=str(SRC / "Exports"),
                        help="Figma 导出目录，缺省用仓库里的 assets/CrosshairHUDMedia/Exports")
    parser.add_argument("--scale", type=int, default=None,
                        help="成品密度，缺省用清单里的 exportScale")
    parser.add_argument("--out", default=None, help="成品输出目录，缺省写回 assets/Textures")
    parser.add_argument("--figma-scale", type=int, default=FIGMA_SCALE,
                        help=f"Figma 端用的导出倍数，缺省 {FIGMA_SCALE}（只用于核对源图尺寸）")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out) if args.out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    # 密度缺省从清单读，别在这儿另写一份——三个兄弟脚本都读清单，只有这里写死就会分叉
    scale = args.scale if args.scale is not None else manifest["exportScale"]

    placement = {}
    for asset in manifest["assets"]:
        name = asset["file"][:-4]                       # 去掉 .png
        is_shadow = name.endswith(SHADOW_SUFFIX)
        # **用 contentSize（补边前的画布），不是 displaySize（补边后的画布）**。
        # Figma 那边导出的是前者，补边是本脚本之后才做的。搞混了这条核对就永远对不上。
        dw, dh = asset["contentSize"]
        want = (dw * scale, dh * scale)

        # 核对导出尺寸：源图应当是「补边前的画布 × 2（预览单位）× Figma 端倍数」
        with Image.open(source / f"{name}.png") as probe:
            sw, sh = probe.size
        expect = (dw * PREVIEW_PER_DESIGN * args.figma_scale,
                  dh * PREVIEW_PER_DESIGN * args.figma_scale)
        assert (sw, sh) == expect, (
            f"{name}: 导出尺寸应为 {expect}，实际 {(sw, sh)}——"
            f"Figma 端的倍数是不是没填对（应填 {args.figma_scale}x）？")

        image = prepare(source, name, want, is_shadow)
        image, pot = pad_to_pot(image)
        image.save(out / asset["file"])
        placement[asset["file"]] = [pot[0] // scale, pot[1] // scale]

        pad = (pot[0] - want[0]) // 2
        note = f"补边 {pad}px" if pad or pot[1] != want[1] else "已是 2 的幂"
        print(f"  {asset['file']:<26} {sw}x{sh} → {want[0]}x{want[1]} → "
              f"{pot[0]}x{pot[1]}  {note}")

    print(f"\n已写入 {out}（{len(manifest['assets'])} 张）")
    print("\n新画布变了，清单的 displaySize 与渲染侧摆放表都要跟着改：")
    print(json.dumps(placement, ensure_ascii=False, indent=4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
