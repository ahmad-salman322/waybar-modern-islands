#!/usr/bin/env python3
# Shared plumbing for the Modern Islands waybar popups (prayer_popup.py, prayer_peek.py).
# Importing it toggles the popup named after the running script (a second click closes
# it), closes the other bar popups, and re-execs with gtk4-layer-shell preloaded, all
# before GTK loads. Then build a PopupWindow subclass and hand it to run().

import os
import signal
import sys
import time

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
# pidfile -> word that must appear in that process's command line
POPUPS = {
    "calendar-popup": "calendar_popup",
    "prayer-popup": "prayer_popup",
}
LIB = "/usr/lib/libgtk4-layer-shell.so"

_name = None


def _pidfile(name):
    return os.path.join(RUNTIME, f"{name}.pid")


def running_pid(name):
    try:
        with open(_pidfile(name)) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if POPUPS[name].encode() in f.read():
                return pid
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass
    return None


def _prepare():
    global _name
    script = os.path.basename(sys.argv[0])
    _name = next((n for n, word in POPUPS.items() if script.startswith(word)), None)
    if _name is None:
        # a helper outside the click-to-toggle group (e.g. prayer_peek.py): it isn't
        # toggled or closed by the others, it only needs gtk4-layer-shell preloaded
        _name = os.path.splitext(script)[0].lower()
        if LIB not in os.environ.get("LD_PRELOAD", "") and os.path.exists(LIB):
            os.environ["LD_PRELOAD"] = LIB
            os.execv(sys.executable, [sys.executable] + sys.argv)
        return
    name = _name
    if LIB not in os.environ.get("LD_PRELOAD", ""):
        pid = running_pid(name)
        if pid and pid != os.getpid():
            os.kill(pid, signal.SIGTERM)  # toggle: second click closes
            sys.exit(0)
        # clicking the bar button closes the popup via focus loss first; don't reopen it
        try:
            if time.time() - os.path.getmtime(_pidfile(name) + ".closed") < 0.5:
                sys.exit(0)
        except FileNotFoundError:
            pass
        for other in POPUPS:
            pid = other != name and running_pid(other)
            if pid:
                os.kill(pid, signal.SIGTERM)
        if os.path.exists(LIB):
            # gtk4-layer-shell must be loaded before libwayland-client
            os.environ["LD_PRELOAD"] = LIB
            os.execv(sys.executable, [sys.executable] + sys.argv)


def child_env():
    """environment for commands started from a popup (without the layer-shell preload)"""
    env = dict(os.environ)
    env.pop("LD_PRELOAD", None)
    return env


_prepare()

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell as LayerShell  # noqa: E402

# colors match the bar's style.css
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
.title { color: #b48cf9; font-weight: 800; font-size: 13px; }
.muted { color: #8a93b8; font-size: 11px; }
.card { background: rgba(255, 255, 255, 0.04); border-radius: 12px; padding: 10px; }
.btn {
    background: rgba(139, 124, 246, 0.16);
    color: #b48cf9;
    border-radius: 10px;
    border: none;
    box-shadow: none;
    padding: 4px 12px;
    min-height: 0;
    font-weight: 700;
}
.btn:hover { background: #8b7cf6; color: #11121c; }
.btn:disabled { opacity: 0.5; }
.chip-btn {
    background: none;
    border: none;
    box-shadow: none;
    border-radius: 8px;
    padding: 2px 6px;
    min-height: 0;
    color: #8a93b8;
}
.chip-btn:hover { background: rgba(255, 255, 255, 0.12); color: #e6e8f2; }
.danger { color: #f27a8a; }
.danger:hover { background: #f27a8a; color: #11121c; }
.status { color: #f5b86b; font-size: 11px; font-weight: 600; }
progressbar trough { min-height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); }
progressbar progress { min-height: 6px; border-radius: 3px; }
scrolledwindow, viewport, list { background: transparent; }
scrollbar { background: transparent; }
scrollbar slider { background: rgba(255, 255, 255, 0.15); border-radius: 4px; min-width: 4px; }
"""


class PopupWindow(Gtk.ApplicationWindow):
    """layer-shell panel under the bar's right side; closes on Esc or when focus moves away"""

    def __init__(self, app, width):
        super().__init__(application=app)
        self.set_title(_name)
        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, 6)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 8)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
        LayerShell.set_namespace(self, _name)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.panel.add_css_class("panel")
        self.panel.set_size_request(width, -1)
        self.set_child(self.panel)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("notify::is-active", self.on_active)
        self._was_active = False

    def on_key(self, _ctrl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def on_active(self, *_):
        if self.is_active():
            self._was_active = True
        elif self._was_active:
            # focus can flicker while the popup maps; only close if it stays away
            GLib.timeout_add(200, self.close_if_inactive)

    def close_if_inactive(self):
        # POPUP_STAY=1 keeps it open (for screenshots while something else has focus)
        if not self.is_active() and not os.environ.get("POPUP_STAY"):
            open(_pidfile(_name) + ".closed", "w").close()
            self.close()
        return False


def button(label, action, *classes, tooltip=None):
    b = Gtk.Button(label=label, tooltip_text=tooltip)
    for c in classes or ("btn",):
        b.add_css_class(c)
    b.connect("clicked", lambda *_: action())
    return b


def label(text="", *classes, **props):
    lab = Gtk.Label(label=text, **props)
    for c in classes:
        lab.add_css_class(c)
    return lab


class Parts(Gtk.Box):
    """a line of short pieces joined by dots; each piece is its own label so Arabic words
    and Latin numbers/units don't get reordered into each other"""

    def __init__(self, *classes):
        super().__init__(spacing=5)
        self.classes = classes

    def set_parts(self, parts):
        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        for i, part in enumerate(p for p in parts if p):
            if i:
                self.append(label("·", *self.classes))
            self.append(label(part, *self.classes))


def run(make_window, css=""):
    pidfile = _pidfile(_name)
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS + css)
    app = Gtk.Application(application_id=f"local.{_name.replace('-', '.')}")

    def activate(app):
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        make_window(app).present()

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
            os.remove(pidfile)
        except FileNotFoundError:
            pass
