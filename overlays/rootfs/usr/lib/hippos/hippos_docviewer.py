from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, Gtk
from evdev import ecodes

DOWNLOAD_TIMEOUT_S = 10
RENDER_TIMEOUT_S = 15
SCROLL_STEP_SHARE = 0.25
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
TEXT_SUFFIXES = ('.txt', '.md', '.nfo')


def pixbuf_from_bytes(data: bytes) -> GdkPixbuf.Pixbuf:
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    return loader.get_pixbuf()


def fetch(location: str, folder: Path) -> Path:
    if not location.startswith(('http://', 'https://')):
        return Path(location)
    with urllib.request.urlopen(location, timeout=DOWNLOAD_TIMEOUT_S) as response:
        kind = response.headers.get_content_type()
        data = response.read()
    suffix = {'application/pdf': '.pdf', 'application/zip': '.cbz', 'text/plain': '.txt'}.get(kind)
    if suffix is None and kind.startswith('image/'):
        suffix = '.' + kind.split('/', 1)[1]
    target = folder / f'document{suffix or Path(location).suffix}'
    target.write_bytes(data)
    return target


def _natural_key(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', name)]


def page_renderers(path: Path, height: int) -> list[Callable[[], GdkPixbuf.Pixbuf]]:
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        info = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=RENDER_TIMEOUT_S)
        count = int(next((line.split()[-1] for line in info.stdout.splitlines() if line.startswith('Pages:')), '0'))

        def pdf_page(number: int) -> GdkPixbuf.Pixbuf:
            png = subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-png', '-scale-to-y', str(height),
                                  '-scale-to-x', '-1', str(path)], capture_output=True, timeout=RENDER_TIMEOUT_S).stdout
            return pixbuf_from_bytes(png)
        return [lambda number=number: pdf_page(number) for number in range(1, count + 1)]
    if suffix in ('.cbz', '.zip'):
        archive = zipfile.ZipFile(path)
        names = sorted((name for name in archive.namelist() if name.lower().endswith(IMAGE_SUFFIXES)), key=_natural_key)
        return [lambda name=name: pixbuf_from_bytes(archive.read(name)) for name in names]
    if suffix in IMAGE_SUFFIXES:
        return [lambda: GdkPixbuf.Pixbuf.new_from_file(str(path))]
    return []


class DocumentViewer(Gtk.Box):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class('document')
        self.on_close = on_close
        self.folder = tempfile.TemporaryDirectory(prefix='hippos-quickmenu-')
        self.pages: list[Callable[[], GdkPixbuf.Pixbuf]] = []
        self.page = 0
        self.status = Gtk.Label(xalign=0.5)
        self.status.get_style_context().add_class('hint')
        self.scroller = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.text = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.pack_start(self.image, False, False, 0)
        content.pack_start(self.text, False, False, 0)
        self.scroller.add(content)
        self.pack_start(self.scroller, True, True, 0)
        self.pack_end(self.status, False, False, 0)

    def open(self, location: str, height: int) -> None:
        self.page = 0
        self.image.clear()
        self.text.set_text('')
        try:
            path = fetch(location, Path(self.folder.name))
            if path.suffix.lower() in TEXT_SUFFIXES:
                self.pages = []
                self.text.set_text(path.read_text(errors='replace'))
                self.status.set_text('B  back')
                return
            self.pages = page_renderers(path, height)
        except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            self.pages = []
            self.text.set_text(f'Could not open this document: {exc}')
            return
        if not self.pages:
            self.text.set_text('This document has no pages to show.')
            return
        self.show_page()

    def show_page(self) -> None:
        self.image.set_from_pixbuf(self.pages[self.page]())
        self.scroller.get_vadjustment().set_value(0)
        self.status.set_text(f'Page {self.page + 1} / {len(self.pages)}      L1 / R1  page      B  back')

    def turn(self, step: int) -> None:
        if self.pages:
            self.page = max(0, min(len(self.pages) - 1, self.page + step))
            self.show_page()

    def scroll(self, direction: int) -> None:
        adjustment = self.scroller.get_vadjustment()
        adjustment.set_value(adjustment.get_value() + direction * adjustment.get_page_size() * SCROLL_STEP_SHARE)

    def handle_button(self, code: int) -> None:
        if code in (ecodes.BTN_TL, ecodes.BTN_DPAD_LEFT):
            self.turn(-1)
        elif code in (ecodes.BTN_TR, ecodes.BTN_DPAD_RIGHT):
            self.turn(1)
        elif code == ecodes.BTN_DPAD_UP:
            self.scroll(-1)
        elif code == ecodes.BTN_DPAD_DOWN:
            self.scroll(1)
        elif code == ecodes.BTN_EAST:
            self.on_close()

    def handle_hat(self, code: int, value: int) -> None:
        if code == ecodes.ABS_HAT0X:
            self.turn(value)
        else:
            self.scroll(value)
