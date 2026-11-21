import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_emulator_integration as integration

SYSTEMS = {
    '_defaults': {'command': integration.DEFAULT_COMMAND},
    '_emulator_defaults': {'psx': {'emulator': 'newpsx', 'core': 'newpsx'}},
    'psx': {'name': 'PlayStation', 'extensions': ['cue']},
}

BASE_FEATURES = '''<?xml version="1.0" encoding="UTF-8" ?>
<features>
  <sharedFeatures />
  <emulator name="oldpsx" features="ratio" />
</features>
'''


class IntegrationRoot:
    def __init__(self, root: Path):
        self.root = root
        self.share = root / integration.SHARE_DIR
        self.packages = root / integration.PACKAGES_DIR
        self.state = root / integration.STATE_DIR
        self.share.mkdir(parents=True)
        self.packages.mkdir(parents=True)
        (self.share / integration.SYSTEMS_FILE).write_text(yaml.safe_dump(SYSTEMS))
        (self.share / integration.BASE_FEATURES_FILE).write_text(BASE_FEATURES)
        self.image_emulator('oldpsx', {'requireArtifact': 'oldpsx', 'systems': ['psx']})

    def image_emulator(self, name: str, data: dict) -> None:
        (self.share / f'{name}.emulator.yml').write_text(yaml.safe_dump(data))

    def install(self, name: str, data: dict | None = None, features: str | None = None,
                desktop: bool = False, sha: str = 'sha') -> Path:
        package = self.packages / name
        (package / 'bin').mkdir(parents=True, exist_ok=True)
        (package / integration.INSTALLED_SHA256_FILE).write_text(sha + '\n')
        hippos = package / integration.PACKAGE_DIR
        if data is not None:
            hippos.mkdir(exist_ok=True)
            (hippos / f'{name}.emulator.yml').write_text(yaml.safe_dump(data))
        if features is not None:
            (hippos / integration.ES_FEATURES).write_text(features)
        if desktop:
            (hippos / 'applications').mkdir(exist_ok=True)
            (hippos / 'applications' / f'hippos-{name}.desktop').write_text('[Desktop Entry]\n')
        return package

    def psx_emulators(self) -> dict[str, str | None]:
        systems = ET.parse(self.state / integration.ES_SYSTEMS).getroot()
        return {e.get('name'): e.find('cores/core').get('default')
                for s in systems.iter('system') if s.findtext('name') == 'psx' for e in s.iter('emulator')}


class EmulatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env = IntegrationRoot(Path(tmp.name))
        self.env.install('oldpsx')

    def sync(self, force: bool = False) -> bool:
        return integration.sync(root=self.env.root, arch='amd64', force=force)

    def test_package_emulator_joins_its_systems_and_takes_the_declared_default(self):
        self.env.install('newpsx', {'requireArtifact': 'newpsx', 'systems': ['psx']})
        self.sync()
        self.assertEqual(self.env.psx_emulators(), {'newpsx': 'true', 'oldpsx': None})
        defaults = json.loads((self.env.state / integration.LAUNCHER_DEFAULTS).read_text())
        self.assertEqual(defaults['psx'], {'emulator': 'newpsx', 'core': 'newpsx'})

    def test_declared_default_falls_back_while_its_package_is_missing(self):
        self.sync()
        self.assertEqual(self.env.psx_emulators(), {'oldpsx': 'true'})

    def test_image_emulator_without_its_package_is_left_out(self):
        self.env.image_emulator('absent', {'requireArtifact': 'absent', 'systems': ['psx']})
        self.sync()
        self.assertNotIn('absent', self.env.psx_emulators())

    def test_package_yml_replaces_the_image_yml_of_the_same_emulator(self):
        self.env.install('oldpsx', {'requireArtifact': 'oldpsx', 'systems': []})
        self.sync()
        self.assertEqual(self.env.psx_emulators(), {})

    def test_unfinished_install_is_ignored(self):
        self.env.install('newpsx.new', {'systems': ['psx']})
        self.sync()
        self.assertNotIn('newpsx.new', self.env.psx_emulators())

    def test_package_features_are_merged_into_the_base(self):
        self.env.install('newpsx', {'systems': ['psx']}, features=(
            '<features><emulator name="newpsx" features="rewind" />'
            '<emulator name="oldpsx" features="cheevos" /></features>'))
        self.sync()
        features = ET.parse(self.env.state / integration.ES_FEATURES).getroot()
        self.assertEqual({e.get('name'): e.get('features') for e in features.iter('emulator')},
                         {'oldpsx': 'cheevos', 'newpsx': 'rewind'})
        self.assertIsNotNone(features.find('sharedFeatures'))

    def test_sync_runs_again_only_after_packages_change(self):
        self.assertTrue(self.sync())
        self.assertFalse(self.sync())
        self.env.install('newpsx', {'systems': ['psx']})
        self.assertTrue(self.sync())
        self.env.install('newpsx', {'systems': ['psx']}, sha='other')
        self.assertFalse(self.sync())
        self.assertFalse(self.sync(force=True))

    def test_package_desktop_entries_are_exported_and_withdrawn(self):
        package = self.env.install('newpsx', {'systems': ['psx']}, desktop=True)
        self.sync()
        link = self.env.state / integration.APPLICATIONS_EXPORT / 'hippos-newpsx.desktop'
        self.assertEqual(Path(os.readlink(link)),
                         integration.EMULATORS_ROOT / 'newpsx' / 'hippos' / 'applications' / 'hippos-newpsx.desktop')
        for path in sorted(package.rglob('*'), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        package.rmdir()
        self.sync()
        self.assertFalse(link.is_symlink())

    def test_broken_package_yml_is_skipped(self):
        package = self.env.install('newpsx', {'systems': ['psx']})
        (package / 'hippos' / 'newpsx.emulator.yml').write_text('systems: [psx\n')
        self.sync()
        self.assertEqual(self.env.psx_emulators(), {'oldpsx': 'true'})


if __name__ == '__main__':
    unittest.main()
