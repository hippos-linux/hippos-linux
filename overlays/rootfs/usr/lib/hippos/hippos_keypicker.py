from __future__ import annotations

from typing import Callable

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

UNIT = 4
NAV_START = 15.5

# (label, key, width in key units); a None key leaves a gap of that width.
MAIN_ROWS = (
    (('Esc', 'KEY_ESC', 1), (None, None, 1), ('F1', 'KEY_F1', 1), ('F2', 'KEY_F2', 1), ('F3', 'KEY_F3', 1),
     ('F4', 'KEY_F4', 1), (None, None, 0.5), ('F5', 'KEY_F5', 1), ('F6', 'KEY_F6', 1), ('F7', 'KEY_F7', 1),
     ('F8', 'KEY_F8', 1), (None, None, 0.5), ('F9', 'KEY_F9', 1), ('F10', 'KEY_F10', 1), ('F11', 'KEY_F11', 1),
     ('F12', 'KEY_F12', 1)),
    (('`', 'KEY_GRAVE', 1), ('1', 'KEY_1', 1), ('2', 'KEY_2', 1), ('3', 'KEY_3', 1), ('4', 'KEY_4', 1),
     ('5', 'KEY_5', 1), ('6', 'KEY_6', 1), ('7', 'KEY_7', 1), ('8', 'KEY_8', 1), ('9', 'KEY_9', 1),
     ('0', 'KEY_0', 1), ('-', 'KEY_MINUS', 1), ('=', 'KEY_EQUAL', 1), ('Backspace', 'KEY_BACKSPACE', 2)),
    (('Tab', 'KEY_TAB', 1.5), ('Q', 'KEY_Q', 1), ('W', 'KEY_W', 1), ('E', 'KEY_E', 1), ('R', 'KEY_R', 1),
     ('T', 'KEY_T', 1), ('Y', 'KEY_Y', 1), ('U', 'KEY_U', 1), ('I', 'KEY_I', 1), ('O', 'KEY_O', 1),
     ('P', 'KEY_P', 1), ('[', 'KEY_LEFTBRACE', 1), (']', 'KEY_RIGHTBRACE', 1), ('\\', 'KEY_BACKSLASH', 1.5)),
    (('Caps', 'KEY_CAPSLOCK', 1.75), ('A', 'KEY_A', 1), ('S', 'KEY_S', 1), ('D', 'KEY_D', 1), ('F', 'KEY_F', 1),
     ('G', 'KEY_G', 1), ('H', 'KEY_H', 1), ('J', 'KEY_J', 1), ('K', 'KEY_K', 1), ('L', 'KEY_L', 1),
     (';', 'KEY_SEMICOLON', 1), ("'", 'KEY_APOSTROPHE', 1), ('Enter', 'KEY_ENTER', 2.25)),
    (('Shift', 'KEY_LEFTSHIFT', 2.25), ('Z', 'KEY_Z', 1), ('X', 'KEY_X', 1), ('C', 'KEY_C', 1), ('V', 'KEY_V', 1),
     ('B', 'KEY_B', 1), ('N', 'KEY_N', 1), ('M', 'KEY_M', 1), (',', 'KEY_COMMA', 1), ('.', 'KEY_DOT', 1),
     ('/', 'KEY_SLASH', 1), ('Shift', 'KEY_RIGHTSHIFT', 2.75)),
    (('Ctrl', 'KEY_LEFTCTRL', 1.5), ('Super', 'KEY_LEFTMETA', 1.25), ('Alt', 'KEY_LEFTALT', 1.25),
     ('Space', 'KEY_SPACE', 6), ('Alt', 'KEY_RIGHTALT', 1.25), ('Super', 'KEY_RIGHTMETA', 1.25),
     ('Menu', 'KEY_MENU', 1.25), ('Ctrl', 'KEY_RIGHTCTRL', 1.25)),
)
NAV_ROWS = (
    (('PrtSc', 'KEY_PRINT', 1), ('ScrLk', 'KEY_SCROLLLOCK', 1), ('Pause', 'KEY_PAUSE', 1)),
    (('Ins', 'KEY_INSERT', 1), ('Home', 'KEY_HOME', 1), ('PgUp', 'KEY_PAGEUP', 1)),
    (('Del', 'KEY_DELETE', 1), ('End', 'KEY_END', 1), ('PgDn', 'KEY_PAGEDOWN', 1)),
    (),
    ((None, None, 1), ('↑', 'KEY_UP', 1)),
    (('←', 'KEY_LEFT', 1), ('↓', 'KEY_DOWN', 1), ('→', 'KEY_RIGHT', 1)),
)
EXTRA_ROWS = (
    (('Num', 'KEY_NUMLOCK', 1), ('KP 0', 'KEY_KP0', 1), ('KP 1', 'KEY_KP1', 1), ('KP 2', 'KEY_KP2', 1),
     ('KP 3', 'KEY_KP3', 1), ('KP 4', 'KEY_KP4', 1), ('KP 5', 'KEY_KP5', 1), ('KP 6', 'KEY_KP6', 1),
     ('KP 7', 'KEY_KP7', 1), ('KP 8', 'KEY_KP8', 1), ('KP 9', 'KEY_KP9', 1), ('KP .', 'KEY_KPDOT', 1),
     ('KP +', 'KEY_KPPLUS', 1), ('KP -', 'KEY_KPMINUS', 1), ('KP *', 'KEY_KPASTERISK', 1),
     ('KP /', 'KEY_KPSLASH', 1), ('KP Ent', 'KEY_KPENTER', 1.5)),
    (('Mouse left', 'BTN_LEFT', 3), ('Mouse middle', 'BTN_MIDDLE', 3), ('Mouse right', 'BTN_RIGHT', 3),
     (None, None, 1), ('Not mapped', 'none', 3)),
)


class KeyPicker(Gtk.Box):
    def __init__(self, on_pick: Callable[[list[str]], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class('keypicker')
        self.on_pick = on_pick
        self.buttons: dict[str, Gtk.Button] = {}
        self.combination: list[str] = []
        self.title = Gtk.Label(xalign=0)
        self.title.get_style_context().add_class('choice-title')
        grid = Gtk.Grid(column_homogeneous=True, halign=Gtk.Align.CENTER)
        self.place(grid, MAIN_ROWS, 0, 0)
        self.place(grid, NAV_ROWS, int(NAV_START * UNIT), 0)
        self.place(grid, EXTRA_ROWS, 0, len(MAIN_ROWS) + 1)
        spacer = Gtk.Label()
        spacer.get_style_context().add_class('keypicker-gap')
        grid.attach(spacer, 0, len(MAIN_ROWS), 1, 1)
        self.pack_start(self.title, False, False, 0)
        self.pack_start(grid, True, True, 0)

    def place(self, grid: Gtk.Grid, rows, first_column: int, first_row: int) -> None:
        for row_index, row in enumerate(rows):
            column = first_column
            for label, key, width in row:
                span = int(width * UNIT)
                if key is not None:
                    button = Gtk.Button(label=label)
                    button.get_style_context().add_class('key')
                    button.connect('clicked', lambda _button, key=key: self.pick(key))
                    grid.attach(button, column, first_row + row_index, span, 1)
                    self.buttons[key] = button
                column += span

    def open(self, title: str, current_keys: list[str]) -> None:
        self.title.set_text(title.upper())
        self.combination = []
        for key, button in self.buttons.items():
            context = button.get_style_context()
            context.remove_class('in-combination')
            context.add_class('current') if key in current_keys else context.remove_class('current')
        (self.buttons.get(current_keys[-1] if current_keys else '') or self.buttons['KEY_ESC']).grab_focus()

    def focused_key(self) -> str | None:
        focus = self.get_toplevel().get_focus()
        return next((key for key, button in self.buttons.items() if button is focus), None)

    def toggle_focused(self) -> None:
        key = self.focused_key()
        if key is None or key == 'none':
            return
        context = self.buttons[key].get_style_context()
        if key in self.combination:
            self.combination.remove(key)
            context.remove_class('in-combination')
        else:
            self.combination.append(key)
            context.add_class('in-combination')

    def pick(self, key: str) -> None:
        self.on_pick([] if key == 'none' else self.combination + [key])

    def clear(self) -> None:
        self.on_pick([])
