"""evmapy context manager for emulatorlauncher.

Searches for .keys files, merges them, writes per-controller evmapy JSON
configs, then starts/stops the evmapy daemon around the game process.

.keys files are JSON with the structure:
{
  "actions_player1": [
    {"trigger": "hotkey+start", "type": "key",  "target": "KEY_ESC"},
    {"trigger": "hotkey+b",     "type": "exec", "target": "/usr/bin/hippos-screenshot"}
  ]
}
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulatorlauncher_impl import ControllerInfo, ESControllerProfile

_log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_USER_EVMAPY   = Path('/userdata/system/evmapy')
_SYSTEM_EVMAPY = Path('/usr/share/hippos/evmapy')
_RUN_EVMAPY    = Path('/var/run/evmapy')          # evmapy watches this dir directly
_MERGED_KEYS   = Path('/var/run/evmapy_merged.keys')

HIPPOS_EVMAPY  = Path('/usr/lib/hippos/hippos-evmapy')


# ── Key file search ────────────────────────────────────────────────────────────

def _find_keys_files(system: str, emulator: str, rom: Path) -> list[Path]:
    """Return ordered list of existing .keys files to merge."""
    candidates = [
        # Per-ROM (highest priority)
        (rom.parent / f'{rom.name}.keys') if not rom.is_dir() else (rom / 'padto.keys'),
        # User per-system/emulator overrides
        _USER_EVMAPY / f'{system}.{emulator}.keys',
        _USER_EVMAPY / f'{system}.keys',
        _USER_EVMAPY / f'{emulator}.keys',
        _USER_EVMAPY / 'any.keys',
        # System defaults
        _SYSTEM_EVMAPY / f'{system}.{emulator}.keys',
        _SYSTEM_EVMAPY / f'{system}.keys',
        _SYSTEM_EVMAPY / f'{emulator}.keys',
        _SYSTEM_EVMAPY / 'any.keys',
    ]
    found = [p for p in candidates if p.exists()]

    # Global hotkeys appended last (lowest priority)
    for hotkeys in (_USER_EVMAPY / 'hotkeys.keys', _SYSTEM_EVMAPY / 'hotkeys.keys'):
        if hotkeys.exists():
            found.append(hotkeys)
            break

    return found


# ── Merge ──────────────────────────────────────────────────────────────────────

def _merge_keys_files(files: list[Path]) -> dict:
    """Merge multiple .keys files. First occurrence of a trigger wins."""
    merged: dict[str, dict[str, dict]] = defaultdict(dict)

    for f in files:
        try:
            data: dict = json.loads(f.read_text())
        except Exception as exc:
            _log.warning("evmapy: could not parse %s: %s", f, exc)
            continue

        for player_key, actions in data.items():
            for action in actions:
                trigger = action.get('trigger', '')
                if isinstance(trigger, list):
                    trigger = '-'.join(sorted(trigger))
                if trigger and trigger not in merged[player_key]:
                    merged[player_key][trigger] = action

    return {k: list(v.values()) for k, v in merged.items()}


# ── Per-controller config ──────────────────────────────────────────────────────

def _controller_evmapy_config(
    ctrl: ControllerInfo,
    profile: ESControllerProfile,
    actions: list[dict],
) -> dict:
    """Build evmapy JSON config for one controller."""
    buttons = []
    axes = []
    seen_codes: set[int] = set()
    seen_axis_codes: set[int] = set()

    for binding in profile.inputs.values():
        if binding.type == 'button':
            if binding.code not in seen_codes:
                seen_codes.add(binding.code)
                buttons.append({'name': binding.name, 'code': binding.code})
        elif binding.type == 'hat':
            # Map hat to two axes (X and Y)
            for suffix, offset in ((':min', 0), (':max', 1)):
                axis_code = binding.code * 2 + offset + 16  # HAT0X = 16 in linux/input.h
                if axis_code not in seen_axis_codes:
                    seen_axis_codes.add(axis_code)
                    axes.append({
                        'name': f'HAT{binding.code}{"X" if offset == 0 else "Y"}',
                        'code': axis_code,
                        'min': -1,
                        'max': 1,
                    })
        elif binding.type == 'axis':
            if binding.code not in seen_axis_codes:
                seen_axis_codes.add(binding.code)
                axes.append({
                    'name': binding.name,
                    'code': binding.code,
                    'min': -32768,
                    'max': 32767,
                })

    # Build button-name → evmapy-name lookup for trigger resolution
    name_map = {b['name']: b['name'] for b in buttons}

    resolved_actions = []
    for action in actions:
        trigger = action.get('trigger', '')
        if isinstance(trigger, list):
            parts = trigger
        else:
            parts = trigger.split('+') if '+' in trigger else [trigger]
        # Only include action if all trigger parts are known buttons/axes
        if all(p in name_map for p in parts):
            resolved_actions.append({k: v for k, v in action.items() if k != 'description'})

    return {
        'grab': False,
        'buttons': buttons,
        'axes': axes,
        'actions': resolved_actions,
    }


# ── Context manager ────────────────────────────────────────────────────────────

@contextmanager
def evmapy_context(
    system: str,
    emulator: str,
    rom: Path,
    controllers: list[ControllerInfo],
    profiles: list[ESControllerProfile],
):
    """Start evmapy daemon for the game, stop it on exit."""
    from emulatorlauncher_impl import _pick_es_profile

    started = _prepare(system, emulator, rom, controllers, profiles)
    try:
        yield
    finally:
        if started:
            subprocess.call([str(HIPPOS_EVMAPY), 'stop'],  stderr=subprocess.DEVNULL)
            subprocess.call([str(HIPPOS_EVMAPY), 'clear'], stderr=subprocess.DEVNULL)


def _prepare(
    system: str,
    emulator: str,
    rom: Path,
    controllers: list[ControllerInfo],
    profiles: list[ESControllerProfile],
) -> bool:
    from emulatorlauncher_impl import _pick_es_profile

    files = _find_keys_files(system, emulator, rom)
    if not files:
        _log.debug("evmapy: no .keys files for system=%s emulator=%s", system, emulator)
        return False

    merged = _merge_keys_files(files)
    if not merged:
        return False

    _RUN_EVMAPY.mkdir(parents=True, exist_ok=True)

    # Clear stale configs
    subprocess.call([str(HIPPOS_EVMAPY), 'clear'], stderr=subprocess.DEVNULL)

    wrote_any = False
    for ctrl in controllers:
        player_key = f'actions_player{ctrl.player}'
        actions = merged.get(player_key)
        if not actions:
            continue
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            _log.debug("evmapy: no ES profile for controller %s", ctrl.name)
            continue
        device_name = Path(ctrl.device_path).name if ctrl.device_path else f'js{ctrl.index}'
        cfg = _controller_evmapy_config(ctrl, profile, actions)
        cfg_path = _RUN_EVMAPY / f'{device_name}.json'
        cfg_path.write_text(json.dumps(cfg, indent=2))
        _log.info("evmapy: wrote config for player %d → %s", ctrl.player, cfg_path)
        wrote_any = True

    if not wrote_any:
        return False

    ret = subprocess.call([str(HIPPOS_EVMAPY), 'start'], stderr=subprocess.DEVNULL)
    if ret != 0:
        _log.warning("evmapy: start returned %d", ret)
        return False

    _log.info("evmapy: started for system=%s emulator=%s", system, emulator)
    return True
