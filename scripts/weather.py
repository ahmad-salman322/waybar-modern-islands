#!/usr/bin/env python3
# Weather chip for the Modern Islands waybar (wttr.in, no API key).
# Location is detected from your IP; set WEATHER_LOCATION (e.g. "Amman") to pin one.

import json
import os
import urllib.parse
import urllib.request

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
        print(json.dumps({"text": "  --", "tooltip": "Weather unavailable", "class": "offline"}))


if __name__ == "__main__":
    main()
