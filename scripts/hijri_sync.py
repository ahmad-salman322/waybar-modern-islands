#!/usr/bin/env python3
# Keeps the Hijri date in line with moon-sighting announcements.
# Runs from an invisible waybar module every 30 minutes, but only asks the
# AlAdhan API around the end/start of a month (day 28 .. day 2), at most once an hour.
# The confirmed first day of each month is saved to ~/.cache/hijri-sync.json and
# used by hijri.py instead of the calculated date. Months corrected by hand in the
# calendar popup are left alone.
#
# HIJRI_METHOD picks the AlAdhan calendar (default HJCoSA: Umm al-Qura corrected
# by the Saudi High Judiciary Council's crescent sightings).
#   hijri_sync.py          -> check if it's time, print nothing for waybar
#   hijri_sync.py --force  -> check now and print what was found

import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hijri

METHOD = os.environ.get("HIJRI_METHOD", "HJCoSA")
API = "https://api.aladhan.com/v1/gToH/{:%d-%m-%Y}?calendarMethod={}"
MIN_GAP = 3600
FAIL_GAP = 6 * 3600  # site unreachable: try again later instead of every run
KEEP = 24  # months of history to keep
SIGNAL = 9  # date chip


def ask(day):
    req = urllib.request.Request(API.format(day, METHOD), headers={"User-Agent": "waybar-modern-islands"})
    with urllib.request.urlopen(req, timeout=15) as r:
        h = json.load(r)["data"]["hijri"]
    return int(h["year"]), int(h["month"]["number"]), int(h["day"])


def main():
    force = "--force" in sys.argv
    data = hijri.load_sync()
    today = datetime.date.today()
    y, m, d = hijri.to_hijri(today)
    known = f"{y:04d}-{m:02d}" in data["starts"]

    now = time.time()
    due = force or ((d >= 28 or d <= 2 or not known)
                    and now - data.get("checked", 0) >= MIN_GAP
                    and now - data.get("failed", 0) >= FAIL_GAP)
    if not due:
        print("")
        return

    before = dict(data["starts"])
    try:
        # tomorrow catches the announcement made on the evening of the 29th
        for day in (today, today + datetime.timedelta(days=1)):
            hy, hm, hd = ask(day)
            key = f"{hy:04d}-{hm:02d}"
            # a correction made by hand in the calendar wins over the API
            if key not in data.get("manual", []):
                data["starts"][key] = (day - datetime.timedelta(days=hd - 1)).isoformat()
    except Exception as e:
        data["starts"] = before
        data["failed"] = now
        data["error"] = str(e)[:200]
        hijri.save_sync(data)
        print(f"check failed: {e}" if force else "")
        return

    data["starts"] = dict(sorted(data["starts"].items())[-KEEP:])
    data["manual"] = [k for k in data.get("manual", []) if k in data["starts"]]
    data["checked"] = now
    data.pop("failed", None)
    data.pop("error", None)
    data["method"] = METHOD
    hijri.save_sync(data)

    if data["starts"] != before:
        subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"])
    if force:
        print(json.dumps(data["starts"], indent=1))
        print("today:", hijri.hijri_text(today, weekday=True))
    else:
        print("")


if __name__ == "__main__":
    main()
