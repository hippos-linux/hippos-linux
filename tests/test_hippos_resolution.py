import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos/hippos-resolution'


class GameModeTests(unittest.TestCase):
    def game_mode(self, xrandr_query: str, *mode: str) -> tuple[list[str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            calls = bin_dir / 'calls'
            (bin_dir / 'query').write_text(xrandr_query)
            (bin_dir / 'xrandr').write_text(
                f'#!/bin/sh\n[ "$1" = --query ] && exec cat {bin_dir}/query\necho "$*" >> {calls}\n')
            (bin_dir / 'hippos-settings').write_text('#!/bin/sh\nexit 1\n')
            for tool in ('xrandr', 'hippos-settings'):
                (bin_dir / tool).chmod(0o755)
            env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
            out = subprocess.run(['bash', str(SCRIPT), 'gameMode', *mode], env=env,
                                 capture_output=True, text=True, check=True).stdout
            return out.splitlines(), calls.read_text() if calls.exists() else ''

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


if __name__ == '__main__':
    unittest.main()
