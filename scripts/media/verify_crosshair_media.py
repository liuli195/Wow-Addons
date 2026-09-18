"""校验准星 HUD 的成品纹理（与 build_crosshair_media.py 配对）。

这里断言的都是**染色能否正确**所依赖的性质，不是外观好不好看：

1. 尺寸与 `manifest.json` 一致（显示尺寸 × 导出倍率）——错了说明素材被换过或重导失败。
2. RGB 三通道处处相等（中性灰）——不中性则 `SetVertexColor` 染色会偏色。
3. 不透明像素恰好是纯白 (255,255,255)——这是"白色蒙版"的定义，偏暗会让染色结果发灰。
4. 边缘不做预乘 alpha——预乘会让抗锯齿边缘染色后发黑。
5. 遮罩的左半全不透明、右半全透明、中线单调过渡——镜像翻转会让所有填充方向整体反向，
   而这一条光看代码发现不了。
6. 条沿半径方向的跨度与设计稿一致——条加粗是"AOE 混战里看得清"这件事的依据，
   改细改粗都会让它失去依据，而这个跨度只有量过才知道。（对两条弧它就是线宽；
   六个资源格是实心块，量到的是整块的径向长度，见 measure_radial_span_units。）
7. 准星正中要有中心定位点——它没有源几何上的依赖，掉了也看不出来。
8. 阴影必须**被柔化过**（半透明裙边大于不透明核心）——硬边是明确否决过的做法。
9. 形状贴图的边缘必须**有足够宽的过渡带**（不少于 2 个纹理像素）——「边缘平滑」是设计稿
   定稿的样子，而这条只有量过才知道。2026-09-19 从 Figma 重导时它丢了，游戏里边缘出现
   锯齿，当时**所有断言都是绿的**：图还是那张图、尺寸还对、颜色还白，只有过渡带没了。
   这条就是那次留下的。判据为什么用「宽度」而不是「占比」，见 EDGE_TRANSITION_MIN。
10. 贴图的像素边长必须是 **2 的幂**——这是「缩小显示不出锯齿」真正依赖的那一条，
   而补边是没写代码就看不出来的东西：画布悄悄变大、内容原地不动，图还是那张图。
   理由与实机验证记录见 POT_REQUIRED。

用法：python scripts/media/verify_crosshair_media.py
"""

from pathlib import Path
import json
import math
import sys

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "assets" / "CrosshairHUDMedia"
MEDIA = REPO / "addons" / "MYUI" / "Media" / "CrosshairHUD"

MASK_NAME = "mask_half.png"
# 必须与 build_crosshair_media.py 的同名常量一致。两处一旦分叉，下面
# verify_mask 的尺寸断言会立刻失败——这正是那条断言存在的意义之一。
MASK_PX_PER_UNIT = 8
MASK_UNITS = 128
# 中线过渡带的宽度（像素）。**下面断言的两侧纯净区要从它推导，不能写死**
# ——过渡带一宽，写死的边界就会把过渡像素当成"左半"，报出假的"左半不纯"。
MASK_SOFTNESS_PX = 8
RING_RADIUS = 54          # 设计稿圆环半径，与 Logic.RING.radius 一致
DESIGN_CENTER = 128       # 设计稿坐标系里的圆环中心
ARC_STROKE = 7.8          # 设计稿定稿的条宽（设计单位）：两条弧是线宽，资源格是半径跨度
ARC_STROKE_TOL = 0.3
CROSSHAIR_NAME = "crosshair.png"   # 准星是线不是弧，不适用弧线线宽
# 中心定位点：设计稿上是准星圆心处一个直径 10 预览单位（＝5 设计稿单位）的实心白点。
# 检查半径只是"有没有点"的粗查；**直径另有一条断言，画大画小都算偏离设计稿**。
DOT_CHECK_RADIUS = 4
DOT_DESIGN_UNITS = 5.0
DOT_TOL = 0.75            # 容差：量的是不透明段，含边缘那圈过渡
SHADOW_SUFFIX = "_shadow"

# 边缘过渡带的最小宽度，单位是**纹理像素**。
#
# 判据是「中间像素数 ÷ 周长」——过渡带有多宽，这个数就是多少。它**与密度无关**，
# 这正是它胜过「半透明像素占比」的地方：占比会随密度变化，密度一提，
# 同一条过渡带占的比例就变小，于是明明做对了也会被判成硬的（我第一版就栽在这）。
#
# 2.0 是从实测的空档里取的。2026-09-19 三组素材实测：
#
#     素材                        过渡带宽度
#     老素材（目标手感）           2.45 – 3.17 px
#     现役（硬边，重导丢了过渡）   0.08 – 1.57 px
#     改成高倍导出＋降采样之后     2.38 – 3.10 px
#
# (1.57, 2.38) 是一段空档，2.0 落在正中。
EDGE_TRANSITION_MIN = 2.0

# 贴图的**像素边长必须是 2 的幂**。这是「缩小显示不出锯齿」真正依赖的那一条。
#
# 魔兽的 `SetTexture` 只有在过滤模式给 `TRILINEAR` 且**贴图边长是 2 的幂**时才用得上
# mipmap。少了任何一条，它就只能双线性采样：缩小显示时每个屏幕像素只读 4 个纹素，
# 高频全丢，边缘出锯齿。2026-09-19 实机逐条验过：
#
#     密度 8 + 边长非 2 的幂 + TRILINEAR   → 缩到 0.8 档锯齿明显
#     密度 8 + 边长 2 的幂   + TRILINEAR   → **锐利且无锯齿**（实机确认）
#
# **不能靠"把边缘抹软"来绕**：软边确实也能消锯齿，但那是拿锐度换的（实机原话：
# 「它不锐利，但是很柔」）。2 的幂这一条才是既锐利又不锯的正路。
#
# 补边必须**四周对称**地补：圆心偏移不变，内容位置与大小不变，只有透明边变多。
POT_REQUIRED = True

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

    if POT_REQUIRED:
        is_pot = lambda n: n > 0 and (n & (n - 1)) == 0
        check(is_pot(w) and is_pot(h),
            f"{name}: 边长 {w}x{h} 不是 2 的幂——魔兽只对 2 的幂贴图生成 mipmap，"
            f"少了它缩小时必出锯齿（见 POT_REQUIRED）")

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


def measure_radial_span_units(image, asset, scale):
    """量图形沿半径方向的跨度（设计单位）。

    取 alpha 过半覆盖的像素，量它们到圆环中心的距离跨度。

    **八张图的读数都是 7.8**，但那个数对两者含义不同，别混：

    - **两条弧**是细弧（平口端点沿半径切，端点不撑大跨度），所以读数**就是描边宽度**。
    - **六个资源格是实心块**（实测：bbox 内部没有洞，是菱形／长条），读数**是整块沿半径
      方向的长度**——它**恰好也等于 7.8**，因为设计稿给两者用的是同一个值。

    两者都随"加粗"一起变大，所以这条断言对两者都抓得住变化。**别因为读数相同就以为
    资源格是弧线**：它没有弧，也没有沿角度的分段。
    """
    h, w = image.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cx = DESIGN_CENTER + asset["centerOffset"][0]
    cy = DESIGN_CENTER + asset["centerOffset"][1]
    dw, dh = asset["displaySize"]
    dx = cx - dw / 2.0 + (xx + 0.5) / scale
    dy = cy - dh / 2.0 + (yy + 0.5) / scale
    dist = np.hypot(dx - DESIGN_CENTER, dy - DESIGN_CENTER)

    sel = image[:, :, 3] >= 128
    if not sel.any():
        return None
    return float(dist[sel].max() - dist[sel].min())


def verify_arc_stroke(asset, scale):
    name = asset["file"]
    # 准星是线不是弧；阴影是被**模糊过**的，本来就比形状宽，两者都不适用这条
    if name == CROSSHAIR_NAME or name.endswith(SHADOW_SUFFIX + ".png"):
        return
    image = load(MEDIA / name)
    if image is None:
        return

    got = measure_radial_span_units(image, asset, scale)
    if got is None:
        check(False, f"{name}: 量不出半径方向的跨度（没有过半覆盖的像素）")
        return
    check(abs(got - ARC_STROKE) <= ARC_STROKE_TOL,
        f"{name}: 沿半径的跨度应为 {ARC_STROKE} 设计单位，实测 {got:.2f}")


def verify_center_dot(asset, scale):
    """准星正中必须有中心定位点，**大小还要与设计稿一致**。

    设计稿上它是准星圆心处一个实心的白点——AOE 混战里快速转头之后，玩家靠它
    把视线拉回屏幕正中。它没有源几何上的依赖，掉了看不出来，**画大画小同样看不出来**
    （都是"有个点"），所以尺寸也得量。

    量法：十字线在正中是断开的，所以过中心那一条不透明段的长度就是点的直径。
    """
    name = asset["file"]
    if name != CROSSHAIR_NAME:
        return
    image = load(MEDIA / name)
    if image is None:
        return

    h, w = image.shape[:2]
    cy, cx = h // 2, w // 2

    r = DOT_CHECK_RADIUS
    window = image[:, :, 3][cy - r:cy + r + 1, cx - r:cx + r + 1]
    check(window.max() == 255,
        f"{name}: 正中缺少中心定位点（中心 {r * 2 + 1}×{r * 2 + 1} 窗口最大不透明度 {window.max()}）")

    alpha = image[:, :, 3]
    if alpha[cy, cx] == 0:
        return  # 点都没有，上面那条已经报过了

    def run_length(line, at):
        lo = at
        while lo > 0 and line[lo - 1] > 0:
            lo -= 1
        hi = at
        while hi < len(line) - 1 and line[hi + 1] > 0:
            hi += 1
        return hi - lo + 1

    for line, axis in ((alpha[cy, :], "水平"), (alpha[:, cx], "垂直")):
        units = run_length(line, cx if axis == "水平" else cy) / scale
        check(abs(units - DOT_DESIGN_UNITS) <= DOT_TOL,
            f"{name}: 中心定位点{axis}直径应为 {DOT_DESIGN_UNITS} 设计单位，"
            f"实测 {units:.2f}（画大了画小了都偏离设计稿）")


def verify_shadow_softness(asset):
    """阴影必须**被柔化过**。

    判据是结构性的，不拍阈值：柔化过的阴影，**半透明的裙边比不透明的核心更大**；
    硬边形状正相反（核心一大片，只有一圈 1 像素的抗锯齿边）。

    这条盯的是一个被明确否决过的做法——"不是让你在准心的圆圈和十字线边上加黑边"。
    硬边同样能提供分离度，但那是另一种观感，且不是设计稿的样子。
    """
    name = asset["file"]
    if not name.endswith(SHADOW_SUFFIX + ".png"):
        return
    image = load(MEDIA / name)
    if image is None:
        return

    alpha = image[:, :, 3]
    soft = int(np.count_nonzero((alpha > 0) & (alpha < 245)))
    solid = int(np.count_nonzero(alpha >= 245))
    check(soft > solid,
        f"{name}: 像是硬边而不是柔化阴影（半透明 {soft} 像素 ≤ 不透明 {solid} 像素）")


def verify_edge_softness(asset):
    """形状贴图的边缘必须有足够宽的过渡带。

    判据是**过渡带宽度 = 中间像素数 ÷ 周长**（单位：纹理像素）。周长用「实心区域与其
    一像素腐蚀之差」估。硬边只有图元自身那不到一像素的抗锯齿，读数在 1 上下；真正
    柔化过的边读数在 2 以上。**这个数不随密度变化**，所以换个导出倍率也不用重标门槛。

    它盯的是 2026-09-19 那次重导丢掉的过渡。那次**其余断言全是绿的**——丢的是"过渡"
    而不是"内容"：尺寸没变、颜色没偏、该有的图形一个不少，游戏里却是一圈锯齿。

    阴影不走这条：它是靠模糊出来的、本来就没"实心核心"可言，由 verify_shadow_softness 管。
    """
    name = asset["file"]
    if name.endswith(SHADOW_SUFFIX + ".png"):
        return
    image = load(MEDIA / name)
    if image is None:
        return

    alpha = image[:, :, 3]
    solid = alpha >= 245
    if not solid.any():
        return  # 没有实心区域，由 verify_texture 负责报，这里不重复

    eroded = solid.copy()
    eroded[1:, :] &= solid[:-1, :]
    eroded[:-1, :] &= solid[1:, :]
    eroded[:, 1:] &= solid[:, :-1]
    eroded[:, :-1] &= solid[:, 1:]
    perimeter = int(np.count_nonzero(solid & ~eroded))
    if perimeter == 0:
        return

    transition = int(np.count_nonzero((alpha > 0) & (alpha < 245))) / perimeter
    check(transition >= EDGE_TRANSITION_MIN,
        f"{name}: 边缘像是硬的（过渡带只有 {transition:.2f} 像素宽，"
        f"应不少于 {EDGE_TRANSITION_MIN}）——贴图丢了过渡，游戏里会是一圈锯齿")



def next_pot(n):
    return 1 if n <= 1 else 2 ** math.ceil(math.log2(n))


def verify_canvas_padding(asset, scale):
    """画布必须正好是「补边前的画布按密度算像素、再对称补到 2 的幂」。

    清单里 `contentSize` 是 Figma 那边的画布，`displaySize` 是补过边的画布，两者由这条
    规则绑定。分叉就说明有一步被手工改过而另一步没跟上——而 `displaySize` 同时是渲染侧
    摆放表的依据，错了会让 HUD 整体错位或缩放，不是报错而是**静默变形**。
    """
    cw, ch = asset["contentSize"]
    dw, dh = asset["displaySize"]
    want = (next_pot(cw * scale) // scale, next_pot(ch * scale) // scale)
    check((dw, dh) == want,
        f"{asset['file']}: 画布应是补边后的 {want[0]}x{want[1]}，"
        f"清单写的是 {dw}x{dh}（补边前的画布是 {cw}x{ch}）")


def verify_mask():
    image = load(MEDIA / MASK_NAME)
    if image is None:
        return
    side = MASK_UNITS * MASK_PX_PER_UNIT
    h, w = image.shape[:2]
    check((w, h) == (side, side), f"{MASK_NAME}: 尺寸应为 {side}，实际 ({w}, {h})")

    alpha = image[:, :, 3]
    mid = w // 2
    # 过渡带是 [mid - 软边 + 1, mid]，两侧之外才该是纯的
    left = alpha[:, :mid - MASK_SOFTNESS_PX + 1]
    right = alpha[:, mid + 1:]
    check(np.all(left == 255), f"{MASK_NAME}: 左半不是全不透明")
    check(np.all(right == 0), f"{MASK_NAME}: 右半不是全透明")

    # 中线必须是单调过渡，且整体从左(255)向右(0)下降；反转即方向错。
    # 取整条过渡带，不是它的一小段——方向反了要能一眼看出来。
    row = alpha[h // 2, max(0, mid - MASK_SOFTNESS_PX):mid + 2]
    check(np.all(np.diff(row) <= 0), f"{MASK_NAME}: 中线过渡不是从左侧不透明向右侧透明的单调下降（可能被镜像翻转）")
    check(row[0] > row[-1], f"{MASK_NAME}: 中线两侧明暗关系反了")

    # 软边宽度必须**不超过**渲染侧预留的余量
    #
    # 渲染侧把切口退到弧起点之前 FILL_MARGIN 度（Logic.lua），正是为了盖住这条软边与
    # 素材描边的余量。两边是一对：软边一旦比余量宽，弧的起点就会重新露边（实机上
    # 出现过 1–2 像素的露边）。这里反向钉住，
    # 常量见 addons/MYUI_CrosshairHUD/Logic.lua 的 Logic.FILL_MARGIN。
    fill_margin_deg = 2.0
    soft_px = int(np.count_nonzero((alpha[h // 2, :mid] > 0) & (alpha[h // 2, :mid] < 255)))
    # 1 像素 = 1 / MASK_PX_PER_UNIT 个设计单位；换算成角度要除以环半径
    soft_deg = np.degrees(soft_px / MASK_PX_PER_UNIT / RING_RADIUS)
    check(soft_deg <= fill_margin_deg,
        f"{MASK_NAME}: 软边 {soft_deg:.2f}° 超过了渲染侧预留的 {fill_margin_deg}° 余量，弧起点会露边")


def main():
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    scale = manifest["exportScale"]
    for asset in manifest["assets"]:
        want = (asset["displaySize"][0] * scale, asset["displaySize"][1] * scale)
        verify_texture(asset["file"], want)
        verify_arc_stroke(asset, scale)
        verify_center_dot(asset, scale)
        verify_shadow_softness(asset)
        verify_edge_softness(asset)
        verify_canvas_padding(asset, scale)
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
