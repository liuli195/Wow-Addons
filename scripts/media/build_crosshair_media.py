"""构建准星 HUD 的成品纹理（技术 A：旋转半平面遮罩）。

源：`assets/CrosshairHUDMedia/`（素材包的固化副本，含 9 张成品 PNG、11 个 SVG 矢量源、manifest.json）

产出 10 个文件：

- 9 张成品纹理：**逐字节复制**，不重新编码、不缩放、不重采样、不改图形。经核实素材包本身是
  2 像素/设计稿单位，而界面缩放滑块上限是 2.0（即 2 界面单位/设计稿单位），因此在全范围内
  永远不会被放大，不需要重新导出。
- 1 张半平面遮罩 `mask_half.png`：左半不透明、右半透明，**中线带 2 像素线性过渡**（这就是弧线
  切线的抗锯齿来源；实机已验证观感平滑）。它是本技术唯一新增的素材。

本模块被 `build_assets.py`（仓库统一素材构建入口）调用；也可以单独运行。

单独运行：python scripts/media/build_crosshair_media.py   → 输出到 addons/MYUI/Media/CrosshairHUD/

关于遮罩的约定（与实现里的换算公式是**一对**，不能单独改其中一边）：
    遮罩图像左半不透明；旋转 θ 后不透明区域为半平面 {p : p·(cosθ, sinθ) < 0}。
    把遮罩图镜像翻转会让所有填充方向整体反向（校验脚本会拦住这一条）。
"""

from pathlib import Path
import json
import shutil

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "assets" / "CrosshairHUDMedia"
DEFAULT_OUT = REPO / "addons" / "MYUI" / "Media" / "CrosshairHUD"

MASK_NAME = "mask_half.png"
MASK_UNITS = 128      # 遮罩画布边长（设计稿单位），圆心居中；须覆盖环外径 57
MASK_PX_PER_UNIT = 2  # 与素材包同密度
MASK_SOFTNESS_PX = 2  # 中线过渡宽度；实机基线，可调


def copy_textures(manifest, out_dir):
    """逐字节复制 9 张成品，并按 manifest 校验源图尺寸。"""
    scale = manifest["exportScale"]
    for asset in manifest["assets"]:
        name = asset["file"]
        want = (asset["displaySize"][0] * scale, asset["displaySize"][1] * scale)
        src = SRC / "Textures" / name
        with Image.open(src) as image:
            actual = image.size
        assert actual == want, f"{name}: 期望 {want}，实际 {actual}"
        shutil.copyfile(src, out_dir / name)
        print(f"  copy   {name:<18} {want[0]}x{want[1]}  (逐字节)")
    return len(manifest["assets"])


def build_mask(out_dir):
    """生成半平面遮罩：左半不透明，右半全透明，中线线性过渡。"""
    side = MASK_UNITS * MASK_PX_PER_UNIT
    mask = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    data = mask.load()
    mid = side // 2
    for x in range(side):
        if x < mid - MASK_SOFTNESS_PX + 1:
            alpha = 255
        elif x <= mid:
            alpha = int(255 * (mid - x) / MASK_SOFTNESS_PX)
        else:
            alpha = 0
        for y in range(side):
            data[x, y] = (255, 255, 255, alpha)
    mask.save(out_dir / MASK_NAME)
    print(f"  mask   {MASK_NAME:<18} {side}x{side}  过渡 {MASK_SOFTNESS_PX}px")


def build(out_dir):
    """把准星 HUD 的全部成品纹理写进 out_dir，返回文件数。"""
    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 清掉旧版本留下的文件，避免残留误导
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    count = copy_textures(manifest, out_dir)
    build_mask(out_dir)
    print(f"Built {count + 1} CrosshairHUD PNG assets into {out_dir}.")
    return count + 1


if __name__ == "__main__":
    build(DEFAULT_OUT)
