import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HIPPOS_LIB = Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'
sys.path.insert(0, str(HIPPOS_LIB))
_loader = importlib.machinery.SourceFileLoader('hippos_overlay_backup_notify',
                                               str(HIPPOS_LIB / 'hippos-overlay-backup-notify'))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
notify_module = importlib.util.module_from_spec(_spec)
_loader.exec_module(notify_module)


class OverlayBackupNotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.backup = self.tmp / 'backups' / 'overlay-1ab167211a9a'
        self.pending = self.tmp / 'overlay-backup-pending'
        self.pending.write_text('1ab167211a9a\n')
        version = self.tmp / 'hippos-version'
        version.write_text('HIPPOS_VERSION=0.7.1\nBUILD_ID=1ab167211a9a\n')
        patches = [
            mock.patch.object(notify_module, 'PENDING', self.pending),
            mock.patch.object(notify_module, 'BACKUP_ROOT', self.tmp / 'backups'),
            mock.patch.object(notify_module, 'VERSION_FILE', version),
            mock.patch.object(notify_module, '_desktop_session', return_value=False),
            mock.patch.object(notify_module, '_es_ready', return_value=True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def add(self, relative: str) -> None:
        path = self.backup / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x')

    def test_generated_files_alone_do_not_notify(self):
        self.add('usr/lib/python3/dist-packages/smbc/__pycache__/xattr.cpython-313.pyc')
        self.add('usr/share/icons/hicolor/icon-theme.cache')
        self.add('usr/share/applications/mimeinfo.cache')
        with mock.patch.object(notify_module, '_post_es') as post:
            notify_module.main()
        post.assert_not_called()
        self.assertFalse(self.pending.exists())

    def test_changed_files_are_reported_with_the_version_and_no_restore(self):
        self.add('usr/share/hippos/hippos-defaults.conf')
        self.add('usr/bin/emulationstation')
        self.add('usr/share/icons/hicolor/icon-theme.cache')
        with mock.patch.object(notify_module, '_post_es') as post:
            notify_module.main()
        path, message = post.call_args[0]
        self.assertEqual(path, '/messagebox')
        self.assertIn('HippOS 0.7.1 replaced 2 system files you had changed', message)
        self.assertIn(str(self.backup), message)
        self.assertNotIn('Restore', message)


if __name__ == '__main__':
    unittest.main()
