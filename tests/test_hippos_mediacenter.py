import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


mc = _load('hippos_mediacenter', LIB / 'hippos-mediacenter')
store = _load('hippos_store', LIB / 'hippos-store')


class AvailabilityTests(unittest.TestCase):
    def test_pc_offers_all_four(self):
        with mock.patch.object(mc, 'ARCH', 'x86_64'):
            self.assertEqual([c.id for c in mc.available()], ['kodi', 'jellyfin', 'emby', 'plex'])

    def test_pi_leaves_out_plex(self):
        with mock.patch.object(mc, 'ARCH', 'aarch64'):
            self.assertEqual([c.id for c in mc.available()], ['kodi', 'jellyfin', 'emby'])

    def test_package_sources_follow_apt_deb_flatpak_order(self):
        sources = {c.id: ('flatpak' if c.flatpak_id else 'package') for c in mc.MEDIA_CENTERS}
        self.assertEqual(sources, {'kodi': 'package', 'jellyfin': 'flatpak', 'emby': 'package', 'plex': 'flatpak'})


class DebCatalogTests(unittest.TestCase):
    def test_deb_item_only_shows_for_architectures_it_has(self):
        item = {'type': 'deb', 'deb': {'amd64': {'url': 'u', 'sha256': 's'}}}
        with mock.patch.object(store, 'DEB_ARCH', 'amd64'):
            self.assertTrue(store.for_this_machine(item))
        with mock.patch.object(store, 'DEB_ARCH', 'arm64'):
            self.assertFalse(store.for_this_machine(item))


if __name__ == '__main__':
    unittest.main()
