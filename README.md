
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
- **Fortnite pickaxe preset** — one click per swing, nothing wasted.
- **Windows 11 light / dark** (follows your system) + accent theme picker.
- **Settings persist** between launches (`%APPDATA%\DubtrackrAutoClicker`).
- Ships as a single `.exe` — no install, no dependencies.

## Download & run

Grab `DubtrackrAutoClicker.exe` from the [Releases](https://github.com/dubtrackrsupport-ship-it/dubtrackr-autoclicker/releases/latest) page and
run it. Press each engine's hotkey (default **F6** mouse, **F7** keyboard) to
toggle it — the hotkeys work even when the window isn't focused.

### Is it safe?

Yes. DubTrackr AutoClickr is fully open source — every line is in this repo, and the
released `.exe` matches the source (verify the SHA-256 on the release page).

Because it's an **unsigned, PyInstaller-packaged** app that simulates mouse/keyboard
input, a few antivirus engines flag it *heuristically*. On
[VirusTotal](https://www.virustotal.com/gui/file/e3475397677d60eac0f60faee2e04c6dc64a609fa6893c1c4422246b951f7814),
a handful of engines flag it with generic ML labels (e.g. Microsoft `Wacatac.B!ml`, a
well-known false positive for PyInstaller apps) — while **all major engines report it
clean** and VirusTotal's **behavioral sandbox finds no malicious activity** (no network
calls, no dropped files, nothing).

Prefer not to trust a pre-built binary? Build it yourself from source (below). Code
signing via the [SignPath Foundation](https://signpath.io/solutions/open-source-community)
OSS program is planned, which will clear these heuristic flags.

## Build from source

```bash
pip install -r requirements.txt
python dubtrackr_autoclicker.py            # run from source
```

Build the exe:

```bash
pip install pyinstaller
python build.py                            # produces dist/DubtrackrAutoClicker.exe
```

## Usage notes

- Don't set a keyboard engine's auto-key to the same key as its toggle hotkey.
- **Use responsibly.** Automating input can violate the terms of service of some
  games and online services. You are responsible for how you use this tool.

## License

MIT — free to use, modify, and share.
