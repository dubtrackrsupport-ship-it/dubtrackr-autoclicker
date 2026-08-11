
# DubTrackr AutoClickr

A lightweight, open-source **dual-engine autoclicker** — click your mouse *and*
auto-fire a keyboard key at the same time, each fully independent. Part of the
[Dubtrackr Network](https://www.dubtrackr.win).

<img width="559" height="499" alt="Screenshot 2026-07-20 152436" src="https://github.com/user-attachments/assets/fc557385-957c-4df9-a42e-4589a44e4e6b" />

## Features

- **Two independent engines** — a mouse clicker and a keyboard clicker run
  separately, each with its own toggle hotkey.
- **Mouse speed** — one control: clicks per second (CPS). Handles fast spam
  and slow taps alike (e.g. 0.5 CPS = one click every 2 seconds).
- **Keyboard rate** — one simple control: press **every N ms / sec / min**
  (e.g. once every 20 seconds), or switch to **Hold** to keep the key down.
- **Human-like jitter** — randomizes each interval so the timing isn't robotic.
- **Mouse options** — left / right / middle button, single or double click.
- **Keyboard options** — **Tap** (repeat a key) or **Hold** (keep a key held
  down, e.g. sprint) for any key: `space`, `w`, `a`, `s`, `d`, ...
- **Droid Tycoon scrap/craft preset** — tuned for scrap-table and crafting swings.
- **Windows 11 light / dark** (follows your system) + accent theme picker.
- **Settings persist** between launches (`%APPDATA%\DubtrackrAutoClicker`).
- Ships as a single `.exe` — no install, no dependencies.

## Download & run

Grab `DubtrackrAutoClicker.exe` from the [Releases](https://github.com/dubtrackrsupport-ship-it/dubtrackr-autoclicker/releases/latest) page and
run it. Press each engine's hotkey (default **F6** mouse, **F7** keyboard) to
toggle it — the hotkeys work even when the window isn't focused.

### Is it safe?

DubTrackr AutoClickr is fully open source. Official GitHub release executables starting
with v1.0.1 are Authenticode-signed and RFC 3161 timestamped through Microsoft Azure
Artifact Signing. In **Properties → Digital Signatures**, verify that Windows reports a
valid signature from **Daniel Meier**. The release page also publishes the exact SHA-256.

The app simulates mouse and keyboard input, so SmartScreen or antivirus software can still
scrutinize a new release. A valid signature proves who published the file and that it has
not changed since signing; it does not override game rules or antivirus policy.

Prefer not to trust a pre-built binary? Build it yourself from source (below). Runtime
and build dependencies are pinned for the release build.

## Build from source

```bash
pip install -r requirements.txt
python dubtrackr_autoclicker.py            # run from source
```

Build the exe:

```bash
pip install -r requirements-build.txt
python build.py                            # produces dist/DubtrackrAutoClicker.exe
```

The v1.0.1 release build uses Python 3.14.6 (recorded in `.python-version`).

## Usage notes

- Don't set a keyboard engine's auto-key to the same key as its toggle hotkey.
- **Use responsibly.** Automating input can violate the terms of service of some
  games and online services. You are responsible for how you use this tool.

## License

MIT — free to use, modify, and share.
