#!/usr/bin/env python3
# Optional: keep Waybar hidden and show it only while Super is held (Hyprland).
# Shows on Super press, hides on release. Reads the keyboards straight from evdev
# (your user must be in the "input" group); nothing is grabbed, so Super still works
# for your binds. Works with keyd too (its virtual keyboard is picked up).
# Super+\ pins the bar on (press again to unpin); the choice is kept in
# ~/.cache/waybar-pinned, so it survives a restart.
# Needs "start_hidden": true in config.jsonc. See "Show the bar only while Super is
# held" in the README.
import json
import os
import re
import select
import struct
import subprocess
import time

SUPER = {125, 126}          # KEY_LEFTMETA, KEY_RIGHTMETA
KEY_BACKSLASH = 43          # Super+\ pins the bar on / off
PINFILE = os.path.expanduser("~/.cache/waybar-pinned")   # exists = pinned (survives restart)
EV_KEY = 1
EVENT = struct.Struct("llHHi")
HOLD_DELAY = 0              # seconds Super must be held before the bar shows


def hypr_json(what):
    try:
        return json.loads(subprocess.run(["hyprctl", what, "-j"], capture_output=True,
                                         text=True, timeout=2).stdout)
    except Exception:
        return None


def bar_visible():
    # waybar 0.15 "hides" by moving the bar to the bottom layer (level 1, invisible);
    # shown it sits on the top layer (level 2).
    d = hypr_json("layers") or {}
    return any(s.get("namespace") == "waybar"
               for mon in d.values() for lvl, ss in mon.get("levels", {}).items()
               if lvl in ("2", "3") for s in ss)


def set_bar(show):
    if bar_visible() != show:
        subprocess.run(["pkill", "-USR1", "-x", "waybar"])


def fix_stale_reserve():
    # after `hyprctl reload` Hyprland can keep the hidden bar's 38 px reserved;
    # a show+hide cycle makes waybar re-send its (empty) exclusive zone
    if bar_visible():
        return
    mons = hypr_json("monitors") or []
    if any(m.get("reserved", [0, 0])[1] > 0 for m in mons):
        subprocess.run(["pkill", "-USR1", "-x", "waybar"])
        time.sleep(0.3)
        subprocess.run(["pkill", "-USR1", "-x", "waybar"])


def keyboards():
    # every device with a Super key and letters -- includes "keyd virtual keyboard",
    # since keyd grabs the real keyboard and only re-emits through its virtual one
    found = []
    try:
        blocks = open("/proc/bus/input/devices").read().split("\n\n")
    except OSError:
        return found
    for b in blocks:
        ev = re.search(r"H: Handlers=.*?\b(event\d+)", b)
        key = re.search(r"B: KEY=([0-9a-f ]+)", b)
        if not ev or not key:
            continue
        bits = 0
        for word in key.group(1).split():
            bits = (bits << 64) | int(word, 16)
        if bits >> 125 & 1 and bits >> 30 & 1:      # KEY_LEFTMETA and KEY_A
            found.append("/dev/input/" + ev.group(1))
    return found


def main():
    files = {}
    held = False
    shown = False
    show_at = None
    pinned = os.path.exists(PINFILE)
    set_bar(pinned)
    shown = pinned
    while True:
        for real in keyboards():
            if real not in files.values():
                try:
                    files[open(real, "rb", buffering=0)] = real
                except OSError:
                    pass
        timeout = max(0.0, show_at - time.monotonic()) if show_at else 5
        ready, _, _ = select.select(list(files), [], [], timeout)
        if not ready and not held and not pinned:
            fix_stale_reserve()
        for fh in ready:
            try:
                data = fh.read(EVENT.size * 64)
            except OSError:
                data = None
            if not data:                    # keyboard unplugged
                files.pop(fh)
                fh.close()
                continue
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _s, _us, typ, code, value = EVENT.unpack_from(data, off)
                if typ != EV_KEY or value == 2:
                    continue
                if code == KEY_BACKSLASH and value == 1 and held:
                    pinned = not pinned
                    try:
                        if pinned:
                            open(PINFILE, "w").close()
                        else:
                            os.remove(PINFILE)
                    except OSError:
                        pass
                    continue
                if code not in SUPER:
                    continue
                if value == 1 and not held:
                    held = True
                    show_at = time.monotonic() + HOLD_DELAY
                elif value == 0 and held:
                    held, show_at = False, None
                    if shown and not pinned:
                        set_bar(False)
                        shown = False
        if held and show_at and time.monotonic() >= show_at:
            show_at = None
            set_bar(True)
            shown = True

if __name__ == "__main__":
    main()
