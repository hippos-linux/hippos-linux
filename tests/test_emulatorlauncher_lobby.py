import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))
sys.path.insert(0, str(ROOT / 'services' / 'hippos-lobby'))

import emulatorlauncher_lobby as launcher_lobby
from emulatorlauncher_registry import Emulator
import hippos_lobby
from emulatorlauncher_shared import LaunchContext, NetplaySession

RIVERHORSE = Emulator('riverhorse', lambda ctx: 0)

GAMEINFO = '''<?xml version="1.0"?>
<gameList><game><path>/userdata/roms/psx/ctr.chd</path><name>Crash Team Racing</name><crc32>abcd1234</crc32></game></gameList>
'''


def _host_ctx(gameinfoxml=None, emulator='riverhorse') -> LaunchContext:
    return LaunchContext(system='psx', rom=Path('/userdata/roms/psx/ctr.chd'), emulator=emulator, core='riverhorse',
                         gameinfoxml=gameinfoxml, netplay=NetplaySession(mode='host', port='55435', nickname='fox'))


class LobbyGameTests(unittest.TestCase):
    def test_name_and_crc_come_from_es_game_info(self):
        with tempfile.NamedTemporaryFile('w', suffix='.xml') as xml:
            xml.write(GAMEINFO)
            xml.flush()
            self.assertEqual(launcher_lobby.lobby_game(_host_ctx(Path(xml.name))),
                             launcher_lobby.LobbyGame('Crash Team Racing', 'ABCD1234'))

    def test_without_game_info_uses_rom_name(self):
        self.assertEqual(launcher_lobby.lobby_game(_host_ctx()), launcher_lobby.LobbyGame('ctr', ''))


class HostedSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = hippos_lobby.make_server('127.0.0.1', 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.conf = {'global.netplay_public_announce': '1',
                     'global.netplay.hipposlobby': f'http://127.0.0.1:{self.server.server_port}/'}
        self.rooms = self.server.RequestHandlerClass.rooms
        patcher = mock.patch.object(launcher_lobby.UpnpPortMapping, 'open', return_value=True)
        self.upnp_open = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _wait_for_room(self) -> list[dict]:
        for _ in range(100):
            if listing := self.rooms.listing():
                return listing
            threading.Event().wait(0.02)
        return []

    def test_host_room_is_listed_while_playing_and_removed_after(self):
        with launcher_lobby.hosted_session(self.conf, _host_ctx(), RIVERHORSE):
            fields = self._wait_for_room()[0]['fields']
            self.assertEqual((fields['emulator'], fields['core_name'], fields['port'], fields['username'], fields['upnp']),
                             ('riverhorse', 'riverhorse', 55435, 'fox', True))
        self.assertEqual(self.rooms.listing(), [])

    def test_announce_off_only_maps_the_port(self):
        with launcher_lobby.hosted_session({**self.conf, 'global.netplay_public_announce': '0'}, _host_ctx(), RIVERHORSE):
            pass
        self.upnp_open.assert_called_once()
        self.assertEqual(self.rooms.listing(), [])

    def test_emulators_that_announce_themselves_are_skipped(self):
        with launcher_lobby.hosted_session(self.conf, _host_ctx(emulator='libretro'), Emulator('libretro', lambda ctx: 0, netplay_announce='emulator')):
            pass
        self.upnp_open.assert_not_called()

    def test_unreachable_lobby_does_not_block_the_game(self):
        conf = {**self.conf, 'global.netplay.hipposlobby': 'http://127.0.0.1:9'}
        with launcher_lobby.hosted_session(conf, _host_ctx(), RIVERHORSE):
            pass


if __name__ == '__main__':
    unittest.main()
