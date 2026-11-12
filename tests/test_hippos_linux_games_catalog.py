import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_linux_games as linux_games


class CatalogLauncherTests(unittest.TestCase):
    def test_apps_go_to_linux_apps_and_games_to_linux_games(self):
        self.assertEqual(linux_games.catalog_launcher({'id': 'app-kodi', 'category': 'apps'}),
                         Path('/userdata/roms/webapps/app-kodi.sh'))
        self.assertEqual(linux_games.catalog_launcher({'id': 'port-openttd', 'category': 'ports'}),
                         Path('/userdata/roms/linux/port-openttd.sh'))


if __name__ == '__main__':
    unittest.main()
