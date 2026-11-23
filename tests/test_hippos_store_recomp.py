import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))

import hippos_software_index as index
import hippos_store_catalog as catalog


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


store = _load('hippos_store_recomp', LIB / 'hippos-store')

ZELDA = {'id': 'zelda64recomp', 'name': 'Zelda 64: Recompiled', 'repo': 'Zelda64Recomp/Zelda64Recomp',
         'version': '1.2.2', 'downloads': 400, 'blurb': 'Majora\'s Mask on PC.', 'needs': 'Your own ROM',
         'released_at': '2025-08-27T00:58:35Z', 'author': 'Zelda64Recomp', 'license': 'GPL-3.0',
         'assets': {'windows': 'Zelda64Recompiled-*-Windows.zip', 'linux': 'Zelda64Recompiled-*-Linux-X64.zip'},
         'boot': {'start': 'Zelda64Recompiled.exe'}}
ARM_ONLY = {'id': 'armgame', 'repo': 'a/b', 'assets': {'linux': 'game-linux-aarch64.tar.gz'}}
NO_LINUX = {'id': 'winonly', 'repo': 'a/b', 'assets': {'windows': 'game.zip'}}
GITLAB = {'id': 'gitlab', 'repo': 'https://gitlab.com/a/b', 'assets': {'linux': 'game.zip'}}


class RecompCatalogTests(unittest.TestCase):
    def test_linux_build_must_match_the_machine(self):
        with mock.patch.object(catalog, 'DEB_ARCH', 'amd64'):
            self.assertEqual(catalog.recomp_linux_pattern(ZELDA), 'Zelda64Recompiled-*-Linux-X64.zip')
            self.assertIsNone(catalog.recomp_linux_pattern(ARM_ONLY))
            self.assertIsNone(catalog.recomp_linux_pattern(NO_LINUX))
            self.assertIsNone(catalog.recomp_linux_pattern(GITLAB))
        with mock.patch.object(catalog, 'DEB_ARCH', 'arm64'):
            self.assertIsNone(catalog.recomp_linux_pattern(ZELDA))
            self.assertEqual(catalog.recomp_linux_pattern(ARM_ONLY), 'game-linux-aarch64.tar.gz')

    def test_index_entries(self):
        with mock.patch.object(catalog, 'DEB_ARCH', 'amd64'):
            found = list(index.read_recomps([ZELDA, ARM_ONLY, NO_LINUX]))
        self.assertEqual([app.key for app, _ in found], ['recomp:zelda64recomp'])
        app, details = found[0]
        self.assertEqual((app.sources[0].name, app.installs, app.installs_source),
                         ('recomp::zelda64recomp', 400, 'recomp'))
        self.assertIn('Recomps', app.categories)
        self.assertIn('Needs: Your own ROM', details.description)
        self.assertEqual(details.homepage, 'https://github.com/Zelda64Recomp/Zelda64Recomp')

    def test_updates_compare_versions_without_a_v(self):
        state = {'recomp::zelda64recomp': {'version': 'v1.2.1'}, 'recomp::same': {'version': 'v2.0'}}
        entries = [ZELDA, {'id': 'same', 'version': '2.0'}]
        self.assertEqual(index.recomp_updates(entries, state), {'recomp::zelda64recomp'})


class RecompInstallTests(unittest.TestCase):
    def test_release_asset_matches_the_pattern(self):
        releases = [{'draft': True, 'tag_name': 'v9', 'assets': [{'name': 'Zelda64Recompiled-v9-Linux-X64.zip'}]},
                    {'tag_name': 'v1.2.2', 'assets': [{'name': 'Zelda64Recompiled-v1.2.2-Windows.zip'},
                                                       {'name': 'Zelda64Recompiled-v1.2.2-Linux-X64.zip'}]}]
        latest = {'tag_name': 'v1.3', 'assets': [{'name': 'Zelda64Recompiled-v1.3-Windows.zip'}]}
        answers = {'https://api.github.com/repos/Zelda64Recomp/Zelda64Recomp/releases/latest': latest}
        with mock.patch.object(catalog, 'DEB_ARCH', 'amd64'), \
                mock.patch.object(store, '_gh_get', side_effect=lambda url: answers.get(url, releases)):
            tag, asset = store._recomp_release_asset(ZELDA)
        self.assertEqual((tag, asset['name']), ('v1.2.2', 'Zelda64Recompiled-v1.2.2-Linux-X64.zip'))
        answers[next(iter(answers))] = releases[1]
        with mock.patch.object(catalog, 'DEB_ARCH', 'amd64'), \
                mock.patch.object(store, '_gh_get', side_effect=lambda url: answers.get(url, [])):
            self.assertEqual(store._recomp_release_asset(ZELDA)[0], 'v1.2.2')

    def test_executable_prefers_the_named_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, size in (('Zelda64Recompiled', 10), ('helper', 500), ('libfoo.so', 900)):
                Path(tmp, name).write_bytes(b'\x7fELF' + b'0' * size)
            Path(tmp, 'readme.txt').write_text('hi')
            chosen = store._recomp_executable(tmp, ZELDA)
            self.assertEqual(os.path.basename(chosen), 'Zelda64Recompiled')
            self.assertTrue(os.access(chosen, os.X_OK))

    def test_executable_falls_back_to_the_largest_top_level_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'sub').mkdir()
            Path(tmp, 'sub', 'deep').write_bytes(b'\x7fELF' + b'0' * 900)
            Path(tmp, 'small').write_bytes(b'\x7fELF' + b'0' * 10)
            Path(tmp, 'game').write_bytes(b'\x7fELF' + b'0' * 100)
            self.assertEqual(os.path.basename(store._recomp_executable(tmp, {'boot': None})), 'game')

    def test_a_download_holding_one_archive_is_unpacked_again(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp, 'Zelda64Recompiled')
            game.write_bytes(b'\x7fELF')
            dest = Path(tmp, 'dest')
            dest.mkdir()
            with tarfile.open(dest / 'Zelda64Recompiled.tar.gz', 'w:gz') as tar:
                tar.add(game, arcname='Zelda64Recompiled')
            with mock.patch('builtins.print'):
                store._unpack_inner_archive(str(dest))
            self.assertEqual(os.listdir(dest), ['Zelda64Recompiled'])


if __name__ == '__main__':
    unittest.main()
