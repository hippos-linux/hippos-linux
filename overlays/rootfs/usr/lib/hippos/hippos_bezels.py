"""Bezel / decoration helpers for emulatorlauncher."""

from __future__ import annotations

import json
import logging
import shutil
import struct
from pathlib import Path
from typing import Optional, TypedDict

_log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

USER_DECORATIONS   = Path('/userdata/decorations')
SYSTEM_DECORATIONS = Path('/usr/share/hippos/decorations')
CONTROLLER_OVERLAYS = Path('/usr/share/hippos/controller-overlays')

RUNTIME_BEZEL       = Path('/var/run/hippos/bezel.png')
SHADER_BEZEL_DIR    = Path('/var/run/hippos/shader_bezels')
SHADER_BEZEL        = SHADER_BEZEL_DIR / 'bezel.png'


class BezelInfos(TypedDict):
    png:              Path
    info:             Path
    layout:           Path
    mamezip:          Path
    specific_to_game: bool


# ── PNG header read (no PIL required) ─────────────────────────────────────────

def fast_image_size(path: Path) -> tuple[int, int]:
    try:
        with path.open('rb') as f:
            head = f.read(32)
        if len(head) != 32 or struct.unpack('>i', head[4:8])[0] != 0x0d0a1a0a:
            return -1, -1
        return struct.unpack('>ii', head[16:24])
    except OSError:
        return -1, -1


# ── Bezel search ──────────────────────────────────────────────────────────────

def get_bezel_infos(
    rom: Path,
    bezel: str,
    system: str,
    emulator: str,
) -> Optional[BezelInfos]:
    """Search for bezel PNG in priority order. Returns None if none found."""
    rom_base = rom.stem

    # Build candidate list in priority order:
    # per-game (user) → per-game (system) → per-system (user) → per-system (system) → default
    candidates: list[tuple[Path, bool]] = [
        (USER_DECORATIONS   / bezel / 'games' / system / f'{rom_base}.png', True),
        (SYSTEM_DECORATIONS / bezel / 'games' / system / f'{rom_base}.png', True),
        (USER_DECORATIONS   / bezel / 'games' / f'{rom_base}.png',          True),
        (SYSTEM_DECORATIONS / bezel / 'games' / f'{rom_base}.png',          True),
        (USER_DECORATIONS   / bezel / 'systems' / f'{system}.png',          False),
        (SYSTEM_DECORATIONS / bezel / 'systems' / f'{system}.png',          False),
        (USER_DECORATIONS   / bezel / 'default.png',                        False),
        (SYSTEM_DECORATIONS / bezel / 'default.png',                        False),
    ]

    for png, specific in candidates:
        if png.exists():
            base = png.with_suffix('')
            return BezelInfos(
                png=png,
                info=base.with_suffix('.info'),
                layout=base.with_suffix('.lay'),
                mamezip=base.with_suffix('.zip'),
                specific_to_game=specific,
            )

    return None


# ── Image operations ───────────────────────────────────────────────────────────

def resize_image(src: Path, dst: Path, width: int, height: int, stretch: bool = False) -> None:
    from PIL import Image, ImageOps
    img = Image.open(src)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    if stretch:
        img = ImageOps.fit(img, (width, height))
    else:
        img = img.resize((width, height), Image.Resampling.BICUBIC)
    img.save(dst, format='PNG')


def tattoo_image(src: Path, dst: Path, system: str, tattoo_type: str,
                 tattoo_file: Optional[str], corner: str, resize: bool) -> None:
    """Composite a controller overlay onto the bezel."""
    from PIL import Image

    if tattoo_type == 'system':
        tattoo_path = CONTROLLER_OVERLAYS / f'{system}.png'
        if not tattoo_path.exists():
            tattoo_path = CONTROLLER_OVERLAYS / 'generic.png'
    elif tattoo_type == 'custom' and tattoo_file:
        tattoo_path = Path(tattoo_file)
    else:
        tattoo_path = CONTROLLER_OVERLAYS / 'generic.png'

    if not tattoo_path.exists():
        _log.warning("tattoo: image not found: %s", tattoo_path)
        shutil.copy2(src, dst)
        return

    back = Image.open(src).convert('RGBA')
    tattoo = Image.open(tattoo_path).convert('RGBA')
    w, h = back.size
    tw, th = tattoo.size

    if resize:
        twtemp = int((225 / 1920) * w)
        pcent = twtemp / tw
        th = int(th * pcent)
        tattoo = tattoo.resize((twtemp, th), Image.Resampling.BICUBIC)
        tw = twtemp
    elif tw > w or th > h:
        pcent = w / tw
        th = int(th * pcent)
        tattoo = tattoo.resize((w, th), Image.Resampling.BICUBIC)
        tw = w

    margin = int((20 / 1080) * h)
    canvas = Image.new('RGBA', back.size)
    c = corner.upper()
    if c == 'NE':
        canvas.paste(tattoo, (w - tw, margin))
    elif c == 'SE':
        canvas.paste(tattoo, (w - tw, h - th - margin))
    elif c == 'SW':
        canvas.paste(tattoo, (0, h - th - margin))
    else:  # NW default
        canvas.paste(tattoo, (0, margin))

    result = Image.alpha_composite(back, canvas)
    result.save(dst, format='PNG')


# ── Gun border ────────────────────────────────────────────────────────────────

GUN_OVERLAYS = Path('/usr/share/hippos/guns-overlays')
GUN_HELP_PNG = Path('/var/run/hippos/gun_help.png')
_GUN_HELP_CACHE = Path('/var/run/hippos/gun_help_default.png')

_BORDER_SIZES: dict[str, tuple[int, int]] = {
    'thin':   (1, 0),
    'medium': (2, 0),
    'big':    (2, 1),
}


def gun_border_image(
    src: Path,
    dst: Path,
    aspect_ratio: Optional[str] = None,
    inner_pct: int = 2,
    outer_pct: int = 3,
    inner_color: str = '#ffffff',
    outer_color: str = '#000000',
) -> int:
    """Draw inner+outer gun border rectangles onto bezel. Returns total border px."""
    from PIL import Image, ImageDraw

    w, h = fast_image_size(src)

    # Centre a 4:3 area if widescreen and 4:3 forced
    if abs(w / h - 4 / 3) < 0.01 or aspect_ratio != '4:3':
        new_w = w
    else:
        new_w = int((4 / 3) * h)
    offset_x = (w - new_w) // 2

    outer = max(0, w * outer_pct // 100)
    inner = max(1, w * inner_pct // 100)

    outer_rects = [
        [(offset_x,                      0),         (offset_x + new_w,          outer)],
        [(offset_x + new_w - outer,      0),         (offset_x + new_w,          h)],
        [(offset_x,                      h - outer), (offset_x + new_w,          h)],
        [(offset_x,                      0),         (offset_x + outer,           h)],
    ]
    inner_rects = [
        [(offset_x + outer,              outer),              (offset_x + new_w - outer,      outer + inner)],
        [(offset_x + new_w - outer - inner, outer),          (offset_x + new_w - outer,      h - outer)],
        [(offset_x + outer,              h - outer - inner), (offset_x + new_w - outer,      h - outer)],
        [(offset_x + outer,              outer),              (offset_x + outer + inner,      h - outer)],
    ]

    back = Image.open(src)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    img.paste(back, (0, 0, w, h))
    draw = ImageDraw.Draw(img)
    for rect in outer_rects:
        draw.rectangle(rect, fill=outer_color)
    for rect in inner_rects:
        draw.rectangle(rect, fill=inner_color)
    img.save(dst, format='PNG')
    return outer + inner


def gun_border_color(conf: dict[str, str]) -> str:
    mapping = {'red': '#ff0000', 'green': '#00ff00', 'blue': '#0000ff', 'white': '#ffffff'}
    return mapping.get(conf.get('controllers.guns.borderscolor', ''), '#ffffff')


# ── Gun help overlay ───────────────────────────────────────────────────────────

_DEFAULT_REPLACEMENTS = {
    '<TRIGGER>': 'TRIGGER', '<ACTION>': 'ACTION',
    '<START>': 'START',     '<SELECT>': 'SELECT',
    '<SUB1>': 'SUB1',       '<SUB2>': 'SUB2',   '<SUB3>': 'SUB3',
    '<UP>': 'UP',           '<DOWN>': 'DOWN',
    '<LEFT>': 'LEFT',       '<RIGHT>': 'RIGHT',
}


def _png_with_texts(src: Path, dst: Path, data: dict, height: int) -> None:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(src)
    ratio = img.width / img.height
    img = img.resize((int(height * ratio), height))
    draw = ImageDraw.Draw(img)

    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def get_font(size: int) -> ImageFont.FreeTypeFont:
        if size not in fonts:
            if font_path.exists():
                fonts[size] = ImageFont.truetype(str(font_path), size)
            else:
                fonts[size] = ImageFont.load_default()
        return fonts[size]

    base_font_size = int(data.get('font_size_per_height', 0.04) * height)
    iw, ih = img.size
    color = data.get('color', 'black')

    for text in data.get('texts', []):
        val = text.get('value', '')
        if not val:
            continue
        # draw connecting lines
        if 'line' in text:
            pts_raw = text['line']
            pts = [(pts_raw[i] * iw, pts_raw[i + 1] * ih)
                   for i in range(0, len(pts_raw) - 1, 2)]
            draw.line(pts, fill=text.get('line_color', 'black'), width=2)
        # draw text
        if 'x' in text and 'y' in text:
            fs = int(text.get('font_size_per_height', data.get('font_size_per_height', 0.04)) * ih)
            font = get_font(fs)
            x, y = int(text['x'] * iw), int(text['y'] * ih)
            tc = text.get('color', color)
            align = text.get('align', 'left')
            if align in ('center', 'right'):
                tw = draw.textlength(val, font=font)
                x -= int(tw / 2) if align == 'center' else int(tw)
            draw.text((x, y), val, fill=tc, font=font)

    img.save(dst, 'PNG')


def generate_gun_help(
    system: str,
    rom: Path,
    lightgun: bool,
    game_gun: dict[str, str],
    resolution: tuple[int, int],
) -> None:
    """Generate gun help overlay at GUN_HELP_PNG. No-op if no gun active."""
    if not lightgun or not game_gun:
        if GUN_HELP_PNG.exists():
            GUN_HELP_PNG.unlink()
        return

    gun_name = game_gun.get('name', 'default')
    gun_png  = GUN_OVERLAYS / f'{gun_name}.png'
    gun_info = GUN_OVERLAYS / f'{gun_name}.infos'

    if not gun_png.exists():
        _log.info("gun help: overlay not found for gun '%s'", gun_name)
        return

    # Use cached version if available and no customisation needed
    if _GUN_HELP_CACHE.exists():
        shutil.copy2(_GUN_HELP_CACHE, GUN_HELP_PNG)
        _log.info("gun help: using cache")
        return

    data: dict = {}
    if gun_info.exists():
        try:
            data = json.loads(gun_info.read_text())
        except Exception as exc:
            _log.warning("gun help: could not parse %s: %s", gun_info, exc)

    # Apply button label replacements
    replacements = dict(_DEFAULT_REPLACEMENTS)
    for text in data.get('texts', []):
        for key in list(replacements):
            text['value'] = text.get('value', '').replace(key, replacements[key])

    GUN_HELP_PNG.parent.mkdir(parents=True, exist_ok=True)
    img_height = resolution[1] // 2
    try:
        _png_with_texts(gun_png, GUN_HELP_PNG, data, img_height)
        shutil.copy2(GUN_HELP_PNG, _GUN_HELP_CACHE)
        _log.info("gun help: generated %s", GUN_HELP_PNG)
    except Exception as exc:
        _log.error("gun help: generation failed: %s", exc)


# ── QR code overlay ────────────────────────────────────────────────────────────

def add_qr_code(src: Path, dst: Path, ra_game_id: str, corner: str = 'NE') -> None:
    """Composite a RetroAchievements QR code onto the bezel."""
    try:
        import qrcode
    except ImportError:
        _log.warning("qr code: python3-qrcode not installed, skipping")
        shutil.copy2(src, dst)
        return

    from PIL import Image
    url = f'https://retroachievements.org/game/{ra_game_id}'

    bxsize, bdsize = 3, 2
    qr = qrcode.QRCode(version=1, box_size=bxsize, border=bdsize)
    qr.add_data(url)
    qr.make()
    qrimg = qr.make_image(back_color=(120, 120, 120)).convert('RGBA')

    x = 29 * bxsize + bdsize * bxsize * 2
    w, h = fast_image_size(src)
    bezel = Image.open(src).convert('RGBA')

    c = corner.upper()
    if c == 'NW':
        bezel.paste(qrimg, (0, 0, x, x))
    elif c == 'SE':
        bezel.paste(qrimg, (w - x, h - x, w, h))
    elif c == 'SW':
        bezel.paste(qrimg, (0, h - x, x, h))
    else:  # NE default
        bezel.paste(qrimg, (w - x, 0, w, x))

    bezel.save(dst, format='PNG')
    _log.info("qr code: composited RA game %s onto bezel (%s corner)", ra_game_id, corner)


# ── Main entry point ───────────────────────────────────────────────────────────

def prepare_bezel(
    rom: Path,
    system: str,
    emulator: str,
    bezel_name: str,
    resolution: tuple[int, int],
    stretch: bool = False,
    tattoo_type: str = 'none',
    tattoo_file: Optional[str] = None,
    tattoo_corner: str = 'NW',
    tattoo_resize: bool = True,
    gun_border: str = 'none',
    gun_aspect_ratio: Optional[str] = None,
    gun_border_col: str = '#ffffff',
    ra_game_id: Optional[str] = None,
    qr_corner: str = 'NE',
) -> Optional[Path]:
    """Find, resize, composite and stage bezel PNG. Returns path or None."""
    infos = get_bezel_infos(rom, bezel_name, system, emulator)
    if infos is None:
        _log.debug("bezel: no bezel found for %s/%s (set=%s)", system, rom.name, bezel_name)
        return None

    src = infos['png']
    w, h = resolution

    RUNTIME_BEZEL.parent.mkdir(parents=True, exist_ok=True)

    tmp = RUNTIME_BEZEL.with_suffix('.tmp.png')
    try:
        resize_image(src, tmp, w, h, stretch)
    except Exception as exc:
        _log.error("bezel: resize failed: %s", exc)
        return None

    if tattoo_type not in ('none', ''):
        try:
            tattoo_image(tmp, tmp, system, tattoo_type, tattoo_file,
                         tattoo_corner, tattoo_resize)
        except Exception as exc:
            _log.warning("bezel: tattoo failed (skipping): %s", exc)

    if gun_border not in ('none', ''):
        inner_pct, outer_pct = _BORDER_SIZES.get(gun_border, (0, 0))
        if inner_pct or outer_pct:
            try:
                gun_border_image(tmp, tmp, gun_aspect_ratio,
                                 inner_pct, outer_pct, gun_border_col)
            except Exception as exc:
                _log.warning("bezel: gun border failed (skipping): %s", exc)

    if ra_game_id:
        try:
            add_qr_code(tmp, tmp, ra_game_id, qr_corner)
        except Exception as exc:
            _log.warning("bezel: QR code failed (skipping): %s", exc)

    tmp.replace(RUNTIME_BEZEL)
    _log.info("bezel: staged %s → %s (%dx%d)", src, RUNTIME_BEZEL, w, h)

    # Symlink for shader-based bezel path
    SHADER_BEZEL_DIR.mkdir(parents=True, exist_ok=True)
    if SHADER_BEZEL.is_symlink() or SHADER_BEZEL.exists():
        SHADER_BEZEL.unlink()
    SHADER_BEZEL.symlink_to(RUNTIME_BEZEL)

    return RUNTIME_BEZEL
