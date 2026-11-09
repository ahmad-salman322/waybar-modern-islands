#!/usr/bin/env python3
# Hold a shortcut to peek at the prayer times: the same window as the prayer chip's
# popup, in the middle of the screen, shown only while the keys are held.
#
# To appear instantly it runs in the background from login with the window already
# built, and the shortcut only tells it to show or hide:
#
#   prayer_peek.py         start in the background (exec-once)
#   prayer_peek.py show     show the window (key press); starts it first if needed
#   prayer_peek.py hide     hide it (key release)
#
# While shown it also hides itself when Super, Shift or P is released, or on Esc.

import os
import signal
import subprocess
import sys

PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "prayer-peek.pid")
cmd = sys.argv[1] if len(sys.argv) > 1 else ""


def running_pid():
    try:
        pid = int(open(PIDFILE).read())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
        if b"PrayerPeek" in cmdline or b"prayer_peek" in cmdline:
            return pid
    except (OSError, ValueError):
        pass
    return None


# show / hide: just signal the running window, before loading anything heavy
if cmd in ("show", "hide") and "LD_PRELOAD" not in os.environ:
    pid = running_pid()
    if pid:
        os.kill(pid, signal.SIGUSR1 if cmd == "show" else signal.SIGUSR2)
    elif cmd == "show":
        # not running yet (first use): start it, shown right away
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--start-shown"],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(0)
if "LD_PRELOAD" not in os.environ and running_pid():
    sys.exit(0)        # already running in the background

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import PopupBase as pb          # re-execs with gtk4-layer-shell preloaded
except ImportError:
    import popup_base as pb
try:
    import PrayerPopup as popup
except ImportError:
    import prayer_popup as popup
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell as LayerShell  # noqa: E402

RELEASE_KEYS = (Gdk.KEY_Super_L, Gdk.KEY_Super_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
                Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_p, Gdk.KEY_P)


class PeekWindow(popup.PrayerPopup):
    def __init__(self, app):
        super().__init__(app)
        LayerShell.set_namespace(self, "prayer-peek")
        # no anchors: the middle of the screen
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, False)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, False)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        keys = Gtk.EventControllerKey()
        keys.connect("key-released", self.on_release)
        self.add_controller(keys)

    def show_now(self):
        # take the keyboard so letting go of the keys is seen here too
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
        self.set_visible(True)
        self.present()
        GLib.idle_add(lambda: (self.build(), False)[1])   # fresh times, after it is on screen

    def hide_now(self):
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        self.set_visible(False)

    def on_release(self, _ctrl, keyval, _code, _state):
        if keyval in RELEASE_KEYS:
            self.hide_now()

    # Esc and losing focus hide it instead of closing, so it stays ready
    def close(self):
        self.hide_now()

    def close_if_inactive(self):
        if not self.is_active() and self.get_visible():
            self.hide_now()
        return False


def main():
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    provider = Gtk.CssProvider()
    provider.load_from_string(pb.CSS + popup.CSS)
    app = Gtk.Application(application_id="local.prayer.peek")
    state = {}

    def activate(app):
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = state["win"] = PeekWindow(app)
        app.hold()   # keep running while the window is hidden
        if "--start-shown" in sys.argv:
            win.show_now()

    app.connect("activate", activate)
    try:
        gi_unix = __import__("gi.repository.GLibUnix", fromlist=["GLibUnix"])
        add_signal = gi_unix.signal_add
    except ImportError:
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_HIGH, signal.SIGUSR1, lambda *_: (state["win"].show_now(), True)[1])
    add_signal(GLib.PRIORITY_HIGH, signal.SIGUSR2, lambda *_: (state["win"].hide_now(), True)[1])
    add_signal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: (app.quit(), False)[1])
    try:
        app.run([])
    finally:
        try:
            os.remove(PIDFILE)
        except FileNotFoundError:
            pass


main()
