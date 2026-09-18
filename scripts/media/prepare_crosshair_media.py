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
from pathlib import Path

import numpy as np
from PIL import Image

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


def prepare(source, name, want_size, is_shadow):
    path = source / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在——Figma 那边导出了吗？画板名对得上吗？")

    with Image.open(path) as image:
        image = image.convert("RGBA")

    # 先降采样、再归一化。顺序反过来会让降采样的加权平均把峰值拉离 255。
    # 用的是 LANCZOS：它按缩放比例放大滤波核的支撑，这正是"带权重"的含义，
    # 也是软边的来源。NEAREST/BOX 会原样保留硬边（见模块文档的实测）。
    resized = image.resize(want_size, Image.LANCZOS)

    data = white_rgb(resized)
    if is_shadow:
        data[:, :, 3] = normalize_peak(data[:, :, 3])
    return Image.fromarray(data, mode="RGBA")


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

        image = prepare(source, name, want, is_shadow)
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
