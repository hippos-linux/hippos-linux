from __future__ import annotations

FRONTEND_NAMES = {'emulationstation': 'EmulationStation'}
INSTALL_ORDER = ('emulator', 'frontend', 'patch', 'kernel', 'system')
INCLUDED_IN_SYSTEM = ('frontend', 'patch', 'kernel')


def is_offered(update: dict) -> bool:
    return update['kind'] != 'emulator' or bool(update['installed'])


def offered(updates: list[dict]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = {}
    for update in sorted(updates, key=lambda u: INSTALL_ORDER.index(u['kind']), reverse=True):
        if is_offered(update):
            key = 'patch' if update['kind'] == 'patch' else f"{update['kind']}:{update['name']}"
            groups.setdefault(key, []).append(update)
    return list(groups.values())


def worth_announcing(groups: list[list[dict]]) -> list[list[dict]]:
    if any(group[0]['kind'] == 'system' for group in groups):
        return [group for group in groups if group[0]['kind'] not in INCLUDED_IN_SYSTEM]
    return groups


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


def versions(group: list[dict]) -> str:
    first = group[0]
    if first['kind'] == 'patch':
        return f"{len(group)} for HippOS {first['available']}"
    if first['installed'] == first['available']:
        return f"{first['available']} · new build"
    return f"{first['installed']} → {first['available']}" if first['installed'] else first['available']


def available_headline(group: list[dict]) -> str:
    first = group[0]
    if first['kind'] == 'system':
        return f"{title(first)} is available"
    return f"{title(first)} {'are' if first['kind'] == 'patch' else 'update is'} available"


def notification_key(group: list[dict]) -> str:
    return ' '.join(sorted(f"{u['kind']}:{u['name']}:{u['available']}" for u in group))
