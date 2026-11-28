import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))


def _load_cli():
    loader = importlib.machinery.SourceFileLoader('hippos_apt_packages', str(LIB / 'hippos-apt-packages'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


cli = _load_cli()
PACKAGES = ['cinnamon', 'kde-plasma-desktop', 'teams-for-linux']


class RestoreTests(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.pending = folder / 'apt-restore-pending'
        self.pending.touch()
        patches = {
            'RESTORE_PENDING': self.pending,
            'PRE_UPDATE_STATUS': folder / 'status',
            'PRE_UPDATE_EXTENDED_STATES': folder / 'extended_states',
            'recorded_user_packages': lambda: list(PACKAGES),
            'missing_packages': lambda packages: list(packages),
            'wait_for_network': lambda: None,
        }
        for name, value in patches.items():
            patcher = mock.patch.object(cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def restore(self, updated, failed, candidates=()):
        with mock.patch.object(cli, 'install_packages', return_value=(updated, failed)), \
                mock.patch.object(cli, 'has_candidate', side_effect=lambda p: p in candidates), \
                mock.patch('sys.stderr'), mock.patch('sys.stdout'):
            return cli.restore()

    def test_no_package_lists_keeps_everything_and_retries_soon(self):
        self.assertEqual(self.restore(updated=False, failed=list(PACKAGES)), cli.RETRY_SOON)
        self.assertTrue(self.pending.exists())

    def test_package_gone_from_apt_is_dropped(self):
        self.assertEqual(self.restore(updated=True, failed=['teams-for-linux']), 0)
        self.assertFalse(self.pending.exists())

    def test_install_failure_with_a_candidate_is_retried_next_boot(self):
        status = self.restore(updated=True, failed=['cinnamon', 'teams-for-linux'], candidates={'cinnamon'})
        self.assertEqual(status, 1)
        self.assertTrue(self.pending.exists())

    def test_everything_installed_finishes_the_restore(self):
        self.assertEqual(self.restore(updated=True, failed=[]), 0)
        self.assertFalse(self.pending.exists())


if __name__ == '__main__':
    unittest.main()
