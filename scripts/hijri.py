#!/usr/bin/env python3
# Gregorian <-> Hijri (Umm al-Qura) using the system ICU library through ctypes.
# Month starts confirmed by moon sighting (fetched by hijri_sync.py) override the
# calculated calendar from that month on.
# Used by DateChip.py (waybar), CalendarPopup.py and hijri_sync.py.

import ctypes
import datetime
import glob
import json
import os
import re
import time

SYNC_FILE = os.path.expanduser("~/.cache/hijri-sync.json")

MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
    "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ICU calendar fields
YEAR, MONTH, DATE = 1, 2, 5

_lib = None
_ver = None


def _icu():
    global _lib, _ver
    if _lib is None:
        path = sorted(glob.glob("/usr/lib*/libicui18n.so.[0-9]*")
                      + glob.glob("/usr/lib/*/libicui18n.so.[0-9]*"))[0]
        _ver = re.search(r"\.so\.(\d+)", path).group(1)
        _lib = ctypes.CDLL(path)
        f = lambda n: getattr(_lib, f"{n}_{_ver}")
        err = ctypes.POINTER(ctypes.c_int)
        f("ucal_open").restype = ctypes.c_void_p
        f("ucal_open").argtypes = [ctypes.c_char_p, ctypes.c_int32, ctypes.c_char_p, ctypes.c_int, err]
        f("ucal_setMillis").argtypes = [ctypes.c_void_p, ctypes.c_double, err]
        f("ucal_getMillis").restype = ctypes.c_double
        f("ucal_getMillis").argtypes = [ctypes.c_void_p, err]
        f("ucal_setDateTime").argtypes = [ctypes.c_void_p] + [ctypes.c_int32] * 6 + [err]
        f("ucal_get").restype = ctypes.c_int32
        f("ucal_get").argtypes = [ctypes.c_void_p, ctypes.c_int, err]
        f("ucal_close").argtypes = [ctypes.c_void_p]
    return lambda n: getattr(_lib, f"{n}_{_ver}")


def _open():
    f = _icu()
    status = ctypes.c_int(0)
    utc = "UTC".encode("utf-16-le")
    cal = f("ucal_open")(utc, 3, b"en@calendar=islamic-umalqura", 0, ctypes.byref(status))
    if status.value > 0:
        raise OSError(f"ICU ucal_open failed: {status.value}")
    return f, cal, status


def load_sync():
    """{"starts": {"YYYY-MM": "gregorian iso date of day 1"}, "checked": unix time}"""
    try:
        with open(SYNC_FILE) as f:
            data = json.load(f)
        data.setdefault("starts", {})
        return data
    except (FileNotFoundError, ValueError):
        return {"starts": {}}


_starts = None


def _confirmed():
    """[((year, month), date of day 1)] sorted, from the sync file"""
    global _starts
    if _starts is None:
        _starts = sorted(
            ((int(k[:4]), int(k[5:])), datetime.date.fromisoformat(v))
            for k, v in load_sync()["starts"].items())
    return _starts


def reload_sync():
    global _starts
    _starts = None


def save_sync(data):
    os.makedirs(os.path.dirname(SYNC_FILE), exist_ok=True)
    tmp = SYNC_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, SYNC_FILE)
    reload_sync()


def adjust_month(y, m, days):
    """move the first day of Hijri month y-m by `days` (manual sighting correction).
    Returns False when that would make the previous month shorter than 29 or longer than 30 days."""
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    new_start = from_hijri(y, m, 1) + datetime.timedelta(days=days)
    if not 29 <= (new_start - from_hijri(py, pm, 1)).days <= 30:
        return False
    key = f"{y:04d}-{m:02d}"
    data = load_sync()
    manual = set(data.get("manual", []))
    data["starts"].pop(key, None)
    manual.discard(key)
    # only keep an entry when it differs from what the calendar gives without it
    save_sync(data)
    if from_hijri(y, m, 1) != new_start:
        data["starts"][key] = new_start.isoformat()
        manual.add(key)
    data["manual"] = sorted(manual)
    save_sync(data)
    return True


def _ago(seconds):
    """Arabic "N minutes/hours/days ago" """
    for size, one, two, few, many in ((86400, "يوم", "يومين", "أيام", "يوماً"),
                                      (3600, "ساعة", "ساعتين", "ساعات", "ساعة"),
                                      (60, "دقيقة", "دقيقتين", "دقائق", "دقيقة")):
        n = int(seconds // size)
        if n >= 1:
            if n == 1:
                return f"قبل {one}"
            if n == 2:
                return f"قبل {two}"
            return f"قبل {n} {few if n <= 10 else many}"
    return "قبل لحظات"


def sync_status(now=None):
    """moon-sighting check result for the popup and the date chip tooltip:
    (state "ok" / "failed" / "never", headline, detail)"""
    data = load_sync()
    now = now or time.time()
    ok, failed = data.get("checked", 0), data.get("failed", 0)
    if failed > ok:
        detail = f"آخر محاولة {_ago(now - failed)}"
        if ok:
            detail += f" · آخر نجاح {_ago(now - ok)}"
        return "failed", "غير متصل بموقع الرؤية", detail
    if ok:
        return "ok", "متصل بموقع الرؤية", f"آخر تحقق {_ago(now - ok)}"
    return "never", "لم يتم التحقق من الرؤية بعد", "يتحقق قرب نهاية كل شهر"


def _next(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def _prev(y, m):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def to_hijri(day):
    """datetime.date -> (year, month 1-12, day), corrected by confirmed month starts"""
    y, m, d = _to_hijri(day)
    # a month confirmed to start later than calculated: the days before it
    # still belong to the previous month (its 30th day)
    start = dict(_confirmed()).get((y, m))
    if start and day < start:
        py, pm = _prev(y, m)
        return py, pm, (day - from_hijri(py, pm, 1)).days + 1
    return y, m, d


def _to_hijri(day):
    confirmed = _confirmed()
    best = None
    for (y, m), start in confirmed:
        if start <= day:
            best = (y, m, start)
    if not best:
        return icu_to_hijri(day)
    y, m, start = best
    offset = (day - start).days
    next_start = dict(confirmed).get(_next(y, m))
    # inside a confirmed month: count from its first day (handles a 30th day the
    # calculated calendar doesn't have); a 30th day stays a prediction until the
    # next month's start is confirmed
    if (next_start and day < next_start) or offset < 29:
        return y, m, offset + 1
    shift = (start - icu_from_hijri(y, m, 1)).days
    return icu_to_hijri(day - datetime.timedelta(days=shift))


def from_hijri(y, m, d):
    """Hijri (year, month 1-12, day) -> datetime.date, corrected by confirmed month starts"""
    shift = 0
    for (cy, cm), start in _confirmed():
        if (cy, cm) == (y, m):
            return start + datetime.timedelta(days=d - 1)
        if (cy, cm) < (y, m):
            shift = (start - icu_from_hijri(cy, cm, 1)).days
    return icu_from_hijri(y, m, d) + datetime.timedelta(days=shift)


def icu_to_hijri(day):
    """datetime.date -> (year, month 1-12, day) by the calculated Umm al-Qura calendar"""
    f, cal, status = _open()
    try:
        noon = datetime.datetime(day.year, day.month, day.day, 12, tzinfo=datetime.timezone.utc)
        f("ucal_setMillis")(cal, noon.timestamp() * 1000.0, ctypes.byref(status))
        y = f("ucal_get")(cal, YEAR, ctypes.byref(status))
        m = f("ucal_get")(cal, MONTH, ctypes.byref(status)) + 1
        d = f("ucal_get")(cal, DATE, ctypes.byref(status))
    finally:
        f("ucal_close")(cal)
    return y, m, d


def icu_from_hijri(y, m, d):
    """Hijri (year, month 1-12, day) -> datetime.date by the calculated Umm al-Qura calendar"""
    f, cal, status = _open()
    try:
        f("ucal_setDateTime")(cal, y, m - 1, d, 12, 0, 0, ctypes.byref(status))
        ms = f("ucal_getMillis")(cal, ctypes.byref(status))
    finally:
        f("ucal_close")(cal)
    if status.value > 0:
        raise ValueError(f"bad Hijri date {y}-{m}-{d}")
    return datetime.datetime.fromtimestamp(ms / 1000.0, datetime.timezone.utc).date()


def month_length(y, m):
    """number of days (29 or 30) in Hijri month m of year y"""
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (from_hijri(ny, nm, 1) - from_hijri(y, m, 1)).days


def hijri_text(day, weekday=False, year=True):
    y, m, d = to_hijri(day)
    s = f"{d} {MONTHS[m - 1]}"
    if year:
        s += f" {y}"
    if weekday:
        s = f"{DAYS[day.weekday()]} {s}"
    return s


if __name__ == "__main__":
    for t in (datetime.date.today(), datetime.date(2026, 2, 18), datetime.date(2026, 6, 16)):
        h = to_hijri(t)
        print(t, h, hijri_text(t, weekday=True), "->", from_hijri(*h), "len", month_length(h[0], h[1]))
