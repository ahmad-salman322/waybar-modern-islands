#!/usr/bin/env python3
"""Prayer times chip for Waybar, using the Al-Awail prayer times service.

Al-Awail (al-awail.com) makes the prayer clocks found in many mosques. Its
website calculates the times for any place and exports a whole year as CSV.
This script fetches that year once, keeps it in ~/.cache/prayer-times, and
prints the next prayer as Waybar JSON.

Location is found from your IP address (ipinfo.io, then ip-api.com) and
re-checked every 6 hours. IP location is only accurate to the city or region,
so you can choose your city in the popup (click the chip), or edit ~/.config/prayer-times.json:

    {"city": "Nablus", "latitude": 32.2211, "longitude": 35.2544,
     "method": 2, "hanafi": false, "offsets": {"Fajr": -3, "Isha": 2}}

Every key is optional. With latitude and longitude set, IP detection is off.
"lang": "ar" shows everything in Arabic. "chip": "time" shows the adhan time on
the bar instead of the time left. "dst": "summer" or "winter" forces the
time instead of following the system clock (the popup has buttons for both).
"offsets" adds minutes to single prayers, to match your mosque or the Al-Awail app.
Methods (as on al-awail.com): 0 Karachi, 1 ISNA, 2 Muslim World League,
3 Umm al-Qura, 4 Egyptian, 5 Diyanet.

Usage:
    prayer_times.py           print the chip (Waybar exec)
    prayer_times.py refresh   detect the location again and re-download
    prayer_times.py lang      switch Arabic / English
    prayer_times.py show      print today's times in the terminal
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CSV_URL = "https://al-awail.com/website/site/5_7_1_csv.php"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "prayer-times.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "prayer-times"
LOCATION_FILE = CACHE / "location.json"
FAIL_FILE = CACHE / "last-failure"

LOCATION_MAX_AGE = 6 * 3600   # IP can change when you travel
RETRY_AFTER = 10 * 60         # wait this long after a failed download
SIGNAL = 10                   # waybar "signal" of the module
SOON = 15                     # minutes: chip turns "soon" before a prayer

NAMES = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
PRAYERS = [n for n in NAMES if n != "Sunrise"]
ICON = "\U000F0D45"           # nf-md-mosque

# Everything shown to the user, in English and Arabic ("lang" in the config).
TEXT = {
    "en": {
        "names": dict(zip(NAMES, NAMES)),
        "title": "Prayer times", "change": "Change city", "cancel": "Cancel",
        "search": "Search", "placeholder": "City name (Arabic or English)",
        "auto_entry": "Automatic (from internet address)", "badge": "approved times",
        "in": "in {}", "tomorrow": "{} (tomorrow)", "tomorrow_in": "tomorrow, in {}",
        "h": "h", "m": "m",
        "loc_config": "chosen by you", "loc_ip": "found from your internet address",
        "loc_unknown": "Location unknown (no internet?)",
        "choose_hint": "Choose your city with “Change city”.",
        "unreachable": "Can't reach al-awail.com yet.\nIt tries again every 10 minutes.",
        "searching": "Searching…", "no_city": "No city found for “{}”", "cant_search": "Can't search: {}",
        "downloading": "Downloading the times for {}…", "finding": "Finding your location…",
        "saved_failed": "City saved, but al-awail.com didn't answer. It tries again every 10 minutes.",
        "location": "Location {}: {}", "time": "Time",
        "dst": {"auto": "Auto", "summer": "Summer", "winter": "Winter"},
        "lang_btn": "عربي",
        "show": "On the bar", "show_opts": {"left": "Time left", "time": "Prayer time"},
        "countries": {"PS": "Palestine"},
        "src": {"approved": "Officially approved times (Al-Awail)",
                "approved-est": "Al-Awail, adjusted to this week's approved times",
                "al-awail": "Al-Awail calculator",
                "local": "Calculated on this computer (al-awail.com not answering)"},
        "methods": ["Karachi", "ISNA", "Muslim World League", "Umm al-Qura", "Egyptian", "Diyanet"],
        "hanafi": " · Hanafi Asr",
        "hint": "Click: all times and settings · Right-click: refresh",
        "no_loc": "Can't find your location (no internet?)", "cant_reach": "Can't reach al-awail.com",
        "dst_note": {"summer": "Summer time forced", "winter": "Winter time forced"},
    },
    "ar": {
        "names": {"Fajr": "الفجر", "Sunrise": "الشروق", "Dhuhr": "الظهر",
                  "Asr": "العصر", "Maghrib": "المغرب", "Isha": "العشاء"},
        "title": "مواقيت الصلاة", "change": "تغيير المدينة", "cancel": "إلغاء",
        "search": "بحث", "placeholder": "اسم المدينة (عربي أو إنجليزي)",
        "auto_entry": "تلقائي (من عنوان الإنترنت)", "badge": "مواعيد معتمدة",
        "in": "بعد {}", "tomorrow": "{} (غداً)", "tomorrow_in": "غداً، بعد {}",
        "h": "س", "m": "د",
        "loc_config": "اخترته أنت", "loc_ip": "من عنوان الإنترنت",
        "loc_unknown": "الموقع غير معروف (لا يوجد إنترنت؟)",
        "choose_hint": "اختر مدينتك من زر «تغيير المدينة».",
        "unreachable": "موقع الأوائل لا يرد بعد.\nيعيد المحاولة كل عشر دقائق.",
        "searching": "جارٍ البحث…", "no_city": "لا توجد مدينة باسم «{}»", "cant_search": "تعذّر البحث: {}",
        "downloading": "جارٍ تنزيل مواعيد {}…", "finding": "جارٍ تحديد موقعك…",
        "saved_failed": "حُفظت المدينة، لكن موقع الأوائل لم يرد. يعيد المحاولة كل عشر دقائق.",
        "location": "الموقع {}: {}", "time": "التوقيت",
        "dst": {"auto": "تلقائي", "summer": "صيفي", "winter": "شتوي"},
        "lang_btn": "English",
        "show": "على الشريط", "show_opts": {"left": "الوقت المتبقي", "time": "وقت الأذان"},
        "countries": {"PS": "فلسطين", "TR": "تركيا"},   # TR: iso-codes renamed it, the translation lags
        "src": {"approved": "مواعيد معتمدة رسمياً (الأوائل)",
                "approved-est": "حاسبة الأوائل مصحّحة على مواعيد هذا الأسبوع المعتمدة",
                "al-awail": "حاسبة موقع الأوائل",
                "local": "محسوبة على هذا الجهاز (موقع الأوائل لا يرد)"},
        "methods": ["كراتشي", "أمريكا الشمالية", "رابطة العالم الإسلامي", "أم القرى", "الهيئة المصرية", "ديانت"],
        "hanafi": " · عصر حنفي",
        "hint": "ضغطة: كل المواعيد والإعدادات · زر يمين: تحديث",
        "no_loc": "تعذّر تحديد موقعك (لا يوجد إنترنت؟)", "cant_reach": "موقع الأوائل لا يرد",
        "dst_note": {"summer": "التوقيت الصيفي مفروض", "winter": "التوقيت الشتوي مفروض"},
    },
}



# ---------- small helpers ----------

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(path)


def http(url, data=None, timeout=10):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "waybar-prayer-times"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def local_zone():
    """The system time zone (follows /etc/localtime), for daylight saving."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if not tz:
        try:
            tz = os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1]
        except IndexError:
            tz = "UTC"
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("UTC")


def offset_hours(tz, day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=tz).utcoffset().total_seconds() / 3600


def lang():
    return "ar" if (read_json(CONFIG, {}) or {}).get("lang") == "ar" else "en"


def tr(key):
    return TEXT[lang()][key]


def pname(name):
    return TEXT[lang()]["names"].get(name, name)


def chip_mode():
    """What the bar shows next to the prayer: "left" (time left) or "time" (adhan time)."""
    return "time" if (read_json(CONFIG, {}) or {}).get("chip") == "time" else "left"


# Al-Awail, and this script, list these places under Palestine
COUNTRY_ALIASES = {"IL": "PS"}
LABEL_FIXES = {"Palestinian Territories": "Palestine", "الأراضي الفلسطينية": "فلسطين",
               "Israel": "Palestine", "إسرائيل": "فلسطين"}


def country_code(cc):
    cc = (cc or "").upper()
    return COUNTRY_ALIASES.get(cc, cc)


_ISO = None


def country_name(cc):
    """Country name in the current language, from the system's iso-codes list."""
    global _ISO
    cc = country_code(cc)
    if not cc or cc in tr("countries"):
        return tr("countries").get(cc, cc)
    if _ISO is None:
        _ISO = {}
        try:
            for c in json.loads(Path("/usr/share/iso-codes/json/iso_3166-1.json").read_text())["3166-1"]:
                _ISO[c["alpha_2"]] = (c["name"], c.get("common_name", c["name"]))
        except (OSError, ValueError, KeyError):
            pass
    if cc not in _ISO:
        return cc
    name, common = _ISO[cc]
    if lang() == "ar":
        import gettext
        ar = gettext.translation("iso_3166-1", languages=["ar"], fallback=True)
        for n in (common, name):
            if ar.gettext(n) != n:
                return ar.gettext(n)
    return common


def city_name(loc):
    """The city in the current language (both names are kept when a place is chosen)."""
    return loc.get("city_ar" if lang() == "ar" else "city_en") or loc.get("city") or "?"


def place_text(loc):
    """"City - Country", or just the city when the country isn't known."""
    country = country_name(loc.get("country"))
    return f"{city_name(loc)} - {country}" if country else city_name(loc)


def names_for(lat, lon):
    """Arabic and English name of the city at a point, from OpenStreetMap (kept in the cache)."""
    names = read_json(CACHE / "city-names.json", {}) or {}
    key = f"{lat:.3f},{lon:.3f}"
    hit = names.get(key)
    if hit and ("ar" in hit or time.time() - hit.get("failed", 0) < 3600):
        return hit.get("ar"), hit.get("en")
    try:
        url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
            {"lat": lat, "lon": lon, "format": "json", "zoom": 10, "namedetails": 1})
        nd = json.loads(http(url, timeout=6)).get("namedetails", {})
        hit = {"ar": nd.get("name:ar") or nd.get("name"), "en": nd.get("name:en") or nd.get("name")}
    except Exception:
        hit = {"failed": time.time()}
    names[key] = hit
    write_json(CACHE / "city-names.json", names)
    return hit.get("ar"), hit.get("en")


def dst_mode():
    """"auto" follows the system clock; "summer"/"winter" force it, like Al-Awail's buttons."""
    mode = (read_json(CONFIG, {}) or {}).get("dst", "auto")
    return mode if mode in ("auto", "summer", "winter") else "auto"


def set_config(**values):
    """Change single settings (None removes one) and keep the rest."""
    cfg = read_json(CONFIG, {}) or {}
    for k, v in values.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    if cfg:
        write_json(CONFIG, cfg)
    else:
        CONFIG.unlink(missing_ok=True)


# ---------- location ----------

def detect_location():
    """City and coordinates from the public IP. Returns None when offline."""
    try:
        d = json.loads(http("https://ipinfo.io/json", timeout=6))
        lat, lon = map(float, d["loc"].split(","))
        return {"city": d.get("city") or "?", "country": d.get("country", ""),
                "latitude": lat, "longitude": lon, "source": "ipinfo.io", "time": time.time()}
    except Exception:
        pass
    try:
        d = json.loads(http("http://ip-api.com/json/", timeout=6))
        if d.get("status") == "success":
            return {"city": d.get("city") or "?", "country": d.get("countryCode", ""),
                    "latitude": d["lat"], "longitude": d["lon"], "source": "ip-api.com",
                    "time": time.time()}
    except Exception:
        pass
    return None


def get_location(force=False):
    cfg = read_json(CONFIG, {}) or {}
    if "latitude" in cfg and "longitude" in cfg:
        loc = {"city": cfg.get("city", "Custom location"), "country": country_code(cfg.get("country")),
               "latitude": float(cfg["latitude"]), "longitude": float(cfg["longitude"]),
               "source": "config", "awail_page": cfg.get("awail_page"),
               "city_ar": cfg.get("city_ar"), "city_en": cfg.get("city_en")}
        if not (loc["city_ar"] and loc["city_en"]):     # chosen before both names were kept
            ar, en = names_for(loc["latitude"], loc["longitude"])
            if ar and en:
                set_config(city_ar=ar, city_en=en)
                loc.update(city_ar=ar, city_en=en)
        return loc
    loc = read_json(LOCATION_FILE)
    if force or not loc or time.time() - loc.get("time", 0) > LOCATION_MAX_AGE:
        fresh = detect_location()
        if fresh:
            loc = fresh
            write_json(LOCATION_FILE, loc)
    if loc and "city_ar" not in loc:
        loc["city_ar"], loc["city_en"] = names_for(loc["latitude"], loc["longitude"])
        if loc["city_ar"]:
            write_json(LOCATION_FILE, loc)
    if loc and "awail_page" not in loc:
        loc["awail_page"] = find_approved([loc.get("city")], loc.get("country", ""))
        write_json(LOCATION_FILE, loc)
    if loc and cfg.get("city"):
        loc["city"] = cfg["city"]
    if loc:
        loc["country"] = country_code(loc.get("country"))
    return loc


# ---------- prayer times ----------

def settings():
    cfg = read_json(CONFIG, {}) or {}
    return int(cfg.get("method", 2)), bool(cfg.get("hanafi", False))


def offsets():
    """Minutes added to each prayer, e.g. {"Fajr": -3, "Isha": 2}, to match a mosque or app."""
    raw = (read_json(CONFIG, {}) or {}).get("offsets", {})
    out = {}
    for name in NAMES:
        try:
            out[name] = int(raw.get(name, 0))
        except (TypeError, ValueError):
            pass
    return out


def year_file(loc, year):
    method, hanafi = settings()
    key = f"{loc['latitude']:.3f}_{loc['longitude']:.3f}_{year}_m{method}{'h' if hanafi else ''}"
    return CACHE / f"{key}.json"


def download_year(loc, year, tz):
    """One year of times from Al-Awail, in local standard time."""
    method, hanafi = settings()
    std = min(offset_hours(tz, date(year, 1, 1)), offset_hours(tz, date(year, 7, 1)))
    form = {
        "page": "5_7_1", "id": "0", "city_name": loc.get("city", ""),
        "longitude": f"{loc['longitude']:.6f}", "latitude": f"{loc['latitude']:.6f}",
        "timezone": f"{std:g}", "is_hanafy": "1" if hanafi else "0",
        "method_id": str(method), "fajr_angle": "18", "isha_angle": "18",
        "dateFrom": f"{year}-01-01", "dateTo": f"{year}-12-31", "btn_manual": "1",
    }
    days = {}
    for line in http(CSV_URL, form, timeout=40).splitlines():
        parts = line.strip().split(";")
        if len(parts) >= 7 and parts[0].startswith(f"{year}-") and parts[1]:
            days[parts[0]] = parts[1:7]
    if len(days) < 365:
        raise ValueError(f"Al-Awail returned {len(days)} days instead of a full year")
    return {"std_offset": std, "days": days}


# ---------- backup: the same calculation done on this computer ----------
# Used only while al-awail.com can't be reached and no year is saved for the place.
# Checked against a full Al-Awail year (Muslim World League): Sunrise to Isha match
# on 96-98% of days and are never more than a minute off; Fajr is within a minute
# on 99% of days, rarely 2.

import math

# method -> (fajr angle, isha angle or None, isha minutes after maghrib or None)
ANGLES = {0: (18, 18, None), 1: (15, 15, None), 2: (18, 17, None),
          3: (18.5, None, 90), 4: (19.5, 17.5, None), 5: (18, 17, None)}


def _sun(jd):
    """Sun declination (degrees) and equation of time (hours)."""
    d = jd - 2451545.0
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    lng = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    e = math.radians(23.439 - 0.00000036 * d)
    ra = math.degrees(math.atan2(math.cos(e) * math.sin(lng), math.cos(lng))) / 15
    eqt = (q / 15 - ra % 24 + 12) % 24 - 12
    return math.degrees(math.asin(math.sin(e) * math.sin(lng))), eqt


def _julian(d):
    y, m = (d.year - 1, d.month + 12) if d.month <= 2 else (d.year, d.month)
    a = y // 100
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d.day + 2 - a + a // 4 - 1524.5


def _day(d, lat, lon, std, fajr, isha, isha_min, asr_factor):
    jd = _julian(d) - lon / 360
    phi = math.radians(lat)

    def noon(t):
        return 12 - _sun(jd + t / 24)[1]

    def at_angle(angle, t, before_noon):
        decl = math.radians(_sun(jd + t / 24)[0])
        v = (-math.sin(math.radians(angle)) - math.sin(decl) * math.sin(phi)) / (math.cos(decl) * math.cos(phi))
        h = math.degrees(math.acos(max(-1.0, min(1.0, v)))) / 15
        return noon(t) - h if before_noon else noon(t) + h

    def asr(t):
        decl = _sun(jd + t / 24)[0]
        angle = -math.degrees(math.atan(1 / (asr_factor + math.tan(math.radians(abs(lat - decl))))))
        return at_angle(angle, t, False)

    t = [5, 6, 12, 13, 18, 18]
    for _ in range(2):   # second pass refines with the sun position at the first guess
        t = [at_angle(fajr, t[0], True), at_angle(0.833, t[1], True), noon(t[2]), asr(t[3]),
             at_angle(0.833, t[4], False), at_angle(isha or 17, t[5], False)]
    if isha_min:
        t[5] = t[4] + isha_min / 60
    out = []
    for i, x in enumerate(t):
        x += std - lon / 15
        m = math.floor(x * 60) if i == 1 else math.ceil(x * 60)   # Al-Awail's rounding
        out.append(f"{m // 60 % 24:02d}:{m % 60:02d}")
    return out


def compute_year(loc, year, tz):
    method, hanafi = settings()
    fajr, isha, isha_min = ANGLES.get(method, ANGLES[2])
    std = min(offset_hours(tz, date(year, 1, 1)), offset_hours(tz, date(year, 7, 1)))
    days, d = {}, date(year, 1, 1)
    while d.year == year:
        days[d.isoformat()] = _day(d, loc["latitude"], loc["longitude"], std,
                                   fajr, isha, isha_min, 2 if hanafi else 1)
        d += timedelta(days=1)
    return {"std_offset": std, "days": days, "local": True}


# where the times on screen came from: "al-awail" or "local"
SOURCE = "al-awail"


def load_year(loc, year, tz, force=False):
    global SOURCE
    path = year_file(loc, year)
    cached = read_json(path)
    if cached and not force:
        SOURCE = "al-awail"
        return cached
    try:
        last_fail = float(FAIL_FILE.read_text())
    except (OSError, ValueError):
        last_fail = 0
    if not force and time.time() - last_fail < RETRY_AFTER:
        SOURCE = "local"
        return compute_year(loc, year, tz)
    try:
        data = download_year(loc, year, tz)
    except Exception as e:
        CACHE.mkdir(parents=True, exist_ok=True)
        FAIL_FILE.write_text(str(time.time()))
        (CACHE / "last-error").write_text(f"{type(e).__name__}: {e}")
        if cached:      # keep the saved year if the site is slow or down
            SOURCE = "al-awail"
            return cached
        SOURCE = "local"
        return compute_year(loc, year, tz)
    write_json(path, data)
    FAIL_FILE.unlink(missing_ok=True)
    SOURCE = "al-awail"
    return data


# ---------- officially approved times (al-awail.com/prayers) ----------
# For some cities Al-Awail publishes the times approved by the local Ministry of
# Awqaf, the same ones as its phone app and mosque clocks. There is no API: each city
# has a page showing the current week only. "?s=1" asks for winter (standard) time.

PRAYERS_URL = "https://www.al-awail.com/prayers/"
APPROVED_MAX_AGE = 12 * 3600


def approved_cities(cc):
    """Cities with approved times in one country: [{"page", "en", "ar"}]."""
    cc = cc.lower()
    path = CACHE / f"approved-list-{cc}.json"
    data = read_json(path)
    if data and time.time() - data.get("time", 0) < 30 * 86400:
        return data["cities"]
    import re
    page = http(PRAYERS_URL + f"0_{cc}_.html", timeout=20)
    cities, seen = [], set()
    for m in re.finditer(r'href="((\d+)_' + cc + r'_([^"]*?)-\(([^)"]*)\)\.html)"', page):
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        cities.append({"page": m.group(1), "en": m.group(3).replace("-", " "),
                       "ar": m.group(4).replace("-", " ")})
    write_json(path, {"time": time.time(), "cities": cities})
    return cities


def find_approved(names, cc):
    """The approved-times page for a city name (Arabic or English), if Al-Awail has one."""
    want = {n.strip().lower() for n in names if n}
    # Al-Awail lists the cities of historic Palestine under "ps"
    for code in dict.fromkeys([cc.lower(), "ps"] if cc.lower() in ("il", "ps") else [cc.lower()]):
        try:
            for c in approved_cities(code):
                if c["ar"].lower() in want or c["en"].lower() in want:
                    return c["page"]
        except Exception:
            pass
    return None


def approved_rows(page, force=False):
    """{date: [6 times]} in standard time, saved as weeks go by."""
    import re
    path = CACHE / f"approved-{page.split('_')[0]}.json"
    data = read_json(path, {"time": 0, "days": {}})
    today = date.today().isoformat()
    if force or time.time() - data["time"] > APPROVED_MAX_AGE or today not in data["days"]:
        try:
            last_fail = float(FAIL_FILE.read_text())
        except (OSError, ValueError):
            last_fail = 0
        if force or time.time() - last_fail > RETRY_AFTER:
            try:
                html = http(PRAYERS_URL + urllib.parse.quote(page) + "?s=1", timeout=20)
                text = re.sub(r"<[^>]+>", " ", html)
                rows = re.findall(r"(\d{4}-\d{2}-\d{2})((?:\s+\d{2}:\d{2}){6})", text)
                if not rows:
                    raise ValueError("no times found on the approved times page")
                for d, times in rows:
                    data["days"][d] = times.split()
                data["time"] = time.time()
                write_json(path, data)
            except Exception as e:
                CACHE.mkdir(parents=True, exist_ok=True)
                FAIL_FILE.write_text(str(time.time()))
                (CACHE / "last-error").write_text(f"{type(e).__name__}: {e}")
    return data["days"]


def _minutes(hm):
    return int(hm[:2]) * 60 + int(hm[3:])


def approved_shift(approved, calc):
    """Typical minutes between approved and calculated times, per prayer (recent days)."""
    common = sorted(d for d in approved if d in calc)[-14:]
    out = []
    for i in range(6):
        diffs = sorted(_minutes(approved[d][i]) - _minutes(calc[d][i]) for d in common)
        out.append(diffs[len(diffs) // 2] if diffs else 0)
    return out


def day_times(loc, day, tz, force=False):
    """[(name, datetime)] for one day, with daylight saving applied."""
    global SOURCE
    data = load_year(loc, day.year, tz, force)
    if not data:
        return None
    row = data["days"].get(day.isoformat())
    if not row:
        return None
    if loc.get("awail_page"):
        approved = approved_rows(loc["awail_page"], force)
        if day.isoformat() in approved:
            row, SOURCE = approved[day.isoformat()], "approved"
        elif approved:
            shift_min = approved_shift(approved, data["days"])
            row = [f"{(_minutes(x) + s) // 60:02d}:{(_minutes(x) + s) % 60:02d}"
                   for x, s in zip(row, shift_min)]
            SOURCE = "approved-est"
    mode = dst_mode()
    hours = {"summer": 1, "winter": 0}.get(mode, offset_hours(tz, day) - data["std_offset"])
    shift = timedelta(hours=hours)
    extra = offsets()
    out = []
    for name, hm in zip(NAMES, row):
        h, m = map(int, hm.split(":"))
        t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz) + shift
        out.append((name, t + timedelta(minutes=extra.get(name, 0))))
    return out


def origin_text():
    """Where the times on screen came from, for the tooltip and popup."""
    return tr("src").get(SOURCE, tr("src")["local"])


def method_text():
    method, hanafi = settings()
    names = tr("methods")
    return (names[method] if 0 <= method < len(names) else f"{method}") + (tr("hanafi") if hanafi else "")


def fmt_left(delta):
    mins = max(0, int(delta.total_seconds() // 60) + 1)
    h, m = divmod(mins, 60)
    return f"{h}{tr('h')} {m}{tr('m')}" if h else f"{m}{tr('m')}"


# ---------- output ----------

def chip(force=False):
    tz = local_zone()
    now = datetime.now(tz)
    loc = get_location(force)
    if not loc:
        return {"text": ICON, "class": "offline", "tooltip": f"{tr('title')}\n{tr('no_loc')}"}
    today = day_times(loc, now.date(), tz, force)
    if not today:
        err = (CACHE / "last-error").read_text() if (CACHE / "last-error").exists() else ""
        return {"text": ICON, "class": "offline",
                "tooltip": f"{tr('title')}\n{tr('cant_reach')}\n{err}".strip()}

    upcoming = [(n, t) for n, t in today if n in PRAYERS and t > now]
    if upcoming:
        nxt = upcoming[0]
    else:
        tomorrow = day_times(loc, now.date() + timedelta(days=1), tz) or []
        nxt = next(((n, t) for n, t in tomorrow if n == "Fajr"), None)
        day_times(loc, now.date(), tz)      # SOURCE describes today again

    width = max(len(pname(n)) for n in NAMES) + 1
    lines = [f"<b>{ICON}  {tr('title')} · {place_text(loc)}</b>", ""]
    for name, t in today:
        row = f"{pname(name):<{width}} {t:%H:%M}"
        if nxt and (name, t) == nxt:
            row = f"<span foreground='#7ee0a1'><b>{row}  ← {tr('in').format(fmt_left(nxt[1] - now))}</b></span>"
        elif t <= now:
            row = f"<span foreground='#8a93b8'>{row}</span>"
        lines.append(f"<tt>{row}</tt>")
    if nxt and nxt[1].date() != now.date():
        lines.append(f"<tt><span foreground='#7ee0a1'><b>{pname('Fajr'):<{width}} {nxt[1]:%H:%M}  ← "
                     f"{tr('tomorrow_in').format(fmt_left(nxt[1] - now))}</b></span></tt>")
    how = tr("loc_config") if loc.get("source") == "config" else tr("loc_ip")
    origin = origin_text() if SOURCE == "approved" else f"{origin_text()}\n{method_text()}"
    mode = dst_mode()
    note = f"\n{tr('dst_note')[mode]}" if mode != "auto" else ""
    lines += ["", f"<small>{origin}{note}\n{tr('location').format(how, place_text(loc))}\n{tr('hint')}</small>"]

    if not nxt:
        return {"text": ICON, "tooltip": "\n".join(lines), "class": "offline"}
    left = nxt[1] - now
    cls = "soon" if left <= timedelta(minutes=SOON) else "normal"
    if chip_mode() == "time":
        text = f"{ICON} {pname(nxt[0])} {nxt[1]:%H:%M}"
    else:
        text = f"{ICON} {pname(nxt[0])} {tr('in').format(fmt_left(left))}"
    return {"text": text, "tooltip": "\n".join(lines), "class": cls, "alt": nxt[0]}


# ---------- city search (used by the popup) ----------

def notify(title, body=""):
    subprocess.run(["notify-send", "-a", "Prayer times", title, body],
                   check=False, stderr=subprocess.DEVNULL)


def search_places(query):
    """Places matching a name (Arabic or English), from OpenStreetMap."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 10, "addressdetails": 1,
         "accept-language": "ar,en" if lang() == "ar" else "en,ar", "featureType": "settlement",
         "namedetails": 1})
    out, seen = [], set()
    for p in json.loads(http(url, timeout=10)):
        if p["display_name"] in seen:      # same town listed twice (node + area)
            continue
        seen.add(p["display_name"])
        a = p.get("address", {})
        city = p.get("name") or p["display_name"].split(",")[0]
        cc = country_code(a.get("country_code"))
        label = p["display_name"]
        for old, new in LABEL_FIXES.items():
            label = label.replace(old, new)
        nd = p.get("namedetails") or {}
        out.append({"city": city, "country": cc,
                    "city_ar": nd.get("name:ar") or city, "city_en": nd.get("name:en") or city,
                    "label": label,
                    "latitude": round(float(p["lat"]), 4),
                    "longitude": round(float(p["lon"]), 4),
                    "awail_page": find_approved([city, nd.get("name:ar"), nd.get("name:en"), query], cc)})
    out.sort(key=lambda x: x["awail_page"] is None)   # approved cities first
    return out


def save_config(place):
    """Store a chosen place, or None to go back to IP detection."""
    keys = ("city", "city_ar", "city_en", "country", "latitude", "longitude", "awail_page")
    set_config(**{k: (place.get(k) if place else None) for k in keys})


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "lang":
        set_config(lang=None if lang() == "ar" else "ar")
        subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"], check=False)
        return
    if arg == "refresh":
        FAIL_FILE.unlink(missing_ok=True)
        out = chip(force=True)
        subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"], check=False)
        import re
        if out.get("class") == "offline":
            notify(tr("title"), re.sub(r"<[^>]+>", "", out["tooltip"]).split("\n", 1)[-1])
        else:
            notify(tr("title"), re.sub(r"<[^>]+>", "", out["tooltip"].split("\n")[0]))
        return
    out = chip()
    if arg == "show":
        import re
        print(re.sub(r"<[^>]+>", "", out["tooltip"]))
        return
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
