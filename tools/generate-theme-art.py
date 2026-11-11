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
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

WIDTH, HEIGHT = 1600, 900
JPEG_QUALITY = 84
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
    "desktopapps": World("0a1c2e", "3f7fb8", "d8e8f7", "5fa8f0", "continents", True),
    "ports": World("2e1006", "c8501e", "ffd8c0", "ff7030", "craters"),
    "prboom": World("2a0505", "b8201e", "f2b8a0", "f03a28", "craters"),
    "auto-favorites": World("2e2004", "d8a81e", "fff6cc", "ffd23f", "ice", True),
    "auto-lastplayed": World("140a3a", "7b3fff", "dcd0ff", "9b6bff", "bands", True),
    "auto-allgames": World("06183f", "1a6fff", "cfe0ff", "4d8dff", "continents", True),
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

def wordmark_svg(font_path: Path, text: str) -> str:
    font = TTFont(font_path)
    glyphs, cmap, metrics = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    ascent, descent = font["hhea"].ascent, font["hhea"].descent
    pen = SVGPathPen(glyphs)
    x = 0
    for character in text:
        glyph = cmap[ord(character)]
        glyphs[glyph].draw(TransformPen(pen, (1, 0, 0, -1, x, ascent)))
        x += metrics[glyph][0]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x} {ascent - descent}">'
        f'<path fill="#fff" d="{pen.getCommands()}"/></svg>\n'
    )

def render_chrome(theme_dir: Path) -> None:
    assets = theme_dir / "assets"
    (theme_dir / "art" / "quiver.svg").write_text(wordmark_svg(assets / "fonts" / "Sora-ExtraBold.ttf", "Quiver"))
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
    return WORLDS.get(system) or FALLBACK_WORLDS[seed % len(FALLBACK_WORLDS)]

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
