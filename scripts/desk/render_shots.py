#!/usr/bin/env python3
"""Draw the three desk pages at the panel size.

The JC4827 has no screen-capture command. These frames match the pages
uploaded by desk.py: 480×272, stored here at 2× so the README stays sharp.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "images"
LOGO = ROOT / "app" / "src" / "touchy_pad" / "assets" / "touchy-256.png"

W, H = 960, 544
BG = (0, 0, 32)
PANEL = (26, 26, 46)
BTN = (28, 28, 58)
BTN_EDGE = (70, 70, 120)
WHITE = (255, 255, 255)
MUTED = (180, 186, 210)
TOMATO = (226, 61, 40)
CREAM = (242, 210, 196)

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def rounded_button(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, size: int = 28) -> None:
    draw.rounded_rectangle(box, radius=16, fill=BTN, outline=BTN_EDGE, width=2)
    draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), label, font=font(size), fill=WHITE, anchor="mm")


def chrome(base: Image.Image) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, W, H), fill=BG)
    rounded_button(draw, (16, 16, 180, 72), "< Prev", 26)
    rounded_button(draw, (W - 180, 16, W - 16, 72), "Next >", 26)
    return draw


def shot_apps() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    chrome(img)
    draw = ImageDraw.Draw(img)
    labels = ["Zen", "Zed", "Amp", "Ghostty", "Slack", "Mail", "Grok", "Spotify"]
    gap = 14
    top = 92
    left = 16
    cols, rows = 4, 2
    bw = (W - left * 2 - gap * (cols - 1)) // cols
    bh = (H - top - 16 - gap) // rows
    for i, label in enumerate(labels):
        c, r = i % cols, i // cols
        x = left + c * (bw + gap)
        y = top + r * (bh + gap)
        rounded_button(draw, (x, y, x + bw, y + bh), label, 32)
    return img


def shot_tomato() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    chrome(img)
    draw = ImageDraw.Draw(img)
    face = (16, 92, W - 16, 400)
    draw.rounded_rectangle(face, radius=18, fill=PANEL)
    draw.text((W / 2, 120), "Tomato", font=font(36, bold=True), fill=TOMATO, anchor="mt")
    draw.text((W / 2, 180), "25:00", font=font(92, bold=True), fill=WHITE, anchor="mt")
    draw.text((W / 2, 330), "Focus - 0/4 - paused", font=font(28), fill=CREAM, anchor="mt")
    labels = ["Start", "Pause", "Skip", "Reset"]
    gap = 14
    top = 420
    left = 16
    bw = (W - left * 2 - gap * 3) // 4
    bh = 100
    for i, label in enumerate(labels):
        x = left + i * (bw + gap)
        rounded_button(draw, (x, top, x + bw, top + bh), label, 28)
    return img


def shot_trackpad() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    chrome(img)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((16, 92, W - 16, H - 16), radius=24, fill=PANEL)
    logo = Image.open(LOGO).convert("RGB")
    logo.thumbnail((520, 520), Image.Resampling.LANCZOS)
    x = (W - logo.width) // 2
    y = 92 + ((H - 16 - 92) - logo.height) // 2
    img.paste(logo, (x, y))
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = {
        "desk-apps.png": shot_apps(),
        "desk-tomato.png": shot_tomato(),
        "desk-trackpad.png": shot_trackpad(),
    }
    for name, image in shots.items():
        path = OUT / name
        image.save(path, "PNG")
        print(path)


if __name__ == "__main__":
    main()
