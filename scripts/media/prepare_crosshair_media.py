"""将Figma（设计工具）的10倍导出加工成白色透明PNG核对图。

成品密度和摆放读manifest.json；对称补边到2的幂，不改内容位置。
此步骤保留高倍率原图细节并生成边缘过渡，但不能单独保证游戏内平滑。
后续build_crosshair_media.py保存完整缩小层并经游戏验收。
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

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


def prepare(source, name, want_size, is_shadow, hollow_shadow=False):
    path = source / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在——Figma 那边导出了吗？画板名对得上吗？")

    with Image.open(path) as image:
        image = image.convert("RGBA")

    # 用 LANCZOS 降采样：它按缩放比例放大滤波核的支撑，这正是"带权重"的含义，
    # 也是那圈过渡的来源；游戏缩小层另用面积平均，不混淆这两个阶段。
    resized = image.resize(want_size, Image.LANCZOS)

    data = white_rgb(resized)
    if is_shadow:
        data[:, :, 3] = normalize_peak(data[:, :, 3])
        if hollow_shadow:
            shape = prepare(source, name.removesuffix(SHADOW_SUFFIX), want_size, False)
            # 少挖成品纹理的2像素，留下窄重叠区，避免主体和阴影的软边叠成透明缝。
            coverage = np.asarray(shape.getchannel("A").filter(
                ImageFilter.MinFilter(5))).astype(np.uint32)
            # 只挖去主体覆盖范围，外围扩散和浓淡保持原值；边缘沿用主体平滑覆盖。
            data[:, :, 3] = ((data[:, :, 3].astype(np.uint32) * (255 - coverage)
                             + 127) // 255).astype(np.uint8)
    return Image.fromarray(data, mode="RGBA")


def prepare_crosshair_parts(source, out):
    """从保留的原 PNG 裁主体，四张小图保持原尺寸；阴影按同风格重建。

    原影已经扁平，不能无损分开；三层 source-over（透明度叠加）用成品像素
    半径 3/8/20 的 1.5 倍候选，待实机观感校准，不冒称逐像素一致。
    """
    original, _ = pad_to_pot(prepare(source, "crosshair", (560, 560), False))
    for name, box, size, shadow_size in (
        ("crosshair_arm", (565, 501, 707, 523), (256, 64), (512, 256)),
        ("crosshair_point", (489, 489, 535, 535), (64, 64), (256, 256)),
    ):
        shape = original.crop(box).getchannel("A")
        alpha = Image.new("L", size)
        alpha.paste(shape, ((size[0] - shape.width) // 2, (size[1] - shape.height) // 2))
        art = Image.new("RGBA", size, (255, 255, 255, 0))
        art.putalpha(alpha)
        art.save(out / f"{name}.png")
        coverage = Image.new("L", shadow_size)
        coverage.paste(shape, ((shadow_size[0] - shape.width) // 2,
                               (shadow_size[1] - shape.height) // 2))
        combined = np.zeros((shadow_size[1], shadow_size[0]), dtype=np.float64)
        for radius, weight in ((4.5, 1), (12, 0.85), (30, 0.65)):
            layer = np.asarray(coverage.filter(ImageFilter.GaussianBlur(radius))) * weight / 255
            combined = 1 - (1 - combined) * (1 - layer)
        shadow = normalize_peak(np.rint(combined * 255).astype(np.uint8))
        core = np.asarray(coverage.filter(ImageFilter.MinFilter(5))).astype(np.uint32)
        shadow = ((shadow.astype(np.uint32) * (255 - core) + 127) // 255).astype(np.uint8)
        image = Image.new("RGBA", shadow_size, (255, 255, 255, 0))
        image.putalpha(Image.fromarray(shadow))
        image.save(out / f"{name}_shadow.png")


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
    if scale != 8:
        raise ValueError("当前四张准星裁图按已确认的8像素/设计单位生产")
    prepare_crosshair_parts(source, out)

    placement = {}
    for asset in manifest["assets"]:
        name = asset["file"][:-4]                       # 去掉 .png
        if name.startswith("crosshair_"):
            continue
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

        image = prepare(source, name, want, is_shadow,
                        name + ".png" in manifest.get("hollowShadows", []))
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
