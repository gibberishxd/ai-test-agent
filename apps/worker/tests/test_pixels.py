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

    change = region_change(spinner("red"), spinner("green"), spinner("blue"), BOX, VIEWPORT)
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
