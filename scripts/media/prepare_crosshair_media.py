"""把 Figma 的高倍导出加工成仓库里的成品纹理。

**为什么需要这一步**：Figma 的导出**不带抗锯齿**。这不是导出配置问题，是它的渲染
结果——形状的边缘落在整数像素网格上时，硬边就是那个分辨率下的正确渲染。实测：

    素材                      中间像素占非透明像素
    Figma SCALE 1 导出        3.8%   ← 现役贴图就是它，游戏里边缘呈锯齿
    Figma SCALE 2 导出        2.1%
    Figma SCALE 8 导出        0.6%   ← 只是把同样的硬边放大了
    老素材（高倍导出再降采样） 77.9%  ← 目标手感

**提高导出倍率本身不解决问题**：整数倍箱式平均（也就是 GPU mipmap 的行为）会把
硬边原封不动保留——8 倍图按箱式降到 1 倍，中间像素仍然只有 4.4%。必须**带权重地
降采样**，把软边烘进贴图；烘进去之后再过 GPU 缩小也不会被磨掉（实测 67.4%）。

所以流程是：**Figma 里按 10 倍导出 → 本脚本降到成品倍率**。

    python scripts/media/prepare_crosshair_media.py <导出目录> [--scale 8] [--out 暂存目录]

- `<导出目录>`：Figma 里选中 18 个画板、Export 倍数填 10x、导出的那个目录。
  画板名必须与清单里的文件名（去掉扩展名）一致。
- `--scale`：成品倍率，与 `manifest.json` 的 `exportScale` 同义（成品像素 = 显示尺寸 × 它）。
  缺省 8，即每设计单位 8 像素。
- `--out`：成品写到哪。缺省直接写 `assets/CrosshairHUDMedia/Textures/`；给暂存目录则先落在那儿。

**阴影**额外做两件事：把 RGB 统一成纯白（染色是乘法，阴影的颜色由顶点色给），
并把 alpha 峰值归一化到 255（"最重档"＝通道上限，游戏内只能往下调）。
"""

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "assets" / "CrosshairHUDMedia"
DEFAULT_OUT = SRC / "Textures"

# 成品倍率：成品像素 = 显示尺寸 × 它。与 manifest.json 的 exportScale 同义。
DEFAULT_EXPORT_SCALE = 8

# Figma 端的导出倍率。这个值是给**人**在 Figma 里填的，脚本只拿它核对源图尺寸。
#
# 两边差一个系数：Figma 画板用的是**预览单位**，1 预览单位 = 0.5 设计稿单位
# （设计稿是 2 倍预览）。所以「画板宽 140 预览单位」对应「显示尺寸 70」，
# 在 Figma 里导 10 倍得到 1400 像素，而不是 700。忘了这个系数就会把尺寸核对错一倍。
FIGMA_SCALE = 10
PREVIEW_PER_DESIGN = 2

SHADOW_SUFFIX = "_shadow"

# 过渡带的目标宽度，单位是**设计稿单位**。
#
# **这是防锯齿的那一条**，比"多少个像素"重要得多。屏幕像素永远比设计稿单位粗，
# 过渡带在设计稿单位上不够宽，贴图缩小显示后它就会窄于一个屏幕像素——等于硬边。
# 魔兽默认的过滤模式（LINEAR）不采样 mipmap，没有更低频的层级可退，只能靠它。
#
# **它不随密度缩放，这一点是反直觉的**：降采样得到的过渡带在**像素**上恒定两三像素，
# 所以密度一翻倍，它在设计稿单位上就窄一半。2026-09-19 提密度到 8 时正是栽在这里——
# 过渡带只剩 0.30 个单位，实机缩到 0.8 档满屏锯齿。
#
# 1.4 取原始素材包实测宽度（1.22 – 1.59）的中值附近——那是实机各档位都被接受过的值。
SOFTEN_UNITS = 1.4

# 降采样本身（LANCZOS）大约会留下这么宽的过渡带，抹开时要把这份算进去，免得抹过头。
DOWNSAMPLE_TRANSITION_PX = 2.4

# 高斯模糊半径换算成过渡带宽度的系数。
#
# **4.2 是实测标定出来的，不是理论值**：理论上的 10%–90% 宽度是 2.56σ，但本脚本量的是
# alpha 落在 (0,245) 之间的**全部**像素（接近 1%–99%，约 4.65σ），而且还要叠上降采样
# 留下的底子。实测：σ=2.93 时两条弧的过渡带是 14.62 像素，σ=0 时是 2.38 像素。
GAUSS_SPAN = 4.2


def load_manifest():
    import json
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


def soften(image, density):
    """把边缘的过渡带抹到 SOFTEN_UNITS 那么宽（设计稿单位）。

    不清这一步也能过「过渡带不少于两像素」那条断言——但那条只管"不是硬边"。
    真正决定**贴图缩小显示时会不会出锯齿**的，是过渡带在**设计稿单位**上的宽度，
    理由见 SOFTEN_UNITS。
    """
    target_px = SOFTEN_UNITS * density
    extra = target_px - DOWNSAMPLE_TRANSITION_PX
    if extra <= 0:
        return image
    return image.filter(ImageFilter.GaussianBlur(radius=extra / GAUSS_SPAN))


def prepare(source, name, want_size, is_shadow, density):
    path = source / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在——Figma 那边导出了吗？画板名对得上吗？")

    with Image.open(path) as image:
        image = image.convert("RGBA")

    # 先降采样、再归一化。顺序反过来会让降采样的加权平均把峰值拉离 255。
    # 用的是 LANCZOS：它按缩放比例放大滤波核的支撑，这正是"带权重"的含义，
    # 也是软边的来源。NEAREST/BOX 会原样保留硬边（见模块文档的实测）。
    resized = image.resize(want_size, Image.LANCZOS)

    # 先统一成白图再模糊：否则透明区的 RGB 会被模糊晕进边缘，染色时会偏色
    data = white_rgb(resized)
    if is_shadow:
        # 阴影本来就是模糊出来的，过渡带够宽，不需要再抹；
        # 只把 alpha 峰值归一化（"最重档"＝通道上限，游戏内只能往下调）
        data[:, :, 3] = normalize_peak(data[:, :, 3])
        return Image.fromarray(data, mode="RGBA")

    softened = soften(Image.fromarray(data, mode="RGBA"), density)
    return Image.fromarray(white_rgb(softened), mode="RGBA")   # 模糊会把 RGB 晕花，再统一一次


def main():
    parser = argparse.ArgumentParser(description="把 Figma 高倍导出加工成成品纹理")
    parser.add_argument("source", help="Figma 导出目录")
    parser.add_argument("--scale", type=int, default=DEFAULT_EXPORT_SCALE,
                        help=f"成品倍率，缺省 {DEFAULT_EXPORT_SCALE}")
    parser.add_argument("--out", default=None, help="成品输出目录，缺省写回 assets/Textures")
    parser.add_argument("--figma-scale", type=int, default=FIGMA_SCALE,
                        help=f"Figma 端用的导出倍数，缺省 {FIGMA_SCALE}（只用于核对源图尺寸）")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out) if args.out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    for asset in manifest["assets"]:
        name = asset["file"][:-4]                       # 去掉 .png
        is_shadow = name.endswith(SHADOW_SUFFIX)
        dw, dh = asset["displaySize"]
        want = (dw * args.scale, dh * args.scale)

        # 核对导出尺寸：源图应当是「显示尺寸 × 2（预览单位）× Figma 端倍数」
        with Image.open(source / f"{name}.png") as probe:
            sw, sh = probe.size
        expect = (dw * PREVIEW_PER_DESIGN * args.figma_scale,
                  dh * PREVIEW_PER_DESIGN * args.figma_scale)
        assert (sw, sh) == expect, (
            f"{name}: 导出尺寸应为 {expect}，实际 {(sw, sh)}——"
            f"Figma 端的倍数是不是没填对（应填 {args.figma_scale}x）？")

        image = prepare(source, name, want, is_shadow, args.scale)
        image.save(out / asset["file"])
        alpha = np.asarray(image)[:, :, 3]
        nontransparent = int((alpha > 0).sum())
        soft = int(((alpha > 0) & (alpha < 255)).sum())
        ratio = soft / nontransparent if nontransparent else 0.0
        print(f"  {asset['file']:<26} {sw}x{sh} → {want[0]}x{want[1]}   "
              f"中间像素 {ratio:5.1%}")

    print(f"\n已写入 {out}（{len(manifest['assets'])} 张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
