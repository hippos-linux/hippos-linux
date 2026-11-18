import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parent.parent
HOTKEY_CONTEXTS = REPO / 'overlays' / 'rootfs' / 'usr' / 'share' / 'hippos' / 'hotkeys' / 'contexts'
NON_EMULATOR_CONTEXTS = {'emulationstation', 'game-default', 'waydroid'}
sys.path.insert(0, str(REPO / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_impl  # noqa: F401
import emulatorlauncher_shared as shared
from emulatorlauncher_registry import registered


def _systems_by_emulator() -> dict[str, set[str]]:
    systems: dict[str, set[str]] = {}
    for yml in sorted((REPO / 'packages' / 'emulators').glob('*/*.emulator.yml')):
        entries = (yaml.safe_load(yml.read_text()) or {}).get('systems') or []
        if isinstance(entries, dict):
            entries = list(entries)
        name = yml.name.removesuffix('.emulator.yml')
        for entry in entries:
            system = entry.get('name') if isinstance(entry, dict) else entry
            if system:
                systems.setdefault(name, set()).add(str(system))
    frontend = yaml.safe_load((REPO / 'packages' / 'frontend' / 'systems.yml').read_text())
    for key in ('_emulator_defaults', '_emulator_defaults_arm64'):
        for system, default in (frontend.get(key) or {}).items():
            if isinstance(default, dict) and default.get('emulator'):
                systems.setdefault(default['emulator'], set()).add(system)
    return systems


def _systems_with_own_command() -> set[str]:
    frontend = yaml.safe_load((REPO / 'packages' / 'frontend' / 'systems.yml').read_text())
    default = frontend['_defaults']['command']
    return {
        name for name, data in frontend.items()
        if isinstance(data, dict) and data.get('command') not in (None, default)
    }


class RegistryTests(unittest.TestCase):
    def test_every_es_emulator_resolves_to_one_launcher(self):
        own_command = _systems_with_own_command()
        unresolved = sorted(
            name for name, systems in _systems_by_emulator().items()
            if not systems <= own_command and name not in registered()
        )
        self.assertEqual(unresolved, [])

    def test_registered_binaries_are_found_in_their_package(self):
        for name, emulator in registered().items():
            with self.subTest(emulator=name), tempfile.TemporaryDirectory() as root:
                binary = Path(root) / name / 'bin' / emulator.binary_names[0]
                binary.parent.mkdir(parents=True)
                binary.write_text('#!/bin/sh\n')
                binary.chmod(0o755)
                with mock.patch.object(shared, 'EMULATORS_ROOT', Path(root)):
                    self.assertEqual(shared._find_emulator_bin(name), binary)


    def test_explicit_hotkey_contexts_exist(self):
        missing = sorted(
            f"{name}: {emulator.hotkeys}" for name, emulator in registered().items()
            if emulator.hotkeys and not (HOTKEY_CONTEXTS / f'{emulator.hotkeys}.json').is_file()
        )
        self.assertEqual(missing, [])

    def test_every_hotkey_context_file_is_used(self):
        used = {emulator.hotkey_context for emulator in registered().values()} | NON_EMULATOR_CONTEXTS
        unused = sorted(p.stem for p in HOTKEY_CONTEXTS.glob('*.json') if p.stem not in used)
        self.assertEqual(unused, [])


if __name__ == '__main__':
    unittest.main()
