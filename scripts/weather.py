#!/usr/bin/env python3
# Weather chip for the Modern Islands waybar (wttr.in, no API key).
# Location is detected from your IP; set WEATHER_LOCATION (e.g. "Amman") to pin one.

import json
import os
import socket
import subprocess
import time
import urllib.parse
import urllib.request

SIGNAL = 11   # "signal" of custom/weather in config.jsonc

# wttr.in weather codes -> nerd font weather glyphs
ICONS = {
    "113": "",                                   # sunny
    "116": "",                                   # partly cloudy
    "119": "", "122": "",                  # cloudy / overcast
    "143": "", "248": "", "260": "",  # mist / fog
    "200": "", "386": "", "389": "",
    "392": "", "395": "",                  # thunder
}
RAIN = {"176", "263", "266", "281", "284", "293", "296", "299", "302", "305",
        "308", "311", "314", "353", "356", "359"}
SNOW = {"179", "182", "185", "227", "230", "317", "320", "323", "326", "329",
        "332", "335", "338", "350", "362", "365", "368", "371", "374", "377"}


def icon(code):
    if code in RAIN:
        return ""
    if code in SNOW:
        return ""
    return ICONS.get(code, "")


def online():
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            socket.create_connection((host, 53), timeout=2).close()
            return True
        except OSError:
            pass
    return False


def refresh_when_online():
    """At login the bar starts before Wi-Fi connects. Instead of showing "--" until the
    next run, wait in the background and refresh the chip as soon as the internet is back."""
    lock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "weather-wait.lock")
    try:
        import fcntl
        fd = os.open(lock, os.O_CREAT | os.O_WRONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)   # one watcher at a time
    except OSError:
        return
    if os.fork():
        return                       # the chip prints and exits; the child keeps waiting
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    for std in (0, 1, 2):
        os.dup2(devnull, std)        # don't keep waybar's pipe open
    for _ in range(360):             # every 5 s, for up to 30 minutes
        time.sleep(5)
        if online():
            subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"])
            break
    os._exit(0)


def main():
    place = urllib.parse.quote(os.environ.get("WEATHER_LOCATION", ""))
    url = f"https://wttr.in/{place}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        now = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        city = area.get("areaName", [{}])[0].get("value", "")
        country = area.get("country", [{}])[0].get("value", "")
        desc = now["weatherDesc"][0]["value"]
        today = data["weather"][0]
        print(json.dumps({
            "text": f"{icon(now['weatherCode'])}  {now['temp_C']}°C",
            "tooltip": (f"{desc}\n{city}, {country}\n"
                        f"Feels like {now['FeelsLikeC']}°C\n"
                        f"Min {today['mintempC']}°C  Max {today['maxtempC']}°C\n"
                        f"Humidity {now['humidity']}%  Wind {now['windspeedKmph']} km/h"),
            "class": "weather",
        }, ensure_ascii=False))
    except Exception:
        print(json.dumps({"text": "  --", "tooltip": "Weather unavailable\nRefreshes by itself when the internet is back",
                          "class": "offline"}, ensure_ascii=False), flush=True)
        refresh_when_online()


if __name__ == "__main__":
    main()
