
# Dubtrackr AutoClicker

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

### "Windows protected your PC" / antivirus warning

This is an **unsigned** build, so Windows SmartScreen and some antivirus engines
may warn about it — this is a known false positive for any autoclicker (they
simulate input, which heuristics flag). The app is fully open source; you can:

1. **Verify it** on [VirusTotal](https://www.virustotal.com/) — upload the exe.
2. **Build it yourself** from source (below) — takes under a minute.

Signed builds via the [SignPath Foundation](https://signpath.io/solutions/open-source-community)
OSS program are planned.

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
