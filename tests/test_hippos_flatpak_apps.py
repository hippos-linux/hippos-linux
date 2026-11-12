import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_flatpak_apps as flatpak_apps


class AppIdTests(unittest.TestCase):
    def test_flathub_ids_are_accepted(self):
        for app_id in ('com.moonlight_stream.Moonlight', 'com.github.iwalton3.jellyfin-media-player',
                       'io.github.streetpea.Chiaki4deck'):
            self.assertTrue(flatpak_apps.valid_app_id(app_id), app_id)

    def test_shell_text_and_short_names_are_rejected(self):
        for app_id in ('moonlight', 'com.x', 'com.x.y; rm -rf /', 'com.x.$(id)', ''):
            self.assertFalse(flatpak_apps.valid_app_id(app_id), app_id)

    def test_invalid_id_never_runs_flatpak(self):
        with mock.patch.object(flatpak_apps.subprocess, 'run') as run:
            self.assertEqual(flatpak_apps.install('com.x.y;reboot'), 1)
            self.assertEqual(flatpak_apps.remove('bad'), 1)
        run.assert_not_called()


class CommandTests(unittest.TestCase):
    def test_root_runs_flatpak_as_the_session_user(self):
        with mock.patch.object(flatpak_apps.os, 'geteuid', return_value=0):
            command = flatpak_apps._flatpak('install', '--user', 'flathub', 'com.a.b')
        self.assertEqual(command[:4], ['runuser', '-l', 'hippos', '-c'])
        self.assertEqual(command[4], 'flatpak install --user flathub com.a.b')

    def test_session_user_runs_flatpak_directly(self):
        with mock.patch.object(flatpak_apps.os, 'geteuid', return_value=1000):
            self.assertEqual(flatpak_apps._flatpak('info', '--user', 'com.a.b'), ['flatpak', 'info', '--user', 'com.a.b'])


if __name__ == '__main__':
    unittest.main()
