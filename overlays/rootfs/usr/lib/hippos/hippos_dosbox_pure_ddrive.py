from __future__ import annotations

import glob
import itertools
import re
import zipfile
import zlib
from collections import Counter
from pathlib import Path

FREE_SPACE_CHOICES = ('1024', '2048', '4096', '8192')
DEFAULT_FREE_SPACE = '1024'
MAX_ORDERED_FILES = 7
EVIDENCE_GAMES = 5

_HASH_BASE = 0x11111111
_IMAGE_EXTENSIONS = {'ISO', 'CHD', 'CUE', 'INS', 'IMG', 'IMA', 'VHD', 'JRC'}
_CUE_TRACK_EXTENSIONS = {'ISO', 'IMG', 'IMA', 'BIN'}
_UNHASHED_SAVE_FILES = {'AUTOBOOT.DBP', 'PADMAP.DBP', 'FRONTEND.DBP', 'DOSBOX~1.CON', 'DOSBOX.CON'}
_VALID_CHAR_BITS = (0, 0, 0, 0, 250, 43, 255, 3, 255, 255, 255, 199, 1, 0, 0, 232,
                    1, 192, 5, 254, 224, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255)
_CUE_FILE = re.compile(r'^\s*FILE\s+"?([^"]+?)"?\s+\S+\s*$', re.IGNORECASE | re.MULTILINE)
_ARCHIVE_ATTR = 0x20


def _valid_char(byte: int) -> bool:
    return bool(_VALID_CHAR_BITS[byte // 8] & (1 << (byte % 8)))


def _filtered(byte: int) -> int:
    if _valid_char(byte):
        return byte
    if ord('a') <= byte <= ord('z'):
        return byte & 0x5F
    return ord('-') if byte < 0x80 else byte


def dos_name(name: str) -> bytes:
    raw = name.encode('latin-1', 'replace')
    dot = raw.rfind(b'.')
    base, ext = (raw[:dot], raw[dot + 1:]) if dot > 0 else (raw, b'')
    if len(base) <= 8 and len(ext) <= 3 and all(_valid_char(c) or i == dot for i, c in enumerate(raw)):
        return raw
    kept = base[:4] + base[-4:] if len(base) > 8 else base
    short = bytes(_filtered(c) for c in kept) or b'-'
    return short + b'.' + bytes(_filtered(c) for c in ext[:3]) if ext else short


def _next_free_name(name: bytes, taken: set[bytes]) -> bytes:
    candidate = bytearray(name)
    base_len = candidate.find(b'.') if b'.' in candidate else len(candidate)
    start = 4 if base_len > 8 else base_len // 2
    while bytes(candidate) in taken:
        for index in (start, start + 1, start + 2):
            if index < base_len and candidate[index] < ord('~'):
                candidate[index] += 1
                break
        else:
            break
    return bytes(candidate)


def _dos_datetime(date_time: tuple[int, ...]) -> tuple[int, int]:
    year, month, day, hour, minute, second = date_time
    return ((year - 1980) << 9) | (month << 5) | day, (hour << 11) | (minute << 5) | (second // 2)


def _entry(path: bytes, size: int, date_time: tuple[int, ...]) -> tuple[bytes, bytes]:
    date, time = _dos_datetime(date_time)
    return path, size.to_bytes(4, 'big') + date.to_bytes(2, 'big') + time.to_bytes(2, 'big') + bytes([_ARCHIVE_ATTR])


def _cue_tracks(archive: zipfile.ZipFile, cue: zipfile.ZipInfo) -> set[str]:
    text = archive.read(cue).decode('latin-1', 'replace')
    return {track.strip().lower() for track in _CUE_FILE.findall(text)}


def hashed_entries(rom: Path, save_zip: Path) -> list[tuple[bytes, bytes]] | None:
    with zipfile.ZipFile(rom) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if any('/' in info.filename for info in infos):
            return None
        tracks = set().union(*(_cue_tracks(archive, info) for info in infos
                               if info.filename.upper().endswith('.CUE')))
        entries, taken = {}, set()
        for info in infos:
            name = _next_free_name(dos_name(info.filename), taken)
            taken.add(name)
            extension = info.filename.rsplit('.', 1)[-1].upper()
            is_cue_track = extension in _CUE_TRACK_EXTENSIONS and info.filename.lower() in tracks
            if extension in _IMAGE_EXTENSIONS and not is_cue_track:
                continue
            entries[name] = _entry(name, info.file_size, info.date_time)
    if save_zip.is_file():
        with zipfile.ZipFile(save_zip) as overlay:
            for info in overlay.infolist():
                name = info.filename.upper().encode('latin-1', 'replace')
                if info.is_dir() or b'/' in name or info.filename.upper() in _UNHASHED_SAVE_FILES or name.endswith(b'.SKC'):
                    continue
                entries[name] = _entry(name, info.file_size, info.date_time)
    return list(entries.values()) if len(entries) <= MAX_ORDERED_FILES else None


def drive_hash(entries: list[tuple[bytes, bytes]], free_space: str) -> int:
    value = (_HASH_BASE - int(DEFAULT_FREE_SPACE) + int(free_space)) & 0xFFFFFFFF
    for path, details in entries:
        value = zlib.crc32(details, zlib.crc32(path, value))
    return value


def drive_saves(rom: Path, saves: Path) -> dict[int, Path]:
    pattern = re.compile(re.escape(rom.stem) + r'(?:-([0-9A-F]{8}))?\.sav')
    found = {}
    for save in saves.glob(f'{glob.escape(rom.stem)}*.sav'):
        if match := pattern.fullmatch(save.name):
            found[int(match.group(1), 16) if match.group(1) else _HASH_BASE] = save
    return found


def matched_free_space(rom: Path, saves: Path) -> str | None:
    existing = drive_saves(rom, saves)
    if not existing:
        return None
    entries = hashed_entries(rom, saves / f'{rom.stem}.pure.zip')
    if entries is None:
        return None
    matches = {}
    for free_space in FREE_SPACE_CHOICES:
        for order in itertools.permutations(entries):
            if (save := existing.get(drive_hash(list(order), free_space))) is not None:
                matches[free_space] = save.stat().st_mtime
                break
    return max(matches, key=matches.get) if matches else None


def usual_free_space(rom: Path, saves: Path) -> str | None:
    votes = Counter()
    for other in sorted(rom.parent.glob('*.zip')):
        if other == rom or not drive_saves(other, saves):
            continue
        if free_space := matched_free_space(other, saves):
            votes[free_space] += 1
            if votes[free_space] >= EVIDENCE_GAMES:
                break
    return votes.most_common(1)[0][0] if votes else None


def free_space_for(rom: Path, saves: Path) -> str:
    if rom.suffix.lower() != '.zip' or not drive_saves(rom, saves):
        return DEFAULT_FREE_SPACE
    return matched_free_space(rom, saves) or usual_free_space(rom, saves) or DEFAULT_FREE_SPACE
