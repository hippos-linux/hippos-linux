import asyncio
import sys
import time
import unittest
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_impl as impl
from emulatorlauncher_async import Parallel, in_thread


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
    return in_thread(step())


class HelperTests(unittest.TestCase):
    def test_steps_run_at_the_same_time(self):
        events = []

        async def run():
            started = time.perf_counter()
            async with Parallel(_blocking_step(events, 'a', 0.2), _blocking_step(events, 'b', 0.2)) as values:
                return values, time.perf_counter() - started

        values, elapsed = asyncio.run(run())
        self.assertEqual(values, ['a', 'b'])
        self.assertLess(elapsed, 0.35)
        self.assertEqual(sorted(events), ['enter a', 'enter b', 'exit a', 'exit b'])

    def test_failed_step_undoes_the_others(self):
        events = []

        async def run():
            async with Parallel(_blocking_step(events, 'a'), _blocking_step(events, 'b', fail=True)):
                events.append('body')

        with self.assertRaisesRegex(RuntimeError, 'b failed'):
            asyncio.run(run())
        self.assertEqual(events, ['enter a', 'exit a'])

    def test_cleanup_runs_when_the_body_raises(self):
        events = []

        async def run():
            async with _blocking_step(events, 'a'):
                raise ValueError('launch failed')

        with self.assertRaises(ValueError):
            asyncio.run(run())
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
            '_switch_video_mode': lambda conf, system: ('HDMI-1', '1920x1080'),
            '_restore_video_mode': lambda out, mode, conf: ev.append(f'video restored to {mode}'),
            '_prepare_ctx_bezel': bezel,
            '_build_hud_config': lambda conf, ctx: None,
            '_load_es_input_configs': lambda: [],
            'start_controller_monitor': lambda ctx, profiles: None,
            'game_power_settings': power,
            'mount_squashfs': squashfs,
            '_start_save_sync': lambda: ev.append('save sync'),
            'subprocess': SimpleNamespace(run=lambda *a, **k: SimpleNamespace(stdout='1280x720\n')),
        }
        for name, value in patches.items():
            patcher = mock.patch.object(impl, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ctx = SimpleNamespace(system='ports', rom=Path('/userdata/roms/ports/game.squashfs'), resolution=None)

    def run_with(self, launch):
        emulator = SimpleNamespace(launch=launch, writes_to_rom=False)
        with self.assertLogs(level='INFO'):
            return asyncio.run(impl._prepare_and_run(self.ctx, {}, emulator))

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


if __name__ == '__main__':
    unittest.main()
