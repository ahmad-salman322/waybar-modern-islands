#!/usr/bin/env python3
# Calendar popup for the Modern Islands waybar.
# Run once to open, run again (or Esc / click outside) to close.
# Gregorian and Hijri (Umm al-Qura) grids, each with its own month/year navigation.
# Scroll = months, Shift+scroll or PageUp/PageDown = years, arrows = days, T = today,
# H = Hijri / Gregorian (shared with the bar's date chip).

import os
import signal
import sys
import time

PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "calendar-popup.pid")
CLOSED = PIDFILE + ".closed"


def running_pid():
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"calendar_popup" in f.read():
                return pid
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass
    return None


# toggle: if already open, close it and exit
pid = running_pid()
if pid and pid != os.getpid():
    os.kill(pid, signal.SIGTERM)
    sys.exit(0)

# clicking the bar button closes the popup via focus loss first; don't reopen it
try:
    if time.time() - os.path.getmtime(CLOSED) < 0.5:
        sys.exit(0)
except FileNotFoundError:
    pass

# gtk4-layer-shell must be loaded before libwayland-client
LIB = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(LIB) and LIB not in os.environ.get("LD_PRELOAD", ""):
    os.environ["LD_PRELOAD"] = LIB
    os.execv(sys.executable, [sys.executable] + sys.argv)

import datetime
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell as LayerShell

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hijri import DAYS, MONTHS, adjust_month, from_hijri, load_sync, month_length, reload_sync, sync_status, to_hijri
from date_chip import get_mode, set_mode

# Sunday-first, like the Gregorian grid
HIJRI_DAY_NAMES = ["أحد", "اثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت"]
SYNC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hijri_sync.py")

CSS = """
window { background: transparent; }

.panel {
    background: rgba(17, 18, 28, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 14px;
    color: #e6e8f2;
    font-family: "JetBrainsMono Nerd Font";
}

.today-big {
    font-size: 26px;
    font-weight: 800;
    color: #11121c;
    background: linear-gradient(90deg, #8b7cf6, #5ec8f2);
    border-radius: 12px;
    padding: 6px 14px;
}

.today-sub { color: #8a93b8; font-weight: 600; }

calendar {
    background: transparent;
    border: none;
    color: #e6e8f2;
    font-weight: 600;
}

calendar > header { border: none; }
calendar > header > button { color: #5ec8f2; border-radius: 8px; }
calendar > header > button:hover { background: rgba(255, 255, 255, 0.12); }
calendar > header > label { color: #b48cf9; font-weight: 800; }

calendar > grid > label.day-name { color: #f5b86b; font-weight: 800; }
calendar > grid > label.week-number { color: #8a93b8; }
calendar > grid > label.day-number { border-radius: 9px; padding: 4px; }
calendar > grid > label.day-number:hover { background: rgba(255, 255, 255, 0.12); }
calendar > grid > label.day-number.other-month { color: rgba(138, 147, 184, 0.35); }
calendar > grid > label.day-number.today {
    color: #5ec8f2;
    box-shadow: inset 0 0 0 2px #5ec8f2;
}
calendar > grid > label.day-number:selected {
    color: #11121c;
    background: linear-gradient(90deg, #8b7cf6, #5ec8f2);
}

/* hijri grid, styled like the gtk calendar above */
.hnav {
    background: none;
    border: none;
    box-shadow: none;
    color: #5ec8f2;
    border-radius: 8px;
    padding: 2px 6px;
    min-height: 0;
}
.hnav:hover { background: rgba(255, 255, 255, 0.12); }
.hmonth, .hyear { color: #b48cf9; font-weight: 800; }
.hdayname { color: #f5b86b; font-weight: 800; font-size: 11px; }

.hday {
    background: none;
    border: none;
    box-shadow: none;
    border-radius: 9px;
    padding: 2px 0;
    min-width: 36px;
    min-height: 0;
    color: #e6e8f2;
}
.hday:hover { background: rgba(255, 255, 255, 0.12); }
.hday .hnum { font-weight: 700; }
.hday .hgreg { font-size: 9px; color: #8a93b8; }
.hday.other { opacity: 0.35; }
.hday.today { color: #5ec8f2; box-shadow: inset 0 0 0 2px #5ec8f2; }
.hday.selected { background: linear-gradient(90deg, #8b7cf6, #5ec8f2); color: #11121c; }
.hday.selected .hgreg { color: #11121c; }
.hadjust-label { color: #8a93b8; font-size: 11px; font-weight: 600; }
.hadjust {
    background: rgba(245, 184, 107, 0.14);
    color: #f5b86b;
    border: none;
    box-shadow: none;
    border-radius: 8px;
    padding: 0 8px;
    min-height: 0;
    font-weight: 800;
}
.hadjust:hover { background: #f5b86b; color: #11121c; }
.sync { background: rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 6px 8px; }
.sync .hadjust { padding: 2px 10px; font-size: 11px; }
.sync-title { font-size: 11px; font-weight: 800; }
.sync-detail { color: #8a93b8; font-size: 10px; }
.sync.ok .sync-title { color: #7ee0a1; }
.sync.failed .sync-title { color: #f27a8a; }
.sync.never .sync-title { color: #8a93b8; }

.btn {
    background: rgba(139, 124, 246, 0.16);
    color: #b48cf9;
    border-radius: 10px;
    border: none;
    padding: 4px 12px;
    font-weight: 700;
}
.btn:hover { background: #8b7cf6; color: #11121c; }

.selected-label { color: #7ee0a1; font-weight: 700; }
.span-label { color: #5ee0c8; font-weight: 700; }
"""


def load_error():
    return load_sync().get("error") if sync_status()[0] == "failed" else None


def gdate(dt):
    return datetime.date(dt.get_year(), dt.get_month(), dt.get_day_of_month())


def gdatetime(day):
    return GLib.DateTime.new_local(day.year, day.month, day.day, 12, 0, 0)


class HijriGrid(Gtk.Box):
    """month view of the Hijri calendar; calls on_select(date) when a day is picked"""

    def __init__(self, on_select, on_adjust):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.on_select = on_select
        self.on_adjust = on_adjust
        self.selected = datetime.date.today()
        self.year, self.month, _ = to_hijri(self.selected)

        header = Gtk.Box(spacing=2)
        self.month_label = Gtk.Label(width_chars=12)
        self.month_label.add_css_class("hmonth")
        self.year_label = Gtk.Label(width_chars=5)
        self.year_label.add_css_class("hyear")
        for widget in (self.nav("◂", lambda: self.shift(months=-1)), self.month_label,
                       self.nav("▸", lambda: self.shift(months=1))):
            header.append(widget)
        header.append(Gtk.Box(hexpand=True))
        for widget in (self.nav("◂", lambda: self.shift(years=-1)), self.year_label,
                       self.nav("▸", lambda: self.shift(years=1))):
            header.append(widget)
        self.append(header)

        self.grid = Gtk.Grid(column_spacing=2, row_spacing=2, column_homogeneous=True)
        for col, name in enumerate(HIJRI_DAY_NAMES):
            label = Gtk.Label(label=name)
            label.add_css_class("hdayname")
            self.grid.attach(label, col, 0, 1, 1)

        self.cells = []
        for i in range(42):
            num = Gtk.Label()
            num.add_css_class("hnum")
            greg = Gtk.Label()
            greg.add_css_class("hgreg")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(num)
            box.append(greg)
            button = Gtk.Button(child=box)
            button.add_css_class("hday")
            button.connect("clicked", self.on_cell)
            button.day = None
            self.grid.attach(button, i % 7, i // 7 + 1, 1, 1)
            self.cells.append((button, num, greg))
        self.append(self.grid)

        # moon sighting differs from the calculation: move this month's first day
        adjust = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        label = Gtk.Label(label="بداية الشهر حسب الرؤية")
        label.add_css_class("hadjust-label")
        earlier = Gtk.Button(label="-1", tooltip_text="Month starts a day earlier")
        later = Gtk.Button(label="+1", tooltip_text="Month starts a day later")
        for button, days in ((earlier, -1), (later, 1)):
            button.add_css_class("hadjust")
            button.connect("clicked", lambda _b, n=days: self.adjust(n))
        adjust.append(earlier)
        adjust.append(label)
        adjust.append(later)
        self.append(adjust)

        # did the moon-sighting check reach the site? (see hijri_sync.py)
        self.sync = Gtk.Box(spacing=8)
        self.sync.add_css_class("sync")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.sync_title = Gtk.Label(xalign=1)
        self.sync_title.add_css_class("sync-title")
        self.sync_detail = Gtk.Label(xalign=1)
        self.sync_detail.add_css_class("sync-detail")
        text.append(self.sync_title)
        text.append(self.sync_detail)
        self.check_btn = Gtk.Button(label="تحقق الآن", valign=Gtk.Align.CENTER)
        self.check_btn.add_css_class("hadjust")
        self.check_btn.connect("clicked", lambda *_: self.check_now())
        self.sync.append(self.check_btn)
        self.sync.append(text)
        self.append(self.sync)
        self.show_status()

    def show_status(self):
        state, title, detail = sync_status()
        error = load_error()
        for cls in ("ok", "failed", "never"):
            if cls == state:
                self.sync.add_css_class(cls)
            else:
                self.sync.remove_css_class(cls)
        self.sync_title.set_label(f"{title} ●")
        self.sync_detail.set_label(detail)
        self.sync.set_tooltip_text(error or None)

    def check_now(self):
        self.check_btn.set_sensitive(False)
        self.sync_title.set_label("جارٍ التحقق…")
        self.sync_detail.set_label("")
        env = dict(os.environ)
        env.pop("LD_PRELOAD", None)

        def run():
            try:
                subprocess.run([sys.executable, SYNC, "--force"], env=env,
                               capture_output=True, timeout=60)
            except subprocess.TimeoutExpired:
                pass
            GLib.idle_add(done)

        def done():
            reload_sync()
            self.check_btn.set_sensitive(True)
            self.on_adjust()  # a new month start may move today's date
            self.show_status()

        threading.Thread(target=run, daemon=True).start()

    def nav(self, text, action):
        button = Gtk.Button(label=text)
        button.add_css_class("hnav")
        button.connect("clicked", lambda *_: action())
        return button

    def select(self, day):
        self.selected = day
        self.year, self.month, _ = to_hijri(day)
        self.redraw()
        self.on_select(day)

    def shift(self, months=0, years=0, days=0):
        if days:
            self.select(self.selected + datetime.timedelta(days=days))
            return
        _, _, d = to_hijri(self.selected)
        m = self.month - 1 + months
        y = self.year + years + m // 12
        m = m % 12 + 1
        self.select(from_hijri(y, m, min(d, month_length(y, m))))

    def adjust(self, days):
        if not adjust_month(self.year, self.month, days):
            self.error_bell()
            return
        self.redraw()
        self.on_adjust()

    def on_cell(self, button):
        if button.day:
            self.select(button.day)

    def redraw(self):
        self.month_label.set_label(MONTHS[self.month - 1])
        self.year_label.set_label(str(self.year))
        first = from_hijri(self.year, self.month, 1)
        length = month_length(self.year, self.month)
        offset = (first.weekday() + 1) % 7  # Sunday = 0
        today = datetime.date.today()
        for i, (button, num, greg) in enumerate(self.cells):
            day = first + datetime.timedelta(days=i - offset)
            inside = 0 <= i - offset < length
            num.set_label(str(i - offset + 1) if inside else str(to_hijri(day)[2]))
            greg.set_label(day.strftime("%-d/%-m"))
            button.day = day
            for cls, on in (("other", not inside), ("today", day == today), ("selected", day == self.selected)):
                if on:
                    button.add_css_class(cls)
                else:
                    button.remove_css_class(cls)


class Popup(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("calendar-popup")

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, 6)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
        LayerShell.set_namespace(self, "calendar-popup")

        self.mode = get_mode()
        self.selected = datetime.date.today()

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("panel")

        top = Gtk.Box(spacing=12)
        self.big = Gtk.Label()
        self.big.add_css_class("today-big")
        self.sub = Gtk.Label(xalign=0)
        self.sub.add_css_class("today-sub")
        top.append(self.big)
        top.append(self.sub)
        panel.append(top)

        # months of the other calendar covered by the month on screen
        self.span = Gtk.Label()
        self.span.add_css_class("span-label")
        panel.append(self.span)

        self.cal = Gtk.Calendar()
        self.cal.set_show_week_numbers(True)
        self.cal.connect("day-selected", self.on_greg_selected)
        self.hgrid = HijriGrid(self.on_hijri_selected, self.on_hijri_adjusted)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.cal, "greg")
        self.stack.add_named(self.hgrid, "hijri")
        panel.append(self.stack)

        bottom = Gtk.Box(spacing=8)
        self.sel = Gtk.Label(hexpand=True, xalign=0)
        self.sel.add_css_class("selected-label")
        self.mode_btn = Gtk.Button()
        self.mode_btn.add_css_class("btn")
        self.mode_btn.connect("clicked", lambda *_: self.toggle_mode())
        today_btn = Gtk.Button(label="Today")
        today_btn.add_css_class("btn")
        today_btn.connect("clicked", lambda *_: self.go_today())
        bottom.append(self.sel)
        bottom.append(self.mode_btn)
        bottom.append(today_btn)
        panel.append(bottom)

        self.set_child(panel)
        self.refresh()

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        self.stack.add_controller(scroll)

        # close when focus moves elsewhere (click outside)
        self.connect("notify::is-active", self.on_active)
        self._was_active = False

    def hijri(self):
        return self.mode == "hijri"

    def toggle_mode(self):
        self.mode = "greg" if self.hijri() else "hijri"
        set_mode(self.mode)
        self.refresh()

    def refresh(self):
        now = datetime.date.today()
        if self.hijri():
            y, m, d = to_hijri(now)
            self.big.set_label(str(d))
            self.sub.set_label(f"{DAYS[now.weekday()]}\n{MONTHS[m - 1]} {y}")
            self.mode_btn.set_label("ميلادي")
            self.hgrid.select(self.selected)
        else:
            self.big.set_label(now.strftime("%d"))
            self.sub.set_label(now.strftime("%A\n%B %Y"))
            self.mode_btn.set_label("هجري")
            self.set_cal(gdatetime(self.selected))
        self.stack.set_visible_child_name(self.mode)
        self.update_labels()

    def go_today(self):
        self.select(datetime.date.today())

    def select(self, day):
        if self.hijri():
            self.hgrid.select(day)
        else:
            self.set_cal(gdatetime(day))

    def shift(self, months=0, years=0, days=0):
        if self.hijri():
            self.hgrid.shift(months=months, years=years, days=days)
            return
        d = self.cal.get_date()
        if days:
            self.set_cal(d.add_days(days))
            return
        # keep the day valid when jumping between months of different length
        d = d.add_days(1 - d.get_day_of_month())
        d = d.add_full(years, months, 0, 0, 0, 0)
        self.set_cal(d)

    def set_cal(self, dt):
        # select_day is deprecated since GTK 4.20 in favour of set_date
        if hasattr(self.cal, "set_date"):
            self.cal.set_date(dt)
        else:
            self.cal.select_day(dt)

    def on_greg_selected(self, cal):
        self.selected = gdate(cal.get_date())
        self.update_labels()

    def on_hijri_selected(self, day):
        self.selected = day
        self.update_labels()

    def on_hijri_adjusted(self):
        # refresh today's header and the bar's date chip, staying on the same month
        shown = (self.hgrid.year, self.hgrid.month)
        set_mode(self.mode)
        self.refresh()
        self.hgrid.year, self.hgrid.month = shown
        self.hgrid.redraw()

    def update_labels(self):
        day = self.selected
        diff = (day - datetime.date.today()).days
        if self.hijri():
            rel = "اليوم" if diff == 0 else (f"بعد {diff} يوم" if diff > 0 else f"قبل {-diff} يوم")
            y, m, d = to_hijri(day)
            self.sel.set_label(f"{d} {MONTHS[m - 1]} {y} · {rel}")
            # gregorian months covered by this hijri month
            first = from_hijri(y, m, 1)
            last = first + datetime.timedelta(days=month_length(y, m) - 1)
            if first.year == last.year:
                span = f"{first:%B} – {last:%B %Y}" if first.month != last.month else f"{first:%B %Y}"
            else:
                span = f"{first:%B %Y} – {last:%B %Y}"
        else:
            rel = "today" if diff == 0 else (f"in {diff} days" if diff > 0 else f"{-diff} days ago")
            self.sel.set_label(f"{day:%a %d %b %Y} · {rel}")
            # hijri months covered by this gregorian month
            first = day.replace(day=1)
            last = (first + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
            y1, m1, _ = to_hijri(first)
            y2, m2, _ = to_hijri(last)
            if (y1, m1) == (y2, m2):
                span = f"{MONTHS[m1 - 1]} {y1}"
            elif y1 == y2:
                span = f"{MONTHS[m1 - 1]} – {MONTHS[m2 - 1]} {y2}"
            else:
                span = f"{MONTHS[m1 - 1]} {y1} – {MONTHS[m2 - 1]} {y2}"
        self.span.set_label(span)

    def on_key(self, _ctrl, keyval, _code, _state):
        hijri_arrows = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1, Gdk.KEY_Up: -7, Gdk.KEY_Down: 7}
        if keyval == Gdk.KEY_Escape:
            self.close()
        elif keyval == Gdk.KEY_Page_Up:
            self.shift(years=-1)
        elif keyval == Gdk.KEY_Page_Down:
            self.shift(years=1)
        elif keyval in (Gdk.KEY_t, Gdk.KEY_T):
            self.go_today()
        elif keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.toggle_mode()
        elif self.hijri() and keyval in hijri_arrows:
            self.shift(days=hijri_arrows[keyval])
        else:
            return False
        return True

    def on_scroll(self, ctrl, _dx, dy):
        if dy == 0:
            return False
        step = 1 if dy > 0 else -1
        if ctrl.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK:
            self.shift(years=step)
        else:
            self.shift(months=step)
        return True

    def on_active(self, *_):
        if self.is_active():
            self._was_active = True
        elif self._was_active:
            # focus can flicker while the popup maps; only close if it stays away
            GLib.timeout_add(200, self.close_if_inactive)

    def close_if_inactive(self):
        if not self.is_active():
            open(CLOSED, "w").close()
            self.close()
        return False


def main():
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))

    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)

    app = Gtk.Application(application_id="local.calendar.popup")

    def activate(app):
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = Popup(app)
        win.present()

    app.connect("activate", activate)
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except (ImportError, ValueError):
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: (app.quit(), False)[1])
    try:
        app.run([])
    finally:
        try:
            os.remove(PIDFILE)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
