
# DubTrackr AutoClickr

A lightweight, open-source autoclicker with separate controls for mouse clicks,
keyboard repetition and walking. Part of the
[Dubtrackr Network](https://www.dubtrackr.win).

<img width="559" height="499" alt="Screenshot 2026-07-20 152436" src="https://github.com/user-attachments/assets/fc557385-957c-4df9-a42e-4589a44e4e6b" />

## Features

- Mouse clicks, keyboard repetition and walking run separately, each with its
  own Start/Stop button and toggle hotkey.
- DubTrackr AutoWalkr: hold **S for 1 second**, release it, then hold
  **W for an adjustable return time** and release it. Set the wait between cycles in seconds
  or minutes (default: 30 seconds). Walking starts after a 3-second delay
  so you can switch to the game. **F8** starts or stops walking.
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
run it. Press each engine's hotkey (default **F6** mouse, **F7** keyboard,
**F8** walking) to toggle it. The hotkeys work when the window isn't focused.

### DubTrackr AutoWalkr

AutoWalkr targets normal jogging without walk or tactical sprint modifiers.
The backward leg stays at 1 second. Return time starts at 1.05 seconds as a
starting point for calibration. Use **Test once** to try one cycle. If you finish behind
your starting spot, increase Return time. If you go past it, decrease Return time.
The adjustment buttons change it by 0.01 seconds; the field accepts 0.1 to 10 seconds.
Your chosen return time is saved between launches.

The wait begins after W is released. With the starting timing, a 30-second wait
means a 2.05-second cycle followed by 30 seconds without movement. The wait is saved between launches
and accepts 0.1 seconds to 24 hours. Stopping or closing the app releases the
movement key immediately. Starting again begins with S.

Walking sends input to the active window. Switch to the game during the
3-second startup delay, or use F8 while the game is focused. W and S cannot
run through the keyboard control while walking is active. Choose separate
hotkeys other than W or S.

AutoWalkr does not measure your position. Collisions, movement modifiers,
acceleration and game timing can cause drift even after calibration.

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
