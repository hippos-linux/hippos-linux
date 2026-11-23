import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_flatpak_apps
import hippos_store_search as store_search


class DebianResultsTests(unittest.TestCase):
    def setUp(self):
        for name, value in {
            'refresh_apt_lists': mock.Mock(),
            'image_packages': mock.Mock(return_value=frozenset({'retroarch'})),
            'search_packages': mock.Mock(return_value=[
                ('retroarch', 'part of the system'),
                ('libretro-core', 'a library'),
                ('foo-dev', 'headers'),
                ('supertux', 'a game'),
                ('frotz', 'another game'),
            ]),
            'missing_packages': mock.Mock(return_value=['frotz']),
        }.items():
            patcher = mock.patch.object(store_search, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_leaves_out_system_and_non_app_packages(self):
        results = store_search.debian_results('game')
        self.assertEqual([r.name for r in results], ['apt::supertux', 'apt::frotz'])
        self.assertEqual([r.installed for r in results], [True, False])

    def test_refuses_to_remove_a_system_package(self):
        with self.assertRaises(store_search.StoreSearchError):
            store_search.remove('apt::retroarch')

    def test_refuses_a_name_that_is_not_a_package(self):
        with self.assertRaises(store_search.StoreSearchError):
            store_search.install('apt::foo; rm -rf /')


class FlathubSearchTests(unittest.TestCase):
    def test_parses_tab_separated_search_output(self):
        listing = ('org.libretro.RetroArch\tRetroArch\tFrontend for emulators\t1.22.2\n'
                   'not an app id\tBroken\tline\t1\n')
        runs = [mock.Mock(stdout=''), mock.Mock(stdout=''), mock.Mock(stdout=listing)]
        with mock.patch.object(hippos_flatpak_apps.subprocess, 'run', side_effect=runs):
            apps = hippos_flatpak_apps.search_flathub('retro')
        self.assertEqual(apps, [hippos_flatpak_apps.FlathubApp(
            'org.libretro.RetroArch', 'RetroArch', 'Frontend for emulators', '1.22.2')])


if __name__ == '__main__':
    unittest.main()
