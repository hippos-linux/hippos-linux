import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_generic as generic
import emulatorlauncher_misc as misc
from emulatorlauncher_shared import LaunchContext


class Pico8FallbackTests(unittest.TestCase):
    def test_missing_pico8_uses_retro8(self):
        ctx = LaunchContext(system='pico8', rom=Path('/userdata/roms/pico8/cart.p8'), emulator='lexaloffle-pico8', core='pico8')
        with mock.patch.object(misc, 'BIOS', Path(tempfile.mkdtemp())), \
                mock.patch.object(generic, 'launch_libretro', return_value=0) as libretro:
            self.assertEqual(misc.launch_lexaloffle(ctx), 0)
        used = libretro.call_args.args[0]
        self.assertEqual((used.emulator, used.core, used.rom), ('retroarch', 'retro8', ctx.rom))

    def test_missing_voxatron_still_fails(self):
        ctx = LaunchContext(system='voxatron', rom=Path('/userdata/roms/voxatron/game.vx'), emulator='lexaloffle-voxatron', core='voxatron')
        with mock.patch.object(misc, 'BIOS', Path(tempfile.mkdtemp())), \
                mock.patch.object(generic, 'launch_libretro') as libretro:
            self.assertEqual(misc.launch_lexaloffle(ctx), 1)
        libretro.assert_not_called()


if __name__ == '__main__':
    unittest.main()
