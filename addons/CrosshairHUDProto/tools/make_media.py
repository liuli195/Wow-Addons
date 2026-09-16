"""CrosshairHUD 原型的纹理准备（一次性工具，不属于正式插件）。

从素材包生成三类文件：
1. 原样复制 9 张成品 PNG（技术 A 直接按 manifest 的摆放使用，无需重切）。
2. 方形重切：把每条弧/每个符文格放进一个以圆心为正中、128x128 设计稿单位的方形画布。
   技术 B（Cooldown 扫掠）要求扫掠纹理铺满整个方形框体，所以必须有方形版本。
   纯透明画布合成，不缩放也不重采样；画布外的透明留白允许被裁掉。
3. 半平面遮罩：左半不透明、右半透明，中线 2 像素过渡。技术 A 旋转它来切弧。

用法：python addons/CrosshairHUDProto/tools/make_media.py
源素材：D:\\Downloads\\CrosshairHUD_Media_Pack（素材包原版保持不动）
"""

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[3]
SRC = Path(r"D:\Downloads\CrosshairHUD_Media_Pack") / "CrosshairHUD_Media" / "Textures"
OUT = REPO / "addons" / "CrosshairHUDProto" / "Media"

CIRCLE = 128          # 设计稿坐标系圆心
PX = 2                # 素材包导出倍率：2 像素/设计稿单位
SQUARE_UNITS = 128    # 方形画布边长（设计稿单位），圆心居中
SIDE_PX = SQUARE_UNITS * PX

# manifest.json：displaySize（设计稿单位）与相对圆心的偏移（y 向下为正）
ASSETS = {
    "crosshair":   ((64, 64),  (0, 0)),
    "health_arc":  ((64, 128), (-32, 16)),
    "power_arc":   ((64, 128), (32, 16)),
    "resource_01": ((32, 32),  (-38, -38)),
    "resource_02": ((32, 32),  (-24, -48)),
    "resource_03": ((32, 32),  (-8, -53)),
    "resource_04": ((32, 32),  (8, -53)),
    "resource_05": ((32, 32),  (24, -48)),
    "resource_06": ((32, 32),  (38, -38)),
}

# 方形重切只需要这 8 张（准星是直线段，不参与弧线填充）
SQUARE_FOR = [
    "health_arc", "power_arc",
    "resource_01", "resource_02", "resource_03",
    "resource_04", "resource_05", "resource_06",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    for name in ASSETS:
        image = Image.open(SRC / f"{name}.png").convert("RGBA")
        image.save(OUT / f"{name}.png")
        print(f"copy   {name}.png  {image.size}")

    for name in SQUARE_FOR:
        size, offset = ASSETS[name]
        src = Image.open(SRC / f"{name}.png").convert("RGBA")
        assert src.size == (size[0] * PX, size[1] * PX), f"{name}: 尺寸与 manifest 不符"

        # 素材左上角相对圆心的偏移（设计稿单位）→ 方形画布内的像素坐标
        left_units = offset[0] - size[0] / 2
        top_units = offset[1] - size[1] / 2
        px_ = int(round((left_units + SQUARE_UNITS / 2) * PX))
        py_ = int(round((top_units + SQUARE_UNITS / 2) * PX))

        canvas = Image.new("RGBA", (SIDE_PX, SIDE_PX), (0, 0, 0, 0))
        canvas.paste(src, (px_, py_), src)   # 负坐标时 PIL 会自行裁剪
        canvas.save(OUT / f"square_{name}.png")
        print(f"square square_{name}.png  落点=({px_},{py_})")

    mask = Image.new("RGBA", (SIDE_PX, SIDE_PX), (255, 255, 255, 0))
    data = mask.load()
    mid = SIDE_PX // 2
    for y in range(SIDE_PX):
        for x in range(SIDE_PX):
            if x < mid - 1:
                alpha = 255
            elif x <= mid:
                alpha = int(255 * (mid - x + 1) / 2)
            else:
                alpha = 0
            data[x, y] = (255, 255, 255, alpha)
    mask.save(OUT / "mask_half.png")
    print("mask   mask_half.png  左半不透明、右半透明")

    print(f"\n输出目录：{OUT}")


if __name__ == "__main__":
    main()
