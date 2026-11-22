"""Did the screen change around an element? A pixel comparison independent of the page state.

The page-state diff reads the DOM; content revealed with CSS alone (height, opacity,
transform) can leave the DOM text unchanged, so the diff says "nothing happened" when the user
saw something open. Replay verification of a "nothing happens" report therefore also compares
screenshots of the region around the element acted on, before and after the action.

What is compared:
- a band of the screen: the full width, from a quarter of the screen height above the element
  to half the screen height below it (what a click typically reveals: content below the
  control, a menu sliding in from a side);
- minus the element itself and a small margin around it (MASK_MARGIN_PX), where its own focus
  ring, hover and pressed styles are drawn, and the same around the element that had the focus
  before (a field whose focus ring and caret go away when the click moves the focus): those are
  the browser's response to the click, not the app's;
- minus pixels that changed between two "before" screenshots taken a moment apart (a carousel,
  a blinking caret, an animation that runs by itself).

A pixel counts as changed when its brightness differs by more than PIXEL_THRESHOLD (10% of the
range, pixelmatch's default threshold), after a 1-pixel blur of both pictures. That is how
anti-aliasing is ignored, as pixelmatch and Playwright's screenshot comparison do by default:
Chromium on Linux redraws unchanged text with different sub-pixel (coloured) anti-aliasing when
the focus moves, which changed ~1,000 pixels of a page where nothing happened. Brightness
ignores the colour fringes, and the blur averages out edges that moved by a fraction of a
pixel; a real change (new text, a panel) is far larger than one pixel and still shows.

The region changed noticeably when at least MIN_CHANGED_CSS_PX pixels did (in CSS pixels, so
the device's pixel density doesn't matter).
Chromium draws the same page the same way twice (a dead button measured 0 changed pixels
outside its mask), and Playwright's own screenshot assertions count any differing pixel by
default; the floor only absorbs a stray anti-aliased edge. It is an area, not a share of the
screen: the same revealed sentence is 0.8% of a desktop region and 2.6% of a phone's.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageFilter

PIXEL_THRESHOLD = 26  # of 255: 10%, pixelmatch's default
BLUR_PX = 1  # anti-aliasing tolerance
MIN_CHANGED_CSS_PX = 100  # a 10×10 area: about two characters of body text
MASK_MARGIN_PX = 8  # focus rings are 2–4 px wide plus an offset; box-shadow rings similar
ABOVE_SHARE, BELOW_SHARE = 0.25, 0.5  # of the screen height


@dataclass
class RegionChange:
    changed_pixels: int  # device pixels
    compared_pixels: int
    scale: float = 1.0  # device pixels per CSS pixel

    @property
    def share(self) -> float:
        return self.changed_pixels / self.compared_pixels if self.compared_pixels else 0.0

    @property
    def noticeable(self) -> bool:
        return self.changed_pixels / (self.scale**2) >= MIN_CHANGED_CSS_PX

    def describe(self) -> str:
        return (
            f"{self.share:.1%} of the screen region around it changed "
            f"({self.changed_pixels} of {self.compared_pixels} pixels compared)"
        )


def _image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def _changed_mask(a: Image.Image, b: Image.Image) -> Image.Image:
    """1-bit image: white where the blurred brightness differs by more than PIXEL_THRESHOLD."""
    diff = ImageChops.difference(_softened(a), _softened(b))
    return diff.point(lambda v: 255 if v > PIXEL_THRESHOLD else 0).convert("1")


def _softened(image: Image.Image) -> Image.Image:
    """Brightness only, blurred by one pixel: anti-aliasing differences average out."""
    return image.convert("L").filter(ImageFilter.BoxBlur(BLUR_PX))


def region_change(
    before: bytes,
    before_again: bytes,
    after: bytes,
    box: dict,
    viewport: dict,
    also_mask: list[dict] = (),
) -> RegionChange | None:
    """How much of the region around `box` (CSS px, viewport coordinates) changed from
    `before` to `after`, ignoring what changed by itself between `before` and `before_again`,
    `box` itself and the boxes in `also_mask` (each with MASK_MARGIN_PX around it).
    None if the screenshots don't line up (different sizes)."""
    a, a2, b = _image(before), _image(before_again), _image(after)
    if a.size != b.size or a.size != a2.size:
        return None
    scale = a.width / viewport["width"]  # device pixels per CSS pixel
    height = viewport["height"]
    top = max(0, box["y"] - ABOVE_SHARE * height)
    bottom = min(height, box["y"] + box["height"] + BELOW_SHARE * height)
    region = tuple(round(v * scale) for v in (0, top, viewport["width"], bottom))
    if region[3] <= region[1]:
        return None
    changed = _changed_mask(a, b).crop(region)
    by_itself = _changed_mask(a, a2).crop(region)
    compare = Image.new("1", changed.size, 1)
    compare.paste(0, mask=by_itself)  # what moves by itself isn't compared
    m = MASK_MARGIN_PX
    for masked in (box, *also_mask):  # focus, hover and pressed styles
        compare.paste(
            0,
            (
                round((masked["x"] - m) * scale) - region[0],
                round((masked["y"] - m) * scale) - region[1],
                round((masked["x"] + masked["width"] + m) * scale) - region[0],
                round((masked["y"] + masked["height"] + m) * scale) - region[1],
            ),
        )
    counted = ImageChops.logical_and(changed, compare)
    return RegionChange(_white(counted), _white(compare), scale)


def _white(mask: Image.Image) -> int:
    """How many pixels of a 1-bit image are set."""
    return mask.convert("L").histogram()[255]
