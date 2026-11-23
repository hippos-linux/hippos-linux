import hashlib
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
import zipfile
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


store = _load('hippos_store', LIB / 'hippos-store')
import hippos_store_catalog as catalog


def _zip(path, entries):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, mode in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            zf.writestr(info, b'data')


class ExtractZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_keeps_executable_bits(self):
        _zip(self.tmp / 'a.zip', [('Game', 0o755), ('Content/level.json', 0o644)])
        store._extract_zip(str(self.tmp / 'a.zip'), str(self.tmp / 'out'), 0)
        self.assertTrue(os.access(self.tmp / 'out' / 'Game', os.X_OK))
        self.assertFalse(os.access(self.tmp / 'out' / 'Content' / 'level.json', os.X_OK))

    def test_strips_leading_folders(self):
        _zip(self.tmp / 'a.zip', [('Game-1.0/Game', 0o755)])
        store._extract_zip(str(self.tmp / 'a.zip'), str(self.tmp / 'out'), 1)
        self.assertTrue((self.tmp / 'out' / 'Game').exists())

    def test_never_writes_outside_the_folder(self):
        _zip(self.tmp / 'a.zip', [('../escape', 0o644), ('Game', 0o755)])
        store._extract_zip(str(self.tmp / 'a.zip'), str(self.tmp / 'out'), 0)
        self.assertFalse((self.tmp / 'escape').exists())
        self.assertTrue((self.tmp / 'out' / 'Game').exists())


class InstallArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _zip(self.tmp / 'game.zip', [('Game', 0o755)])
        self.sha = hashlib.sha256((self.tmp / 'game.zip').read_bytes()).hexdigest()
        self.patches = [
            mock.patch.object(store, 'GAMES_DIR', str(self.tmp / 'games')),
            mock.patch.object(store, 'CACHE_DIR', str(self.tmp / 'cache')),
            mock.patch.object(store, 'DEB_ARCH', 'amd64'),
            mock.patch.object(store, '_download', lambda url, dest, label: Path(dest).write_bytes((self.tmp / 'game.zip').read_bytes())),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()

    def _pkg(self, sha):
        return {'id': 'port-game', 'name': 'Game', 'category': 'ports', 'type': 'archive',
                'archive': {'amd64': {'url': 'https://example.org/game.zip', 'sha256': sha}},
                'launcher_command': 'Game --fullscreen'}

    def test_launcher_runs_the_game_from_its_own_folder(self):
        with mock.patch.object(store, 'add_catalog_game') as add:
            store._install_archive(self._pkg(self.sha))
        command = add.call_args.args[0]['launcher_command']
        self.assertEqual(command, f'env -C {self.tmp}/games/port-game ./Game --fullscreen')
        self.assertTrue(os.access(self.tmp / 'games' / 'port-game' / 'Game', os.X_OK))

    def test_appimage_is_kept_as_the_launcher_binary(self):
        image = self.tmp / 'Tool.AppImage'
        image.write_bytes(b'\x7fELF')
        pkg = {'id': 'app-tool', 'name': 'Tool', 'category': 'apps', 'type': 'archive',
               'archive': {'amd64': {'url': 'https://example.org/Tool-1.0.AppImage',
                                     'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}},
               'launcher_command': 'tool --no-sandbox'}
        with mock.patch.object(store, '_download', lambda url, dest, label: Path(dest).write_bytes(image.read_bytes())), \
                mock.patch.object(store, 'add_catalog_game') as add:
            store._install_archive(pkg)
        self.assertTrue(os.access(self.tmp / 'games' / 'app-tool' / 'tool', os.X_OK))
        self.assertEqual(add.call_args.args[0]['launcher_command'], f'env -C {self.tmp}/games/app-tool ./tool --no-sandbox')

    def test_bad_checksum_installs_nothing(self):
        with mock.patch.object(store, 'add_catalog_game') as add, self.assertRaises(SystemExit):
            store._install_archive(self._pkg('0' * 64))
        add.assert_not_called()
        self.assertFalse((self.tmp / 'games' / 'port-game').exists())

    def test_only_offered_where_there_is_a_download(self):
        pkg = self._pkg(self.sha)
        with mock.patch.object(catalog, 'DEB_ARCH', 'amd64'):
            self.assertTrue(store.for_this_machine(pkg))
        with mock.patch.object(catalog, 'DEB_ARCH', 'arm64'):
            self.assertFalse(store.for_this_machine(pkg))


if __name__ == '__main__':
    unittest.main()
