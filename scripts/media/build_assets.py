from collections import deque
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageFilter


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "assets/EUI_FacetedMedia"
SOURCE = ROOT / "New-Crystal-Set" / "Final-PNG"
MEDIA = REPO / "addons/EUI_FacetedPortrait/Media"
STATUSBAR = ROOT / "SharedMedia_MyMedia" / "statusbar"
BORDER = ROOT / "SharedMedia_MyMedia" / "border"
RESAMPLE = Image.Resampling.LANCZOS


def load(name):
    image = Image.open(SOURCE / name).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if not box:
        raise ValueError(f"{name}: empty alpha channel")
    return image.crop(box)


def neutral(image):
    rgba = np.asarray(image).copy()
    gray = np.clip(
        rgba[:, :, 0] * 0.2126
        + rgba[:, :, 1] * 0.7152
        + rgba[:, :, 2] * 0.0722,
        0,
        255,
    ).astype(np.uint8)
    rgba[:, :, :3] = gray[:, :, None]
    return Image.fromarray(rgba, "RGBA")


def exact(image, size, opaque=False):
    image = neutral(image).resize(size, RESAMPLE)
    if opaque:
        image.putalpha(255)
    return image


def contain(image, size):
    image = neutral(image)
    image.thumbnail(size, RESAMPLE)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def clean_alpha_fringe(image):
    rgba = np.asarray(image).copy()
    alpha = rgba[:, :, 3]
    faint = (alpha > 0) & (alpha < 32)
    rgba[:, :, :3][faint] = np.minimum(rgba[:, :, :3][faint], 96)
    rgba[alpha < 4] = 0
    return Image.fromarray(rgba, "RGBA")


def edge_atlas(image):
    image = neutral(image)
    rgba = np.asarray(image)
    alpha = rgba[:, :, 3]
    height, width = alpha.shape
    mid_x, mid_y = width // 2, height // 2

    left_run = np.where(alpha[mid_y, :width // 2] > 32)[0]
    right_run = np.where(alpha[mid_y, width // 2:] > 32)[0] + width // 2
    top_run = np.where(alpha[:height // 2, mid_x] > 32)[0]
    bottom_run = np.where(alpha[height // 2:, mid_x] > 32)[0] + height // 2
    if not all((left_run.size, right_run.size, top_run.size, bottom_run.size)):
        raise ValueError("rectangular border has an open edge")

    band = 10
    atlas = Image.new("RGBA", (256, 32), (0, 0, 0, 0))

    def opaque_strip(crop, size):
        strip = neutral(crop).resize(size, RESAMPLE)
        strip.putalpha(255)
        return strip

    left = opaque_strip(image.crop((0, height // 3, left_run[-1] + 1, height * 2 // 3)), (band, 32))
    right = opaque_strip(image.crop((right_run[0], height // 3, width, height * 2 // 3)), (band, 32))
    top = opaque_strip(image.crop((width // 3, 0, width * 2 // 3, top_run[-1] + 1)), (32, band)).rotate(90, expand=True)
    bottom = opaque_strip(image.crop((width // 3, bottom_run[0], width * 2 // 3, height)), (32, band)).rotate(90, expand=True)
    atlas.alpha_composite(left, (16, 0))
    atlas.alpha_composite(right, (32 + 16 - band, 0))
    atlas.alpha_composite(top, (64 + 16, 0))
    atlas.alpha_composite(bottom, (96 + 16 - band, 0))

    cap = min(width // 2, height // 2)
    corners = (
        (image.crop((0, 0, cap, cap)), (128 + 16, 16)),
        (image.crop((width - cap, 0, width, cap)), (160, 16)),
        (image.crop((0, height - cap, cap, height)), (192 + 16, 0)),
        (image.crop((width - cap, height - cap, width, height)), (224, 0)),
    )
    for corner, position in corners:
        atlas.alpha_composite(corner.resize((16, 16), RESAMPLE), position)
    return atlas


def horizontal_nine_slice(image, size):
    image = neutral(image)
    scaled_width = max(3, round(image.width * size[1] / image.height))
    image = image.resize((scaled_width, size[1]), RESAMPLE)
    cap = min(size[0] // 2, image.width // 3)
    left = image.crop((0, 0, cap, size[1]))
    middle = image.crop((cap, 0, image.width - cap, size[1]))
    right = image.crop((image.width - cap, 0, image.width, size[1]))
    middle = middle.resize((size[0] - cap * 2, size[1]), RESAMPLE)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(left, (0, 0))
    canvas.alpha_composite(middle, (cap, 0))
    canvas.alpha_composite(right, (size[0] - cap, 0))
    return canvas


def opening_mask(border):
    alpha = np.asarray(border.getchannel("A"))
    clear = alpha < 32
    outside = np.zeros(clear.shape, dtype=bool)
    queue = deque()
    height, width = clear.shape
    for x in range(width):
        for y in (0, height - 1):
            if clear[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if clear[y, x] and not outside[y, x]:
                outside[y, x] = True
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and clear[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                queue.append((nx, ny))
    opening = Image.fromarray((clear & ~outside).astype(np.uint8) * 255, "L")
    opening = opening.filter(ImageFilter.MaxFilter(5))
    mask = Image.new("RGBA", border.size, (255, 255, 255, 0))
    mask.putalpha(opening)
    return mask


def save_tga(path, image):
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    height, width = rgba.shape[:2]
    header = struct.pack(
        "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0,
        width, height, 32, 0x08,
    )
    payload = rgba[::-1, :, [2, 1, 0, 3]].tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + payload)


def main():
    rectangle_border = load("01-Rectangular-Border.png")
    rectangle_fill = load("02-Rectangular-Fill.png")
    hex_border = clean_alpha_fringe(contain(load("08-Hexagonal-Border.png"), (128, 128)))

    bar = exact(rectangle_fill, (256, 64), opaque=True)
    frame = horizontal_nine_slice(rectangle_border, (1024, 64))

    save_tga(STATUSBAR / "EUI Faceted Bar.tga", bar)
    save_tga(BORDER / "EUI Faceted Border.tga", edge_atlas(rectangle_border))
    save_tga(MEDIA / "FacetedPowerBar.tga", bar)
    save_tga(MEDIA / "FacetedHexPortraitBorder.tga", hex_border)
    save_tga(MEDIA / "FacetedHexPortraitMask.tga", opening_mask(hex_border))

    extras = {
        "CrystalRectangularBorder.tga": frame,
        "CrystalRectangularFill.tga": bar,
        "CrystalSquareFill.tga": contain(load("03-Square-Fill.png"), (256, 256)),
        "CrystalCircularFill.tga": contain(load("04-Circular-Fill.png"), (256, 256)),
        "CrystalHexagonalFill.tga": contain(load("05-Hexagonal-Fill.png"), (256, 256)),
        "CrystalSquareBorder.tga": contain(load("06-Square-Border.png"), (256, 256)),
        "CrystalCircularBorder.tga": contain(load("07-Circular-Border-v2.png"), (256, 256)),
        "CrystalHexagonalBorder.tga": contain(load("08-Hexagonal-Border.png"), (256, 256)),
    }
    for name, image in extras.items():
        save_tga(MEDIA / name, image)

    print(f"Built {5 + len(extras)} WoW TGA assets from New-Crystal-Set.")


if __name__ == "__main__":
    main()
