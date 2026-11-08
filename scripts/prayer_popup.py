#!/usr/bin/env python3
# Prayer times popup for the Modern Islands waybar, opened by clicking the prayer chip.
# Shows today's adhan and iqama times (from al-awail.com, see prayer_times.py), and has:
#   - "Change city": type a city in Arabic or English and pick it from the list
#   - Auto / Summer / Winter: follow the system clock or force summer or winter time
#   - Time left / Prayer time: what the chip shows next to the prayer name
#   - Arabic / English: the language of the popup, the chip and its tooltip

import os
import sys
import threading
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import PopupBase as pb          # live copy in ~/.config/hypr/UserScripts
except ImportError:
    import popup_base as pb         # copy published in the repo
from gi.repository import GLib, Gtk, Gtk4LayerShell as LayerShell  # noqa: E402

try:
    import PrayerTimes as pt
except ImportError:
    import prayer_times as pt

CSS = """
.ptitle { color: #5ee0c8; font-weight: 800; font-size: 13px; }
.city { font-weight: 700; font-size: 12px; }
.prow { border-radius: 10px; padding: 5px 10px; }
.pname { font-weight: 700; }
.ptime { font-weight: 800; font-size: 13px; }
.past { opacity: 0.45; }
.next { background: rgba(94, 224, 200, 0.16); }
.next .pname, .next .ptime { color: #5ee0c8; }
.left { color: #5ee0c8; font-size: 11px; font-weight: 700; }
.iqtime { color: #8a93b8; font-weight: 700; font-size: 12px; }
.phead { padding: 0 10px; }
.wait { background: rgba(245, 184, 107, 0.16); }
.wait .pname, .wait .ptime, .wait .iqtime, .wait .left { color: #f5b86b; }
.next .iqtime { color: #5ee0c8; }
.teal-btn { background: rgba(94, 224, 200, 0.14); color: #5ee0c8; }
.teal-btn:hover { background: #5ee0c8; color: #11121c; }
.seg { background: rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 2px; }
.seg-btn {
    background: none; border: none; box-shadow: none; border-radius: 8px;
    padding: 3px 10px; min-height: 0; color: #8a93b8; font-weight: 700; font-size: 11px;
}
.seg-btn:hover { background: rgba(255, 255, 255, 0.08); color: #e6e8f2; }
.seg-btn.on { background: #5ee0c8; color: #11121c; }
entry {
    background: rgba(255, 255, 255, 0.06); color: #e6e8f2; border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: none; padding: 4px 8px;
}
.result { background: none; border: none; box-shadow: none; border-radius: 10px;
          padding: 6px 8px; min-height: 0; }
.result:hover { background: rgba(255, 255, 255, 0.08); }
.rname { font-weight: 700; }
.badge { color: #11121c; background: #5ee0c8; border-radius: 6px; padding: 0 6px;
         font-size: 10px; font-weight: 800; }
"""

WIDTH = 340


class PrayerPopup(pb.PopupWindow):
    def __init__(self, app):
        super().__init__(app, WIDTH)
        # the chip sits in the middle island, so open under the middle of the bar
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, False)
        self._busy_until = 0   # clicks that rebuild part of the window must not close it
        self.build()
        GLib.timeout_add_seconds(30, lambda: (self.refresh_view(), True)[1])

    # ----- layout (rebuilt when the language changes) -----

    def build(self):
        clear(self.panel)
        Gtk.Widget.set_default_direction(
            Gtk.TextDirection.RTL if pt.lang() == "ar" else Gtk.TextDirection.LTR)
        T = pt.tr

        head = Gtk.Box(spacing=6)
        head.append(pb.label(f"{pt.ICON}  {T('title')}", "ptitle", xalign=0, hexpand=True))
        head.append(pb.button(T("lang_btn"), self.toggle_lang, "btn"))
        self.change_btn = pb.button(T("change"), self.toggle_search, "btn", "teal-btn")
        head.append(self.change_btn)
        self.panel.append(head)

        # "City - Country": separate labels, so an Arabic city next to an English
        # country name isn't reordered into each other
        self.city = Gtk.Box(spacing=6)
        self.panel.append(self.city)

        # Auto / Summer / Winter
        row = Gtk.Box(spacing=8)
        row.append(pb.label(T("time"), "muted", xalign=0, hexpand=True))
        seg = Gtk.Box(spacing=2)
        seg.add_css_class("seg")
        self.dst_btns = {}
        for mode in ("auto", "summer", "winter"):
            b = pb.button(T("dst")[mode], lambda m=mode: self.set_dst(m), "seg-btn")
            self.dst_btns[mode] = b
            seg.append(b)
        mark(self.dst_btns, pt.dst_mode())
        row.append(seg)
        self.panel.append(row)

        # what the bar shows: time left / adhan time
        row = Gtk.Box(spacing=8)
        row.append(pb.label(T("show"), "muted", xalign=0, hexpand=True))
        seg = Gtk.Box(spacing=2)
        seg.add_css_class("seg")
        self.chip_btns = {}
        for mode in ("left", "time"):
            b = pb.button(T("show_opts")[mode], lambda m=mode: self.set_chip(m), "seg-btn")
            self.chip_btns[mode] = b
            seg.append(b)
        mark(self.chip_btns, pt.chip_mode())
        row.append(seg)
        self.panel.append(row)

        # city search (hidden until "Change city")
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.search_box.add_css_class("card")
        self.entry = Gtk.Entry(placeholder_text=T("placeholder"), hexpand=True)
        self.entry.connect("activate", lambda *_: self.search())
        srow = Gtk.Box(spacing=6)
        srow.append(self.entry)
        srow.append(pb.button(T("search"), self.search))
        self.search_box.append(srow)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.search_box.append(self.results)
        self.search_box.append(pb.button(f"\U000F0350  {T('auto_entry')}", self.choose_auto, "chip-btn"))
        self.search_box.set_visible(False)
        self.panel.append(self.search_box)

        self.status = pb.label("", "status", xalign=0, wrap=True)
        self.status.set_visible(False)
        self.panel.append(self.status)

        self.times = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.times.add_css_class("card")
        self.panel.append(self.times)

        self.foot = pb.label("", "muted", xalign=0, wrap=True)
        self.panel.append(self.foot)
        self.refresh_view()

    # ----- today's times -----

    def refresh_view(self):
        T = pt.tr
        tz = pt.local_zone()
        now = datetime.now(tz)
        loc = pt.get_location()
        clear(self.times)
        if not loc:
            self.set_place([T("loc_unknown")])
            self.times.append(pb.label(T("choose_hint"), "muted"))
            return
        self.set_place([pt.city_name(loc), pt.country_name(loc.get("country"))])
        today = pt.day_times(loc, now.date(), tz)
        source = pt.SOURCE
        if not today:
            self.times.append(pb.label(T("unreachable"), "muted", xalign=0))
        else:
            upcoming = [(n, t) for n, t in today if n in pt.PRAYERS and t > now]
            nxt = upcoming[0] if upcoming else None
            wait = pt.waiting_iqama(today, now)
            self.times.append(self.header_row())
            for name, t in today:
                state = ("wait" if wait and name == wait[0] else
                         "next" if (name, t) == nxt else None)
                self.times.append(self.time_row(pt.pname(name), t, pt.iqama_time(name, t), now, state))
            if not nxt:
                tomorrow = pt.day_times(loc, now.date() + timedelta(days=1), tz) or []
                fajr = next(((n, t) for n, t in tomorrow if n == "Fajr"), None)
                if fajr:
                    self.times.append(self.time_row(T("tomorrow").format(pt.pname("Fajr")), fajr[1],
                                                    pt.iqama_time("Fajr", fajr[1]), now, "next"))
        pt.SOURCE = source
        how = T("loc_config") if loc.get("source") == "config" else T("loc_ip")
        origin = pt.origin_text() if source == "approved" else f"{pt.origin_text()}\n{pt.method_text()}"
        self.foot.set_text(f"{T('location').format(how, pt.place_text(loc))}\n{origin}")

    def set_place(self, parts):
        clear(self.city)
        for i, part in enumerate(p for p in parts if p):
            if i:
                self.city.append(pb.label("-", "city"))
            self.city.append(pb.label(part, "city"))

    def header_row(self):
        row = Gtk.Box(spacing=8)
        row.add_css_class("phead")
        row.append(pb.label("", hexpand=True))
        row.append(pb.label(pt.tr("adhan"), "muted", width_chars=6))
        row.append(pb.label(pt.tr("iqama"), "muted", width_chars=6))
        return row

    def time_row(self, name, t, iq, now, state):
        """state: "next" (next adhan), "wait" (adhan called, iqama not yet) or None."""
        row = Gtk.Box(spacing=8)
        row.add_css_class("prow")
        row.append(pb.label(name, "pname", xalign=0, hexpand=True))
        if state == "next":
            row.add_css_class("next")
            row.append(pb.label(pt.tr("in").format(pt.fmt_left(t - now)), "left"))
        elif state == "wait":
            row.add_css_class("wait")
            row.append(pb.label(pt.tr("iqama_of").format("") + pt.tr("in").format(pt.fmt_left(iq - now)),
                                "left"))
        elif (iq or t) <= now:
            row.add_css_class("past")
        row.append(pb.label(f"{t:%H:%M}", "ptime", width_chars=6))
        row.append(pb.label(f"{iq:%H:%M}" if iq else "", "iqtime", width_chars=6))
        return row

    # ----- settings -----

    def bar_update(self):
        pt.subprocess.run(["pkill", f"-RTMIN+{pt.SIGNAL}", "-x", "waybar"], check=False)

    def close_if_inactive(self):
        if time.monotonic() < self._busy_until:
            return False
        return super().close_if_inactive()

    def toggle_lang(self):
        # the whole window changes language and direction, so it is built again; that
        # removes the button that was just clicked, and the focus moving must not close it
        pt.set_config(lang=None if pt.lang() == "ar" else "ar")
        self.bar_update()
        self._busy_until = time.monotonic() + 1.5
        GLib.idle_add(self.rebuild)

    def rebuild(self):
        self.build()
        self.present()
        return False

    def set_chip(self, mode):
        pt.set_config(chip=None if mode == "left" else mode)
        self._busy_until = time.monotonic() + 1
        mark(self.chip_btns, mode)
        self.bar_update()

    def set_dst(self, mode):
        pt.set_config(dst=None if mode == "auto" else mode)
        self._busy_until = time.monotonic() + 1
        mark(self.dst_btns, mode)
        self.bar_update()
        self.refresh_view()

    # ----- change city -----

    def toggle_search(self):
        show = not self.search_box.get_visible()
        self.search_box.set_visible(show)
        self.change_btn.set_label(pt.tr("cancel") if show else pt.tr("change"))
        if show:
            self.entry.grab_focus()

    def set_status(self, text):
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    def search(self):
        query = self.entry.get_text().strip()
        if not query:
            return
        self.set_status(pt.tr("searching"))
        clear(self.results)

        def work():
            try:
                places, err = pt.search_places(query), None
            except Exception as e:
                places, err = [], pt.tr("cant_search").format(type(e).__name__)
            GLib.idle_add(self.show_results, places, err, query)

        threading.Thread(target=work, daemon=True).start()

    def show_results(self, places, err, query):
        clear(self.results)
        if err or not places:
            self.set_status(err or pt.tr("no_city").format(query))
            return False
        self.set_status("")
        for p in places:
            b = Gtk.Button()
            b.add_css_class("result")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            top = Gtk.Box(spacing=6)
            top.append(pb.label(p["city"], "rname", xalign=0))
            if p.get("awail_page"):
                top.append(pb.label(pt.tr("badge"), "badge"))
            box.append(top)
            box.append(pb.label(p["label"], "muted", xalign=0, wrap=True, max_width_chars=40))
            b.set_child(box)
            b.connect("clicked", lambda _b, place=p: self.choose(place))
            self.results.append(b)
        return False

    def choose(self, place):
        pt.save_config(place)
        self.apply(pt.tr("downloading").format(place["city"]))

    def choose_auto(self):
        pt.save_config(None)
        pt.LOCATION_FILE.unlink(missing_ok=True)
        self.apply(pt.tr("finding"))

    def apply(self, message):
        self.toggle_search()
        clear(self.results)
        self.entry.set_text("")
        self.set_status(message)

        def work():
            pt.FAIL_FILE.unlink(missing_ok=True)
            out = pt.chip(force=True)
            self.bar_update()
            GLib.idle_add(self.applied, out.get("class") == "offline")

        threading.Thread(target=work, daemon=True).start()

    def applied(self, failed):
        self.set_status(pt.tr("saved_failed") if failed else "")
        self.refresh_view()
        return False


def mark(buttons, current):
    for mode, b in buttons.items():
        if mode == current:
            b.add_css_class("on")
        else:
            b.remove_css_class("on")


def clear(box):
    child = box.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


pb.run(PrayerPopup, CSS)
