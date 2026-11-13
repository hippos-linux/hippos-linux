from __future__ import annotations

FRONTEND_NAMES = {'emulationstation': 'EmulationStation'}


def is_offered(update: dict) -> bool:
    return update['kind'] != 'emulator' or bool(update['installed'])


def title(update: dict) -> str:
    match update['kind']:
        case 'system':
            return f"HippOS {update['available']}"
        case 'kernel':
            return 'Linux kernel'
        case 'frontend':
            return FRONTEND_NAMES.get(update['name'], update['name'])
        case 'patch':
            return 'Fixes for this version'
    return update['name']


def summary(updates: list[dict]) -> str:
    emulators = [u for u in updates if u['kind'] == 'emulator']
    patches = [u for u in updates if u['kind'] == 'patch']
    parts = [title(u) for u in updates if u['kind'] in ('system', 'kernel', 'frontend')]
    if len(emulators) == 1:
        parts.append(title(emulators[0]))
    elif emulators:
        parts.append(f'{len(emulators)} emulators')
    if patches:
        parts.append(f"{len(patches)} fix{'es' if len(patches) > 1 else ''}")
    return ', '.join(parts)


def headline(updates: list[dict]) -> str:
    system = next((u for u in updates if u['kind'] == 'system'), None)
    return f"HippOS {system['available']} is available" if system else 'Updates are available'


def notification_key(updates: list[dict]) -> str:
    return '\n'.join(sorted(f"{u['kind']}:{u['name']}:{u['available']}" for u in updates))
