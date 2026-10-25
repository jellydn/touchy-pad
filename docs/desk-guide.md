# Desk pages on the JC4827W543

This is the setup that is on the pad: firmware from [geeksville/touchy-pad](https://github.com/geeksville/touchy-pad), then three pages loaded over USB.

The script is [`scripts/desk/desk.py`](../scripts/desk/desk.py).

## What you need

- A **USB data cable** in the USB-C port on the JC4827W543. A charge-only cable lights the panel and never shows up on the Mac. There is one USB-C port; it is wired to the ESP32-S3.
- While the app is running the Mac names the board **Touchy-Pad** / Geeksville. That is the link the pages and the tomato clock use. It is not a serial port, so `ls /dev/cu.*` does not list the board.
- To flash, hold **BOOT**, tap **RST**, and release **BOOT**. The ROM serial port then appears as `/dev/cu.usbmodem*`. `just up` lists `/dev/cu.*` and writes the built image to that port.
- Python 3.11–3.14 and Poetry, from the `app` directory. Pillow is already a dependency.
- Tuna running, with the hyper chords in `~/Projects/dotfiles/macos/.config/tuna/config.toml`. Hyper is `ctrl+opt+shift+cmd`.
- macOS, for the tomato chime (`afplay` and `osascript`) and the fonts the clock face uses.

## Load the three pages

Stop a running `clock` process first. It holds the USB command link.

```bash
cd app
poetry install
poetry run python ../scripts/desk/desk.py setup
```

`setup` writes these files, then shows the apps page:

1. `F:host/s/default.pb` — the prev/next bar and a page body.
2. `F:host/images/touchy.png` — the ITMAN logo, stored on the pad as `touchy.bin` at 256 pixels. The source file is `app/src/touchy_pad/assets/touchy-256.png`.
3. `F:host/uscr/trackpad.pb` — the stock multitouch trackpad with that logo behind it.
4. `F:host/uscr/apps.pb` — the eight app buttons.
5. `F:host/uscr/tomato.pb` — the clock face at 25:00, paused, plus Start / Pause / Skip / Reset.

Prev and Next walk that directory in sorted order: **Apps**, **Tomato**, **Trackpad**, then back to Apps.

## App buttons

Each button is a device-side key tap. The pad acts as a USB keyboard, so the helper can exit and the buttons still work.

| Button | Tuna chord | App |
| --- | --- | --- |
| Zen | Hyper+E | Zen |
| Zed | Hyper+C | Zed Preview |
| Amp | Hyper+A | Amp |
| Ghostty | Hyper+Tab | Ghostty |
| Slack | Hyper+S | Slack |
| Mail | Hyper+M | Canary Mail |
| Grok | Hyper+B | Grok Bot |
| Spotify | Hyper+R | Spotify |

VMware Fusion is bound to Hyper+W in that config and is not installed, so it is not a button. Finder, Notes, Downloads, and Home are combo-mode keys. Combo mode is disabled, so they are not buttons either.

## Tomato clock

```bash
cd app
poetry run python ../scripts/desk/desk.py clock
```

Leave this running. It uploads the tomato page again so the four buttons call back into this process, then rewrites the page once a second so the time label changes. The time is a label, same as the buttons. A bitmap clock face was uploaded before and did not show on this panel: the image was decoded, and its box collapsed, so only the buttons stayed on screen.

`just up` writes firmware. It does not draw this clock. Prev and Next open `F:host/uscr/tomato.pb`. Until the helper replaces that file, the page is the old picture: buttons, and no digits.

If the data cable is unplugged or the pad resets, the helper waits and opens the pad again, keeping the same countdown. Plug the data cable back in and leave the process up.

- Focus is 25:00. Short break is 5:00. The fourth focus is followed by a 15:00 long break.
- **Start** runs the current phase. **Pause** holds it. **Skip** jumps to the next phase and keeps the running or paused state. **Reset** returns to a paused 25:00 and clears the count.
- When a phase ends, the Mac plays `Glass.aiff` and shows a notification titled Tomato.

`TOUCHY_TOMATO_SHOW=0` saves the page and leaves whichever page is on screen. The default is to switch to the tomato page.

The clock counts in this process. Once a second it writes the page again, and the pad rebuilds that body so the digits change. Quit the process and the last time stays on screen.

## Trackpad

The page is the stock trackpad body from `touchy_pad.pages.trackpad`, with `F:host/images/touchy.png` as the background. Touches still move the host pointer. The logo sits in the middle of that surface.

## Page pictures

`scripts/desk/render_shots.py` draws the three frames in `docs/images/`. The panel is 480×272. The files are 2× that size. The board cannot send a framebuffer back to the host, so these frames are the pages that were uploaded, drawn to the same size as the glass.

```bash
python3 scripts/desk/render_shots.py
```

## Firmware on this board

Board id `jc4827w543`, chip ESP32-S3, 4 MB flash, 8 MB octal PSRAM. The image that is running was built with ESP-IDF v6.0.1 and written in DIO mode at 80 MHz.

On this Mac, build once, put the board in the ROM bootloader (data cable, hold **BOOT**, tap **RST**), then flash:

```bash
just firmware-build
just up
```

`just up` runs `ls /dev/cu.*`, keeps the single `/dev/cu.usbmodem*` (or `usbserial` / `wchusbserial` / `SLAB_USBtoUART`) port, and runs esptool with `firmware/build/flash_args` (DIO, 80 MHz, 4 MB). Set `TOUCHY_PORT` when more than one USB serial port is present. `just flash` still looks for an IDF v6.1 activate script and for `/host/dev/ttyACM*`, which this Mac does not have.

The previous Token Pulse image was copied off the chip before that write. The 4 MB dump is outside this repo, under `~/src/tries/jc4827w543-backups/`. Restore it by writing that whole file at offset 0 with the same flash mode, after the ROM port is back. Do not commit that dump. It can contain Wi-Fi credentials.
