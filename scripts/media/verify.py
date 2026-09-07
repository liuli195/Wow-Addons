from pathlib import Path
import struct

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "assets/EUI_FacetedMedia"
MEDIA = REPO / "addons/EUI_FacetedPortrait/Media"
ASSETS = {
    ROOT / "SharedMedia_MyMedia/statusbar/EUI Faceted Bar.tga": (256, 64),
    ROOT / "SharedMedia_MyMedia/border/EUI Faceted Border.tga": (256, 32),
    MEDIA / "FacetedPowerBar.tga": (256, 64),
    MEDIA / "FacetedHexPortraitBorder.tga": (128, 128),
    MEDIA / "FacetedHexPortraitMask.tga": (128, 128),
    MEDIA / "CrystalRectangularBorder.tga": (1024, 64),
    MEDIA / "CrystalRectangularFill.tga": (256, 64),
    MEDIA / "CrystalSquareFill.tga": (256, 256),
    MEDIA / "CrystalCircularFill.tga": (256, 256),
    MEDIA / "CrystalHexagonalFill.tga": (256, 256),
    MEDIA / "CrystalSquareBorder.tga": (256, 256),
    MEDIA / "CrystalCircularBorder.tga": (256, 256),
    MEDIA / "CrystalHexagonalBorder.tga": (256, 256),
}


def read_tga(path, size):
    data = path.read_bytes()
    assert data[2] == 2, f"{path.name}: must be uncompressed true-color TGA"
    assert struct.unpack("<HH", data[12:16]) == size, f"{path.name}: wrong size"
    assert data[16:18] == bytes((32, 0x08)), f"{path.name}: must be 32-bit bottom-left TGA"
    image = np.asarray(Image.open(path).convert("RGBA"))
    assert np.array_equal(image[:, :, 0], image[:, :, 1]), f"{path.name}: not neutral grayscale"
    assert np.array_equal(image[:, :, 1], image[:, :, 2]), f"{path.name}: not neutral grayscale"
    return image


images = {path: read_tga(path, size) for path, size in ASSETS.items()}

atlas = images[ROOT / "SharedMedia_MyMedia/border/EUI Faceted Border.tga"]
tiles = [atlas[:, x * 32:(x + 1) * 32, 3] for x in range(8)]
assert all(tile.max() == 255 for tile in tiles), "border atlas is missing an edge slice"
assert tiles[4][:16, :16].max() == 0 and tiles[4][16:, 16:].max() == 255, \
    "SharedMedia border is not an eight-slice edge atlas"

health = images[ROOT / "SharedMedia_MyMedia/statusbar/EUI Faceted Bar.tga"]
power = images[MEDIA / "FacetedPowerBar.tga"]
assert health[:, :, 3].min() == 255, "health fill must be opaque"
assert np.array_equal(health, power), "health and power fills must match"

portrait = images[MEDIA / "FacetedHexPortraitBorder.tga"]
mask = images[MEDIA / "FacetedHexPortraitMask.tga"]
assert portrait[64, 64, 3] == 0, "portrait opening must stay transparent"
assert mask[64, 64, 3] == 255 and mask[0, 0, 3] == 0, "portrait mask is invalid"
outer_antialias = (portrait[:, :, 3] > 0) & (portrait[:, :, 3] < 32)
assert portrait[:, :, 0][outer_antialias].max() <= 128, "portrait has a bright alpha fringe"

core = (REPO / "addons/EUI_FacetedPortrait/Core.lua").read_text(encoding="utf-8")
for required in (
    'local BAR_KEY = "sm:EUI Faceted Bar"',
    'local BORDER_KEY = "sm:EUI Faceted Border"',
    "EllesmereUI.ApplyBorderStyle",
    "FacetedHexPortraitBorder.tga",
):
    assert required in core, f"Core.lua missing: {required}"
assert "FacetedHealthFrame.tga" not in core, "single-piece border still distorts when the bar ratio changes"

toc = (REPO / "addons/EUI_FacetedPortrait/EUI_FacetedPortrait.toc").read_text(encoding="utf-8")
assert "## Version: 0.5.1" in toc, "TOC version was not updated"

print("PASS: 13 neutral RGBA assets; WoW TGA headers; eight-slice border atlas; clean portrait alpha fringe.")
