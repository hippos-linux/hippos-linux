"""
hippos_switchres — thin ctypes wrapper around libswitchres.so.

Only used when /etc/switchres.ini is present (CRT mode active).
Falls back gracefully if the library is absent.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re

_log = logging.getLogger(__name__)

_LIBPATH  = "/usr/lib/libswitchres.so"
_INI_PATH = "/etc/switchres.ini"

SR_MODE_INTERLACED = 1 << 0


class _SrMode(ctypes.Structure):
    _fields_ = [
        ("width",          ctypes.c_int),
        ("height",         ctypes.c_int),
        ("refresh",        ctypes.c_int),
        ("vfreq",          ctypes.c_double),
        ("hfreq",          ctypes.c_double),
        ("pclock",         ctypes.c_uint64),
        ("hbegin",         ctypes.c_int),
        ("hend",           ctypes.c_int),
        ("htotal",         ctypes.c_int),
        ("vbegin",         ctypes.c_int),
        ("vend",           ctypes.c_int),
        ("vtotal",         ctypes.c_int),
        ("interlace",      ctypes.c_int),
        ("doublescan",     ctypes.c_int),
        ("hsync",          ctypes.c_int),
        ("vsync",          ctypes.c_int),
        ("is_refresh_off", ctypes.c_int),
        ("is_stretched",   ctypes.c_int),
        ("x_scale",        ctypes.c_double),
        ("y_scale",        ctypes.c_double),
        ("v_scale",        ctypes.c_double),
        ("id",             ctypes.c_int),
    ]


def _load() -> ctypes.CDLL | None:
    try:
        lib = ctypes.CDLL(_LIBPATH)
    except OSError:
        return None
    lib.sr_init.restype            = None
    lib.sr_init.argtypes           = []
    lib.sr_load_ini.restype        = None
    lib.sr_load_ini.argtypes       = [ctypes.c_char_p]
    lib.sr_init_disp.restype       = ctypes.c_int
    lib.sr_init_disp.argtypes      = [ctypes.c_char_p, ctypes.c_void_p]
    lib.sr_switch_to_mode.restype  = ctypes.c_int
    lib.sr_switch_to_mode.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_double,
        ctypes.c_int, ctypes.POINTER(_SrMode),
    ]
    lib.sr_set_log_level.restype   = None
    lib.sr_set_log_level.argtypes  = [ctypes.c_int]
    lib.sr_deinit.restype          = None
    lib.sr_deinit.argtypes         = []
    return lib


def is_available() -> bool:
    """True when libswitchres.so and /etc/switchres.ini are both present."""
    return os.path.isfile(_LIBPATH) and os.path.isfile(_INI_PATH)


_VIDEOMODE_RE = re.compile(r'^(\d+)[xX](\d+)(i)?(?:@([\d.]+))?$')


def parse_videomode(s: str) -> tuple[int, int, float, bool] | None:
    """Parse a videomode string into (w, h, hz, interlaced).

    Accepts: '256x240@60', '640x480i', '320x240', '640x480i@50'
    Returns None if unparseable.
    """
    m = _VIDEOMODE_RE.match(s.strip())
    if not m:
        return None
    w, h       = int(m.group(1)), int(m.group(2))
    interlaced = m.group(3) == 'i'
    hz         = float(m.group(4)) if m.group(4) else 60.0
    return w, h, hz, interlaced


def switch_to_mode(w: int, h: int, hz: float, interlaced: bool = False) -> bool:
    """Apply a CRT modeline via libswitchres.so.

    Reads display and monitor profile from /etc/switchres.ini (written by
    hippos-crt-setup). Returns True if the mode was applied successfully.
    """
    lib = _load()
    if lib is None:
        _log.warning("switchres: libswitchres.so not found at %s", _LIBPATH)
        return False
    if not os.path.isfile(_INI_PATH):
        _log.warning("switchres: ini not found at %s", _INI_PATH)
        return False

    flags = SR_MODE_INTERLACED if interlaced else 0
    mode  = _SrMode()

    lib.sr_init()
    lib.sr_set_log_level(0)
    lib.sr_load_ini(_INI_PATH.encode())
    if not lib.sr_init_disp(None, None):
        _log.warning("switchres: sr_init_disp failed")
        lib.sr_deinit()
        return False

    ok = lib.sr_switch_to_mode(w, h, ctypes.c_double(hz), flags, ctypes.byref(mode))
    lib.sr_deinit()

    if not ok:
        _log.warning("switchres: sr_switch_to_mode failed for %dx%d@%.2f", w, h, hz)
        return False

    _log.info("switchres: %dx%d@%.2f → %dx%d vfreq=%.4f hfreq=%.4f",
              w, h, hz, mode.width, mode.height, mode.vfreq, mode.hfreq)
    return True
