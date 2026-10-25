#!/usr/bin/env python3
"""Desk pages for the JC4827W543.

Pages, in prev/next order: apps, tomato, trackpad, usage.

``setup`` uploads the chrome, the ITMAN logo, and the three page bodies:

* ``F:host/uscr/apps.pb``    — eight Tuna hyper-key icon buttons
* ``F:host/uscr/tomato.pb``  — tomato clock face and controls
* ``F:host/uscr/trackpad.pb`` — multitouch trackpad on the logo

``setup`` also uploads the icons under ``F:host/images/apps/``. ``apps``
re-uploads just the icons and that page, then brings it to the front, so the
page can be refreshed without touching the other two.

``clock`` keeps the tomato digits moving. Leave that process running.
The app keys do not need it. Tuna must be running for those keys,
because each one sends the hyper chord from ``config.toml``.

``pulse`` writes the Token Pulse page from a local CodexBar server.
Leave that process running too. Start the server first::

    codexbar serve --host 127.0.0.1 --port 8080 --refresh-interval 60 --identity redacted

From the ``app`` directory::

    poetry run python ../scripts/desk/desk.py setup
    poetry run python ../scripts/desk/desk.py apps
    poetry run python ../scripts/desk/desk.py clock
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

import usb.core
from touchy_pad.api import (
    Layer,
    LvState,
    TextAlign,
    build_default_screen,
    button,
    cell,
    col,
    grid,
    grow,
    hid_keys,
    host_action,
    image_button,
    label,
    macro_action,
    protobuf,
    row,
    spacer,
    style,
    touchy_open,
)
from touchy_pad.api.errors import TouchyError
from touchy_pad.api.images import make_touchy_png
from touchy_pad.api.macros import key_tap, set_delay
from touchy_pad.pages.trackpad import build as build_trackpad

from pulse import pulse_loop

LOGO_PATH = "F:host/images/touchy.png"
SOUND = "/System/Library/Sounds/Glass.aiff"

# ctrl+opt+shift+cmd. Tuna stores this as carbonModifiers 6912.
HYPER = hid_keys.MOD_LCTRL | hid_keys.MOD_LSHIFT | hid_keys.MOD_LALT | hid_keys.MOD_LGUI

# Live [[hotkeys.custom]] bindings. Combo mode is off, so these chords
# are the ones that open an app.
APPS = [
    ("zen", "Zen", hid_keys.KEY_E),
    ("zed", "Zed", hid_keys.KEY_C),
    ("amp", "Amp", hid_keys.KEY_A),
    ("ghostty", "Ghostty", hid_keys.KEY_TAB),
    ("slack", "Slack", hid_keys.KEY_S),
    ("mail", "Mail", hid_keys.KEY_M),
    ("grok", "Grok", hid_keys.KEY_B),
    ("spotify", "Spotify", hid_keys.KEY_R),
]

FOCUS_S = 25 * 60
SHORT_S = 5 * 60
LONG_S = 15 * 60
PHASE_LABEL = {"focus": "Focus", "short": "Short break", "long": "Long break"}

# Icons are transparent outside the artwork. The button fill matches the
# screen (display.cpp uses 0x000020), so a key has no plate of its own.
SCREEN = 0x000020
ICON_DIR = Path(__file__).resolve().parent / "icons"


def _app_icon_path(wid: str) -> str:
    return f"F:host/images/apps/{wid}.png"


def _clear_key() -> list:
    # Same colour pressed and released, no border or shadow, so the only
    # paint is the transparent icon on the screen.
    return [
        style(bg_color=SCREEN, radius=0, border_w=0, pad=0, shadow_width=0),
        style(
            bg_color=SCREEN,
            radius=0,
            border_w=0,
            pad=0,
            shadow_width=0,
            for_state=LvState.STATE_PRESSED,
        ),
    ]


def upload_app_icons(pad) -> None:
    for wid, _caption, _key in APPS:
        path = _app_icon_path(wid)
        pad.file_save(path, (ICON_DIR / f"{wid}.png").read_bytes())
        print(f"saved {path}", flush=True)


def build_apps_page() -> protobuf.Widget:
    page = Layer(layout=grid(cols=4, rows=2, gap=6))
    for i, (wid, _caption, key) in enumerate(APPS):
        page += cell(
            image_button(
                wid,
                asset=_app_icon_path(wid),
                pressed_scale=0.92,
                on_click=macro_action([set_delay(40), key_tap(key, HYPER)]),
                style=_clear_key(),
            ),
            col=i % 4,
            row=i // 4,
            grow_x=1,
            grow_y=1,
        )
    widget = protobuf.Widget()
    page.copy_into(widget)
    widget.id = "apps"
    return widget


def _fmt(seconds: float) -> str:
    whole = max(0, int(seconds + 0.999)) if seconds > 0 else 0
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _chime(message: str) -> None:
    subprocess.Popen(
        ["osascript", "-e", f'display notification "{message}" with title "Tomato"'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(["afplay", SOUND], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Clock:
    def __init__(self) -> None:
        self.phase = "focus"
        self.remaining = float(FOCUS_S)
        self.running = False
        self.done = 0
        self._deadline = 0.0

    def status(self) -> str:
        text = f"{PHASE_LABEL[self.phase]} - {self.done}/4"
        if not self.running:
            text += " - paused"
        return text

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._deadline = time.monotonic() + self.remaining

    def pause(self) -> None:
        if not self.running:
            return
        self.remaining = max(0.0, self._deadline - time.monotonic())
        self.running = False

    def reset(self) -> None:
        self.phase = "focus"
        self.remaining = float(FOCUS_S)
        self.running = False
        self.done = 0

    def skip(self) -> str | None:
        was_running = self.running
        note = self._advance()
        self.running = was_running
        if self.running:
            self._deadline = time.monotonic() + self.remaining
        return note

    def tick(self) -> str | None:
        if not self.running:
            return None
        self.remaining = self._deadline - time.monotonic()
        if self.remaining > 0:
            return None
        note = self._advance()
        self._deadline = time.monotonic() + self.remaining
        return note

    def _advance(self) -> str:
        if self.phase == "focus":
            self.done += 1
            if self.done >= 4:
                self.phase = "long"
                self.remaining = float(LONG_S)
                return "Four tomatoes. Long break."
            self.phase = "short"
            self.remaining = float(SHORT_S)
            return f"Tomato {self.done}/4 done. Short break."
        self.phase = "focus"
        self.remaining = float(FOCUS_S)
        if self.done >= 4:
            self.done = 0
        return "Break over. Focus."


def build_tomato_page(commands: queue.Queue[str], clock: Clock) -> protobuf.Widget:
    def enqueue(name: str):
        def _on_event(_evt) -> None:
            commands.put(name)

        return _on_event

    # Labels, not a bitmap. The four buttons below are labels too, and
    # those are the widgets that actually show on this panel. The clock
    # face image uploaded to T: but never appeared. Montserrat 30 is the
    # largest font this firmware has.
    page = Layer(layout=col(gap=6))
    page += grow(spacer("clock_above"), y=1)
    page += grow(
        label(
            "title",
            "Tomato",
            font_size=16,
            text_align=TextAlign.CENTER,
            style=style(text_color=0xE23D28),
        ),
        x=1,
    )
    page += grow(
        label(
            "clock",
            _fmt(clock.remaining),
            font_size=30,
            text_align=TextAlign.CENTER,
            rect=protobuf.Rect(h=48),
            style=style(text_color=0xFFFFFF),
        ),
        x=1,
    )
    page += grow(
        label(
            "status",
            clock.status(),
            font_size=16,
            text_align=TextAlign.CENTER,
            style=style(text_color=0xF2D2C4),
        ),
        x=1,
    )
    page += grow(spacer("clock_below"), y=1)
    controls = Layer(layout=row(gap=8))
    for wid, text in (
        ("start", "Start"),
        ("pause", "Pause"),
        ("skip", "Skip"),
        ("reset", "Reset"),
    ):
        controls += grow(
            button(
                wid,
                text=text,
                on_click=host_action(on_event=enqueue(wid)),
                style=style(font_size=16),
            ),
            x=1,
        )
    controls_widget = protobuf.Widget()
    controls.copy_into(controls_widget)
    controls_widget.id = "controls"
    page += grow(controls_widget, x=1)
    widget = protobuf.Widget()
    page.copy_into(widget)
    widget.id = "tomato"
    return widget


def setup() -> None:
    with touchy_open() as pad:
        info = pad.board_info
        print(f"board {info.board_name}  firmware {info.firmware_version_str}", flush=True)
        pad.screen_save(build_default_screen())
        print("saved F:host/s/default.pb", flush=True)
        logo = make_touchy_png()
        pad.file_save(LOGO_PATH, logo, max_width=256, max_height=256)
        print(f"saved {LOGO_PATH} ({len(logo)} bytes)", flush=True)
        _, trackpad = build_trackpad(LOGO_PATH)
        pad.user_screen_save("trackpad", trackpad)
        print("saved F:host/uscr/trackpad.pb", flush=True)
        upload_app_icons(pad)
        pad.user_screen_save("apps", build_apps_page())
        print("saved F:host/uscr/apps.pb", flush=True)
        # Tomato body is uploaded again by `clock`, which owns the buttons.
        # Save a still face here so the page exists before that process starts.
        pad.user_screen_save("tomato", build_tomato_page(queue.Queue(), Clock()))
        print("saved F:host/uscr/tomato.pb", flush=True)
        pad.show_user_screen("apps")
        print("showing apps", flush=True)


def _link_lost(exc: BaseException) -> bool:
    """True when the USB cable dropped or the pad is not plugged in."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, usb.core.USBError):
            return True
        if type(current).__name__ == "DeviceNotFoundError":
            return True
        errno = getattr(current, "errno", None)
        if isinstance(current, OSError) and errno in {5, 19}:
            return True
        current = current.__cause__ or current.__context__
    return False


def _save_tomato(pad, commands: queue.Queue[str], clock: Clock, drive: str) -> str:
    return pad.user_screen_save("tomato", build_tomato_page(commands, clock), drive=drive)


def _serve_clock(commands: queue.Queue[str], clock: Clock) -> None:
    # Rewriting tomato.pb rebuilds the page body in place, which is what
    # makes the label text change. set_property does not reach a label
    # inside a swapped user page.
    # Flash can refuse every F: write after a close with the wrong handle.
    # RAM (R:) still accepts the page, so the digits can show until a reset
    # clears that transaction and the next connection writes flash again.
    shown = ""
    drive = "F"
    visible = ""
    # A page rebuild can deliver a click that was already on the glass.
    ignore_until = time.monotonic() + 1.5
    last_poke = 0.0
    with touchy_open() as pad:
        info = pad.board_info
        print(f"board {info.board_name}  firmware {info.firmware_version_str}", flush=True)
        pad.client.screen_wake()
        print("backlight on", flush=True)
        while True:
            thread = pad._thread
            if thread is not None and not thread.is_alive() and not pad._stop.is_set():
                raise usb.core.USBError("event thread stopped")
            now = time.monotonic()
            if now - last_poke > 2:
                pad.client.screen_wake()
                last_poke = now
            notes: list[str] = []
            while True:
                try:
                    cmd = commands.get_nowait()
                except queue.Empty:
                    break
                if time.monotonic() < ignore_until:
                    continue
                if cmd == "start":
                    clock.start()
                elif cmd == "pause":
                    clock.pause()
                elif cmd == "skip":
                    note = clock.skip()
                    if note:
                        notes.append(note)
                elif cmd == "reset":
                    clock.reset()
            note = clock.tick()
            if note:
                notes.append(note)
            for item in notes:
                print(f"phase {item}", flush=True)
                threading.Thread(target=_chime, args=(item,), daemon=True).start()
            current = f"{_fmt(clock.remaining)} {clock.status()}"
            if current != shown or drive != visible:
                try:
                    path = _save_tomato(pad, commands, clock, drive)
                except TouchyError as exc:
                    if drive == "F" and exc.code_name == "IO_ERROR":
                        print(
                            "flash write is stuck. Showing the clock from RAM. "
                            "Tap RST once, and do not hold BOOT, so this page can be stored.",
                            flush=True,
                        )
                        drive = "R"
                        path = _save_tomato(pad, commands, clock, "R")
                    else:
                        raise
                print(f"saved {path}", flush=True)
                if os.environ.get("TOUCHY_TOMATO_SHOW", "1") != "0" and drive != visible:
                    pad.show_user_screen("tomato", drive=drive)
                    ignore_until = time.monotonic() + 1.5
                    print(f"showing {path}", flush=True)
                elif not visible:
                    print("tomato page saved; current page left up", flush=True)
                else:
                    print(f"tick {current}", flush=True)
                if not shown:
                    print(f"ready {current}", flush=True)
                visible = drive
                shown = current
            time.sleep(0.2)


def clock_loop() -> None:
    commands: queue.Queue[str] = queue.Queue()
    clock = Clock()
    remain = os.environ.get("TOUCHY_TOMATO_REMAINING")
    if remain:
        clock.remaining = float(remain)
    done = os.environ.get("TOUCHY_TOMATO_DONE")
    if done:
        clock.done = int(done)
    if os.environ.get("TOUCHY_TOMATO_RUNNING") == "1":
        clock.start()
    while True:
        try:
            _serve_clock(commands, clock)
        except Exception as exc:
            if not _link_lost(exc):
                raise
            print(
                f"pad link lost ({exc}). Check the USB data cable. Retrying.",
                flush=True,
            )
            time.sleep(1)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("touchy_pad.device").setLevel(logging.INFO)
    parser = argparse.ArgumentParser(description="JC4827 desk pages")
    parser.add_argument("command", choices=("setup", "clock", "apps", "pulse"))
    args = parser.parse_args()
    if args.command == "setup":
        setup()
    elif args.command == "pulse":
        pulse_loop()
    elif args.command == "apps":
        with touchy_open() as pad:
            pad.client.screen_wake()
            upload_app_icons(pad)
            pad.user_screen_save("apps", build_apps_page())
            pad.show_user_screen("apps")
            print("showing apps", flush=True)
    else:
        clock_loop()


if __name__ == "__main__":
    main()
