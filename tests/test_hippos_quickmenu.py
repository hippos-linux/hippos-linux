import importlib.machinery
import importlib.util
import pwd
import os
import signal
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-quickmenu'
sys.path.insert(0, str(SCRIPT_PATH.parent))
DEFAULT_MENU = ROOT / 'overlays' / 'rootfs' / 'usr' / 'share' / 'hippos' / 'quickmenu' / 'quickmenu.xml'

import hippos_session_app as session_app  # noqa: E402


def _load_hippos_quickmenu():
    loader = importlib.machinery.SourceFileLoader('hippos_quickmenu', str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


qm = _load_hippos_quickmenu()

SESSION_USER = pwd.struct_passwd(('hippos', 'x', 1000, 100, '', '/userdata', '/bin/bash'))


class DefaultMenuTests(unittest.TestCase):
    def test_tabs_are_listed_in_order(self):
        root = ET.parse(DEFAULT_MENU).getroot()
        tabs = [tab.get('target') for tab in root.iter('tab')]
        self.assertEqual(tabs, ['Game', 'Keys', 'Gun', 'System', 'Outputs', 'Record'])


class SessionEnvTests(unittest.TestCase):
    def env(self, session_type: str, inherited: dict[str, str], published: dict[str, str]) -> dict[str, str]:
        with mock.patch.object(session_app.pwd, 'getpwnam', return_value=SESSION_USER), \
                mock.patch.object(session_app, 'session_type', return_value=session_type), \
                mock.patch.object(session_app, 'published_env', return_value=published), \
                mock.patch.dict(session_app.os.environ, inherited, clear=True):
            return session_app.session_env()

    def test_x11_session_drops_a_stray_wayland_socket(self):
        env = self.env('x11', {'HOME': '/root', 'WAYLAND_DISPLAY': 'waydroid-0'}, {})
        self.assertNotIn('WAYLAND_DISPLAY', env)
        self.assertEqual(env['HOME'], '/userdata')
        self.assertEqual(env['DISPLAY'], ':0')

    def test_wayland_session_uses_the_published_socket(self):
        env = self.env('wayland', {'HOME': '/root'}, {'WAYLAND_DISPLAY': 'wayland-1'})
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-1')

    def test_wayland_socket_from_the_caller_wins(self):
        env = self.env('wayland', {'WAYLAND_DISPLAY': 'wayland-0'}, {'WAYLAND_DISPLAY': 'wayland-1'})
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-0')


class ControlCenterPidTests(unittest.TestCase):
    def test_finds_the_control_center_by_its_arguments(self):
        with tempfile.TemporaryDirectory() as proc:
            for pid, args in (('100', [b'/usr/bin/emulationstation']),
                              ('200', [b'emulationstation', b'--controlcenter']),
                              ('self', [b'python3'])):
                Path(proc, pid).mkdir()
                Path(proc, pid, 'cmdline').write_bytes(b'\0'.join(args) + b'\0')
            user = pwd.struct_passwd(('hippos', 'x', os.getuid(), 100, '', '/userdata', '/bin/bash'))
            with mock.patch.object(qm, 'PROC', Path(proc)), mock.patch.object(qm.pwd, 'getpwnam', return_value=user):
                self.assertEqual(qm.control_center_pid(), 200)


class ToggleTests(unittest.TestCase):
    def setUp(self):
        patches = {
            'urlopen': mock.patch.object(qm.urllib.request, 'urlopen', side_effect=urllib.error.URLError('down')),
            'pid': mock.patch.object(qm, 'control_center_pid', return_value=None),
            'kill': mock.patch.object(qm.os, 'kill'),
            'popen': mock.patch.object(qm.subprocess, 'Popen'),
            'env': mock.patch.object(qm, 'session_env', return_value={'HOME': '/userdata', 'DISPLAY': ':0'}),
            'euid': mock.patch.object(qm.os, 'geteuid', return_value=0),
        }
        self.mocks = {name: patch.start() for name, patch in patches.items()}
        self.addCleanup(mock.patch.stopall)

    def test_es_in_front_shows_it_in_process(self):
        self.mocks['urlopen'].side_effect = None
        qm.toggle()
        self.mocks['kill'].assert_not_called()
        self.mocks['popen'].assert_not_called()

    def test_running_control_center_is_signalled(self):
        self.mocks['pid'].return_value = 4321
        qm.toggle()
        self.mocks['kill'].assert_called_once_with(4321, signal.SIGUSR1)
        self.mocks['popen'].assert_not_called()

    def test_starts_as_the_session_user_on_x11(self):
        qm.toggle()
        command = self.mocks['popen'].call_args.args[0]
        kwargs = self.mocks['popen'].call_args.kwargs
        self.assertEqual(command, ['runuser', '-u', 'hippos', '--', 'emulationstation', '--controlcenter'])
        self.assertEqual(kwargs['cwd'], '/userdata')
        self.assertNotIn('SDL_VIDEODRIVER', kwargs['env'])

    def test_starts_on_native_wayland_in_a_wayland_session(self):
        self.mocks['env'].return_value = {'HOME': '/userdata', 'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}
        qm.toggle()
        self.assertEqual(self.mocks['popen'].call_args.kwargs['env']['SDL_VIDEODRIVER'], 'wayland')


if __name__ == '__main__':
    unittest.main()
