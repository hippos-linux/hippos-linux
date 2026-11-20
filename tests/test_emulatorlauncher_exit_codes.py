import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_impl as impl
import emulatorlauncher_shared as shared


class ExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.error_file = Path(tempfile.mkdtemp()) / 'launch_error.log'
        self.patches = [
            mock.patch.object(impl, 'LAUNCH_ERROR_FILE', self.error_file),
            mock.patch.object(impl, '_build_parser', return_value=SimpleNamespace(parse_args=lambda: None)),
            mock.patch.object(impl, 'launch_clock', shared.LaunchClock()),
        ]
        for patch in self.patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in self.patches])

    def run_main(self, launch):
        with mock.patch.object(impl, '_launch', launch), self.assertLogs(level=logging.INFO):
            return impl.main()

    def test_unknown_emulator_keeps_its_es_code(self):
        self.assertEqual(self.run_main(lambda args: impl.EXIT_UNKNOWN_EMULATOR), 203)
        self.assertFalse(self.error_file.exists())

    def test_failure_before_the_game_shows_the_last_error(self):
        def launch(args):
            impl._log.error("cemu: binary not found")
            return 1
        self.assertEqual(self.run_main(launch), impl.EXIT_LAUNCH_FAILED)
        self.assertEqual(self.error_file.read_text(), "cemu: binary not found")

    def test_game_exit_code_passes_through(self):
        def launch(args):
            impl.launch_clock.game_started = time.perf_counter()
            impl.launch_clock.game_ended = time.perf_counter()
            impl._log.error("emulator printed an error")
            return 1
        self.assertEqual(self.run_main(launch), 1)
        self.assertFalse(self.error_file.exists())

    def test_game_closed_by_term_or_kill_is_a_normal_exit(self):
        for code in (-15, -9):
            def launch(args, code=code):
                impl.launch_clock.game_started = time.perf_counter()
                impl.launch_clock.game_ended = time.perf_counter()
                return code
            self.assertEqual(self.run_main(launch), 0)

    def test_game_crash_by_signal_is_still_reported(self):
        def launch(args):
            impl.launch_clock.game_started = time.perf_counter()
            impl.launch_clock.game_ended = time.perf_counter()
            return -11
        self.assertEqual(self.run_main(launch), -11)

    def test_unexpected_exception_is_reported(self):
        def launch(args):
            raise RuntimeError("bad config value")
        self.assertEqual(self.run_main(launch), impl.EXIT_LAUNCH_FAILED)
        self.assertEqual(self.error_file.read_text(), "Launch failed: bad config value")

    def test_missing_emulator_binary_names_the_package(self):
        def launch(args):
            with mock.patch.object(shared, '_find_emulator_bin', return_value=None):
                shared._require_emulator_bin('catacombgl', 'CatacombGL')
        self.assertEqual(self.run_main(launch), impl.EXIT_LAUNCH_FAILED)
        self.assertEqual(
            self.error_file.read_text(),
            f"Emulator 'catacombgl' not installed. Expected binary in {shared.EMULATORS_ROOT}/catacombgl or system PATH",
        )


if __name__ == '__main__':
    unittest.main()
