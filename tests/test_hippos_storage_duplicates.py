import importlib.machinery
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HIPPOS_LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'


def _load(name: str, file_name: str):
    loader = importlib.machinery.SourceFileLoader(name, str(HIPPOS_LIB / file_name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


sm = _load('hippos_storage_manager', 'hippos-storage-manager')

ES_SYSTEMS = '''<systemList>
  <system><name>gb</name><path>/userdata/roms/gb</path><extension>.gb .zip</extension></system>
  <system><name>ports</name><path>/userdata/roms/ports</path><extension>.sh</extension></system>
  <system><name>gong</name><path>/userdata/roms/gong</path><extension>.libretro</extension></system>
  <system><name>2048</name><path>/userdata/roms/2048</path><extension>.libretro</extension></system>
</systemList>
'''

ROM = bytes(range(256)) * 512


class GameDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.roms = self.tmp / 'roms'
        self.saves = self.tmp / 'saves'
        es_systems = self.tmp / 'es_systems.cfg'
        es_systems.write_text(ES_SYSTEMS)
        cache = self.tmp / 'cache'
        cache.mkdir()
        patches = [
            mock.patch.object(sm, 'ROMS_POOL', self.roms),
            mock.patch.object(sm, 'ES_SYSTEMS_FILES', [es_systems]),
            mock.patch.object(sm, 'USER_ES_SYSTEMS_DIR', self.tmp / 'none'),
            mock.patch.object(sm, 'REPORT_PATH', cache / 'report.json'),
            mock.patch.object(sm, 'CACHE_ROOT', cache),
            mock.patch.object(sm, 'network_mountpoints', return_value=[]),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        sm.init_db(self.conn)

    def write(self, relative: str, data: bytes) -> Path:
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_zip(self, relative: str, member: str, data: bytes, method: int) -> Path:
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w', compression=method) as archive:
            archive.writestr(member, data)
        return path

    def duplicate_paths(self) -> list[set[str]]:
        sm.scan_roots(self.conn, [(self.roms, 'rom'), (self.saves, 'save')], 1 << 30)
        return [{str(Path(m['path']).relative_to(self.tmp)) for m in group['members']} for group in sm.build_summary(self.conn)['duplicates']]

    def test_same_rom_in_differently_packed_zips_and_loose(self):
        self.write_zip('roms/gb/Game (USA).zip', 'Game (USA).gb', ROM, zipfile.ZIP_DEFLATED)
        self.write_zip('roms/gb/Complete/G/Game (USA).zip', 'game.gb', ROM, zipfile.ZIP_STORED)
        self.write('roms/gb/Game.gb', ROM)
        self.write_zip('roms/gb/Other.zip', 'Other.gb', ROM[::-1], zipfile.ZIP_DEFLATED)
        self.assertEqual(self.duplicate_paths(), [{'roms/gb/Game (USA).zip', 'roms/gb/Complete/G/Game (USA).zip', 'roms/gb/Game.gb'}])

    def test_empty_launchers_are_not_duplicates(self):
        self.write('roms/gong/Gong.libretro', b'')
        self.write('roms/2048/2048.libretro', b'')
        self.assertEqual(self.duplicate_paths(), [])

    def test_files_inside_a_port_are_not_duplicates(self):
        self.write('roms/ports/pmtest/a/gamecontrollerdb.txt', b'same' * 100)
        self.write('roms/ports/pmtest/b/gamecontrollerdb.txt', b'same' * 100)
        self.assertEqual(self.duplicate_paths(), [])

    def test_identical_saves_still_found(self):
        self.write('saves/gb/a.srm', b'save' * 100)
        self.write('saves/gb/b.srm', b'save' * 100)
        self.assertEqual(self.duplicate_paths(), [{'saves/gb/a.srm', 'saves/gb/b.srm'}])


if __name__ == '__main__':
    unittest.main()
