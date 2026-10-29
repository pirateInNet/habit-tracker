#!/usr/bin/env python3
"""Habit Tracker: Python + GTK3 (light: no matplotlib, no libadwaita, stdlib JSON).

Run:  python3 habit_tracker.py
Deps: python3-gi, gir1.2-gtk-3.0 (Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0)
Data: ~/.local/share/habit-tracker/data.json
"""
import datetime as dt
import json
import math
import os
import uuid

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DATA_PATH = os.path.join(GLib.get_user_data_dir(), "habit-tracker", "data.json")

BG = (0.118, 0.122, 0.141)
ZONE = [(0.137, 0.145, 0.169), (0.157, 0.165, 0.192)]
GRID = (0.26, 0.27, 0.31)
TEXT = (0.72, 0.74, 0.80)
AGG = (0.96, 0.96, 0.98)
PALETTE_HEX = ["#4cc9a7", "#f4a261", "#7aa2f7", "#e06c75", "#c792ea", "#e5c07b"]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# ----------------------------------------------------------------- storage
class Store:
    def __init__(self):
        self.d = {
            "tags": {"health": 30, "work": None},
            "colors": {},
            "show_all": False,
            "habits": [],
            "log": {},
            "hidden": {},
        }
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                self.d.update(json.load(f))
        except (OSError, ValueError):
            pass

        for t in list(self.d["tags"]) + [h.get("tag") for h in self.d["habits"] if h.get("tag")]:
            self.ensure_color(t)

    def save(self):
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        tmp = DATA_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, DATA_PATH)

    def value(self, day, hid):
        return self.d["log"].get(day.isoformat(), {}).get(hid, 0)

    def set_value(self, day, hid, v):
        row = self.d["log"].setdefault(day.isoformat(), {})
        if v:
            row[hid] = v
        else:
            row.pop(hid, None)
        self.save()

    def hidden_for_day(self, day):
        day_key = day.isoformat()
        hidden = self.d.get("hidden", {}).get(day_key, [])
        if not isinstance(hidden, list):
            return []
        return hidden

    def is_hidden_today(self, hid, day):
        return hid in self.hidden_for_day(day)

    def set_hidden_today(self, hid, day, hidden):
        day_key = day.isoformat()
        hidden_map = self.d.setdefault("hidden", {})
        arr = hidden_map.setdefault(day_key, [])
        if hidden:
            if hid not in arr:
                arr.append(hid)
        else:
            arr = [x for x in arr if x != hid]
            if arr:
                hidden_map[day_key] = arr
            else:
                hidden_map.pop(day_key, None)
        self.save()

    def completion(self, h, v):
        """0..1 for the chart. Yes/No: 0 = False. Number: value / goal."""
        v = max(0.0, float(v or 0))
        if h["kind"] == "bool":
            return 1.0 if v else 0.0
        goal = h.get("target") or max(
            [row.get(h["id"], 0) for row in self.d["log"].values()] + [0]
        )
        return min(v / goal, 1.0) if goal else (1.0 if v else 0.0)

    def habit_points(self, h, v):
        """Weighted score points for a habit."""
        return float(h.get("weight", 1) * self.completion(h, v))

    def average_completion(self, h, days):
        vals = [self.completion(h, self.value(d, h["id"])) for d in days]
        return sum(vals) / len(vals) if vals else 0.0

    def average_habit_points(self, h, days):
        avg = self.average_completion(h, days)
        return float(h.get("weight", 1) * avg)

    def layout(self):
        groups = {}
        for h in self.d["habits"]:
            groups.setdefault(h["tag"], []).append(h)
        tags = self.d["tags"]
        names = [t for t in tags if t in groups] + [t for t in groups if t not in tags]
        fixed = {t: float(tags[t]) for t in names if tags.get(t) is not None}
        rest = [t for t in names if t not in fixed]
        left = 100 - sum(fixed.values())
        each = left / len(rest) if rest and left > 0 else 5
        raw = {t: fixed.get(t, each) for t in names}
        total = sum(raw.values()) or 1
        return [(t, raw[t] / total, groups[t]) for t in names]

    @staticmethod
    def next_color(used):
        for c in PALETTE_HEX:
            if c not in used:
                return c
        return PALETTE_HEX[len(used) % len(PALETTE_HEX)]

    def ensure_color(self, tag):
        if tag not in self.d["colors"]:
            self.d["colors"][tag] = self.next_color(set(self.d["colors"].values()))

    def tag_hex(self, tag):
        self.ensure_color(tag)
        return self.d["colors"][tag]


# ------------------------------------------------------------------- window
class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="Habit Tracker")
        self.set_default_size(1100, 640)
        self.store = Store()
        self.day = dt.date.today()
        self.point_hits = []
        self.show_hidden = False

        # header bar
        hb = Gtk.HeaderBar(show_close_button=True, title="Habit Tracker")
        self.set_titlebar(hb)
        prev = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON)
        nxt = Gtk.Button.new_from_icon_name("go-next-symbolic", Gtk.IconSize.BUTTON)
        self.date_btn = Gtk.Button()
        prev.connect("clicked", lambda *_: self.shift(-1))
        nxt.connect("clicked", lambda *_: self.shift(1))
        self.date_btn.connect("clicked", lambda *_: self.go_today())
        box = Gtk.Box(spacing=4)
        for w in (prev, self.date_btn, nxt):
            box.pack_start(w, False, False, 0)
        hb.pack_start(box)

        self.days = Gtk.SpinButton.new_with_range(3, 90, 1)
        self.days.set_value(14)
        self.days.connect("value-changed", lambda *_: self.chart.queue_draw())
        hb.pack_end(self.days)
        hb.pack_end(Gtk.Label(label="days shown"))

        self.all_btn = Gtk.ToggleButton(label="All habits")
        self.all_btn.set_tooltip_text("Also draw one line per habit (in its tag's color)")
        self.all_btn.set_active(bool(self.store.d.get("show_all")))
        self.all_btn.connect("toggled", self.on_show_all)
        hb.pack_end(self.all_btn)

        self.show_hidden_btn = Gtk.ToggleButton(label="Show hidden habits")
        self.show_hidden_btn.set_tooltip_text("Show habits hidden for this day")
        self.show_hidden_btn.connect("toggled", self.on_show_hidden)
        hb.pack_end(self.show_hidden_btn)

        # table
        self.model = Gtk.ListStore(str, str, str, str, str, bool, bool, str, bool, str)
        self.tree = Gtk.TreeView(model=self.model)
        self.tree.connect("row-activated", self.on_row_activated)
        self.tree.get_selection().connect("changed", self.on_selection_changed)

        for i, title in ((1, "Habit"), (2, "Tag"), (3, "Type"), (4, "Weight")):
            r = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, r, text=i)
            if i in (1, 2):
                col.add_attribute(r, "foreground", 9)
            col.set_resizable(True)
            if i == 1:
                col.set_expand(True)
            self.tree.append_column(col)

        col = Gtk.TreeViewColumn("Entry")
        tog = Gtk.CellRendererToggle()
        tog.set_property("xalign", 0.5)
        tog.connect("toggled", self.on_toggled)

        txt = Gtk.CellRendererText(editable=True)
        txt.set_property("xalign", 0.5)
        txt.connect("edited", self.on_edited)

        col.pack_start(tog, False)
        col.pack_start(txt, True)
        col.add_attribute(tog, "active", 6)
        col.add_attribute(tog, "visible", 5)
        col.add_attribute(txt, "text", 7)
        col.add_attribute(txt, "visible", 8)
        col.set_min_width(110)
        col.set_alignment(0.5)
        self.tree.append_column(col)

        sc = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sc.add(self.tree)

        # note preview panel
        note_frame = Gtk.Frame(label="Note")
        note_frame.set_margin_top(6)
        note_frame.set_margin_bottom(6)
        note_frame.set_margin_start(4)
        note_frame.set_margin_end(4)
        self.note_label = Gtk.Label(
            label="No habit selected",
            xalign=0,
            yalign=0,
            wrap=True,
            selectable=True,
            valign=Gtk.Align.START,
            margin=8,
        )
        note_frame.add(self.note_label)

        # selected habit quick controls
        ctrl_frame = Gtk.Frame(label="Entry")
        ctrl_frame.set_margin_top(6)
        ctrl_frame.set_margin_bottom(6)
        ctrl_frame.set_margin_start(4)
        ctrl_frame.set_margin_end(4)

        self.entry_minus = Gtk.Button(label="-")
        self.entry_value = Gtk.Label(label="0", xalign=0.5)
        self.entry_plus = Gtk.Button(label="+")
        self.hide_today_btn = Gtk.Button(label="Hide today")
        self.entry_box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin=8)
        self.entry_box.pack_start(self.entry_minus, False, False, 0)
        self.entry_box.pack_start(self.entry_value, False, False, 0)
        self.entry_box.pack_start(self.entry_plus, False, False, 0)
        self.entry_box.pack_start(self.hide_today_btn, False, False, 0)

        self.entry_minus.connect("clicked", self.on_entry_minus)
        self.entry_plus.connect("clicked", self.on_entry_plus)
        self.hide_today_btn.connect("clicked", self.on_hide_today)

        ctrl_frame.add(self.entry_box)

        bar = Gtk.Box(spacing=6, margin=6)
        for label, cb in (
            ("Add", self.on_add),
            ("Edit", self.on_edit),
            ("Delete", self.on_delete),
            ("Tags", self.on_tags),
        ):
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            bar.pack_start(b, False, False, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(sc, True, True, 0)
        left.pack_start(note_frame, False, False, 0)
        left.pack_start(ctrl_frame, False, False, 0)
        left.pack_start(bar, False, False, 0)

        # chart
        self.chart = Gtk.DrawingArea()
        self.chart.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.chart.set_has_tooltip(True)
        self.chart.connect("query-tooltip", self.on_query_tooltip)
        self.chart.connect("draw", self.draw)

        paned = Gtk.Paned()
        paned.pack1(left, True, False)
        paned.pack2(self.chart, True, False)
        paned.set_position(470)
        self.add(paned)
        self.refresh()

    def on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if not self.point_hits:
            return False

        best = None
        for px, py, text in self.point_hits:
            dx = x - px
            dy = y - py
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 100:
                if best is None or dist_sq < best[0]:
                    best = (dist_sq, text)

        if best is None:
            return False

        tooltip.set_text(best[1])
        return True

    def on_show_hidden(self, btn):
        self.show_hidden = btn.get_active()
        self.refresh()

    def on_selection_changed(self, selection):
        _model, treeiter = selection.get_selected()
        if treeiter is None:
            self.note_label.set_text("No habit selected")
            self.entry_value.set_text("—")
            self.entry_minus.set_sensitive(False)
            self.entry_plus.set_sensitive(False)
            self.hide_today_btn.set_sensitive(False)
            self.hide_today_btn.set_label("Hide today")
            return

        hid = self.model[treeiter][0]
        h = self.habit(hid)
        self.entry_minus.set_sensitive(True)
        self.entry_plus.set_sensitive(True)
        self.hide_today_btn.set_sensitive(True)

        value = self.store.value(self.day, h["id"])
        if h["kind"] == "bool":
            self.entry_value.set_text("Yes" if value else "No")
        else:
            self.entry_value.set_text(f"{value:g}")

        if self.store.is_hidden_today(hid, self.day):
            self.hide_today_btn.set_label("Show today")
        else:
            self.hide_today_btn.set_label("Hide today")

        note = (h.get("note") or "").strip()
        if not note:
            self.note_label.set_text("No note for this habit.")
        else:
            self.note_label.set_text(note)

    def on_entry_minus(self, *_):
        hid = self.selected()
        if not hid:
            return
        h = self.habit(hid)
        current = self.store.value(self.day, hid)
        if h["kind"] == "bool":
            new_value = 0
        else:
            new_value = max(0.0, current - 1.0)
        self.store.set_value(self.day, hid, new_value)
        self.refresh()

    def on_entry_plus(self, *_):
        hid = self.selected()
        if not hid:
            return
        h = self.habit(hid)
        current = self.store.value(self.day, hid)
        if h["kind"] == "bool":
            new_value = 1
        else:
            new_value = current + 1.0
        self.store.set_value(self.day, hid, new_value)
        self.refresh()

    def on_hide_today(self, *_):
        hid = self.selected()
        if not hid:
            return
        hidden = self.store.is_hidden_today(hid, self.day)
        self.store.set_hidden_today(hid, self.day, not hidden)
        self.refresh()

    # ---- header actions
    def shift(self, n):
        self.day += dt.timedelta(days=n)
        self.refresh()

    def go_today(self):
        self.day = dt.date.today()
        self.refresh()

    def on_show_all(self, btn):
        self.store.d["show_all"] = btn.get_active()
        self.store.save()
        self.chart.queue_draw()

    # ---- table
    def refresh(self):
        self.model.clear()
        for h in self.store.d["habits"]:
            if self.store.is_hidden_today(h["id"], self.day) and not self.show_hidden:
                continue

            v = self.store.value(self.day, h["id"])
            is_bool = h["kind"] == "bool"
            if is_bool:
                detail = "yes / no"
            else:
                detail = h.get("unit") or "number"
                if h.get("target"):
                    detail += f" (goal {h['target']:g})"

            self.model.append([
                h["id"],
                h["name"],
                h["tag"],
                detail,
                f"{h['weight']:g}",
                is_bool,
                bool(v),
                f"{v:g}",
                not is_bool,
                self.store.tag_hex(h["tag"]),
            ])

        label = self.day.strftime("%a %d %b %Y")
        self.date_btn.set_label("Today" if self.day == dt.date.today() else label)
        self.date_btn.set_tooltip_text(label + " (click = jump to today)")
        self.chart.queue_draw()
        self.on_selection_changed(self.tree.get_selection())

    def habit(self, hid):
        return next(h for h in self.store.d["habits"] if h["id"] == hid)

    def on_toggled(self, _r, path):
        row = self.model[path]
        self.store.set_value(self.day, row[0], 0 if row[6] else 1)
        self.refresh()

    def on_edited(self, _r, path, text):
        try:
            v = float(text.strip().replace(",", ".") or 0)
        except ValueError:
            return
        self.store.set_value(self.day, self.model[path][0], max(0.0, v))
        self.refresh()

    def selected(self):
        _m, it = self.tree.get_selection().get_selected()
        return self.model[it][0] if it else None

    def on_row_activated(self, _t, path, _c):
        self.habit_dialog(self.habit(self.model[path][0]))

    def on_add(self, *_):
        self.habit_dialog(None)

    def on_edit(self, *_):
        hid = self.selected()
        if hid:
            self.habit_dialog(self.habit(hid))

    def on_delete(self, *_):
        hid = self.selected()
        if not hid:
            return
        self.store.d["habits"] = [h for h in self.store.d["habits"] if h["id"] != hid]
        for row in self.store.d["log"].values():
            row.pop(hid, None)
        self.store.d.setdefault("hidden", {})
        for day_key, items in list(self.store.d["hidden"].items()):
            self.store.d["hidden"][day_key] = [x for x in items if x != hid]
            if not self.store.d["hidden"][day_key]:
                del self.store.d["hidden"][day_key]
        self.store.save()
        self.refresh()

    # ---- dialogs
    def habit_dialog(self, h):
        dlg = Gtk.Dialog(title="Habit", transient_for=self, modal=True)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        grid = Gtk.Grid(row_spacing=8, column_spacing=10, margin=14)

        name = Gtk.Entry(hexpand=True, activates_default=True)
        tag = Gtk.ComboBoxText.new_with_entry()
        for t in self.store.d["tags"]:
            tag.append_text(t)

        kind = Gtk.ComboBoxText()
        kind.append_text("Yes / No")
        kind.append_text("Number (minutes, reps, anything)")
        unit = Gtk.Entry(placeholder_text="min, reps, pages, ...")
        target = Gtk.Entry(placeholder_text="daily goal (optional, makes 100% on the chart)")
        weight = Gtk.SpinButton.new_with_range(0.5, 20, 0.5)

        rows = [
            ("Name", name),
            ("Tag", tag),
            ("Type", kind),
            ("Unit", unit),
            ("Goal", target),
            ("Weight", weight),
        ]
        for i, (lbl, w) in enumerate(rows):
            grid.attach(Gtk.Label(label=lbl, xalign=1), 0, i, 1, 1)
            grid.attach(w, 1, i, 1, 1)

        note_tv = Gtk.TextView()
        note_tv.set_wrap_mode(Gtk.WrapMode.WORD)
        note_sw = Gtk.ScrolledWindow()
        note_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        note_sw.set_size_request(-1, 120)
        note_sw.add(note_tv)

        note_expander = Gtk.Expander(label="Notes")
        note_expander.set_expanded(False)
        note_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        note_box.pack_start(note_sw, True, True, 0)
        note_expander.add(note_box)

        grid.attach(note_expander, 0, len(rows), 2, 1)

        grid.attach(
            Gtk.Label(
                label="Weight = how many points / how much width this habit gets inside its tag. "
                      "Its color comes from its tag (Tags button).",
                xalign=0,
                wrap=True,
                max_width_chars=44,
            ),
            1,
            len(rows) + 1,
            1,
            1,
        )

        def sync(*_):
            num = kind.get_active() == 1
            unit.set_sensitive(num)
            target.set_sensitive(num)

        kind.connect("changed", sync)

        if h:
            name.set_text(h["name"])
            tag.get_child().set_text(h["tag"])
            kind.set_active(0 if h["kind"] == "bool" else 1)
            unit.set_text(h.get("unit") or "")
            target.set_text(f"{h['target']:g}" if h.get("target") else "")
            weight.set_value(h["weight"])

            buf = note_tv.get_buffer()
            buf.set_text(h.get("note") or "")
        else:
            tag.get_child().set_text(next(iter(self.store.d["tags"]), "general"))
            kind.set_active(0)
            weight.set_value(1)

        sync()

        dlg.get_content_area().add(grid)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK and name.get_text().strip():
            try:
                goal = float(target.get_text().replace(",", ".")) if target.get_text().strip() else None
            except ValueError:
                goal = None

            note_buffer = note_tv.get_buffer()
            note_text = note_buffer.get_text(
                note_buffer.get_start_iter(),
                note_buffer.get_end_iter(),
                False,
            )

            rec = {
                "id": h["id"] if h else uuid.uuid4().hex[:8],
                "name": name.get_text().strip(),
                "tag": tag.get_child().get_text().strip() or "general",
                "kind": "bool" if kind.get_active() == 0 else "num",
                "unit": unit.get_text().strip(),
                "target": goal if kind.get_active() == 1 else None,
                "weight": weight.get_value(),
                "note": note_text.strip(),
            }

            if rec["tag"] not in self.store.d["tags"]:
                self.store.d["tags"][rec["tag"]] = None
            self.store.ensure_color(rec["tag"])

            if h:
                h.update(rec)
            else:
                self.store.d["habits"].append(rec)

            self.store.save()
            self.refresh()

        dlg.destroy()

    def on_tags(self, *_):
        dlg = Gtk.Dialog(title="Tags: width share and color", transient_for=self, modal=True)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dlg.set_default_size(400, 340)

        ls = Gtk.ListStore(str, str, str)
        for t, p in self.store.d["tags"].items():
            ls.append([t, "" if p is None else f"{p:g}", self.store.tag_hex(t)])

        tv = Gtk.TreeView(model=ls)
        for i, title in ((0, "Tag"), (1, "% (empty = the rest)")):
            r = Gtk.CellRendererText(editable=True)
            r.connect("edited", lambda _r, p, t, i=i: ls.set_value(ls.get_iter(p), i, t.strip()))
            c = Gtk.TreeViewColumn(title, r, text=i)
            c.set_expand(True)
            tv.append_column(c)

        swatch = Gtk.CellRendererText(text="██████")
        ccol = Gtk.TreeViewColumn("Color (click)", swatch)
        ccol.add_attribute(swatch, "foreground", 2)
        tv.append_column(ccol)
        tv.set_activate_on_single_click(True)

        def pick(_tv, path, col):
            if col is not ccol:
                return
            ch = Gtk.ColorChooserDialog(title="Tag color", transient_for=dlg, modal=True)
            rgba = Gdk.RGBA()
            rgba.parse(ls[path][2])
            ch.set_rgba(rgba)
            if ch.run() == Gtk.ResponseType.OK:
                c = ch.get_rgba()
                ls[path][2] = "#%02x%02x%02x" % (
                    round(c.red * 255),
                    round(c.green * 255),
                    round(c.blue * 255),
                )
            ch.destroy()

        tv.connect("row-activated", pick)
        sc = Gtk.ScrolledWindow(vexpand=True, margin=10)
        sc.add(tv)

        bar = Gtk.Box(spacing=6, margin_start=10, margin_end=10, margin_bottom=10)
        add = Gtk.Button(label="Add tag")
        rem = Gtk.Button(label="Remove")
        add.connect(
            "clicked",
            lambda *_: ls.append(["new tag", "", Store.next_color({r[2] for r in ls})]),
        )

        def remove(*_):
            _m, it = tv.get_selection().get_selected()
            if it:
                ls.remove(it)

        rem.connect("clicked", remove)
        bar.pack_start(add, False, False, 0)
        bar.pack_start(rem, False, False, 0)

        area = dlg.get_content_area()
        area.pack_start(sc, True, True, 0)
        area.pack_start(bar, False, False, 0)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            tags, colors = {}, {}
            for t, p, c in ls:
                if t:
                    colors[t] = c
                    try:
                        tags[t] = float(p.replace(",", ".")) if p else None
                    except ValueError:
                        tags[t] = None
            self.store.d["tags"] = tags
            self.store.d["colors"] = colors
            for h in self.store.d["habits"]:
                self.store.ensure_color(h["tag"])
            self.store.save()
            self.refresh()
        dlg.destroy()

    # ---- chart
    def draw(self, area, cr):
        W, H = area.get_allocated_width(), area.get_allocated_height()
        cr.set_source_rgb(*BG)
        cr.paint()
        cr.select_font_face("Sans")
        cr.set_font_size(11)
        self.point_hits = []

        visible_habits = [
            h for h in self.store.d["habits"]
            if (not self.store.is_hidden_today(h["id"], self.day)) or self.show_hidden
        ]

        if not visible_habits:
            cr.set_source_rgb(*TEXT)
            cr.move_to(W / 2 - 80, H / 2)
            cr.show_text("Add a habit to start")
            return

        L, R, T, B = 62, 16, 30, 100
        pw, ph = W - L - R, H - T - B
        if pw < 60 or ph < 60:
            return

        n = int(self.days.get_value())
        rowh = ph / n
        days = [self.day - dt.timedelta(days=n - 1 - i) for i in range(n)]
        yc = lambda i: T + ph - (i + 0.5) * rowh

        show_all = self.all_btn.get_active()
        total_points = sum(float(h.get("weight", 1)) for h in visible_habits)
        if total_points <= 0:
            total_points = 1.0

        x_axis_y = T + ph + 14
        cr.set_source_rgb(*GRID)
        cr.move_to(L, x_axis_y)
        cr.line_to(L + pw, x_axis_y)
        cr.stroke()

        tick_values = [0, 0.25, 0.5, 0.75, 1.0]
        for k in tick_values:
            x = L + k * pw
            val = k * total_points
            cr.move_to(x, x_axis_y)
            cr.line_to(x, x_axis_y + 6)
            cr.stroke()
            cr.move_to(x - 10, x_axis_y + 18)
            cr.show_text(f"{val:g}")

        groups = {}
        for h in visible_habits:
            groups.setdefault(h["tag"], []).append(h)

        tags = self.store.d["tags"]
        names = [t for t in tags if t in groups] + [t for t in groups if t not in tags]
        fixed = {t: float(tags[t]) for t in names if tags.get(t) is not None}
        rest = [t for t in names if t not in fixed]
        left = 100 - sum(fixed.values())
        each = left / len(rest) if rest and left > 0 else 5
        raw = {t: fixed.get(t, each) for t in names}
        total = sum(raw.values()) or 1
        layout = [(t, raw[t] / total, groups[t]) for t in names]

        slots, x = [], L
        for gi, (tag, frac, hs) in enumerate(layout):
            zw = pw * frac
            color = hex_to_rgb(self.store.tag_hex(tag))
            base = ZONE[gi % 2]

            if show_all:
                cr.set_source_rgb(*[b * 0.86 + c * 0.14 for b, c in zip(base, color)])
                cr.rectangle(x, T, zw, ph)
                cr.fill()
                cr.set_source_rgb(*color)
                cr.move_to(x + 4, T - 10)
                cr.show_text(f"{tag}  {frac * 100:.0f}%"[: max(4, int(zw / 7))])

            tw = sum(h["weight"] for h in hs) or 1
            sx = x
            for h in hs:
                sw = zw * h["weight"] / tw
                slots.append((h, sx, sw, color))
                sx += sw
            x += zw

        step = max(1, math.ceil(n / max(1, ph / 18)))
        cr.set_line_width(1)
        for i, d in enumerate(days):
            cr.set_source_rgb(*GRID)
            cr.move_to(L, yc(i))
            cr.line_to(L + pw, yc(i))
            cr.stroke()
            if (n - 1 - i) % step == 0:
                cr.set_source_rgb(*TEXT)
                cr.move_to(6, yc(i) + 4)
                cr.show_text(d.strftime("%d %b"))

        if show_all and slots:
            for h, sx, sw, color in slots:
                cr.set_source_rgb(*GRID)
                cr.move_to(sx, T)
                cr.line_to(sx, T + ph)
                cr.stroke()
                cr.set_source_rgb(*color)
                cr.save()
                cr.translate(sx + sw / 2 + 4, T + ph + 8)
                cr.rotate(math.pi / 2)
                cr.show_text(h["name"][:16])
                cr.restore()

            cr.set_source_rgb(*GRID)
            cr.move_to(L + pw, T)
            cr.line_to(L + pw, T + ph)
            cr.stroke()

        if show_all and slots:
            for h, sx, sw, color in slots:
                pad = min(8, sw * 0.15)
                pts = []
                for i, d in enumerate(days):
                    score = self.store.habit_points(h, self.store.value(d, h["id"]))
                    x_pos = sx + pad + (score / total_points) * (sw - 2 * pad)
                    pts.append((x_pos, yc(i)))

                cr.set_source_rgba(*color, 0.9)
                cr.set_line_width(1.6)
                cr.move_to(*pts[0])
                for p in pts[1:]:
                    cr.line_to(*p)
                cr.stroke()

                for i, (px, py) in enumerate(pts):
                    score = self.store.habit_points(h, self.store.value(days[i], h["id"]))
                    self.point_hits.append((px, py, f"{h['name']}: {score:.1f} pts"))
                    cr.arc(px, py, 3.6 if i == n - 1 else 2.2, 0, 2 * math.pi)
                    cr.fill()

                avg_score = self.store.average_habit_points(h, days)
                avg_pts = []
                for i in range(n):
                    x_pos = sx + pad + (avg_score / total_points) * (sw - 2 * pad)
                    avg_pts.append((x_pos, yc(i)))

                cr.set_source_rgba(0.75, 0.75, 0.75, 0.85)
                cr.set_line_width(1.1)
                cr.move_to(*avg_pts[0])
                for p in avg_pts[1:]:
                    cr.line_to(*p)
                cr.stroke()
                for px, py in avg_pts:
                    self.point_hits.append((px, py, f"{h['name']} avg: {avg_score:.1f} pts"))
                    cr.arc(px, py, 2.4, 0, 2 * math.pi)
                    cr.fill()

        if not show_all and slots:
            agg = []
            for i, d in enumerate(days):
                total = 0.0
                for h, _sx, _sw, _c in slots:
                    total += self.store.habit_points(h, self.store.value(d, h["id"]))
                x_pos = L + (total / total_points) * pw
                agg.append((x_pos, yc(i)))

            avg_total = 0.0
            for h, _sx, _sw, _c in slots:
                avg_total += self.store.average_habit_points(h, days)
            avg_x = L + (avg_total / total_points) * pw
            avg_pts = [(avg_x, yc(i)) for i in range(n)]

            cr.set_source_rgba(0.75, 0.75, 0.75, 0.85)
            cr.set_line_width(1.2)
            cr.move_to(*avg_pts[0])
            for p in avg_pts[1:]:
                cr.line_to(*p)
            cr.stroke()
            for px, py in avg_pts:
                self.point_hits.append((px, py, f"All habits avg: {avg_total:.1f} pts"))
                cr.arc(px, py, 2.8, 0, 2 * math.pi)
                cr.fill()

            cr.set_source_rgb(*AGG)
            cr.set_line_width(3)
            cr.move_to(*agg[0])
            for p in agg[1:]:
                cr.line_to(*p)
            cr.stroke()

            for i, (px, py) in enumerate(agg):
                score = 0.0
                for h, _sx, _sw, _c in slots:
                    score += self.store.habit_points(h, self.store.value(days[i], h["id"]))
                self.point_hits.append((px, py, f"All habits: {score:.1f} pts"))
                cr.arc(px, py, 5 if i == n - 1 else 3.2, 0, 2 * math.pi)
                cr.fill()


def main():
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
    win = App()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
