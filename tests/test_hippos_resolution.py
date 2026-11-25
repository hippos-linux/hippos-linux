import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos/hippos-resolution'


def run_resolution(xrandr_query: str, *args: str) -> tuple[list[str], str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp)
        calls = bin_dir / 'calls'
        settings = bin_dir / 'settings'
        (bin_dir / 'query').write_text(xrandr_query)
        (bin_dir / 'xrandr').write_text(
            f'#!/bin/sh\n[ "$1" = --query ] && exec cat {bin_dir}/query\necho "$*" >> {calls}\n')
        (bin_dir / 'hippos-settings').write_text(
            f'#!/bin/sh\n[ "$1" = set ] && echo "$*" >> {settings}\nexit 1\n')
        for tool in ('xrandr', 'hippos-settings'):
            (bin_dir / tool).chmod(0o755)
        env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
        out = subprocess.run(['bash', str(SCRIPT), *args], env=env,
                             capture_output=True, text=True, check=True).stdout
        return (out.splitlines(),
                calls.read_text() if calls.exists() else '',
                settings.read_text() if settings.exists() else '')


class GameModeTests(unittest.TestCase):
    def game_mode(self, xrandr_query: str, *mode: str) -> tuple[list[str], str]:
        lines, calls, _ = run_resolution(xrandr_query, 'gameMode', *mode)
        return lines, calls

    def test_screen_stays_on_its_own_mode(self):
        lines, calls = self.game_mode(
            'DP-2 connected primary 2880x1800+0+0\n'
            '   2880x1800     60.00*+ 120.00\n'
            '   640x480       59.94\n')
        self.assertEqual(calls, '')
        self.assertEqual(lines, ['DP-2', '2880x1800', '2880x1800'])

    def test_4k_screen_stays_4k(self):
        _, calls = self.game_mode(
            'HDMI-1 connected primary 3840x2160+0+0\n'
            '   3840x2160     60.00*+\n'
            '   1920x1080     60.00\n')
        self.assertEqual(calls, '')

    def test_configured_videomode_is_applied(self):
        _, calls = self.game_mode(
            'HDMI-1 connected primary 3840x2160+0+0\n'
            '   3840x2160     60.00*+\n'
            '   1920x1080     60.00\n', '1920x1080.60')
        self.assertEqual(calls, '--output HDMI-1 --mode 1920x1080 --rate 60\n')


TWO_SCREENS = ('eDP-1 connected primary 800x1280+0+0\n'
               '   800x1280      60.00*+\n'
               'HDMI-1 connected 1920x1080+800+0\n'
               '   1920x1080     60.00*+\n')


class OutputTests(unittest.TestCase):
    def test_primary_output_keeps_the_others_on(self):
        _, calls, settings = run_resolution(TWO_SCREENS, 'setPrimaryOutput', 'HDMI-1')
        self.assertEqual(calls, '--output HDMI-1 --primary\n')
        self.assertEqual(settings, 'set display.output HDMI-1\n')

    def test_all_outputs_on_clears_the_saved_output(self):
        _, calls, settings = run_resolution(TWO_SCREENS, 'enableAllOutputs')
        self.assertEqual(calls, '--auto\n')
        self.assertEqual(settings, 'set display.output \n')

    def test_set_output_turns_the_others_off(self):
        _, calls, _ = run_resolution(TWO_SCREENS, 'setOutput', 'HDMI-1')
        self.assertEqual(calls, '--output eDP-1 --off\n--output HDMI-1 --primary --auto\n')


if __name__ == '__main__':
    unittest.main()
