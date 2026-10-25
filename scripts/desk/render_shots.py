#!/usr/bin/env python3
"""Draw the desk pages at the panel size.

The JC4827 has no screen-capture command. These frames match the pages
from desk.py: 480×272, stored here at 2× so the README stays sharp.
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
MUTED = (161, 161, 170)
TOMATO = (226, 61, 40)
CREAM = (242, 210, 196)
TEAL = (45, 212, 191)
INK = (244, 244, 245)
ICONS = Path(__file__).resolve().parent / "icons"

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
    names = ["zen", "zed", "amp", "ghostty", "slack", "mail", "grok", "spotify"]
    gap = 12
    top = 96
    left = 16
    cols, rows = 4, 2
    bw = (W - left * 2 - gap * (cols - 1)) // cols
    bh = (H - top - 16 - gap) // rows
    for i, name in enumerate(names):
        icon = Image.open(ICONS / f"{name}.png").convert("RGBA")
        icon.thumbnail((bw - 24, bh - 24), Image.Resampling.LANCZOS)
        c, r = i % cols, i // cols
        x = left + c * (bw + gap) + (bw - icon.width) // 2
        y = top + r * (bh + gap) + (bh - icon.height) // 2
        img.paste(icon, (x, y), icon)
    return img


def shot_usage() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    chrome(img)
    draw = ImageDraw.Draw(img)
    draw.text((W / 2, 96), "Token Pulse", font=font(32, bold=True), fill=WHITE, anchor="mt")
    draw.text((W / 2, 142), "30 days  761k tokens", font=font(28), fill=MUTED, anchor="mt")
    rows = [
        ("Copilot", "22% left", TEAL),
        ("Grok", "35% left", TEAL),
        ("Zed", "66% left", TEAL),
        ("Amp", "91% left", TEAL),
        ("Codex", "99% left, 646 cr", TEAL),
    ]
    y = 196
    for name, value, color in rows:
        draw.text((36, y), name, font=font(28), fill=INK, anchor="lt")
        draw.text((W - 36, y), value, font=font(28), fill=color, anchor="rt")
        y += 52
    return img


def shot_tomato() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    chrome(img)
    draw = ImageDraw.Draw(img)
    draw.text((W / 2, 110), "Tomato", font=font(32, bold=True), fill=TOMATO, anchor="mt")
    draw.text((W / 2, 168), "25:00", font=font(92, bold=True), fill=WHITE, anchor="mt")
    draw.text((W / 2, 290), "Focus - 0/4 - paused", font=font(28), fill=CREAM, anchor="mt")
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
        "desk-usage.png": shot_usage(),
        "desk-tomato.png": shot_tomato(),
        "desk-trackpad.png": shot_trackpad(),
    }
    for name, image in shots.items():
        path = OUT / name
        image.save(path, "PNG")
        print(path)


if __name__ == "__main__":
    main()
