import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared


class GameMonitorPrimaryTests(unittest.TestCase):
    def run_game(self, monitor: int, outputs: dict[str, str]) -> list[list[str]]:
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[1] == 'outputForMonitor':
                return SimpleNamespace(stdout=outputs.get(cmd[2], '') + '\n')
            if cmd[1] == 'primaryOutput':
                return SimpleNamespace(stdout='eDP-1\n')
            return SimpleNamespace(stdout='')

        with mock.patch.object(shared.subprocess, 'run', run):
            with shared.game_monitor_primary(SimpleNamespace(monitor=monitor)):
                calls.append(['game'])
        return calls

    def test_game_on_another_monitor_moves_primary_and_restores_it(self):
        self.assertEqual(self.run_game(1, {'1': 'HDMI-1'}), [
            ['hippos-resolution', 'outputForMonitor', '1'],
            ['hippos-resolution', 'primaryOutput'],
            ['hippos-resolution', 'applyPrimaryOutput', 'HDMI-1'],
            ['game'],
            ['hippos-resolution', 'applyPrimaryOutput', 'eDP-1'],
        ])

    def test_game_on_the_primary_monitor_changes_nothing(self):
        calls = self.run_game(0, {'0': 'eDP-1'})
        self.assertNotIn('applyPrimaryOutput', [c[1] for c in calls if len(c) > 1])

    def test_no_monitor_chosen_runs_no_display_commands(self):
        self.assertEqual(self.run_game(-1, {}), [['game']])

    def test_unknown_monitor_changes_nothing(self):
        self.assertEqual(self.run_game(3, {}), [['hippos-resolution', 'outputForMonitor', '3'], ['game']])


if __name__ == '__main__':
    unittest.main()
