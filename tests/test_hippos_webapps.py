import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'))

import hippos_webapps  # noqa: E402
from hippos_webapps import WebApp  # noqa: E402

try:
    import gi
    gi.require_version('GLib', '2.0')
    from gi.repository import GLib
except (ImportError, ValueError):
    GLib = None


class WebAppsTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        paths = {
            'WEBAPPS_DIR': self.base / 'roms' / 'linuxapps',
            'WEBAPPS_LIST': self.base / 'system' / 'webapps.json',
            'STATE_FILE': self.base / 'system' / 'webapps-launchers.json',
            'WEBAPP_PROFILES': self.base / 'system' / 'webapps' / 'profiles',
            'WEBAPP_ICONS': self.base / 'system' / 'webapps' / 'icons',
            'DESKTOP_ENTRIES': self.base / '.local' / 'share' / 'applications',
            'MINT_PROFILES': self.base / '.local' / 'share' / 'ice' / 'profiles',
        }
        for name, path in paths.items():
            patcher = mock.patch.object(hippos_webapps, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, name.lower(), path)
        patcher = mock.patch.object(hippos_webapps, 'reload_es')
        patcher.start()
        self.addCleanup(patcher.stop)

    def entries(self):
        return sorted(path.name for path in self.desktop_entries.glob('*.desktop'))


class DesktopEntryTests(WebAppsTestCase):
    def test_sync_writes_a_menu_entry_per_web_app_with_the_es_profile(self):
        icon = self.base / 'yt.png'
        icon.write_bytes(b'png')
        hippos_webapps.save_webapps([WebApp('YouTube', 'https://www.youtube.com/', str(icon), 'Videos')])
        hippos_webapps.sync()
        self.assertEqual(self.entries(), ['hippos-webapp-youtube.desktop'])
        text = (self.desktop_entries / 'hippos-webapp-youtube.desktop').read_text()
        self.assertIn('Name=YouTube', text)
        self.assertIn(f'Icon={icon}', text)
        self.assertIn(f'--user-data-dir={self.webapp_profiles / "YouTube"}', text)
        self.assertNotIn('--kiosk', text)

    def test_removed_web_apps_lose_their_menu_entry(self):
        hippos_webapps.save_webapps([WebApp('One', 'https://one.example/'), WebApp('Two', 'https://two.example/')])
        hippos_webapps.sync()
        hippos_webapps.save_webapps([WebApp('Two', 'https://two.example/')])
        hippos_webapps.sync()
        self.assertEqual(self.entries(), ['hippos-webapp-two.desktop'])

    @unittest.skipIf(GLib is None, 'needs PyGObject')
    def test_exec_line_parses_back_to_the_same_arguments(self):
        url = 'https://example.com/a b?q=100%&x="y"$z\\w'
        args = ['chromium', f'--app={url}', '--user-data-dir=/userdata/system/webapps/profiles/My App']
        keyfile = GLib.KeyFile()
        data = f'[Desktop Entry]\nExec={hippos_webapps._exec_line(args)}\n'
        keyfile.load_from_data(data, len(data.encode()), GLib.KeyFileFlags.NONE)
        _, parsed = GLib.shell_parse_argv(keyfile.get_string('Desktop Entry', 'Exec'))
        self.assertEqual([arg.replace('%%', '%') for arg in parsed], args)


class MintImportTests(WebAppsTestCase):
    def mint_entry(self, codename, url, browser='chromium'):
        self.desktop_entries.mkdir(parents=True, exist_ok=True)
        icon = self.base / f'{codename}.png'
        icon.write_bytes(b'png')
        (self.desktop_entries / f'WebApp-{codename}.desktop').write_text(
            '[Desktop Entry]\nName=Mint App\nComment=From Mint\n'
            f'Icon={icon}\nX-WebApp-Browser={browser}\nX-WebApp-URL={url}\nStartupWMClass=WebApp-{codename}\n')
        profile = self.mint_profiles / codename
        profile.mkdir(parents=True)
        (profile / 'Cookies').write_text('signed in')

    def test_chromium_web_apps_move_over_with_their_sign_in(self):
        self.mint_entry('mint1234', 'https://mail.example/')
        self.assertEqual(hippos_webapps.import_mint_webapps(), 1)
        app, = hippos_webapps.load_webapps()
        self.assertEqual((app.name, app.url, app.description), ('Mint App', 'https://mail.example/', 'From Mint'))
        self.assertTrue(Path(app.icon).is_file())
        self.assertEqual((self.webapp_profiles / 'Mint App' / 'Cookies').read_text(), 'signed in')
        self.assertEqual(self.entries(), ['hippos-webapp-mint-app.desktop'])

    def test_other_browsers_keep_their_profile_and_known_urls_are_not_duplicated(self):
        hippos_webapps.save_webapps([WebApp('Mail', 'https://mail.example/')])
        self.mint_entry('mint5678', 'https://mail.example/', browser='firefox')
        self.assertEqual(hippos_webapps.import_mint_webapps(), 1)
        self.assertEqual([app.name for app in hippos_webapps.load_webapps()], ['Mail'])
        self.assertTrue((self.mint_profiles / 'mint5678' / 'Cookies').exists())
        self.assertFalse((self.desktop_entries / 'WebApp-mint5678.desktop').exists())


if __name__ == '__main__':
    unittest.main()
