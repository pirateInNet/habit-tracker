# Habit Tracker

A lightweight GTK3 habit tracker for daily progress tracking.

This app lets you:
- add and edit habits
- group habits by tag
- track yes/no and numeric habits
- visualize progress over time
- compare each habit against its historical average
- toggle a per-habit overlay view and a single aggregate view

It is intentionally simple and dependency-light: no matplotlib, no libadwaita, and no heavy UI framework.

## Features

- Daily check-in for habits
- Bool habits: yes/no
- Numeric habits: minutes, reps, pages, etc.
- Tag-based organization
- Weighted habit widths inside each tag
- Historical chart view
- Per-habit lines plus a combined all-habits line
- Grey historical average line
- Hover tooltips showing percentages on chart points
- Data stored locally as JSON

## Requirements

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0
```

You may also need:
- `python3-gobject` depending on your system configuration

## Install

Clone the repository:

```bash
git clone <your-repo-url>
cd <repo-folder>
```

Then run:

```bash
python3 habit_tracker.py
```

## Running

From the project directory:

```bash
python3 habit_tracker.py
```

The app will open a GTK window and begin tracking habits.

## Data storage

The app saves its data in:

```bash
~/.local/share/habit-tracker/data.json
```

This file stores:
- habit definitions
- tags
- colors
- daily log values
- settings such as whether “All habits” is enabled

## Habit types

### Yes / No
Use this for habits like:
- took a walk
- drank water
- meditated

### Number
Use this for habits like:
- minutes worked
- reps completed
- pages read

For numeric habits, you can optionally set a daily goal. The chart uses that goal to calculate completion percent.

## Chart behavior

- Default view: only the aggregate line is shown
- “All habits” mode: each habit is drawn separately in its tag color
- Grey average line is shown in both modes
- Hovering over plotted points shows the percent value

## Project layout

```text
.
├── habit_tracker.py
├── README.md
└── .gitignore
```

## Notes

This app is intended to be lightweight and easy to run on a local desktop without needing a complex Python environment.

## Troubleshooting

### GTK import errors
If Python reports a GTK import problem, make sure you installed:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

Then try again.

### App does not start
Check that Python 3 is installed:

```bash
python3 --version
```

### Data not saved
Ensure you have write access to your user config directory and that the app can create:

```bash
~/.local/share/habit-tracker
```

or add a license file manually.

## Contributing

Feel free to fork, modify, and improve the app. If you add features or fix bugs, open a pull request.
