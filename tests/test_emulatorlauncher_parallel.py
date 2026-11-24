import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_impl as impl
import emulatorlauncher_power as power
from emulatorlauncher_parallel import Parallel
from emulatorlauncher_shared import NetplaySession


def _blocking_step(events, name, seconds=0.0, fail=False):
    @contextmanager
    def step():
        time.sleep(seconds)
        if fail:
            raise RuntimeError(f'{name} failed')
        events.append(f'enter {name}')
        try:
            yield name
        finally:
            events.append(f'exit {name}')
    return step()


class HelperTests(unittest.TestCase):
    def test_steps_run_at_the_same_time(self):
        events = []

        started = time.perf_counter()
        with Parallel(_blocking_step(events, 'a', 0.2), _blocking_step(events, 'b', 0.2)) as values:
            elapsed = time.perf_counter() - started
        self.assertEqual(values, ['a', 'b'])
        self.assertLess(elapsed, 0.35)
        self.assertEqual(sorted(events), ['enter a', 'enter b', 'exit a', 'exit b'])

    def test_failed_step_undoes_the_others(self):
        events = []

        with self.assertRaisesRegex(RuntimeError, 'b failed'):
            with Parallel(_blocking_step(events, 'a'), _blocking_step(events, 'b', fail=True)):
                events.append('body')
        self.assertEqual(events, ['enter a', 'exit a'])

    def test_cleanup_runs_when_the_body_raises(self):
        events = []

        with self.assertRaises(ValueError):
            with Parallel(_blocking_step(events, 'a')):
                raise ValueError('launch failed')
        self.assertEqual(events, ['enter a', 'exit a'])


class PrepareAndRunTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        ev = self.events

        @contextmanager
        def power(conf, system, rom):
            ev.append(f'power uses {rom.name}')
            yield
            ev.append('power restored')

        @contextmanager
        def squashfs(rom):
            ev.append('mounted')
            yield Path('/run/mnt') / rom.stem
            ev.append('unmounted')

        def bezel(ctx, conf):
            ev.append(f'bezel uses {ctx.rom.name} at {ctx.resolution}')

        patches = {
            '_switch_video_mode': lambda conf, system: ('HDMI-1', '1920x1080', '1280x720'),
            '_restore_video_mode': lambda out, mode, conf: ev.append(f'video restored to {mode}'),
            '_prepare_ctx_bezel': bezel,
            '_build_hud_config': lambda conf, ctx: None,
            '_load_es_input_configs': lambda: [],
            'start_controller_monitor': lambda ctx, profiles: None,
            'game_power_settings': power,
            'mount_squashfs': squashfs,
            '_start_save_sync': lambda: ev.append('save sync'),
        }
        for name, value in patches.items():
            patcher = mock.patch.object(impl, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ctx = SimpleNamespace(system='ports', rom=Path('/userdata/roms/ports/game.squashfs'), resolution=None,
                                   netplay=NetplaySession())

    def run_with(self, launch):
        emulator = SimpleNamespace(launch=launch, writes_to_rom=False)
        with self.assertLogs(level='INFO'):
            return impl._prepare_and_run(self.ctx, {}, emulator)

    def test_launch_gets_the_mounted_rom_and_teardown_runs_last(self):
        def launch(ctx):
            self.events.append(f'launch {ctx.rom}')
            return 0

        self.assertEqual(self.run_with(launch), 0)
        self.assertIn('power uses game.squashfs', self.events)
        self.assertIn('bezel uses game.squashfs at (1280, 720)', self.events)
        launched = self.events.index('launch /run/mnt/game')
        for teardown in ('video restored to 1920x1080', 'power restored', 'unmounted'):
            self.assertGreater(self.events.index(teardown), launched)
        self.assertEqual(self.events[-1], 'save sync')

    def test_teardown_runs_when_the_launch_raises(self):
        def launch(ctx):
            raise RuntimeError('emulator config broken')

        with self.assertRaisesRegex(RuntimeError, 'emulator config broken'):
            self.run_with(launch)
        for teardown in ('video restored to 1920x1080', 'power restored', 'unmounted', 'save sync'):
            self.assertIn(teardown, self.events)


class SwitchVideoModeTests(unittest.TestCase):
    def run_switch(self, conf):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(stdout='DSI-1\n640x480\n640x480\n')

        with mock.patch.object(impl, '_HAS_SWITCHRES', False), mock.patch.object(impl.subprocess, 'run', run):
            return impl._switch_video_mode(conf, 'gbc'), calls

    def test_one_call_returns_output_original_mode_and_resolution(self):
        state, calls = self.run_switch({})
        self.assertEqual(state, ('DSI-1', '640x480', '640x480'))
        self.assertEqual(calls, [['hippos-resolution', 'gameMode', '']])

    def test_system_videomode_is_passed_to_game_mode(self):
        with self.assertLogs(level='INFO'):
            _, calls = self.run_switch({'gbc.videomode': '1280x720.60'})
        self.assertEqual(calls, [['hippos-resolution', 'gameMode', '1280x720.60']])


class PowerSettingsTests(unittest.TestCase):
    def test_power_mode_runs_in_the_background_and_finishes_before_teardown(self):
        finished = []

        def slow_tool(*args):
            time.sleep(0.3)
            finished.append(args)
            return SimpleNamespace(returncode=0)

        with mock.patch.object(power, '_run_tool', slow_tool):
            started = time.perf_counter()
            with power.game_power_settings({}, 'gbc', Path('/userdata/roms/gbc/game.gbc')):
                self.assertLess(time.perf_counter() - started, 0.2)
            self.assertEqual(finished, [(power._POWER_MODE_TOOL, 'default')])

    def test_game_power_mode_default_applies_and_restores_after_the_game(self):
        calls = []

        def tool(*args):
            calls.append(args)
            return SimpleNamespace(returncode=0)

        with mock.patch.object(power, '_run_tool', tool):
            with power.game_power_settings({'global.game_powermode': 'highperformance'}, 'gbc',
                                           Path('/userdata/roms/gbc/game.gbc')):
                pass
        self.assertEqual(calls, [(power._POWER_MODE_TOOL, 'highperformance'), (power._POWER_MODE_TOOL, 'default')])

    def test_power_mode_finishes_before_the_tdp_tool_runs(self):
        order = []

        def tool(*args):
            if args[0] == power._POWER_MODE_TOOL:
                time.sleep(0.2)
            order.append(args[:2])
            return SimpleNamespace(returncode=0)

        with mock.patch.object(power, '_run_tool', tool), mock.patch.object(power, '_run_detached'):
            with power.game_power_settings({'gbc.tdp': '15'}, 'gbc', Path('/userdata/roms/gbc/game.gbc')):
                pass
        self.assertEqual(order[:2], [(power._POWER_MODE_TOOL, 'default'), (power._TDP_TOOL, 'save')])


if __name__ == '__main__':
    unittest.main()
