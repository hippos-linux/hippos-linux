import json
import os
import signal
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared  # noqa: E402
import hippos_hotkeys_control as control  # noqa: E402


class HotkeysControlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, path in (('CONTEXT_FILE', root / 'hotkeys.context'), ('PID_FILE', root / 'hotkeys.pid'),
                           ('KEYBOARD_SHOWN_FILE', root / 'keyboard.shown')):
            patcher = mock.patch.object(control, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        control.PID_FILE.write_text('4242')
        kill = mock.patch.object(control.os, 'kill')
        self.kill = kill.start()
        self.addCleanup(kill.stop)

    def test_new_context_writes_the_context_and_signals_the_daemon(self):
        control.new_context('retroarch', {'exit': ['hotkey', 'start']}, disable_common=True)
        self.assertEqual(json.loads(control.CONTEXT_FILE.read_text()),
                         {'name': 'retroarch', 'keys': {'exit': ['hotkey', 'start']}, 'common_disabled': True})
        self.kill.assert_called_once_with(4242, signal.SIGHUP)

    def test_default_context_removes_the_context(self):
        control.new_context('retroarch', {})
        control.default_context()
        self.assertFalse(control.CONTEXT_FILE.exists())
        self.assertEqual(self.kill.call_count, 2)

    def test_no_daemon_is_not_an_error(self):
        control.PID_FILE.unlink()
        control.reload()
        self.kill.assert_not_called()

    def test_keyboard_shown_uses_sigusr1(self):
        control.set_keyboard_shown(True)
        self.assertTrue(control.KEYBOARD_SHOWN_FILE.exists())
        self.kill.assert_called_once_with(4242, signal.SIGUSR1)

    def test_a_new_context_forgets_a_keyboard_left_shown(self):
        control.set_keyboard_shown(True)
        control.new_context('desktop', {})
        self.assertFalse(control.KEYBOARD_SHOWN_FILE.exists())
        control.set_keyboard_shown(True)
        control.default_context()
        self.assertFalse(control.KEYBOARD_SHOWN_FILE.exists())



class PressKeysTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(control, 'KEYS_SOCKET', Path(tmp.name) / 'hotkeys.sock')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_keys_reach_the_daemon_socket_in_one_message(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as daemon:
            daemon.bind(str(control.KEYS_SOCKET))
            self.assertTrue(control.press_keys(['KEY_LEFTALT', 'KEY_F4']))
            self.assertEqual(daemon.recv(256), b'KEY_LEFTALT KEY_F4')

    def test_no_daemon_reports_failure(self):
        self.assertFalse(control.press_keys(['KEY_ENTER']))


class KeyCodesTests(unittest.TestCase):
    def test_key_names_become_codes(self):
        import hippos_hotkeys_daemon as daemon
        from evdev import ecodes
        self.assertEqual(daemon.key_codes(['KEY_LEFTCTRL', 'KEY_Q']), [ecodes.KEY_LEFTCTRL, ecodes.KEY_Q])

    def test_daemon_presses_requested_keys_on_its_own_device(self):
        import hippos_hotkeys_daemon as daemon
        from evdev import ecodes
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        hotkeys = daemon.HotkeyDaemon.__new__(daemon.HotkeyDaemon)
        hotkeys.keys_socket, hotkeys.uinput = server, mock.Mock()
        client.send(b'KEY_LEFTALT KEY_F4')
        with mock.patch.object(daemon, 'send_key_combo') as combo, mock.patch.object(daemon, 'log'):
            hotkeys._press_requested_keys()
        combo.assert_called_once_with(hotkeys.uinput, [ecodes.KEY_LEFTALT, ecodes.KEY_F4])

    def test_unknown_or_non_key_names_are_refused(self):
        import hippos_hotkeys_daemon as daemon
        self.assertIsNone(daemon.key_codes([]))
        self.assertIsNone(daemon.key_codes(['KEY_LEFTALT', 'KEY_NOPE']))
        self.assertIsNone(daemon.key_codes(['BTN_LEFT']))


class LauncherDefaultsCacheTests(unittest.TestCase):
    def test_defaults_are_parsed_once_until_the_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            defaults = Path(tmp) / 'defaults.json'
            defaults.write_text('{"snes": {"emulator": "libretro"}}')
            with mock.patch.object(shared, 'DEFAULTS_FILE', defaults), \
                    mock.patch.object(shared.json, 'loads', wraps=shared.json.loads) as loads:
                self.assertEqual(shared._load_launcher_defaults()['snes']['emulator'], 'libretro')
                shared._load_launcher_defaults()
                self.assertEqual(loads.call_count, 1)
                defaults.write_text('{"snes": {"emulator": "snes9x"}}')
                os.utime(defaults, ns=(1, 1))
                self.assertEqual(shared._load_launcher_defaults()['snes']['emulator'], 'snes9x')


if __name__ == '__main__':
    unittest.main()
