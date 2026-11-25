#!/usr/bin/env python3
"""Render the es-theme-hippos system artwork: one generated planet per system.

Output is deterministic for a given system name, so re-running only changes
files whose palette or renderer changed. Requires numpy, Pillow and fontTools.

Usage: generate-theme-art.py <theme-dir> [chrome | system ...]
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

WIDTH, HEIGHT = 1600, 900
JPEG_QUALITY = 84
WORDMARK_LINE_CHARS = 14
PLANET_CENTER = (0.93, 1.12)
PLANET_RADIUS = 0.94
LIGHT = np.array([-0.60, -0.56, -0.40])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
INK = np.array([0.020, 0.016, 0.042])

@dataclass(frozen=True)
class World:
    deep: str
    mid: str
    bright: str
    glow: str
    surface: str
    ring: bool = False

WORLDS = {
    "nes": World("3a0c12", "c5283a", "e8dcd2", "ff4d5e", "continents"),
    "famicom": World("4a0d10", "b3262c", "e8cfa0", "ff5a48", "continents"),
    "fds": World("3f1f06", "c7741b", "f2d394", "ffa23a", "bands"),
    "snes": World("1c1140", "6a45b8", "cfc4ec", "8f6bff", "bands", True),
    "sfc": World("2a1248", "8a4fc0", "e6d3f2", "b07bff", "bands", True),
    "n64": World("0a2b1e", "1f9a5a", "e6cd4c", "2fe08a", "continents"),
    "gamecube": World("140f4a", "4e3fc4", "b9b4f2", "6f5fff", "bands", True),
    "wii": World("0e2f3d", "5fb9d6", "f4fbff", "8fe6ff", "ice"),
    "wiiu": World("06233f", "1a7fc4", "d5efff", "39b4ff", "ice"),
    "switch": World("3d0810", "e0263f", "ffe3e6", "ff4560", "continents"),
    "gb": World("1b2607", "6f8a1e", "cad97a", "a8d13a", "craters"),
    "gbc": World("2c0e4a", "9a3fc8", "f0c6ff", "c95cff", "bands"),
    "gba": World("14124e", "4b45c8", "c3c0ff", "6c66ff", "bands", True),
    "nds": World("151b2a", "68778f", "e3e8f0", "a7bcdc", "craters"),
    "3ds": World("2e0a18", "b52d5a", "f4cedb", "f0507e", "continents"),
    "mastersystem": World("0c1e4a", "c8283c", "e6e9f2", "ff4258", "bands"),
    "megadrive": World("061a42", "1e62c8", "d3e3ff", "2f88ff", "bands", True),
    "genesis": World("061a42", "1e62c8", "d3e3ff", "2f88ff", "bands", True),
    "sega32x": World("2b0a0a", "d0451e", "ffd9b8", "ff6a2a", "bands"),
    "segacd": World("07162f", "2d5fa8", "e3ecf8", "4f8fe8", "ice"),
    "saturn": World("10162e", "45588f", "ccd5ee", "6f8fe0", "bands", True),
    "dreamcast": World("3a1505", "e8681c", "fff0e0", "ff8a2e", "continents"),
    "gamegear": World("07142e", "2448a8", "cdd8ff", "3a6cff", "craters"),
    "psx": World("17181f", "6d7385", "e4e6ee", "a4b0d8", "craters"),
    "ps2": World("050d38", "1c3fbf", "b8c8ff", "2d5cff", "bands", True),
    "ps3": World("0c0c12", "4a4e60", "dfe2ec", "8d97bd", "ice"),
    "psp": World("0d1320", "3f5470", "d4dfef", "6f93c4", "ice"),
    "psvita": World("03183c", "0f64c8", "c2e0ff", "2a90ff", "ice"),
    "xbox": World("0a2408", "52a81e", "d8f2b4", "7ee02e", "continents"),
    "xbox360": World("10240a", "7cc41e", "ecf7d8", "a8ee2e", "ice"),
    "mame": World("2e0638", "c81e8f", "ffc6ee", "ff3dbd", "bands", True),
    "arcade": World("2e0638", "c81e8f", "ffc6ee", "ff3dbd", "bands", True),
    "fbneo": World("35063a", "a828d8", "f2c6ff", "cf4dff", "bands"),
    "neogeo": World("2e2004", "c79a1e", "fff2bf", "ffcc33", "bands", True),
    "pcengine": World("260a2e", "d6503c", "ffe0c8", "ff7a4d", "continents"),
    "atari2600": World("2b1606", "a8622a", "f2d8a8", "e89a3e", "bands"),
    "atarilynx": World("231304", "c78a2c", "f7e3ad", "f2b53e", "craters"),
    "jaguar": World("260505", "a81e1e", "e8b8b8", "e63030", "continents"),
    "amiga500": World("2e1404", "e87c1e", "dfe8f7", "ff9a33", "bands", True),
    "amiga1200": World("2e1404", "e87c1e", "dfe8f7", "ff9a33", "bands", True),
    "c64": World("0f1040", "5a4fc8", "c4bcff", "7d70ff", "craters"),
    "zxspectrum": World("120a2e", "d62878", "ffe066", "ff3d8a", "bands"),
    "msx": World("0a2a3a", "1e9ac8", "ccf0ff", "30c6ff", "continents"),
    "dos": World("03083c", "1a2fc8", "bcc5ff", "2f4dff", "craters"),
    "pc": World("03083c", "1a2fc8", "bcc5ff", "2f4dff", "craters"),
    "windows": World("04213c", "1a8ac8", "cdeeff", "33b4ff", "ice"),
    "steam": World("0a1626", "2f5f8a", "cfe3f2", "4f9fd8", "ice", True),
    "heroic": World("1c0f3a", "5f3fb8", "dcd0ff", "8560ff", "bands"),
    "androidapps": World("0a2a16", "2fb860", "d8f7d0", "4fe080", "continents"),
    "scummvm": World("062a22", "1ea888", "c8f7e8", "30e0b8", "continents"),
    "quiver": World("04192e", "1a8fd8", "c8eeff", "2fc0ff", "ice"),
    "xcloud": World("041c08", "1a8a24", "d2f2c8", "3fe04a", "ice", True),
    "luna": World("170834", "7a3fe0", "e4d6ff", "a46cff", "craters"),
    "linuxapps": World("0a1630", "3f5fd8", "d8e2ff", "6f8fff", "ice", True),
    "desktopshortcuts": World("0a1c2e", "3f7fb8", "d8e8f7", "5fa8f0", "continents", True),
    "linuxgames": World("261804", "d89a14", "fff0c0", "ffc21e", "bands"),
    "ports": World("2e1006", "c8501e", "ffd8c0", "ff7030", "craters"),
    "prboom": World("2a0505", "b8201e", "f2b8a0", "f03a28", "craters"),
    "auto-favorites": World("2e2004", "d8a81e", "fff6cc", "ffd23f", "ice", True),
    "auto-lastplayed": World("140a3a", "7b3fff", "dcd0ff", "9b6bff", "bands", True),
    "auto-allgames": World("06183f", "1a6fff", "cfe0ff", "4d8dff", "continents", True),
    "adrenaline": World("2e0505", "c82020", "ffd8d8", "ff4040", "craters"),
    "alls":       World("041830", "1050c8", "d0e0ff", "2878f0", "ice"),
    "apm3":       World("1a0530", "9820c0", "f0d0ff", "c040e8", "bands"),
    "arcadepc":   World("081028", "2050a0", "ccd8f0", "3870d0", "continents"),
    "europar":    World("0a1430", "1a4cc0", "d8e4ff", "2060e0", "continents"),
    "globalvr":   World("041a10", "189050", "c8f0d8", "30b870", "continents"),
    "konami":     World("1e0408", "900818", "ffd8dc", "b0101e", "craters"),
    "namcoes3":   World("1e1800", "c09000", "fff8cc", "f0c000", "bands"),
    "nesica":     World("2a1000", "c06010", "ffe8c0", "e08020", "bands"),
    "nesica2":    World("1e0c00", "a04808", "ffe0b0", "c86020", "bands"),
    "rawthrills": World("0a1a04", "3a9018", "d8f0c0", "60b830", "craters"),
    "ringedge":   World("041824", "0888b8", "c8eeff", "18b0e0", "ice"),
    "ringedge2":  World("041c28", "0898c8", "d0f4ff", "20c8f8", "ice"),
    "seganu":     World("040c20", "1038a0", "c8d4f0", "1850c8", "continents"),
    "segashell":  World("081828", "1860b0", "cce0f8", "2888d8", "ice"),
    "tsunami":    World("030f20", "0858a0", "c0e0f8", "1080d0", "continents"),
    "typex":      World("1a0430", "8018a8", "f0c8ff", "a030d0", "craters"),
    "unis":       World("101818", "206060", "c0e8e8", "30a0a0", "ice"),
    "wahlap":     World("251000", "b04808", "ffd8b0", "d86010", "bands"),
}

WORLD_VARIANTS = {
    "amiga3000": "amiga1200",
    "amiga4000": "amiga1200",
    "c64gs": "c64",
    "dendy": "famicom",
    "dreamcast-jp": "dreamcast",
    "gamecube-jp": "gamecube",
    "gamecubeh": "gamecube",
    "gbah": "gba",
    "gbch": "gbc",
    "gbh": "gb",
    "genh": "megadrive",
    "ggh": "gamegear",
    "mark3": "mastersystem",
    "megacd32x": "sega32x",
    "n64-jp": "n64",
    "n64h": "n64",
    "neogeo64": "neogeo",
    "neogeomvs": "neogeo",
    "nes-msu": "nes",
    "nes_hd": "nes",
    "nesaladdin": "nes",
    "nesh": "nes",
    "nomad": "megadrive",
    "pspminis": "psp",
    "saturn-jp": "saturn",
    "sega32xcd": "sega32x",
    "snesh": "snes",
    "supercharger": "atari2600",
    "tduo": "pcengine",
    "wiiu-sky": "wiiu",
    "wiiueshop": "wiiu",
    "wiiware": "wii",
    "win11": "windows",
    "win311": "windows",
    "win95": "windows",
    "win98": "windows",
    "xbla": "xbox360",
}

FALLBACK_WORLDS = [
    World("140a3a", "7b3fff", "dcd0ff", "9b6bff", "bands"),
    World("06183f", "1a6fff", "cfe0ff", "4d8dff", "ice"),
    World("1e0a38", "a03ff0", "ecd0ff", "c060ff", "continents"),
    World("0a1c3f", "2f8fe0", "d0eeff", "4fb8ff", "craters"),
    World("2a0a30", "d03fa8", "ffd0ee", "f060c8", "bands"),
    World("062a30", "1fa8b8", "ccf5f7", "33d8e8", "continents"),
    World("2e1006", "e0702a", "ffe0c8", "ff9040", "craters"),
    World("10241e", "3fb890", "d0f7e6", "50e0b0", "ice"),
]

def to_rgb(hex_color: str) -> np.ndarray:
    return np.array([int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)])

def fractal_noise(rng: np.random.Generator, shape: tuple[int, int], base: int, octaves: int) -> np.ndarray:
    total = np.zeros(shape)
    amplitude = 1.0
    aspect = shape[1] / shape[0]
    for octave in range(octaves):
        columns = base * 2**octave
        grid = rng.random((max(2, round(columns / aspect)), columns)).astype(np.float32)
        image = Image.fromarray(grid).resize((shape[1], shape[0]), Image.BICUBIC)
        total += np.asarray(image, dtype=np.float64) * amplitude
        amplitude *= 0.52
    total -= total.min()
    return total / total.max()

def warped_noise(rng: np.random.Generator, shape: tuple[int, int], base: int, octaves: int, strength: float) -> np.ndarray:
    field = fractal_noise(rng, shape, base, octaves)
    offset_y = (fractal_noise(rng, shape, base, 4) - 0.5) * strength * shape[0]
    offset_x = (fractal_noise(rng, shape, base, 4) - 0.5) * strength * shape[1]
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]]
    warped = sample_bilinear(field, np.clip(ys + offset_y, 0, shape[0] - 1), np.clip(xs + offset_x, 0, shape[1] - 1))
    warped -= warped.min()
    return warped / warped.max()

def gaussian_blur(values: np.ndarray, sigma: float) -> np.ndarray:
    radius = int(sigma * 3 + 0.5)
    kernel = np.exp(-(np.arange(-radius, radius + 1) ** 2) / (2 * sigma**2))
    kernel /= kernel.sum()
    for axis in (0, 1):
        values = np.apply_along_axis(np.convolve, axis, values, kernel, mode="same")
    return values

def sample_bilinear(texture: np.ndarray, v: np.ndarray, u: np.ndarray) -> np.ndarray:
    v0, u0 = np.floor(v).astype(int), np.floor(u).astype(int)
    v1, u1 = np.minimum(v0 + 1, texture.shape[0] - 1), np.minimum(u0 + 1, texture.shape[1] - 1)
    fv, fu = v - v0, u - u0
    if texture.ndim == 3:
        fv, fu = fv[..., None], fu[..., None]
    top = texture[v0, u0] * (1 - fu) + texture[v0, u1] * fu
    bottom = texture[v1, u0] * (1 - fu) + texture[v1, u1] * fu
    return top * (1 - fv) + bottom * fv

def lerp_palette(value: np.ndarray, stops: list[tuple[float, np.ndarray]]) -> np.ndarray:
    positions = [stop[0] for stop in stops]
    return np.stack([np.interp(value, positions, [stop[1][c] for stop in stops]) for c in range(3)], axis=-1)

def surface_maps(world: World, rng: np.random.Generator, size: int = 2048) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    deep, mid, bright = to_rgb(world.deep), to_rgb(world.mid), to_rgb(world.bright)
    shape = (size // 2, size)
    detail = warped_noise(rng, shape, 5, 8, 0.10)
    night = np.zeros(shape)

    if world.surface == "bands":
        latitude = np.linspace(0, 1, shape[0])[:, None]
        turbulence = warped_noise(rng, shape, 5, 7, 0.16) - 0.5
        frequency = rng.uniform(7, 12)
        phase = rng.uniform(0, 6.28)
        broad = 0.5 + 0.5 * np.sin((latitude + turbulence * 0.09) * frequency * 6.28 + phase)
        fine = 0.5 + 0.5 * np.sin((latitude + turbulence * 0.05) * frequency * 23 + phase * 2)
        value = np.clip(0.60 * broad + 0.18 * fine + 0.22 * detail, 0, 1)
        albedo = lerp_palette(value, [(0, deep), (0.45, mid), (0.80, (mid + bright) / 2), (1, bright)])
        return albedo, value * 0.35, night

    if world.surface == "continents":
        coast = np.clip((detail - 0.47) / 0.03, 0, 1)
        elevation = np.clip((detail - 0.47) / 0.30, 0, 1)
        land = lerp_palette(elevation, [(0, mid * 0.75), (0.6, mid), (1, (mid + bright) / 2)])
        sea = lerp_palette(np.clip(detail / 0.47, 0, 1), [(0, deep * 0.55), (1, (deep + mid) / 3)])
        albedo = sea * (1 - coast[..., None]) + land * coast[..., None]
        clouds = np.clip((warped_noise(rng, shape, 6, 8, 0.22) - 0.53) / 0.22, 0, 1) ** 1.3
        albedo = albedo * (1 - clouds[..., None] * 0.86) + bright * clouds[..., None] * 0.86
        populated = np.clip((fractal_noise(rng, shape, 18, 4) - 0.52) / 0.16, 0, 1)
        night = (rng.random(shape) > 0.986) * populated * coast * (1 - clouds)
        return albedo, elevation * coast + clouds * 0.3, night

    if world.surface == "ice":
        cracks = 1 - np.abs(warped_noise(rng, shape, 6, 7, 0.18) * 2 - 1)
        value = np.clip(0.75 * detail + 0.25 * cracks**6, 0, 1)
        albedo = lerp_palette(value, [(0, deep), (0.35, mid), (0.70, (mid + bright) / 2), (1, bright)])
        return albedo, value * 0.5, night

    ridges = 1 - np.abs(warped_noise(rng, shape, 7, 8, 0.08) * 2 - 1)
    height = 0.55 * detail + 0.45 * ridges**2
    longitude, latitude = np.meshgrid(np.arange(size), np.arange(size // 2))
    for _ in range(170):
        cx, cy = rng.integers(0, size), rng.integers(size // 8, 3 * size // 8)
        radius = 3 + 42 * rng.random() ** 3.2
        stretch = 1 / max(0.25, np.cos((cy / (size // 2) - 0.5) * np.pi))
        distance = np.hypot((longitude - cx) / stretch, latitude - cy) / radius
        height = height - 0.16 * np.clip(1 - distance, 0, 1) ** 0.6 + 0.09 * np.exp(-((distance - 1) ** 2) * 28)
    height -= height.min()
    height /= height.max()
    albedo = lerp_palette(height, [(0, deep), (0.50, mid), (1, (mid + bright) / 2)])
    return albedo, height * 1.5, night

def starfield(rng: np.random.Generator) -> np.ndarray:
    tints = np.array([[1.0, 0.86, 0.72], [0.82, 0.88, 1.0], [1.0, 1.0, 1.0], [0.92, 0.85, 1.0]])
    layers = np.zeros((HEIGHT, WIDTH, 3))
    for count, power, sigma, gain in ((2600, 9, 0, 0.75), (340, 4, 0.8, 3.4), (34, 1, 1.5, 17)):
        points = np.zeros((HEIGHT, WIDTH, 3))
        ys, xs = rng.integers(0, HEIGHT, count), rng.integers(0, WIDTH, count)
        points[ys, xs] = tints[rng.integers(0, 4, count)] * (rng.random((count, 1)) ** power)
        if sigma:
            for channel in range(3):
                points[..., channel] = gaussian_blur(points[..., channel], sigma)
        layers += points * gain
    return np.clip(layers, 0, 1)

def add_rings(canvas, world, dx, dy, inside, rng):
    squash, angle = 0.20, rng.uniform(-0.62, -0.46)
    along = dx * np.cos(angle) + dy * np.sin(angle)
    across = (-dx * np.sin(angle) + dy * np.cos(angle)) / squash
    distance = np.hypot(along, across)
    inner, outer = 1.22, 1.72
    profile = fractal_noise(rng, (1, 4096), 60, 6)[0]
    band = profile[np.clip(((distance - inner) / (outer - inner) * 4095).astype(int), 0, 4095)]
    edges = np.clip((distance - inner) / 0.03, 0, 1) * np.clip((outer - distance) / 0.10, 0, 1)
    alpha = edges * (0.05 + 0.40 * band**1.8)
    alpha = np.where(inside & (across < 0), 0, alpha)
    color = to_rgb(world.bright) * 0.7 + to_rgb(world.glow) * 0.3
    return canvas * (1 - alpha[..., None]) + color[None, None] * alpha[..., None]

def add_moon(canvas, world, rng):
    center_x, center_y = rng.uniform(0.60, 0.70) * WIDTH, rng.uniform(0.10, 0.20) * HEIGHT
    radius = rng.uniform(0.014, 0.026) * HEIGHT
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float64)
    dx, dy = (xs - center_x) / radius, (ys - center_y) / radius
    distance = np.hypot(dx, dy)
    nz = np.sqrt(np.clip(1 - dx**2 - dy**2, 0, 1))
    lit = np.clip(dx * LIGHT[0] + dy * LIGHT[1] + nz * LIGHT[2], 0, 1)
    surface = (to_rgb(world.bright) * 0.8 + 0.1)[None, None] * (0.004 + lit[..., None] ** 0.7 * 0.9)
    edge = np.clip((1 - distance) * radius / 1.2, 0, 1)[..., None]
    halo = (np.exp(-np.maximum(distance - 1, 0) * 3.2) * 0.10 * (distance >= 1))[..., None]
    return canvas * (1 - edge) + surface * edge + to_rgb(world.glow)[None, None] * halo

def render(world: World, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    glow, mid, bright = to_rgb(world.glow), to_rgb(world.mid), to_rgb(world.bright)
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float64)
    radius = PLANET_RADIUS * HEIGHT
    center_x, center_y = PLANET_CENTER[0] * WIDTH, PLANET_CENTER[1] * HEIGHT
    dx, dy = (xs - center_x) / radius, (ys - center_y) / radius
    distance = np.hypot(dx, dy)
    inside = distance < 1

    dust = warped_noise(rng, (HEIGHT, WIDTH), 3, 7, 0.22)
    wisps = warped_noise(rng, (HEIGHT, WIDTH), 4, 7, 0.28)
    falloff = np.exp(-np.maximum(distance - 1, 0) * 1.5)
    canvas = np.broadcast_to(INK, (HEIGHT, WIDTH, 3)).copy()
    canvas += glow[None, None] * (np.clip(dust - 0.40, 0, 1) ** 1.5 * 0.52 * falloff)[..., None]
    canvas += mid[None, None] * (np.clip(wisps - 0.46, 0, 1) ** 2 * 0.42 * falloff)[..., None]
    canvas += starfield(rng) * np.clip(1.15 - dust * 1.1, 0.12, 1)[..., None]

    outside = np.maximum(distance - 1, 0)
    facing = np.clip((dx * LIGHT[0] + dy * LIGHT[1]) / np.maximum(distance, 1e-6) / np.hypot(LIGHT[0], LIGHT[1]), 0, 1)
    scatter = np.exp(-outside * 90) * 1.0 + np.exp(-outside * 20) * 0.42 + np.exp(-outside * 5.5) * 0.15
    canvas += (glow * 0.82 + bright * 0.18)[None, None] * (scatter * facing**2.4)[..., None]

    if world.ring:
        canvas = add_rings(canvas, world, dx, dy, inside, rng)
    if rng.random() < 0.55:
        canvas = add_moon(canvas, world, rng)

    nz = np.sqrt(np.clip(1 - dx**2 - dy**2, 0, 1))
    tilt = rng.uniform(-0.45, 0.10)
    tilted_x = dx * np.cos(tilt) - dy * np.sin(tilt)
    tilted_y = dx * np.sin(tilt) + dy * np.cos(tilt)
    albedo_map, height_map, night_map = surface_maps(world, rng)
    map_h, map_w = height_map.shape
    u = (np.arcsin(np.clip(tilted_x, -1, 1)) / np.pi + 0.5) * (map_w - 1)
    v = (np.arcsin(np.clip(tilted_y, -1, 1)) / np.pi + 0.5) * (map_h - 1)
    albedo = sample_bilinear(albedo_map, v, u)
    height = sample_bilinear(height_map, v, u)
    night = sample_bilinear(night_map, v, u)

    slope_y, slope_x = np.gradient(gaussian_blur(height, 0.7))
    bump = 5.0
    nx, ny, nzb = dx - slope_x * bump, dy - slope_y * bump, nz + 0.02
    length = np.sqrt(nx**2 + ny**2 + nzb**2)
    lambert = np.clip((nx * LIGHT[0] + ny * LIGHT[1] + nzb * LIGHT[2]) / length, 0, 1)
    terminator = np.clip((dx * LIGHT[0] + dy * LIGHT[1] + nz * LIGHT[2] + 0.10) / 0.55, 0, 1)
    shaded = albedo * (0.004 + 0.92 * (terminator**1.5 * (0.45 + 0.55 * np.minimum(lambert * 3.2, 1)))[..., None])

    limb = (1 - nz) ** 2.6
    shaded += glow[None, None] * (limb * terminator**0.8 * 0.70)[..., None]
    shaded += (glow * 0.7 + bright * 0.3)[None, None] * (np.exp(-(1 - distance) * 130) * facing**3 * 0.75)[..., None]
    darkness = np.clip(1 - terminator * 3.4, 0, 1)
    shaded += np.array([1.0, 0.78, 0.48])[None, None] * (night * darkness * 0.42)[..., None]

    edge = np.clip((1 - distance) * radius / 1.5, 0, 1)[..., None]
    canvas = canvas * (1 - edge) + shaded * edge

    light_length = np.hypot(LIGHT[0], LIGHT[1])
    flare_x = center_x + LIGHT[0] / light_length * radius
    flare_y = center_y + LIGHT[1] / light_length * radius
    flare_dx, flare_dy = (xs - flare_x) / WIDTH, (ys - flare_y) / WIDTH
    flare_distance = np.hypot(flare_dx, flare_dy)
    flare = 0.85 * np.exp(-flare_distance * 120) + 0.16 * np.exp(-flare_distance * 24)
    flare += 0.20 * np.exp(-np.abs(flare_dy) * 620) * np.exp(-np.abs(flare_dx) * 6.5)
    canvas += (bright * 0.5 + glow * 0.2 + 0.3)[None, None] * flare[..., None]

    calm = np.clip((xs / WIDTH - 0.06) / 0.42, 0, 1) ** 1.2
    canvas = INK + (canvas - INK) * (0.20 + 0.80 * calm)[..., None]
    canvas += rng.normal(0, 1.2 / 255, canvas.shape)
    return Image.fromarray((np.clip(canvas, 0, 1) ** (1 / 1.08) * 255 + 0.5).astype(np.uint8))

def save_world(image: Image.Image, path: Path) -> None:
    image.save(path, quality=JPEG_QUALITY, subsampling=0, optimize=True, progressive=True)

def rounded_mask(size: int, radius: int, scale: int = 4) -> np.ndarray:
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius * scale, fill=255)
    return np.asarray(mask.resize((size, size), Image.LANCZOS), dtype=np.float64) / 255

def logo_with_alpha(source: Path, box: tuple[int, int, int, int] | None = None) -> Image.Image:
    pixels = np.asarray(Image.open(source).convert("RGB"), dtype=np.float64) / 255
    alpha = pixels.max(axis=-1)
    color = pixels / np.maximum(alpha[..., None], 1e-3)
    image = Image.fromarray((np.dstack([np.clip(color, 0, 1), alpha]) * 255 + 0.5).astype(np.uint8), "RGBA")
    return image.crop(box) if box else image

@dataclass(frozen=True)
class LogoLine:
    font: str
    text: str
    cap_height: float
    tracking: float = 0.0

@dataclass(frozen=True)
class Logo:
    icon: tuple[str, ...]
    lines: tuple[LogoLine, ...]
    line_gap: float

def rotated(points: list[tuple[float, float]], degrees: float, center: tuple[float, float]) -> list[tuple[float, float]]:
    a = np.radians(degrees)
    cx, cy = center
    return [(cx + (x - cx) * np.cos(a) - (y - cy) * np.sin(a), cy + (x - cx) * np.sin(a) + (y - cy) * np.cos(a))
            for x, y in points]

def polygon(points: list[tuple[float, float]]) -> str:
    return "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in points) + "Z"

ARROW = [(35, 0), (43, 14), (37.5, 19), (37.5, 52), (32.5, 52), (32.5, 19), (27, 14)]

LOGOS = {
    "quiver": Logo(
        icon=(
            *(polygon(rotated(ARROW, angle, (35, 60))) for angle in (-28, 0, 28)),
            "M12 44H58A5 5 0 0 1 63 49V49A5 5 0 0 1 58 54H12A5 5 0 0 1 7 49V49A5 5 0 0 1 12 44Z",
            "M10 57H60L55 84L35 100L15 84Z"
            "M24 67L35 75L46 67L46 73L35 81L24 73Z"
            "M24 78L35 86L46 78L46 84L35 92L24 84Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "QUIVER", 50, 0.08), LogoLine("Sora-SemiBold.ttf", "LAUNCHER", 20, 0.42)),
        line_gap=14,
    ),
    "linuxapps": Logo(
        icon=(
            "M50 2A48 48 0 1 1 50 98A48 48 0 1 1 50 2Z" "M50 9A41 41 0 1 0 50 91A41 41 0 1 0 50 9Z",
            "M50 2A23 48 0 1 1 50 98A23 48 0 1 1 50 2Z" "M50 9A16 41 0 1 0 50 91A16 41 0 1 0 50 9Z",
            "M6 46H94V54H6Z",
            "M46 4H54V96H46Z",
            "M14 26H86V32H14Z",
            "M14 68H86V74H14Z",
        ),
        lines=(LogoLine("Sora-SemiBold.ttf", "WEB", 20, 0.32), LogoLine("Sora-ExtraBold.ttf", "Apps", 50)),
        line_gap=13,
    ),
    "desktopshortcuts": Logo(
        icon=(
            "M10 6H90A8 8 0 0 1 98 14V64A8 8 0 0 1 90 72H10A8 8 0 0 1 2 64V14A8 8 0 0 1 10 6Z"
            "M12 13H88A3 3 0 0 1 91 16V62A3 3 0 0 1 88 65H12A3 3 0 0 1 9 62V16A3 3 0 0 1 12 13Z"
            "M21 19H53A5 5 0 0 1 58 24V54A5 5 0 0 1 53 59H21A5 5 0 0 1 16 54V24A5 5 0 0 1 21 19Z"
            "M23 53V42A13 13 0 0 1 36 29H41V23L51 32L41 41V35H36A7 7 0 0 0 29 42V53Z"
            "M66 21H82A2 2 0 0 1 84 23V35A2 2 0 0 1 82 37H66A2 2 0 0 1 64 35V23A2 2 0 0 1 66 21Z"
            "M66 43H82A2 2 0 0 1 84 45V57A2 2 0 0 1 82 59H66A2 2 0 0 1 64 57V45A2 2 0 0 1 66 43Z",
            "M42 71H58V85H42Z",
            "M30 84H70A4 4 0 0 1 74 88V88A4 4 0 0 1 70 92H30A4 4 0 0 1 26 88V88A4 4 0 0 1 30 84Z",
        ),
        lines=(LogoLine("Sora-SemiBold.ttf", "DESKTOP", 20, 0.32), LogoLine("Sora-ExtraBold.ttf", "Shortcuts", 50)),
        line_gap=13,
    ),
    "lutris": Logo(
        icon=(
            "M30 20H70C86 20 95 32 97 50L99 70C100 84 88 90 80 82L68 70H32L20 82C12 90 0 84 1 70L3 50C5 32 14 20 30 20Z"
            "M23 35H31V43H39V51H31V59H23V51H15V43H23Z"
            "M72 31A6 6 0 1 0 72 43A6 6 0 1 0 72 31Z"
            "M72 51A6 6 0 1 0 72 63A6 6 0 1 0 72 51Z"
            "M62 41A6 6 0 1 0 62 53A6 6 0 1 0 62 41Z"
            "M82 41A6 6 0 1 0 82 53A6 6 0 1 0 82 41Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "LUTRIS", 50, 0.06), LogoLine("Sora-SemiBold.ttf", "GAME LIBRARY", 20, 0.32)),
        line_gap=14,
    ),
    "flatpak": Logo(
        icon=(
            "M50 2L94 27L50 52L6 27Z",
            "M2 34L46 59V100L2 75Z",
            "M98 34V75L54 100V59Z",
        ),
        lines=(LogoLine("Sora-SemiBold.ttf", "APPS", 20, 0.32), LogoLine("Sora-ExtraBold.ttf", "Flatpak", 50)),
        line_gap=13,
    ),
    "linuxgames": Logo(
        icon=(
            "M50 2C31 2 24 19 24 37C24 50 13 62 13 77C13 92 30 98 50 98C70 98 87 92 87 77C87 62 76 50 76 37C76 19 69 2 50 2Z"
            "M50 44C37 44 31 58 31 73C31 86 40 92 50 92C60 92 69 86 69 73C69 58 63 44 50 44Z"
            "M40 17A6.5 7.5 0 1 0 40 32A6.5 7.5 0 1 0 40 17Z"
            "M60 17A6.5 7.5 0 1 0 60 32A6.5 7.5 0 1 0 60 17Z"
            "M40 35H60L50 42Z",
            "M41.5 21A3 3.5 0 1 0 41.5 28A3 3.5 0 1 0 41.5 21Z",
            "M58.5 21A3 3.5 0 1 0 58.5 28A3 3.5 0 1 0 58.5 21Z",
            "M6 93C6 85 30 84 38 92C40 99 6 100 6 93Z",
            "M94 93C94 85 70 84 62 92C60 99 94 100 94 93Z",
        ),
        lines=(LogoLine("Sora-SemiBold.ttf", "LINUX", 20, 0.32), LogoLine("Sora-ExtraBold.ttf", "Games", 50)),
        line_gap=13,
    ),
    **{system: Logo(
        icon=(
            "M38 12A12 12 0 1 0 62 12A12 12 0 1 0 38 12Z",  # ball
            "M44 24H56V58H44Z",                              # shaft
            "M8 58H92A6 6 0 0 1 98 64V94A6 6 0 0 1 92 100H8A6 6 0 0 1 2 94V64A6 6 0 0 1 8 58Z",  # base
            "M14 79A8 8 0 1 0 30 79A8 8 0 1 0 14 79Z",      # button 1
            "M42 73A8 8 0 1 0 58 73A8 8 0 1 0 42 73Z",      # button 2
            "M66 73A8 8 0 1 0 82 73A8 8 0 1 0 66 73Z",      # button 3
            "M78 83A7 7 0 1 0 92 83A7 7 0 1 0 78 83Z",      # button 4
        ),
        lines=lines,
        line_gap=12,
    ) for system, lines in {
        "adrenaline": (LogoLine("Sora-SemiBold.ttf", "ARCADE",    18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Adrenaline",  48)),
        "alls":       (LogoLine("Sora-SemiBold.ttf", "SEGA",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "P-ras MULTI", 48)),
        "apm3":       (LogoLine("Sora-SemiBold.ttf", "ANDAMIRO",  18, 0.08), LogoLine("Sora-ExtraBold.ttf", "PM3",         48)),
        "arcadepc":   (LogoLine("Sora-SemiBold.ttf", "WINDOWS",   18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Arcade PC",   48)),
        "europar":    (LogoLine("Sora-SemiBold.ttf", "ARCADE",    18, 0.08), LogoLine("Sora-ExtraBold.ttf", "EuroPAR",     48)),
        "globalvr":   (LogoLine("Sora-SemiBold.ttf", "GLOBAL",    18, 0.08), LogoLine("Sora-ExtraBold.ttf", "VR",          48)),
        "konami":     (LogoLine("Sora-SemiBold.ttf", "KONAMI",    18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Arcade PC",   48)),
        "namcoes3":   (LogoLine("Sora-SemiBold.ttf", "NAMCO",     18, 0.08), LogoLine("Sora-ExtraBold.ttf", "System ES3",  48)),
        "nesica":     (LogoLine("Sora-SemiBold.ttf", "TAITO",     18, 0.08), LogoLine("Sora-ExtraBold.ttf", "NESiCA",      48)),
        "nesica2":    (LogoLine("Sora-SemiBold.ttf", "TAITO",     18, 0.08), LogoLine("Sora-ExtraBold.ttf", "NESiCA 2",    48)),
        "rawthrills": (LogoLine("Sora-SemiBold.ttf", "RAW",       18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Thrills",     48)),
        "ringedge":   (LogoLine("Sora-SemiBold.ttf", "SEGA",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "RingEdge",    48)),
        "ringedge2":  (LogoLine("Sora-SemiBold.ttf", "SEGA",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "RingEdge 2",  48)),
        "seganu":     (LogoLine("Sora-SemiBold.ttf", "SEGA",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Nu",          48)),
        "segashell":  (LogoLine("Sora-SemiBold.ttf", "SEGA",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Shell",       48)),
        "tsunami":    (LogoLine("Sora-SemiBold.ttf", "TSUNAMI",   18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Visual Tech", 48)),
        "typex":      (LogoLine("Sora-SemiBold.ttf", "TAITO",     18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Type X",      48)),
        "unis":       (LogoLine("Sora-SemiBold.ttf", "UNIS",      18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Technology",  48)),
        "wahlap":     (LogoLine("Sora-SemiBold.ttf", "WAHLAP",    18, 0.08), LogoLine("Sora-ExtraBold.ttf", "Arcade",      48)),
    }.items()},
    "mrboom": Logo(
        icon=(
            "M42 30A35 35 0 1 1 42 100A35 35 0 1 1 42 30Z"
            "M24 52A14 14 0 0 1 38 40L38 47A8 8 0 0 0 31 55Z",
            polygon(rotated([(56, 18), (72, 18), (72, 34), (56, 34)], 40, (64, 26))),
            "M68 18C70 8 78 3 86 6L84 12C79 10 75 13 74 20Z",
            polygon([(92 + r * np.sin(np.radians(a)), 6 + r * -np.cos(np.radians(a)))
                     for a, r in zip(range(0, 360, 30), [9, 3.5] * 6)]),
        ),
        lines=(LogoLine("Sora-SemiBold.ttf", "MR.", 20, 0.32), LogoLine("Sora-ExtraBold.ttf", "BOOM", 50, 0.04)),
        line_gap=13,
    ),
    "rgs": Logo(
        icon=(
            "M50 2A18 18 0 1 1 50 38A18 18 0 1 1 50 2Z" "M43 9A6 6 0 1 0 43 21A6 6 0 1 0 43 9Z",
            "M45 36H55V68H45Z",
            "M26 62H74L90 94H10Z" "M66 72A5 5 0 1 0 66 82A5 5 0 1 0 66 72Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "RGS", 50, 0.08), LogoLine("Sora-SemiBold.ttf", "PIXEL NOSTALGIA", 20, 0.32)),
        line_gap=14,
    ),
    "auto-wheel": Logo(
        icon=(
            "M50 2A48 48 0 1 1 50 98A48 48 0 1 1 50 2Z" "M50 11A39 39 0 1 0 50 89A39 39 0 1 0 50 11Z",
            "M10 45H90V55H10Z",
            "M45 50H55V90H45Z",
            "M50 36A14 14 0 1 1 50 64A14 14 0 1 1 50 36Z" "M50 44A6 6 0 1 0 50 56A6 6 0 1 0 50 44Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "WHEEL", 50, 0.06), LogoLine("Sora-SemiBold.ttf", "GAMES", 20, 0.42)),
        line_gap=14,
    ),
    "auto-lightgun": Logo(
        icon=(
            "M10 22H92A6 6 0 0 1 98 28V40A6 6 0 0 1 92 46H10A6 6 0 0 1 4 40V28A6 6 0 0 1 10 22Z",
            "M8 14H16V22H8Z",
            "M66 46H96L100 90A4 4 0 0 1 96 94H76A4 4 0 0 1 72 90Z",
            "M42 46H64V58A11 11 0 0 1 53 69A11 11 0 0 1 42 58Z" "M48 46H58V57A5 5 0 0 1 48 57Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "LIGHT GUN", 50, 0.04), LogoLine("Sora-SemiBold.ttf", "GAMES", 20, 0.42)),
        line_gap=14,
    ),
    "auto-trackball": Logo(
        icon=(
            "M50 10A32 32 0 1 1 50 74A32 32 0 1 1 50 10Z" "M38 22A8 8 0 1 0 38 38A8 8 0 1 0 38 22Z",
            "M8 60H18.8A36 36 0 0 0 81.2 60H92A6 6 0 0 1 98 66V86A6 6 0 0 1 92 92H8A6 6 0 0 1 2 86V66A6 6 0 0 1 8 60Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "TRACKBALL", 50, 0.04), LogoLine("Sora-SemiBold.ttf", "GAMES", 20, 0.42)),
        line_gap=14,
    ),
    "auto-spinner": Logo(
        icon=(
            polygon([(50 + r * np.sin(np.radians(a)), 50 - r * np.cos(np.radians(a)))
                     for a, r in zip(np.arange(0, 360, 7.5), [48, 42] * 24)])
            + "M50 20A30 30 0 1 0 50 80A30 30 0 1 0 50 20Z",
            "M50 28A22 22 0 1 1 50 72A22 22 0 1 1 50 28Z" "M46 32H54V48H46Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "SPINNER", 50, 0.04), LogoLine("Sora-SemiBold.ttf", "GAMES", 20, 0.42)),
        line_gap=14,
    ),
    "auto-verticalarcade": Logo(
        icon=(
            "M28 2H72A6 6 0 0 1 78 8V92A6 6 0 0 1 72 98H28A6 6 0 0 1 22 92V8A6 6 0 0 1 28 2Z"
            "M31 10H69V80H31Z"
            "M44 86A4 4 0 1 0 44 94A4 4 0 1 0 44 86Z" "M56 86A4 4 0 1 0 56 94A4 4 0 1 0 56 86Z",
            "M50 52L60 72H40Z",
            "M48 32H52V44H48Z",
            "M48 16H52V26H48Z",
        ),
        lines=(LogoLine("Sora-ExtraBold.ttf", "VERTICAL", 50, 0.04), LogoLine("Sora-SemiBold.ttf", "ARCADE", 20, 0.42)),
        line_gap=14,
    ),
}

WORDMARKS = {
    "2048": ("2048", "GABRIELE CIRULLI"),
    "3dsen": ("3DSEN", "GEOD STUDIO"),
    "abc80": ("ABC 80", "LUXOR"),
    "actionmax": ("ACTION MAX", "WORLDS OF WONDER"),
    "advision": ("ADVENTURE VISION", "ENTEX"),
    "aleck64": ("ALECK 64", "SETA"),
    "alice32": ("ALICE 32", "MATRA & HACHETTE"),
    "amiga3000": ("AMIGA 3000", "COMMODORE"),
    "amiga4000": ("AMIGA 4000", "COMMODORE"),
    "anarch": ("ANARCH", "DRUMMYFISH"),
    "apfm1000": ("M-1000", "APF ELECTRONICS"),
    "apogee": ("APOGEE BK-01", "ZAVOD BRA"),
    "appleios": ("IOS", "APPLE"),
    "aquarius": ("AQUARIUS", "MATTEL"),
    "atom": ("ATOM", "ACORN COMPUTERS"),
    "avgn": ("ANGRY VIDEO GAME NERD", ""),
    "batoparrot": ("BATOPARROT", "SLEYK INDUSTRIES"),
    "bbk": ("ELECTRONIC DICTIONARY", "BBK"),
    "beena": ("ADVANCED PICO BEENA", "SEGA"),
    "bigfish": ("BIG FISH GAMES", ""),
    "bk": ("BK", "ELEKTRONIKA"),
    "bml3": ("BASIC MASTER LEVEL 3", "HITACHI"),
    "c16": ("C16", "COMMODORE"),
    "c20": ("VIC-20", "COMMODORE"),
    "c64gs": ("C64 GAME SYSTEM", "COMMODORE"),
    "c64scpu": ("SUPERCPU", "CREATIVE MICRO DESIGNS"),
    "camplynx": ("LYNX", "CAMPUTERS"),
    "cannonball": ("CANNONBALL", "CHRIS WHITE"),
    "captpower": ("CAPTAIN POWER", "MATTEL"),
    "cassettevision": ("CASSETTE VISION", "EPOCH"),
    "cave3rd": ("CV1000", "CAVE"),
    "cbm2": ("CBM-II", "COMMODORE"),
    "cbm5x0": ("CBM 500", "COMMODORE"),
    "cgenie": ("COLOUR GENIE", "EACA"),
    "chip8": ("CHIP-8", ""),
    "clonehero": ("CLONE HERO", ""),
    "commanderx16": ("COMMANDER X16", "THE 8-BIT GUY"),
    "coolbar": ("COOLBAR", "SHANGHAI COOLBAR"),
    "cpc464p": ("CPC 464 PLUS", "AMSTRAD"),
    "cplus4": ("PLUS4", "COMMODORE"),
    "craft": ("CRAFT", "MICHAEL FOGLEMAN"),
    "creativision": ("CREATIVISION", "VTECH"),
    "ctvboy": ("COMPACT VISION TV BOY", "GAKKEN"),
    "datach": ("DATACH", "BANDAI"),
    "dendy": ("DENDY", "STEEPLER"),
    "dice": ("DICE", ""),
    "digiblst": ("DIGIBLAST", "NIKKO"),
    "dingoo": ("DINGOO A320", "DINGOO DIGITAL"),
    "dinothawr": ("DINOTHAWR", "AGNES HEYER"),
    "dragon64": ("DRAGON 64", "DRAGON DATA"),
    "dreamcast-jp": ("DREAMCAST JAPAN", "SEGA"),
    "duke3d": ("DUKE NUKEM 3D", "3D REALMS"),
    "elektronika": ("ELEKTRONIKA IM", "ELEKTRONIKA"),
    "enterprise": ("ENTERPRISE", "ENTERPRISE COMPUTERS"),
    "exaarcadia": ("EXA-ARCADIA", ""),
    "exboard": ("EX-BOARD", "EXAMU"),
    "exl100": ("EXL 100", "EXELVISION"),
    "fallout1-ce": ("FALLOUT", "INTERPLAY"),
    "fallout2-ce": ("FALLOUT 2", "INTERPLAY"),
    "fightcade2": ("FIGHTCADE", ""),
    "gaelco": ("GAELCO", ""),
    "galaksija": ("GALAKSIJA", "VOJA ANTONIC"),
    "galaxy": ("GALAKSIJA", "VOJA ANTONIC"),
    "gam4980": ("LONGMAN 4980", "BBK ELECTRONICS"),
    "gamecube-jp": ("GAMECUBE JAPAN", "NINTENDO"),
    "gamecubeh": ("GAMECUBE HACKS", "NINTENDO"),
    "gamehouse": ("GAMEHOUSE", ""),
    "gamekin3": ("GAMEKING 3", "TIMETOP"),
    "gamepock": ("GAME POCKET COMPUTER", "EPOCH"),
    "gametank": ("GAMETANK", "CLYDEWARE"),
    "gamewave": ("GAME WAVE", "ZAPIT GAMES"),
    "gbah": ("GAME BOY ADVANCE HACKS", "NINTENDO"),
    "gbch": ("GAME BOY COLOR HACKS", "NINTENDO"),
    "gbh": ("GAME BOY HACKS", "NINTENDO"),
    "gemrb": ("GEMRB", "INFINITY ENGINE"),
    "genh": ("GENESIS HACKS", "SEGA"),
    "ggh": ("GAME GEAR HACKS", "SEGA"),
    "gog": ("GOG", "CD PROJEKT"),
    "gong": ("GONG", "DAN ZAIDAN"),
    "gp32": ("GP32", "GAMEPARK"),
    "hec2hr": ("HECTOR 2HR", "MICRONIQUE"),
    "hyperscan": ("HYPERSCAN", "MATTEL"),
    "ibmpcjr": ("PCJR", "IBM"),
    "igspgm": ("POLYGAME MASTER", "IGS"),
    "igtslots": ("IGT SLOTS", ""),
    "ikemen": ("IKEMEN", "ELECBYTE"),
    "iqueplayer": ("IQUE PLAYER", "IQUE"),
    "jazz2": ("JAZZ JACKRABBIT 2", "EPIC MEGAGAMES"),
    "jumpnbump": ("JUMP 'N BUMP", "BRAINCHILD DESIGN"),
    "jupace": ("JUPITER ACE", "JUPITER CANTAB"),
    "konamigx": ("SYSTEM GX", "KONAMI"),
    "konamilcd": ("LCD GAMES", "KONAMI"),
    "konamipc": ("PC BASED", "KONAMI"),
    "laser310": ("LASER 310", "VTECH"),
    "laseractive": ("LASERACTIVE", "PIONEER"),
    "locomalito": ("LOCOMALITO", ""),
    "m24": ("M21", "OLIVETTI"),
    "m5": ("M5", "SORD"),
    "makecode": ("MAKECODE ARCADE", "MICROSOFT"),
    "mark3": ("MARK III", "SEGA"),
    "mbee": ("MICROBEE", "APPLIED TECHNOLOGY"),
    "mc10": ("MC-10", "TANDY RADIO SHACK"),
    "megacd32x": ("MEGA-CD 32X", "SEGA"),
    "microvsn": ("MICROVISION", "MILTON BRADLEY"),
    "microw8": ("MICROW8", "FANTASY"),
    "model1": ("MODEL 1", "SEGA"),
    "mononcol": ("MONON COLOR", "M&D"),
    "mpu1000": ("MPU-1000", "ACETRONIC"),
    "msxlaserdisk": ("PALCOM LASERDISC", "PIONEER"),
    "mtx512": ("MTX 512", "MEMOTECH"),
    "myvision": ("MY VISION", "NICHIBUTSU"),
    "mz2000": ("MZ-2000", "SHARP"),
    "mz2200": ("MZ-2200", "SHARP"),
    "mz2500": ("MZ-2500", "SHARP"),
    "mz700": ("MZ-700", "SHARP"),
    "mz800": ("MZ-800", "SHARP"),
    "mz80k": ("MZ-80K", "SHARP"),
    "n501": ("NUON", "SAMSUNG"),
    "n64-jp": ("NINTENDO 64 JAPAN", "NINTENDO"),
    "n64h": ("NINTENDO 64 HACKS", "NINTENDO"),
    "namco10": ("SYSTEM 10", "NAMCO"),
    "namco11": ("SYSTEM 11", "NAMCO"),
    "namco12": ("SYSTEM 12", "NAMCO"),
    "namco22": ("SYSTEM 22", "NAMCO"),
    "namco23": ("SYSTEM 23", "NAMCO"),
    "namco2x6": ("SYSTEM 246/256", "NAMCO"),
    "native32": ("NATIVE32", "SUNPLUS"),
    "neogeo64": ("HYPER NEO-GEO 64", "SNK"),
    "neogeomvs": ("NEO-GEO MVS", "SNK"),
    "nes-msu": ("NES MSU1", "NINTENDO"),
    "nes_hd": ("NES HD", "NINTENDO"),
    "nesaladdin": ("ALADDIN DECK ENHANCER", "CAMERICA"),
    "nesh": ("NES HACKS", "NINTENDO"),
    "nesicax": ("NESICAXLIVE", "TAITO"),
    "nesicax2": ("NESICAXLIVE 2", "TAITO"),
    "nomad": ("NOMAD", "SEGA"),
    "nuon": ("NUON", "VM LABS"),
    "omicron": ("OMICRON", "FANTASY"),
    "ondrat": ("ONDRA", "TESLA"),
    "openjazz": ("JAZZ JACKRABBIT", "EPIC MEGAGAMES"),
    "openlara": ("OPENLARA", "CORE DESIGN"),
    "orao103": ("ORAO", "PEL VARAZDIN"),
    "p2000t": ("P2000T", "PHILIPS"),
    "pc60": ("PC-6000", "NEC"),
    "pc80": ("PC-8001", "NEC"),
    "pcvr": ("PC VR", ""),
    "pcw": ("PCW", "AMSTRAD"),
    "pcxt": ("PC/XT", "IBM"),
    "pdp1": ("PDP-1", "DEC"),
    "pecom64": ("PECOM 64", "EI NIS"),
    "pegasus": ("PEGASUS", "AAMBER"),
    "pet": ("PET", "COMMODORE"),
    "pico": ("PICO", "SEGA"),
    "piece": ("P/ECE", "AQUAPLUS"),
    "pinballfx": ("PINBALL FX", "ZEN STUDIOS"),
    "pinballfx2": ("PINBALL FX2", "ZEN STUDIOS"),
    "pinballfx3": ("PINBALL FX3", "ZEN STUDIOS"),
    "pinballm": ("PINBALL M", "ZEN STUDIOS"),
    "pippin": ("PIPPIN", "APPLE"),
    "playdia": ("PLAYDIA", "BANDAI"),
    "pocketchallengev2": ("POCKET CHALLENGE V2", "BENESSE"),
    "pocketstation": ("POCKETSTATION", "SONY"),
    "popcap": ("POPCAP GAMES", ""),
    "pspminis": ("PSP MINIS", "SONY"),
    "pv2000": ("PV-2000", "CASIO"),
    "pyxel": ("PYXEL", "FANTASY"),
    "reminiscence": ("REMINISCENCE", "GREGORY MONTOIR"),
    "rx78": ("RX-78", "BANDAI"),
    "saturn-jp": ("SATURN JAPAN", "SEGA"),
    "sc-3000": ("SC-3000", "SEGA"),
    "sega32xcd": ("32X CD", "SEGA"),
    "segaai": ("AI COMPUTER", "SEGA"),
    "segaalls": ("ALLS", "SEGA"),
    "segaer": ("EUROPA-R", "SEGA"),
    "segare": ("RINGEDGE", "SEGA"),
    "segarw": ("RINGWIDE", "SEGA"),
    "segastv": ("ST-V", "SEGA"),
    "segasystem32": ("SYSTEM 32", "SEGA"),
    "singe": ("SINGE", ""),
    "smc777": ("SMC-777", "SONY"),
    "snesh": ("SNES HACKS", "NINTENDO"),
    "snotec": ("SUPER NOTE CLUB", "BANDAI"),
    "socrates": ("SOCRATES", "VTECH"),
    "sorcerer": ("SORCERER", "EXIDY"),
    "spmp8000": ("SPMP8000", "SUNPLUS"),
    "studio2": ("STUDIO II", "RCA"),
    "superbroswar": ("SUPER MARIO WAR", ""),
    "supercharger": ("SUPERCHARGER", "STARPATH"),
    "sv8000": ("SUPER VISION 8000", "BANDAI"),
    "svmu": ("VISUAL MEMORY UNIT", "SEGA"),
    "sys80": ("SYSTEM-80", "EACA"),
    "systemsp": ("SYSTEM SP", "SEGA"),
    "tamagotchi": ("TAMAGOTCHI", "BANDAI"),
    "tduo": ("TURBODUO", "NEC"),
    "thepowdertoy": ("THE POWDER TOY", "THE POWDER TOY TEAM"),
    "thextech": ("THEXTECH", "WOHLSTAND"),
    "ti83": ("TI-83", "TEXAS INSTRUMENTS"),
    "tiger": ("TIGER", "TIGER ELECTRONICS"),
    "tutor": ("TUTOR", "TOMY"),
    "tvc": ("TVC", "VIDEOTON"),
    "typex2": ("TYPE X2", "TAITO"),
    "vaporspec": ("VAPORSPEC", "FANTASY"),
    "vc4000": ("VC 4000", "INTERTON"),
    "vg5000": ("VG 5000", "PHILIPS"),
    "vg5k": ("VG 5000", "PHILIPS"),
    "vgm": ("VIDEO GAME MOVIES", ""),
    "vgmplay": ("VIDEO GAME MUSIC PLAYER", ""),
    "vic10": ("MAX MACHINE", "COMMODORE"),
    "vidbrain": ("VIDEOBRAIN", "UMTECH"),
    "videodriver": ("VIDEO DRIVER", "SEGA"),
    "videopacplus": ("VIDEOPAC+", "PHILIPS"),
    "vii": ("VII", "JUNGLE SOFT"),
    "vircon32": ("VIRCON32", "CARRA"),
    "vis": ("VIDEO INFORMATION SYSTEM", "TANDY"),
    "vmu": ("VISUAL MEMORY UNIT", "SEGA"),
    "voxatron": ("VOXATRON", "LEXALOFFLE"),
    "wenquxing": ("WENQUXING", "GOLDEN GLOBAL VIEW"),
    "wiiu-sky": ("SKYLANDERS", "WII U"),
    "wiiueshop": ("WII U ESHOP", "NINTENDO"),
    "wiiware": ("WIIWARE", "NINTENDO"),
    "win11": ("WINDOWS 11", "MICROSOFT"),
    "win311": ("WINDOWS 3.11", "MICROSOFT"),
    "win95": ("WINDOWS 95", "MICROSOFT"),
    "win98": ("WINDOWS 98", "MICROSOFT"),
    "windows_installers": ("WINDOWS INSTALLERS", "MICROSOFT"),
    "xbla": ("XBOX LIVE ARCADE", "MICROSOFT"),
    "xegs": ("XE GAME SYSTEM", "ATARI"),
    "xrick": ("XRICK", "BIGORNO"),
    "zaccariapinball": ("ZACCARIA PINBALL", "MAGIC PIXEL"),
    "zinc": ("ZINC", ""),
}

def wordmark(name: str, maker: str) -> Logo:
    words, lines = name.split(), [""]
    for word in words:
        if lines[-1] and len(lines[-1]) + 1 + len(word) > WORDMARK_LINE_CHARS:
            lines.append(word)
        else:
            lines[-1] = f"{lines[-1]} {word}".strip()
    big = tuple(LogoLine("Sora-ExtraBold.ttf", line, 50, 0.04) for line in lines)
    small = (LogoLine("Sora-SemiBold.ttf", maker, 20, 0.32),) if maker else ()
    return Logo(icon=(), lines=big + small, line_gap=14)

def path_bounds(paths: list[str]) -> tuple[float, float, float, float]:
    pen = BoundsPen(None)
    for d in paths:
        parse_path(d, pen)
    return pen.bounds

def transformed_path(d: str, transform: tuple[float, ...]) -> str:
    pen = SVGPathPen(None)
    parse_path(d, TransformPen(pen, transform))
    return pen.getCommands()

def text_path(fonts: Path, line: LogoLine, x: float, baseline: float) -> str:
    font = TTFont(fonts / line.font)
    glyphs, cmap, metrics = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = line.cap_height / font["OS/2"].sCapHeight
    pen = SVGPathPen(glyphs)
    for character in line.text:
        glyph = cmap[ord(character)]
        glyphs[glyph].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += metrics[glyph][0] * scale + line.tracking * line.cap_height
    return pen.getCommands()

def logo_paths(fonts: Path, logo: Logo, top: float) -> tuple[list[str], list[str]]:
    text_height = sum(line.cap_height for line in logo.lines) + logo.line_gap * (len(logo.lines) - 1)
    icon, text_left = [], 0.0
    if logo.icon:
        left, icon_top, right, bottom = path_bounds(list(logo.icon))
        scale = text_height / (bottom - icon_top)
        icon = [transformed_path(d, (scale, 0, 0, scale, -left * scale, -icon_top * scale - top)) for d in logo.icon]
        text_left = (right - left) * scale + text_height * 0.22
    text, baseline = [], -top
    for line in logo.lines:
        baseline += line.cap_height
        text.append(text_path(fonts, line, text_left, baseline))
        baseline += logo.line_gap
    return icon, text

def logo_svg(fonts: Path, logo: Logo) -> str:
    _, top, _, _ = path_bounds([d for paths in logo_paths(fonts, logo, 0) for d in paths])
    icon, text = logo_paths(fonts, logo, min(top, 0))
    _, _, width, height = path_bounds(icon + text)
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg version="1.1" viewBox="0 0 {width:.2f} {height:.2f}" xmlns="http://www.w3.org/2000/svg">\n'
        + "".join(f'  <path fill="#ffffff" fill-rule="evenodd" d="{d}"/>\n' for d in icon)
        + "".join(f'  <path fill="#ffffff" d="{d}"/>\n' for d in text)
        + "</svg>\n"
    )

def render_chrome(theme_dir: Path) -> None:
    assets = theme_dir / "assets"
    fonts = assets / "fonts" if (assets / "fonts").is_dir() else assets
    logos = {**{system: wordmark(*text) for system, text in WORDMARKS.items()}, **LOGOS}
    for system, logo in logos.items():
        (theme_dir / "art" / f"{system}.svg").write_text(logo_svg(fonts, logo))
    Image.new("RGBA", (4, 4), (255, 255, 255, 255)).save(assets / "white.png")

    size, radius = 96, 26
    outer = rounded_mask(size, radius)
    inner = np.zeros_like(outer)
    inner[2:-2, 2:-2] = rounded_mask(size - 4, radius - 2)
    border = np.clip(outer - inner, 0, 1)
    frame = np.zeros((size, size, 4))
    frame[..., :3] = 1
    frame[..., 3] = inner + border * 0.34
    Image.fromarray((frame * 255 + 0.5).astype(np.uint8), "RGBA").save(assets / "menu-frame.png")

    size = 512
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    dx, dy = (xs - size / 2) / size, (ys - size / 2) / size
    distance = np.hypot(dx, dy)
    flare = 0.95 * np.exp(-distance * 34) + 0.34 * np.exp(-distance * 10)
    flare += 0.55 * np.exp(-np.abs(dy) * 170) * np.exp(-np.abs(dx) * 9)
    flare *= np.clip((0.5 - distance) / 0.2, 0, 1)
    sprite = np.dstack([np.ones((size, size, 3)), np.clip(flare, 0, 1)])
    Image.fromarray((sprite * 255 + 0.5).astype(np.uint8), "RGBA").save(assets / "flare.png")

    source = Path(__file__).parent / "theme-art" / "hippos-logo.png"
    logo_with_alpha(source, (90, 855, 1165, 1035)).resize((538, 90), Image.LANCZOS).save(assets / "wordmark.png", optimize=True)

    size = (640, 400)
    placeholder = Image.new("RGBA", size, (16, 12, 34, 255))
    mark = logo_with_alpha(source, (110, 140, 1140, 830)).resize((387, 259), Image.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda value: value * 0.28))
    placeholder.alpha_composite(mark, ((size[0] - 387) // 2, (size[1] - 259) // 2))
    placeholder.convert("RGB").save(assets / "no-art.jpg", quality=88)

    seed = int.from_bytes(hashlib.sha256(b"default").digest()[:8], "big")
    splash = render(WORLDS["auto-lastplayed"], seed).convert("RGBA")
    logo = logo_with_alpha(source).resize((600, 600), Image.LANCZOS)
    splash.alpha_composite(logo, (150, 150))
    save_world(splash.convert("RGB"), assets / "splash.jpg")

def world_for(system: str, seed: int) -> World:
    return WORLDS.get(system) or WORLDS.get(WORLD_VARIANTS.get(system, "")) or FALLBACK_WORLDS[seed % len(FALLBACK_WORLDS)]

def main() -> None:
    theme_dir = Path(sys.argv[1])
    if sys.argv[2:] == ["chrome"]:
        render_chrome(theme_dir)
        return
    systems = sys.argv[2:] or sorted(path.stem for path in (theme_dir / "art").glob("*.svg"))
    output = theme_dir / "worlds"
    output.mkdir(exist_ok=True)
    for system in [*systems, *([] if sys.argv[2:] else ["default"])]:
        seed = int.from_bytes(hashlib.sha256(system.encode()).digest()[:8], "big")
        save_world(render(world_for(system, seed), seed), output / f"{system}.jpg")
        print(system, flush=True)

if __name__ == "__main__":
    main()
