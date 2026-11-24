import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_generic as generic
import emulatorlauncher_azahar as azahar
import emulatorlauncher_core as core
import emulatorlauncher_impl as impl
import emulatorlauncher_ppsspp as ppsspp
from emulatorlauncher_shared import LaunchContext, NetplaySession


def _written(netplay: NetplaySession, conf: dict[str, str]) -> dict[str, str]:
    cfg = generic._KVConfig(Path(tempfile.mkdtemp()) / 'retroarch.cfg')
    generic._write_retroarch_netplay(cfg, netplay, conf)
    return cfg._data


class RetroArchNetplayArgsTests(unittest.TestCase):
    def test_no_netplay_adds_nothing(self):
        self.assertEqual(generic._retroarch_netplay_args(NetplaySession()), [])

    def test_host(self):
        self.assertEqual(generic._retroarch_netplay_args(NetplaySession(mode='host', port='55500', nickname='fox')),
                         ['--host', '--port', '55500', '--nick', 'fox'])

    def test_relay_client_joins_session(self):
        netplay = NetplaySession(mode='client', host='1.2.3.4', port='55436', session='abc123')
        self.assertEqual(generic._retroarch_netplay_args(netplay),
                         ['--connect', '1.2.3.4', '--port', '55436', '--mitm-session', 'abc123'])


class RetroArchNetplayConfigTests(unittest.TestCase):
    def test_host_writes_passwords_announce_and_relay(self):
        conf = {
            'global.netplay.password': 'pw',
            'global.netplay.spectatepassword': 'view',
            'global.netplay_public_announce': '1',
            'global.netplay.relay': 'custom',
            'global.netplay.customserver': 'relay.example.org',
        }
        data = _written(NetplaySession(mode='host'), conf)
        self.assertEqual(data['netplay_password'], '"pw"')
        self.assertEqual(data['netplay_spectate_password'], '"view"')
        self.assertEqual(data['netplay_public_announce'], '"true"')
        self.assertEqual(data['netplay_use_mitm_server'], '"true"')
        self.assertEqual(data['netplay_mitm_server'], '"custom"')
        self.assertEqual(data['netplay_custom_mitm_server'], '"relay.example.org"')
        self.assertEqual(data['cheevos_hardcore_mode_enable'], '"false"')

    def test_spectator_joins_without_relay(self):
        conf = {'global.netplay.relay': 'nyc'}
        data = _written(NetplaySession(mode='spectator', host='1.2.3.4'), conf)
        self.assertEqual(data['netplay_start_as_spectator'], '"true"')
        self.assertNotIn('netplay_spectate_password', data)
        self.assertEqual(data['netplay_ip_address'], '"1.2.3.4"')
        self.assertEqual(data['netplay_use_mitm_server'], '"false"')

    def test_no_netplay_writes_nothing(self):
        self.assertEqual(_written(NetplaySession(), {}), {})


def _session(argv: list[str], conf: dict[str, str]) -> NetplaySession:
    args = impl._build_parser().parse_args(['-system', 'snes', '-rom', '/userdata/roms/snes/game.sfc', *argv])
    with mock.patch.object(impl, '_load_hippos_conf', return_value=conf):
        return impl._netplay_session(args)


class NetplaySessionTests(unittest.TestCase):
    def test_es_relay_join_arguments(self):
        netplay = _session(['-netplaymode', 'client', '-netplayport', '55436', '-netplayip', '1.2.3.4',
                            '-netplaysession', 'abc123', '-netplaypass', 'pw'],
                           {'global.netplay.nickname': 'fox'})
        self.assertEqual(netplay, NetplaySession(mode='client', host='1.2.3.4', port='55436',
                                                 session='abc123', nickname='fox'))
        self.assertEqual(_session(['-netplaymode', 'host'], {}).nickname, 'HippOS Player')

    def test_host_port_comes_from_es_setting(self):
        self.assertEqual(_session(['-netplaymode', 'host'], {'global.netplay.port': '55500'}).port, '55500')
        self.assertEqual(_session(['-netplaymode', 'host'], {}).port, '55435')

    def test_lobby_host_asks_to_be_listed(self):
        self.assertTrue(_session(['-netplaymode', 'host', '-netplaylist'], {}).listed)
        self.assertFalse(_session(['-netplaymode', 'host'], {}).listed)

    def test_unknown_mode_is_no_netplay(self):
        self.assertFalse(_session(['-netplaymode', 'bogus'], {}).active)


class PackageApiTests(unittest.TestCase):
    def test_flat_netplay_fields_read_the_session(self):
        ctx = LaunchContext(system='psx', rom=Path('game.chd'), emulator='riverhorse', core='riverhorse',
                            netplay=NetplaySession(mode='client', host='1.2.3.4', port='31200'))
        self.assertEqual((ctx.netplay_mode, ctx.netplay_ip, ctx.netplay_port), ('client', '1.2.3.4', '31200'))


class PpssppNetplayTests(unittest.TestCase):
    def test_host_runs_the_builtin_adhoc_server(self):
        self.assertEqual(ppsspp.ppsspp_network_settings(NetplaySession(mode='host', port='27312')),
                         {'EnableWlan': 'True', 'EnableAdhocServer': 'True',
                          'proAdhocServer': 'localhost', 'EnableUPnP': 'True'})

    def test_client_and_spectator_use_the_hosts_adhoc_server(self):
        for mode in ('client', 'spectator'):
            settings = ppsspp.ppsspp_network_settings(NetplaySession(mode=mode, host='1.2.3.4', port='27312'))
            self.assertEqual((settings['EnableAdhocServer'], settings['proAdhocServer']), ('False', '1.2.3.4'))

    def test_netplay_settings_are_restored_after_the_game(self):
        ini = Path(tempfile.mkdtemp()) / 'ppsspp.ini'
        ini.write_text('[Network]\nEnableWlan = False\nproAdhocServer = socom.cc\n')
        with mock.patch.object(ppsspp, 'PPSSPP_INI', ini):
            with ppsspp._ppsspp_netplay_network(NetplaySession(mode='client', host='1.2.3.4')):
                self.assertIn('proAdhocServer = 1.2.3.4', ini.read_text())
            text = ini.read_text()
        self.assertIn('EnableWlan = False', text)
        self.assertIn('proAdhocServer = socom.cc', text)
        self.assertNotIn('EnableAdhocServer', text)

    def test_ppsspp_hosts_on_its_adhoc_server_port(self):
        emulator = impl.lookup('ppsspp')
        self.assertEqual(emulator.netplay_port, '27312')


class FlycastNetplayTests(unittest.TestCase):
    def test_host_and_client_point_at_each_other(self):
        host = core.flycast_netplay_args(NetplaySession(mode='host', host='198.51.100.7', port='19713'))
        client = core.flycast_netplay_args(NetplaySession(mode='client', host='203.0.113.5', port='19713'))
        self.assertEqual(host, ['-config', 'network:GGPO=yes,network:ActAsServer=yes,network:server=198.51.100.7,network:EnableUPnP=yes'])
        self.assertIn('network:ActAsServer=no', client[1])
        self.assertIn('network:server=203.0.113.5', client[1])

    def test_no_netplay_adds_nothing(self):
        self.assertEqual(core.flycast_netplay_args(NetplaySession()), [])

    def test_flycast_is_listed_by_es_on_its_fixed_port(self):
        emulator = impl.lookup('flycast')
        self.assertEqual((emulator.netplay_port, emulator.netplay_announce), ('19713', 'frontend'))


class AzaharNetplayTests(unittest.TestCase):
    def test_host_joins_its_own_room_and_client_joins_the_hosts(self):
        self.assertEqual(azahar.azahar_multiplayer_args(NetplaySession(mode='host', port='24872', nickname='fox')),
                         ['--multiplayer', 'fox@127.0.0.1:24872'])
        self.assertEqual(azahar.azahar_multiplayer_args(NetplaySession(mode='client', host='1.2.3.4', port='24872', nickname='vm2')),
                         ['--multiplayer', 'vm2@1.2.3.4:24872'])

    def test_azahar_hosts_on_its_room_port(self):
        self.assertEqual(impl.lookup('azahar').netplay_port, '24872')


class RiverhorseNetplayTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / 'packages' / 'emulators' / 'riverhorse' / 'hippos' / 'launcher'))
        import emulatorlauncher_riverhorse
        self.riverhorse = emulatorlauncher_riverhorse

    def _args(self, version: str, mode: str = 'host') -> list[str]:
        ctx = LaunchContext(system='psx', rom=Path('game.chd'), emulator='riverhorse', core='riverhorse',
                            netplay=NetplaySession(mode=mode, host='1.2.3.4', port='55435', nickname='fox'))
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.object(self.riverhorse, 'EMULATORS_ROOT', Path(root)), \
                mock.patch.object(self.riverhorse, '_load_hippos_conf', return_value={}):
            (Path(root) / 'riverhorse').mkdir()
            (Path(root) / 'riverhorse' / 'version').write_text(version)
            return self.riverhorse._riverhorse_netplay_args(ctx)

    def test_releases_without_netplay_events_get_no_flag(self):
        self.assertNotIn('-netplayevents', self._args('v1.2.0'))

    def test_newer_releases_report_netplay_events(self):
        self.assertIn('-netplayevents', self._args('v1.2.1'))
        self.assertEqual(self._args('v1.3.0', mode=''), ['-netplayevents'])


class DolphinNetplayTests(unittest.TestCase):
    def test_traversal_join_uses_the_host_code(self):
        args = core.dolphin_netplay_join_args(NetplaySession(mode='client', host='abcd1234', port='2626',
                                                             session='abcd1234', nickname='fox'))
        self.assertIn('Dolphin.NetPlay.TraversalChoice=traversal', args)
        self.assertIn('Dolphin.NetPlay.HostCode=abcd1234', args)
        self.assertEqual(args[-1], '--netplay_join')

    def test_direct_join_uses_the_address(self):
        args = core.dolphin_netplay_join_args(NetplaySession(mode='client', host='1.2.3.4', port='2626', nickname='fox'))
        self.assertIn('Dolphin.NetPlay.TraversalChoice=direct', args)
        self.assertIn('Dolphin.NetPlay.Address=1.2.3.4', args)
        self.assertIn('Dolphin.NetPlay.ConnectPort=2626', args)

    def test_host_opens_a_direct_session_for_the_game(self):
        args = core.dolphin_netplay_host_args(NetplaySession(mode='host', port='55435', nickname='fox'),
                                              Path('/userdata/roms/gamecube/game.iso'))
        self.assertIn('Dolphin.NetPlay.TraversalChoice=direct', args)
        self.assertIn('Dolphin.NetPlay.HostPort=55435', args)
        self.assertEqual(args[-2:], ['--netplay_host', '/userdata/roms/gamecube/game.iso'])


if __name__ == '__main__':
    unittest.main()
