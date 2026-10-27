# Modern Islands

A colorful, glassy [Waybar](https://github.com/Alexays/Waybar) setup for Hyprland, with a built-in Gregorian and Hijri calendar. The bar is split into three dark islands, and every module sits in its own tinted chip.

![bar](screenshots/bar.png)

<p align="center">
  <img src="screenshots/calendar.png" width="300" alt="Gregorian calendar">
  &nbsp;
  <img src="screenshots/calendar-hijri.png" width="336" alt="Hijri calendar">
</p>

## Features

### The bar

- **Workspaces:** 10 dots. The active one stretches into a violet-to-cyan pill, filled dots have windows, and rings are empty. Scroll to move between workspaces.
- **Center:** weather, the clock, a date chip, and the current media (artist and title, click to play or pause).
- **Right side:** CPU, memory, temperature, Bluetooth, network, brightness, keyboard layout, volume, battery, notifications, and power. Each one has its own color.

### Date chip and calendar popup

- **Date chip:** right-click switches between the **Gregorian** and **Hijri** (Umm al-Qura) date. Left-click opens the calendar popup. The tooltip shows both dates.
- **Calendar popup:** a GTK4 layer-shell panel styled like the bar, with two full calendars:
  - **Gregorian:** the GTK calendar with week numbers. A line above it shows which Hijri months the visible month covers.
  - **Hijri:** its own month grid with Hijri month and year navigation. Each day also shows its Gregorian date, and a line above shows which Gregorian months the Hijri month covers.
  - The footer shows the selected date and how many days it is from today.

| Key | Action |
|---|---|
| Scroll | previous / next month |
| Shift+Scroll, PageUp / PageDown | previous / next year |
| Arrow keys | move by one day |
| `T` | jump to today |
| `H` | switch Hijri / Gregorian (the bar follows) |
| `Esc` or click outside | close |

### Moon sighting

The Hijri date is calculated offline with the Umm al-Qura calendar. Months that really start a day earlier or later, after the crescent is sighted, are handled in two ways:

- **Automatic check:** around the end of each Hijri month (day 28 to day 2), an invisible module asks the [AlAdhan API](https://aladhan.com/islamic-calendar-api) once an hour. If the month was announced as 30 days instead of 29, or started a day late, the bar and the calendar follow the announcement. If the site can't be reached, it waits 6 hours before trying again.
- **Connection status:** under the Hijri grid, a line shows whether the last check reached the site (green) or failed (red), and when. Hover over it to see the error, or press the check button to try again right away. The date chip tooltip shows the same line.
- **Manual correction:** if your region announces a different start, or the API can't be reached from your network, use the `-1` / `+1` buttons under the Hijri grid to move the first day of the month shown. The bar follows it, and the automatic check leaves that month alone.

The Hijri labels in the popup are in Arabic.

## Requirements

Tested on Arch Linux with Hyprland 0.56 and Waybar 0.15.

| Needed for | Packages (Arch names) |
|---|---|
| bar | `waybar`, `ttf-jetbrains-mono-nerd` |
| calendar popup | `python`, `python-gobject`, `gtk4`, `gtk4-layer-shell` |
| Hijri date | `icu` (already installed on almost every system) |
| click actions | `playerctl`, `brightnessctl`, `wireplumber`, `pavucontrol`, `blueman`, `network-manager-applet`, `swaync`, `btop`, `kitty`, and `wlogout` (AUR) |

```sh
sudo pacman -S --needed waybar ttf-jetbrains-mono-nerd python-gobject gtk4 gtk4-layer-shell icu \
    playerctl brightnessctl wireplumber pavucontrol blueman network-manager-applet swaync btop kitty
yay -S wlogout   # or any AUR helper
```

The Hijri conversion calls the system ICU library through `ctypes`, so no pip packages are needed. The click actions are optional: the bar works without them, only that click does nothing.

## Install

```sh
git clone https://github.com/USERNAME/waybar-modern-islands
cd waybar-modern-islands
./install.sh
```

The installer moves your current `~/.config/waybar` to `~/.config/waybar.bak-<date>`, copies the files in, and restarts Waybar.

If Waybar isn't started by your Hyprland config yet, add:

```
exec-once = waybar
```

### Uninstall

Remove the installed folder and move your backup back:

```sh
rm -rf ~/.config/waybar
mv ~/.config/waybar.bak-<date> ~/.config/waybar
```

## Files

```
config.jsonc               bar layout and module settings
style.css                  colors and styles
scripts/date_chip.py       the date chip (Gregorian / Hijri)
scripts/calendar_popup.py  the calendar popup
scripts/hijri.py           Gregorian <-> Hijri conversion, with sighting corrections
scripts/hijri_sync.py      the moon-sighting check
scripts/weather.py         weather from wttr.in
```

Sighting data is saved to `~/.cache/hijri-sync.json`, and the date chip mode to `~/.cache/datechip-mode`.

## Customize

- **Weather location:** it is detected from your IP by [wttr.in](https://wttr.in). To pin a city, set `WEATHER_LOCATION`, for example in `hyprland.conf`:
  ```
  env = WEATHER_LOCATION,Amman
  ```
- **Hijri source:** the default is AlAdhan's `HJCoSA` calendar (Umm al-Qura corrected by the Saudi High Judiciary Council's crescent sightings). To use another method, set `HIJRI_METHOD`, for example `env = HIJRI_METHOD,UAQ`. To check right now from a terminal, run:
  ```sh
  ~/.config/waybar/scripts/hijri_sync.py --force
  ```
- **Colors:** all colors are `@define-color` variables at the top of `style.css`.
- **Terminal:** `kitty` is used for `btop` and `nmtui`. Change it in `config.jsonc` if you use another terminal.
- **Floating islands:** to add a gap from the screen edges, add `"margin-top": 6, "margin-left": 10, "margin-right": 10` to `config.jsonc`.

## Privacy

Two outside services are contacted: wttr.in for the weather (every 30 minutes) and the AlAdhan API for the moon-sighting check (only around the end of each Hijri month). Nothing else leaves your machine.

## License

[MIT](LICENSE)
