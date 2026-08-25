from PIL import Image, ImageDraw

from app.extractors.preprocessing import analyze_image, invert, select_preprocess_plan


def _selected_steps(image: Image.Image):
    quality = analyze_image(image)
    return quality, select_preprocess_plan(image, quality).steps


def test_dark_background_with_small_bright_text_shapes_is_inverted():
    image = Image.new("RGB", (600, 400), "black")
    draw = ImageDraw.Draw(image)
    for row in range(8):
        for column in range(10):
            x = 40 + column * 50
            y = 40 + row * 35
            draw.rectangle((x, y, x + 25, y + 5), fill="white")

    quality, steps = _selected_steps(image)

    assert quality.dark_background is True
    assert invert in steps


def test_large_white_document_on_dark_background_is_not_inverted():
    image = Image.new("RGB", (600, 400), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 100, 449, 299), fill="white")
    for y in range(125, 285, 25):
        draw.rectangle((180, y, 410, y + 4), fill="black")

    quality, steps = _selected_steps(image)

    assert quality.dark_background is False
    assert invert not in steps


def test_white_document_on_colored_photo_background_is_not_inverted():
    image = Image.new("RGB", (600, 400), (75, 45, 25))
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 90, 500, 350), fill="white")
    for y in range(120, 330, 24):
        draw.rectangle((155, y, 465, y + 4), fill="black")

    quality, steps = _selected_steps(image)

    assert quality.dark_background is False
    assert invert not in steps
