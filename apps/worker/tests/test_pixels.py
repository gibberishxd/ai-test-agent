"""The pixel comparison around an element, on synthetic images."""

import io

from PIL import Image, ImageDraw

from worker.pixels import region_change

VIEWPORT = {"width": 200, "height": 200}
BOX = {"x": 80, "y": 40, "width": 40, "height": 20}


def png(draw=None) -> bytes:
    image = Image.new("RGB", (200, 200), "white")
    if draw:
        draw(ImageDraw.Draw(image))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_no_change():
    blank = png()
    change = region_change(blank, blank, blank, BOX, VIEWPORT)
    assert change.changed_pixels == 0 and not change.noticeable


def test_a_panel_opening_below_the_element_is_noticeable():
    after = png(lambda d: d.rectangle([10, 80, 190, 140], fill="black"))
    change = region_change(png(), png(), after, BOX, VIEWPORT)
    assert change.noticeable


def test_the_elements_own_focus_ring_is_ignored():
    ring = png(lambda d: d.rectangle([74, 34, 126, 66], outline="blue", width=4))
    assert not region_change(png(), png(), ring, BOX, VIEWPORT).noticeable


def test_something_that_moves_by_itself_is_ignored():
    def spinner(color):
        return png(lambda d: d.rectangle([10, 100, 60, 150], fill=color))

    dark, mid, light = (20, 20, 20), (128, 128, 128), (235, 235, 235)
    change = region_change(spinner(dark), spinner(mid), spinner(light), BOX, VIEWPORT)
    assert not change.noticeable


def test_a_change_far_below_the_region_is_ignored():
    # The region ends half a screen below the element (y = 60 + 100 = 160).
    after = png(lambda d: d.rectangle([0, 170, 199, 199], fill="black"))
    assert not region_change(png(), png(), after, BOX, VIEWPORT).noticeable


def test_a_few_changed_pixels_are_not_noticeable_but_a_word_is():
    stray = png(lambda d: d.rectangle([10, 100, 14, 104], fill="black"))  # 25 px
    word = png(lambda d: d.rectangle([10, 100, 39, 109], fill="black"))  # 300 px
    assert not region_change(png(), png(), stray, BOX, VIEWPORT).noticeable
    assert region_change(png(), png(), word, BOX, VIEWPORT).noticeable


def test_coloured_anti_aliasing_fringes_are_not_a_change():
    # Chromium on Linux redraws unchanged text with different sub-pixel (coloured) edges when
    # the focus moves: the colour changes a lot, the brightness hardly at all.
    def word(fringe):
        def draw(d):
            d.rectangle([20, 100, 60, 110], fill="black")
            d.line([19, 100, 19, 110], fill=fringe)
            d.line([61, 100, 61, 110], fill=fringe)

        return png(draw)

    reddish, bluish = (200, 150, 150), (150, 150, 200)
    change = region_change(word(reddish), word(reddish), word(bluish), BOX, VIEWPORT)
    assert change.changed_pixels == 0
