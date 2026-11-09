#!/bin/sh
# Fast path for the hold shortcut: signal the background prayer window (prayer_peek.py).
#   prayer_peek.sh show   (key press)     prayer_peek.sh hide   (key release)
pid=$(cat "${XDG_RUNTIME_DIR:-/tmp}/prayer-peek.pid" 2>/dev/null)
case "$1" in
    show) kill -USR1 "$pid" 2>/dev/null || exec "$(dirname "$0")/prayer_peek.py" show ;;
    hide) kill -USR2 "$pid" 2>/dev/null ;;
esac
