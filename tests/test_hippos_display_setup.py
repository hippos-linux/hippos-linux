import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos/hippos-display-setup'
HOTPLUG = SCRIPT.with_name('hippos-display-hotplug')

PANEL_EDID = '00ffffffffffff004c839c4100000000' * 8
TV_EDID = '00ffffffffffff0010ac000000000000' * 8

NVIDIA_PANEL_AND_TV = (
    'Screen 0: minimum 8 x 8, current 4800 x 1800, maximum 32767 x 32767\n'
    'HDMI-0 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm\n'
    '   1920x1080     60.00*+\n'
    'DP-2 connected 2880x1800+1920+0 (normal left inverted right x axis y axis) 302mm x 189mm\n'
    '   2880x1800    120.00*+\n'
)
NVIDIA_PANEL_OFF_AND_TV = (
    'HDMI-0 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm\n'
    '   1920x1080     60.00*+\n'
    'DP-2 connected (normal left inverted right x axis y axis)\n'
    '   2880x1800    120.00 +\n'
)
NVIDIA_PANEL_FIRST = (
    'DP-2 connected primary 2880x1800+0+0 (normal left inverted right x axis y axis) 302mm x 189mm\n'
    '   2880x1800    120.00*+\n'
    'DP-4 connected 1920x1080+2880+0 (normal left inverted right x axis y axis) 1600mm x 900mm\n'
    '   1920x1080     60.00*+\n'
)
DESKTOP_DUAL = (
    'DP-1 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 600mm x 340mm\n'
    '   2560x1440     60.00*+\n'
    'HDMI-1 connected 1920x1080+2560+0 (normal left inverted right x axis y axis) 530mm x 300mm\n'
    '   1920x1080     60.00*+\n'
)


def edid_prop(edid: str) -> str:
    return '\tEDID: \n' + ''.join(f'\t\t{edid[i:i + 32]}\n' for i in range(0, len(edid), 32))


def run_setup(xrandr_query: str, *, lid_closed: bool, prop: str = '', panel_edid: str = '',
              settings: dict[str, str] | None = None, extra_edids: tuple[str, ...] = ()) -> tuple[list[str], str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        calls = root / 'calls'
        (root / 'query').write_text(xrandr_query)
        (root / 'prop').write_text(prop)
        drm = root / 'drm'
        if panel_edid:
            (drm / 'card1-eDP-2').mkdir(parents=True)
            (drm / 'card1-eDP-2' / 'edid').write_bytes(bytes.fromhex(panel_edid))
        for n, edid in enumerate(extra_edids):
            (drm / f'card0-eDP-{n + 1}').mkdir(parents=True)
            (drm / f'card0-eDP-{n + 1}' / 'edid').write_bytes(bytes.fromhex(edid))
        conf = ''.join(f'{key}) echo {value} ;;\n' for key, value in (settings or {}).items())
        tools = {
            'xrandr': f'[ $# -eq 0 ] && exec cat {root}/query\n[ "$1" = --prop ] && exec cat {root}/prop\n'
                      f'echo "$*" >> {calls}\n',
            'busctl': f'echo "b {"true" if lid_closed else "false"}"\n',
            'hippos-settings': f'[ "$1" = get ] || exit 1\ncase "$2" in\n{conf}*) exit 1 ;;\nesac\n',
            'hippos-resolution': 'exit 0\n',
            'xinput': 'exit 0\n',
        }
        for name, body in tools.items():
            (bin_dir / name).write_text('#!/bin/sh\n' + body)
            (bin_dir / name).chmod(0o755)
        env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'DRM_SYSFS': str(drm)}
        out = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, check=True).stdout
        return out.splitlines(), calls.read_text() if calls.exists() else ''


class LidTests(unittest.TestCase):
    def test_nvidia_panel_found_by_edid_and_turned_off_when_lid_closed(self):
        _, calls = run_setup(NVIDIA_PANEL_AND_TV, lid_closed=True, panel_edid=PANEL_EDID,
                             prop=f'HDMI-0 connected primary\n{edid_prop(TV_EDID)}DP-2 connected\n{edid_prop(PANEL_EDID)}')
        self.assertIn('--output HDMI-0 --preferred --rotate normal --primary\n', calls)
        self.assertIn('--output DP-2 --off\n', calls)

    def test_es_moves_off_the_panel_when_lid_closed(self):
        lines, calls = run_setup(NVIDIA_PANEL_FIRST, lid_closed=True, panel_edid=PANEL_EDID,
                                 prop=f'DP-2 connected primary\n{edid_prop(PANEL_EDID)}DP-4 connected\n{edid_prop(TV_EDID)}')
        self.assertIn('[hippos-display-setup] lid closed, using DP-4 instead of DP-2', lines)
        self.assertLess(calls.index('--output DP-4 --preferred'), calls.index('--output DP-2 --off'))

    def test_configured_panel_is_overridden_only_while_lid_closed(self):
        _, closed = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 connected 1920x1080+1920+0 (normal)\n',
                              lid_closed=True, settings={'display.output': 'eDP-1'})
        self.assertIn('--output HDMI-1 --preferred', closed)
        self.assertIn('--output eDP-1 --off', closed)
        _, opened = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 connected 1920x1080+1920+0 (normal)\n',
                              lid_closed=False, settings={'display.output': 'eDP-1'})
        self.assertIn('--output eDP-1 --preferred', opened)
        self.assertNotIn('--off', opened)

    def test_panel_comes_back_when_lid_opens(self):
        lines, calls = run_setup(NVIDIA_PANEL_OFF_AND_TV, lid_closed=False, panel_edid=PANEL_EDID,
                                 prop=f'HDMI-0 connected primary\n{edid_prop(TV_EDID)}DP-2 connected\n{edid_prop(PANEL_EDID)}')
        self.assertIn('--output DP-2 --preferred --right-of HDMI-0\n', calls)
        self.assertIn('[hippos-display-setup] lid open, DP-2 back on', lines)

    def test_lid_closed_without_external_screen_keeps_panel(self):
        _, calls = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\n', lid_closed=True)
        self.assertNotIn('--off', calls)

    def test_desktop_session_keeps_panel_with_lid_closed(self):
        _, calls = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 connected 1920x1080+1920+0 (normal)\n',
                             lid_closed=True, settings={'system.session': 'desktop'})
        self.assertNotIn('--off', calls)

    def test_crt_mode_keeps_panel(self):
        _, calls = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\nVGA-1 connected 640x480+1920+0 (normal)\n',
                             lid_closed=True, settings={'crt.enabled': 'true'})
        self.assertNotIn('--off', calls)

    def test_configured_output_not_connected_falls_back(self):
        lines, calls = run_setup('eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 connected 1920x1080+1920+0 (normal)\n',
                                 lid_closed=True, settings={'display.output': 'DP-3'})
        self.assertIn("[hippos-display-setup] configured output 'DP-3' not connected, using the first connected output", lines)
        self.assertIn('--output HDMI-1 --preferred', calls)
        self.assertIn('--output eDP-1 --off', calls)

    def test_panel_edid_found_after_a_non_matching_connector(self):
        _, calls = run_setup(NVIDIA_PANEL_AND_TV, lid_closed=True, panel_edid=PANEL_EDID,
                             extra_edids=('00ffffffffffff00aaaa000000000000' * 8,),
                             prop=f'HDMI-0 connected primary\n{edid_prop(TV_EDID)}DP-2 connected\n{edid_prop(PANEL_EDID)}')
        self.assertIn('--output DP-2 --off\n', calls)

    def test_desktop_dual_monitor_untouched(self):
        _, calls = run_setup(DESKTOP_DUAL, lid_closed=True)
        self.assertNotIn('--off', calls)
        self.assertNotIn('HDMI-1', calls)


def run_hotplug(before: str, after: str, *, running_game: bool, session: str = 'es') -> tuple[list[str], bool]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        (root / 'before').write_text(before)
        (root / 'after').write_text(after)
        restarted = root / 'restarted'
        tools = {
            'xrandr': f'if [ -e {root}/seen ]; then cat {root}/after; else touch {root}/seen; cat {root}/before; fi\n',
            'sleep': 'exit 0\n',
            'hippos-settings': f'[ "$2" = system.session ] && echo {session}\n',
            'curl': f'printf {200 if running_game else 201}\n',
            'hippos': f'echo "$*" > {restarted}\n',
        }
        for name, body in tools.items():
            (bin_dir / name).write_text('#!/bin/sh\n' + body)
            (bin_dir / name).chmod(0o755)
        env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
        out = subprocess.run(['bash', str(HOTPLUG)], env=env, capture_output=True, text=True).stdout
        return out.splitlines(), restarted.exists() and restarted.read_text() == 'restart session\n'


PANEL_ES = 'eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 connected 1920x1080+1920+0 (normal)\n'
PANEL_OFF = 'eDP-1 connected (normal)\nHDMI-1 connected primary 1920x1080+0+0 (normal)\n'
TV_ES_UNPLUGGED = 'eDP-1 connected 1920x1080+1920+0 (normal)\nHDMI-1 disconnected primary 1920x1080+0+0 (normal)\n'
TV_GONE = 'eDP-1 connected primary 1920x1080+0+0 (normal)\nHDMI-1 disconnected (normal)\n'


@unittest.skipUnless(Path('/tmp/.X11-unix/X0').is_socket(), 'hippos-display-hotplug needs an X socket')
class HotplugTests(unittest.TestCase):
    def test_es_restarts_when_its_screen_is_turned_off(self):
        _, restarted = run_hotplug(PANEL_ES, PANEL_OFF, running_game=False)
        self.assertTrue(restarted)

    def test_es_restarts_when_its_screen_is_unplugged(self):
        _, restarted = run_hotplug(TV_ES_UNPLUGGED, TV_GONE, running_game=False)
        self.assertTrue(restarted)

    def test_running_game_is_left_alone(self):
        lines, restarted = run_hotplug(PANEL_ES, PANEL_OFF, running_game=True)
        self.assertFalse(restarted)
        self.assertIn('[hippos-display-hotplug] eDP-1 is off but a game is running, leaving EmulationStation where it is', lines)

    def test_screen_still_on_no_restart(self):
        _, restarted = run_hotplug(PANEL_ES, PANEL_ES, running_game=False)
        self.assertFalse(restarted)


if __name__ == '__main__':
    unittest.main()
