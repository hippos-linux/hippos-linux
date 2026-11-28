import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_cemu as cemu  # noqa: E402
import emulatorlauncher_core as core  # noqa: E402
import emulatorlauncher_rpcs3 as rpcs3  # noqa: E402
import hippos_es_input  # noqa: E402
from emulatorlauncher_shared import ControllerInfo, ESBinding, ESControllerProfile, ESProfiles, LaunchContext  # noqa: E402

XBOX_GUID = '050000005e0400008e02000030110000'
SDL_NAME = 'Xbox 360 Controller'
EVDEV_NAME = 'Xbox Wireless Controller'
XPADNEO_ABS = '20003003f'


class ControllerDeviceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        sysfs = self.root / 'sys'
        for event in ('event21', 'event30'):
            (sysfs / event / 'device').mkdir(parents=True)
            (sysfs / event / 'device' / 'name').write_text(f'{EVDEV_NAME}\n')
            (sysfs / event / 'device' / 'capabilities').mkdir()
            (sysfs / event / 'device' / 'capabilities' / 'abs').write_text(f'{XPADNEO_ABS}\n')
        patcher = mock.patch.object(hippos_es_input, 'SYS_CLASS_INPUT', sysfs)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pads = [
            ControllerInfo(player=1, index=0, guid=XBOX_GUID, name=SDL_NAME, device_path='/dev/input/event21', nb_axes=7),
            ControllerInfo(player=2, index=1, guid=XBOX_GUID, name=SDL_NAME, device_path='/dev/input/event30', nb_axes=7),
        ]
        profile = ESControllerProfile(device_name=SDL_NAME, device_guid=XBOX_GUID, device_path='',
                                      inputs={'a': ESBinding(name='a', type='button', code=0, value=1),
                                              'up': ESBinding(name='up', type='hat', code=0, value=1),
                                              'left': ESBinding(name='left', type='hat', code=0, value=8),
                                              'joystick1left': ESBinding(name='joystick1left', type='axis', code=0, value=-1),
                                              'joystick2up': ESBinding(name='joystick2up', type='axis', code=4, value=-1)})
        self.profiles = ESProfiles(launch=(profile,), installed_file=None)

    def ctx(self, system):
        return LaunchContext(system=system, rom=Path('game.iso'), emulator='x', core='x', controllers=self.pads)

    def test_evdev_name_reads_kernel_name_and_falls_back_to_es_name(self):
        self.assertEqual(self.pads[0].evdev_name, EVDEV_NAME)
        self.assertEqual(ControllerInfo(player=1, name=SDL_NAME, device_path='/dev/input/event99').evdev_name, SDL_NAME)
        self.assertEqual(ControllerInfo(player=1, name=SDL_NAME).evdev_name, SDL_NAME)

    def test_dolphin_devices_use_kernel_name(self):
        with mock.patch.object(core, 'DOLPHIN_CONFIG_DIR', self.root):
            core._write_dolphin_controller_configs(self.ctx('gamecube'), self.profiles)
            core._write_dolphin_wii_controller_configs(self.ctx('wii'), self.profiles)
        for ini in ('GCPadNew.ini', 'WiimoteNew.ini'):
            text = (self.root / ini).read_text()
            self.assertIn(f'Device = evdev/0/{EVDEV_NAME}\n', text)
            self.assertIn(f'Device = evdev/1/{EVDEV_NAME}\n', text)

    def test_dolphin_axes_follow_evdev_codes_not_sdl_axis_count(self):
        pad = self.pads[0]
        self.assertEqual(pad.evdev_abs_codes, (0, 1, 2, 3, 4, 5, 0x10, 0x11, 0x21))
        with mock.patch.object(core, 'DOLPHIN_CONFIG_DIR', self.root):
            core._write_dolphin_controller_configs(self.ctx('gamecube'), self.profiles)
        text = (self.root / 'GCPadNew.ini').read_text()
        self.assertIn('D-Pad/Up = `Axis 7-`\n', text)
        self.assertIn('D-Pad/Left = `Axis 6-`\n', text)
        self.assertIn('Main Stick/Left = `Axis 0-`\n', text)
        self.assertIn('C-Stick/Up = `Axis 4-`\n', text)

    def test_dolphin_axes_fall_back_without_sysfs(self):
        pad = ControllerInfo(player=1, name=SDL_NAME, nb_axes=6)
        hat = ESBinding(name='up', type='hat', code=0, value=1)
        self.assertEqual(core._es_binding_to_dolphin(hat, 'D-Pad/Up', pad, None), '`Axis 7-`')

    def test_cemu_profiles_use_sdl_uuid_schema(self):
        with mock.patch.object(cemu, 'CEMU_CONTROLLER_PROFILES', self.root):
            cemu._write_cemu_controller_profiles(self.ctx('wiiu'))
        for idx, controller_type in enumerate(('Wii U GamePad', 'Wii U Pro Controller')):
            root = ET.parse(self.root / f'controller{idx}.xml').getroot()
            self.assertEqual(root.tag, 'emulated_controller')
            self.assertEqual(root.findtext('type'), controller_type)
            self.assertEqual(root.findtext('controller/api'), 'SDLController')
            self.assertEqual(root.findtext('controller/uuid'), f'{idx}_{XBOX_GUID}')
            self.assertIsNotNone(root.find('controller/mappings/entry'))

    def write_rpcs3(self, conf):
        with mock.patch.object(rpcs3, '_RPCS3_INPUT_DIR', self.root), \
             mock.patch.object(rpcs3, '_load_hippos_conf', return_value=conf), \
             mock.patch.object(rpcs3, '_load_es_input_configs', return_value=self.profiles):
            rpcs3._write_rpcs3_controller_config(self.ctx('ps3'))
        return (self.root / 'Default.yml').read_text(encoding='utf-8-sig')

    def test_rpcs3_defaults_to_sdl_handler(self):
        text = self.write_rpcs3({})
        self.assertIn(f'  Handler: SDL\n  Device: "{SDL_NAME} 1"\n', text)
        self.assertIn(f'  Device: "{SDL_NAME} 2"\n', text)
        self.assertNotIn('Evdev', text)
        self.assertIn('    Large Vibration Motor Multiplier: 100\n', text)
        self.assertNotIn('Enable Large Vibration Motor', text)

    def test_rpcs3_legacy_evdev_uses_kernel_name(self):
        text = self.write_rpcs3({'rpcs3_controller1': 'Evdev', 'rpcs3_controller2': 'Evdev'})
        self.assertIn(f'  Handler: Evdev\n  Device: "{EVDEV_NAME}"\n', text)
        self.assertIn(f'  Device: "2. {EVDEV_NAME}"\n', text)
        self.assertNotIn('/dev/input', text)


if __name__ == '__main__':
    unittest.main()
