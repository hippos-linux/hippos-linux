import logging
import os
import xml.etree.ElementTree as ET
from typing import Dict

import pygame

DEFAULT_THEME_DIR = '/usr/share/emulationstation/themes/es-theme-hippos'

def _variables(theme_dir: str) -> Dict[str, str]:
    if not theme_dir:
        return {}
    try:
        variables = ET.parse(os.path.join(theme_dir, 'theme.xml')).getroot().find('variables')
    except (OSError, ET.ParseError) as e:
        logging.warning('theme %s unreadable, using defaults: %s', theme_dir, e)
        return {}
    return {v.tag: (v.text or '').strip() for v in variables} if variables is not None else {}

class Theme:
    def __init__(self, theme_dir: str):
        self.dir = theme_dir
        self._variables = _variables(theme_dir)

    def color(self, name: str, default: tuple) -> tuple:
        value = self._variables.get(name, '')
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) if len(value) >= 6 else default

    def font(self, name: str) -> str:
        value = self._variables.get(name)
        return os.path.normpath(os.path.join(self.dir, value)) if value else pygame.font.get_default_font()

    def art(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts) if self.dir else ''

def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
