"""准星素材构建：保留PNG核对图，生成白色可染色BLP2和完整缩小层。

从现有清单读取尺寸和位置，不重新绘制形状。遮罩、刻度和居中填充
沿用现有生成规则；所有游戏成品由white_blp统一保存和检查。
本模块沿用仓库build_assets入口，也可单独运行。
"""

from pathlib import Path
import json
import shutil
import tempfile

import numpy as np
from PIL import Image
from white_blp import MATERIAL_POLICY, write_white_blp, verify_white_blp

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "assets" / "CrosshairHUDMedia"
DEFAULT_OUT = REPO / "addons" / "MYUI" / "Media" / "CrosshairHUD"

MASK_NAME = "mask_half.png"
MASK_UNITS = 128      # 遮罩画布边长（设计稿单位），圆心居中；须覆盖环外径 57
MASK_SOFTNESS_PX = 4  # 原8像素渐隐减半；密度仍为8像素/设计单位。

# 遮罩密度（像素/设计稿单位）。**必须与成品纹理的密度一致。**
#
# 当前渐隐为0.5设计单位，三个中间采样点；完整缩小层与平滑取样保持不变。
MASK_PX_PER_UNIT = 8


def copy_textures(manifest, out_dir):
    """逐字节复制清单内PNG核对图，并校验源图尺寸。"""
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
    """生成半平面遮罩：左半不透明，右半全透明，中线线性过渡。

    逐列算出 alpha 后广播成整幅——过渡带是垂直的，每行都一样。
    """
    side = MASK_UNITS * MASK_PX_PER_UNIT
    mid = side // 2
    x = np.arange(side)
    column = np.where(
        x < mid - MASK_SOFTNESS_PX + 1,
        255,
        np.where(x <= mid, 255 * (mid - x) // MASK_SOFTNESS_PX, 0),
    ).astype(np.uint8)

    data = np.zeros((side, side, 4), dtype=np.uint8)
    data[:, :, :3] = 255
    data[:, :, 3] = column[np.newaxis, :]
    Image.fromarray(data, mode="RGBA").save(out_dir / MASK_NAME)

    soft = int(np.count_nonzero((column > 0) & (column < 255)))
    print(f"  mask   {MASK_NAME:<18} {side}x{side}  "
          f"过渡 {MASK_SOFTNESS_PX}px（{soft} 个中间采样点）")


def build_marker(out_dir):
    """平头直线模板：正方形2的幂画布，四周透明，保留缩小采样所需的软边。"""
    yy, xx = np.mgrid[0:1024, 0:1024]
    distance = np.minimum.reduce([xx - 64 + 0.5, 960 - xx - 0.5,
                                  yy - 384 + 0.5, 640 - yy - 0.5])
    alpha = np.clip(distance / 16 + 0.5, 0, 1)
    data = np.full((1024, 1024, 4), 255, dtype=np.uint8)
    data[:, :, 3] = np.rint(alpha * 255).astype(np.uint8)
    Image.fromarray(data, mode="RGBA").save(out_dir / "death_strike_marker.png")
    print("  marker death_strike_marker.png 1024x1024（白色软边直线）")


def build_blood_fill(manifest, out_dir):
    """只平移原始像素，使径向填充画布的圆心与准星圆心重合。"""
    asset = manifest["coagulatedBloodSource"]["texture"]
    scale = manifest["exportScale"]
    offset = tuple(round(v * scale) for v in asset["centerOffset"])
    with Image.open(SRC / "Textures" / asset["file"]) as source:
        canvas = Image.new("RGBA", source.size, (255, 255, 255, 0))
        canvas.paste(source.convert("RGBA"), offset)
        canvas.save(out_dir / "coagulated_blood_fill.png")
    print("  fill   coagulated_blood_fill.png（保持原像素，仅校正填充圆心）")


def _build(out_dir):
    """把准星 HUD 的全部成品纹理写进 out_dir，返回文件数。"""
    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("gameMaterial") != MATERIAL_POLICY:
        raise ValueError("清单中的游戏材质标准与构建程序不一致")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 清掉旧版本留下的文件，避免残留误导
    for pattern in ("*.png", "*.blp"):
        for stale in out_dir.glob(pattern):
            stale.unlink()

    count = copy_textures(manifest, out_dir)
    build_mask(out_dir)
    build_marker(out_dir)
    build_blood_fill(manifest, out_dir)
    for path in sorted(out_dir.glob("*.png")):
        with Image.open(path) as image:
            write_white_blp(image, path.with_suffix(".blp"))
            levels = verify_white_blp(path.with_suffix(".blp"), image)
        print(f"  blp    {path.stem:<26} {levels}级（原始透明度不变）")
    print(f"Built {count + 3} PNG references + {count + 3} BLP game assets into {out_dir}.")
    return (count + 3) * 2


def build(out_dir):
    """先在暂存目录生成并检查全部素材，原图错误时不清空现有成品。"""
    out_dir = Path(out_dir).resolve()
    if out_dir.is_relative_to(SRC.resolve()):
        raise ValueError("游戏成品输出不能覆盖设计原图或PNG核对图")
    with tempfile.TemporaryDirectory(prefix="crosshair-material-") as directory:
        stage = Path(directory)
        count = _build(stage)
        out_dir.mkdir(parents=True, exist_ok=True)
        produced = {p.name for p in stage.iterdir()}
        for path in stage.iterdir():
            shutil.copyfile(path, out_dir / path.name)
        for pattern in ("*.png", "*.blp"):
            for stale in out_dir.glob(pattern):
                if stale.name not in produced:
                    stale.unlink()
    print(f"Published {count} verified material files into {out_dir}.")
    return count


if __name__ == "__main__":
    build(DEFAULT_OUT)
