"""Token Pulse page for the desk pad.

Polls a local CodexBar server and writes ``F:host/uscr/usage.pb``. The
layout matches the token-pulse board: one total, then each provider that
is actually in use. An empty plan (``0/0`` credits, or nothing remaining)
stays off the page. Rose means under 20% left. Teal is the rest.

Start the server first::

    codexbar serve --host 127.0.0.1 --port 8899 --refresh-interval 60 --identity redacted

Then ``python scripts/desk/desk.py pulse``. The pad cannot see
127.0.0.1, so this process has to stay running to refresh the page.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import usb.core
from touchy_pad.api import (
    Layer,
    TextAlign,
    col,
    grow,
    label,
    protobuf,
    row,
    spacer,
    style,
    touchy_open,
)
from touchy_pad.api.errors import TouchyError

CODEXBAR_URL = os.environ.get("CODEXBAR_URL", "http://127.0.0.1:8899").rstrip("/")
POLL_S = 60
MAX_ROWS = 6
LOW_REMAINING = 20
SCREEN = "usage"

ROSE = 0xFB7185
TEAL = 0x2DD4BF
INK = 0xF4F4F5
MUTED = 0xA1A1AA

_NAMES = {
    "amp": "Amp",
    "claude": "Claude",
    "codebuff": "Codebuff",
    "codex": "Codex",
    "copilot": "Copilot",
    "cursor": "Cursor",
    "gemini": "Gemini",
    "grok": "Grok",
    "kilo": "Kilo",
    "opencodego": "OpenCode",
    "openrouter": "OpenRouter",
    "pi": "Pi",
    "zed": "Zed",
}


@dataclass(frozen=True)
class UsageRow:
    provider: str
    name: str
    value: str
    low: bool


@dataclass(frozen=True)
class UsageSnapshot:
    summary: str
    rows: tuple[UsageRow, ...]

    def key(self) -> str:
        body = "|".join(f"{row.provider}:{row.value}:{row.low}" for row in self.rows)
        return f"{self.summary}|{body}"


def _provider_name(provider: str) -> str:
    return _NAMES.get(provider, provider[:1].upper() + provider[1:])


def _fmt_count(value: float) -> str:
    number = abs(value)
    if number >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if number >= 1_000_000:
        return f"{value / 1_000_000:.0f}M" if number >= 10_000_000 else f"{value / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{value / 1_000:.0f}k" if number >= 10_000 else f"{value / 1_000:.1f}k"
    return str(int(value))


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _windows(usage: dict) -> list[float]:
    found: list[float] = []
    for key in ("primary", "secondary", "tertiary"):
        window = usage.get(key)
        if not isinstance(window, dict):
            continue
        used = _as_float(window.get("usedPercent"))
        if used is not None:
            found.append(used)
    return found


def _empty_account(usage: dict) -> bool:
    """CodexBar marks an unused plan as 100% used with no balance."""
    texts: list[str] = []
    for key in ("primary", "secondary", "tertiary"):
        window = usage.get(key)
        if isinstance(window, dict):
            desc = window.get("resetDescription")
            if isinstance(desc, str):
                texts.append(desc.lower())
    login = usage.get("loginMethod")
    if isinstance(login, str):
        texts.append(login.lower())
    blob = " ".join(texts)
    return "0/0" in blob or "0 remaining" in blob


def _credits(item: dict, usage: dict) -> float | None:
    cost = usage.get("providerCost")
    if isinstance(cost, dict) and cost.get("currencyCode") == "Credits":
        balance = _as_float(cost.get("balance"))
        if balance is not None:
            return balance
    credits = item.get("credits")
    if isinstance(credits, dict):
        return _as_float(credits.get("remaining"))
    return None


def _percent_row(
    provider: str, name: str, used: float, credits: float | None
) -> tuple[float, UsageRow]:
    remaining = max(0.0, 100.0 - used)
    value = f"{remaining:.0f}% left"
    if credits is not None and credits > 0:
        value = f"{value}, {_fmt_count(credits)} cr"
    return (
        remaining,
        UsageRow(provider, name, value, remaining < LOW_REMAINING),
    )


def summarize(usage_payload: object, cost_payload: object) -> UsageSnapshot:
    """List providers in use, tightest first, and sum their 30-day tokens."""
    items = usage_payload if isinstance(usage_payload, list) else []
    best: dict[str, tuple[float | None, float | None]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        provider = item.get("provider")
        if not isinstance(provider, str) or not provider:
            continue
        usage = item.get("usage") if isinstance(item.get("usage"), dict) else {}
        if _empty_account(usage):
            continue
        windows = _windows(usage)
        used = max(windows) if windows else None
        credits = _credits(item, usage)
        prev_used, prev_credits = best.get(provider, (None, None))
        if used is None:
            used = prev_used
        elif prev_used is not None:
            used = max(used, prev_used)
        if credits is None:
            credits = prev_credits
        best[provider] = (used, credits)

    percent_rows: list[tuple[float, UsageRow]] = []
    credit_rows: list[tuple[float, UsageRow]] = []
    active: set[str] = set()
    for provider, (used, credits) in best.items():
        name = _provider_name(provider)
        if used is not None and used > 0:
            percent_rows.append(_percent_row(provider, name, used, credits))
            active.add(provider)
            continue
        if credits is not None and credits > 0:
            credit_rows.append(
                (credits, UsageRow(provider, name, f"{_fmt_count(credits)} cr", False))
            )
            active.add(provider)

    percent_rows.sort(key=lambda item: item[0])
    credit_rows.sort(key=lambda item: item[0], reverse=True)
    slots = MAX_ROWS - (1 if credit_rows and percent_rows else 0)
    chosen = [row for _remaining, row in percent_rows[:slots]]
    if credit_rows:
        chosen.append(credit_rows[0][1])
    if not percent_rows:
        chosen = [row for _credits, row in credit_rows[:MAX_ROWS]]

    tokens = 0.0
    costs = cost_payload if isinstance(cost_payload, list) else []
    for item in costs:
        if not isinstance(item, dict):
            continue
        provider = item.get("provider")
        if provider not in active:
            continue
        amount = _as_float(item.get("last30DaysTokens"))
        if amount is not None:
            tokens += amount
    summary = f"30 days  {_fmt_count(tokens)} tokens" if tokens else "30 days  no token total"
    return UsageSnapshot(summary, tuple(chosen))


def _fetch_json(path: str) -> object:
    request = urllib.request.Request(f"{CODEXBAR_URL}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def fetch_snapshot() -> UsageSnapshot:
    try:
        usage = _fetch_json("/usage?provider=all")
        cost = _fetch_json("/cost")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return UsageSnapshot("CodexBar offline", ())
    return summarize(usage, cost)


def _line(item: UsageRow) -> protobuf.Widget:
    color = ROSE if item.low else TEAL
    line = Layer(layout=row(gap=8))
    line += label(
        f"{item.provider}_name",
        item.name,
        font_size=16,
        style=style(text_color=INK),
    )
    line += grow(spacer(f"{item.provider}_gap"), x=1)
    line += label(
        f"{item.provider}_value",
        item.value,
        font_size=16,
        style=style(text_color=color),
    )
    widget = protobuf.Widget()
    line.copy_into(widget)
    widget.id = item.provider
    return grow(widget, x=1)


def build_usage_page(snapshot: UsageSnapshot) -> protobuf.Widget:
    page = Layer(layout=col(gap=6))
    page += grow(
        label(
            "title",
            "Token Pulse",
            font_size=16,
            text_align=TextAlign.CENTER,
            style=style(text_color=0xFFFFFF),
        ),
        x=1,
    )
    page += grow(
        label(
            "summary",
            snapshot.summary,
            font_size=16,
            text_align=TextAlign.CENTER,
            style=style(text_color=MUTED),
        ),
        x=1,
    )
    if snapshot.rows:
        for row_item in snapshot.rows:
            page += _line(row_item)
    else:
        page += grow(
            label(
                "empty",
                "No provider limits yet",
                font_size=16,
                text_align=TextAlign.CENTER,
                style=style(text_color=MUTED),
            ),
            x=1,
        )
    page += grow(spacer("usage_below"), y=1)
    widget = protobuf.Widget()
    page.copy_into(widget)
    widget.id = SCREEN
    return widget


def _link_lost(exc: BaseException) -> bool:
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


def _save(pad, snapshot: UsageSnapshot, drive: str) -> str:
    return pad.user_screen_save(SCREEN, build_usage_page(snapshot), drive=drive)


def _serve() -> None:
    shown = ""
    drive = "F"
    visible = False
    with touchy_open() as pad:
        pad.client.screen_wake()
        print("backlight on", flush=True)
        while True:
            thread = pad._thread
            if thread is not None and not thread.is_alive() and not pad._stop.is_set():
                raise usb.core.USBError("event thread stopped")
            snapshot = fetch_snapshot()
            current = snapshot.key()
            if current != shown:
                try:
                    path = _save(pad, snapshot, drive)
                except TouchyError as exc:
                    if drive == "F" and exc.code_name == "IO_ERROR":
                        print(
                            "flash write is stuck. Showing Token Pulse from RAM. "
                            "Tap RST once, and do not hold BOOT, so this page can be stored.",
                            flush=True,
                        )
                        drive = "R"
                        path = _save(pad, snapshot, "R")
                    else:
                        raise
                print(f"saved {path}  {snapshot.summary}", flush=True)
                for row_item in snapshot.rows:
                    print(f"  {row_item.name}  {row_item.value}", flush=True)
                if not visible and os.environ.get("TOUCHY_PULSE_SHOW", "1") != "0":
                    pad.show_user_screen(SCREEN, drive=drive)
                    print(f"showing {path}", flush=True)
                visible = True
                shown = current
            time.sleep(POLL_S)


def pulse_loop() -> None:
    while True:
        try:
            _serve()
        except TouchyError as exc:
            if exc.code_name == "IO_ERROR":
                print(
                    "flash write is stuck. Tap RST once, and do not hold BOOT, then run pulse again.",
                    flush=True,
                )
                return
            raise
        except Exception as exc:
            if not _link_lost(exc):
                raise
            print(f"pad link lost ({exc}). Check the USB data cable. Retrying.", flush=True)
            time.sleep(1)
