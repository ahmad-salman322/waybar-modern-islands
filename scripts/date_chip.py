#!/usr/bin/env python3
# Date chip for the Modern Islands waybar.
#   date_chip.py         -> print waybar JSON (Gregorian or Hijri, by saved mode)
#   date_chip.py toggle  -> switch mode and refresh the bar (and the calendar popup if open)

import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hijri import hijri_text, sync_status

STATE = os.path.expanduser("~/.cache/datechip-mode")
SIGNAL = 9


def get_mode():
    try:
        with open(STATE) as f:
            return "hijri" if f.read().strip() == "hijri" else "greg"
    except FileNotFoundError:
        return "greg"


def set_mode(mode):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        f.write(mode)
    subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "toggle":
        set_mode("greg" if get_mode() == "hijri" else "hijri")
        return

    today = datetime.date.today()
    greg = today.strftime("%a %d %b")
    try:
        hijri = hijri_text(today, year=False)
        hijri_full = hijri_text(today, weekday=True)
    except Exception:
        hijri = hijri_full = "?"
    try:
        _, title, detail = sync_status()
        sync = f"\n{title} · {detail}"
    except Exception:
        sync = ""
    mode = get_mode()
    print(json.dumps({
        "text": hijri if mode == "hijri" else greg,
        "tooltip": f"{today.strftime('%A %d %B %Y')}\n{hijri_full}{sync}\n\nClick: calendar\nRight click: Hijri / Gregorian",
        "class": mode,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
