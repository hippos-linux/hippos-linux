import importlib.machinery
import importlib.util
import sys
import unittest
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
mg = _load('hippos_merge_gamelists', 'hippos-merge-gamelists')

DISK = {
    'mmcblk1p1': ('c12a7328-f81f-11d2-ba4b-00a0c93ec93b', 'EFI', 'mmcblk1'),
    'mmcblk1p2': ('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7', 'Tools', 'mmcblk1'),
    'mmcblk1p3': ('0fc63daf-8483-4772-8e79-3d69d8477de4', 'HippOS', 'mmcblk1'),
    'mmcblk1p4': ('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7', 'Games', 'mmcblk1'),
    'mmcblk0p1': ('0xc', '', 'mmcblk0'),
}
MOUNTS = {'/': 'overlay', '/boot/efi': '/dev/mmcblk1p1', '/userdata': '/dev/mmcblk1p3[/@userdata]'}


def _run_text(cmd: list[str]) -> str:
    if cmd[0] == 'findmnt':
        return MOUNTS.get(cmd[-1], '')
    name = Path(cmd[-1]).name
    return {'PARTTYPE': DISK[name][0], 'PARTLABEL': DISK[name][1]}[cmd[2]]


class SystemDeviceTests(unittest.TestCase):
    def setUp(self):
        for target, fake in (('run_text', _run_text), ('parent_disk', lambda name: DISK[name][2])):
            patcher = mock.patch.object(sm, target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_every_partition_of_the_hippos_layout_is_a_system_partition(self):
        for name in ('mmcblk1p1', 'mmcblk1p2', 'mmcblk1p3'):
            self.assertTrue(sm.is_system_device(name), name)

    def test_other_partitions_and_other_cards_can_be_mounted(self):
        self.assertFalse(sm.is_system_device('mmcblk1p4'))
        self.assertFalse(sm.is_system_device('mmcblk0p1'))


class UnreadableBranchTests(unittest.TestCase):
    def test_a_card_that_fails_to_read_is_skipped(self):
        failed: set[Path] = set()
        card = Path('/media/EEROMS')
        real_exists = Path.exists

        def exists(path: Path) -> bool:
            if path.is_relative_to(card):
                raise OSError(5, 'Input/output error')
            return real_exists(path)

        with mock.patch.object(Path, 'exists', exists):
            self.assertEqual(mg.merge_system('nes', Path('/userdata/.roms-rw'), [card], failed), 0)
        self.assertEqual(failed, {card})


if __name__ == '__main__':
    unittest.main()
