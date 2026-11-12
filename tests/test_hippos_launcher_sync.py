"""Tests for the gamelist half of hippos_launcher_sync and the Flatpak metadata reader."""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'))

import hippos_appstream  # noqa: E402
from hippos_launcher_sync import (  # noqa: E402
    GameMetadata,
    known_keys,
    sync_gamelist,
    sync_launchers,
)


class SyncGamelistTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.roms = self.base / 'roms'
        self.state = self.base / 'state.json'

    def sync(self, games):
        sync_launchers(self.roms, self.state, '.app', {key: game.name for key, game in games.items()}, 'App')
        return sync_gamelist(self.roms, self.state, '.app', games)

    def game(self, name):
        for game in ET.parse(self.roms / 'gamelist.xml').getroot().findall('game'):
            if game.findtext('path') == f'./{name}.app':
                return game
        return None

    def test_writes_details_and_copies_image(self):
        icon = self.base / 'icon.png'
        icon.write_bytes(b'png')
        self.assertTrue(self.sync({'id': GameMetadata('App', 'About it', 'Dev', icon)}))
        game = self.game('App')
        self.assertEqual(game.findtext('desc'), 'About it')
        self.assertEqual(game.findtext('developer'), 'Dev')
        self.assertEqual(game.findtext('image'), './images/App.png')
        self.assertEqual((self.roms / 'images/App.png').read_bytes(), b'png')

    def test_second_sync_changes_nothing(self):
        games = {'id': GameMetadata('App', 'About it')}
        self.sync(games)
        self.assertFalse(self.sync(games))

    def test_user_edits_survive(self):
        self.sync({'id': GameMetadata('App', 'Generated')})
        tree = ET.parse(self.roms / 'gamelist.xml')
        tree.getroot().find('game/desc').text = 'Mine'
        tree.getroot().find('game/name').text = 'My name'
        tree.write(self.roms / 'gamelist.xml')
        self.sync({'id': GameMetadata('App', 'Newer', 'Dev')})
        game = self.game('App')
        self.assertEqual(game.findtext('desc'), 'Mine')
        self.assertEqual(game.findtext('name'), 'My name')
        self.assertEqual(game.findtext('developer'), 'Dev')

    def test_blank_fields_get_filled(self):
        self.sync({'id': GameMetadata('App')})
        self.assertTrue(self.sync({'id': GameMetadata('App', 'Now known')}))
        self.assertEqual(self.game('App').findtext('desc'), 'Now known')

    def test_removed_launcher_loses_entry_and_generated_image(self):
        icon = self.base / 'icon.png'
        icon.write_bytes(b'png')
        self.sync({'id': GameMetadata('App', 'About', image=icon)})
        self.sync({})
        self.assertIsNone(self.game('App'))
        self.assertFalse((self.roms / 'images/App.png').exists())

    def test_user_chosen_image_is_kept_on_removal(self):
        self.sync({'id': GameMetadata('App')})
        (self.roms / 'images').mkdir()
        mine = self.roms / 'images/my-art.png'
        mine.write_bytes(b'mine')
        tree = ET.parse(self.roms / 'gamelist.xml')
        ET.SubElement(tree.getroot().find('game'), 'image').text = './images/my-art.png'
        tree.write(self.roms / 'gamelist.xml')
        self.sync({})
        self.assertTrue(mine.exists())

    def test_other_files_entries_are_untouched(self):
        self.sync({'id': GameMetadata('App')})
        tree = ET.parse(self.roms / 'gamelist.xml')
        other = ET.SubElement(tree.getroot(), 'game')
        ET.SubElement(other, 'path').text = './rom.zip'
        tree.write(self.roms / 'gamelist.xml')
        self.sync({})
        paths = [g.findtext('path') for g in ET.parse(self.roms / 'gamelist.xml').getroot().findall('game')]
        self.assertEqual(paths, ['./rom.zip'])

    def test_unparseable_gamelist_is_not_replaced(self):
        self.roms.mkdir()
        (self.roms / 'gamelist.xml').write_text('<gameList><game>')
        self.assertFalse(self.sync({'id': GameMetadata('App', 'About')}))
        self.assertEqual((self.roms / 'gamelist.xml').read_text(), '<gameList><game>')

    def test_known_keys_follow_launchers(self):
        self.assertEqual(known_keys(self.state), set())
        self.sync({'a': GameMetadata('A'), 'b': GameMetadata('B')})
        self.assertEqual(known_keys(self.state), {'a', 'b'})
        self.sync({'b': GameMetadata('B')})
        self.assertEqual(known_keys(self.state), {'b'})


METAINFO = '''<?xml version="1.0"?>
<component>
  <name>App</name>
  <developer_name>Old Dev</developer_name>
  <developer id="x"><name>New Dev</name><name xml:lang="de">Entwickler</name></developer>
  <summary>Short</summary>
  <summary xml:lang="de">Kurz</summary>
  <description>
    <p>First   line
       wrapped.</p>
    <p xml:lang="de">Erste Zeile.</p>
    <ul><li>One</li><li xml:lang="de">Eins</li></ul>
  </description>
</component>
'''


class FlatpakMetadataTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.share = self.root / 'org.x.App/current/active/export/share'
        patcher = mock.patch.object(hippos_appstream, '_INSTALL_ROOTS', (self.root,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_metainfo(self, text):
        (self.share / 'metainfo').mkdir(parents=True)
        (self.share / 'metainfo/org.x.App.metainfo.xml').write_text(text)

    def icon(self, size, name='org.x.App.png'):
        path = self.share / 'icons/hicolor' / size / 'apps' / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'i')
        return path

    def test_reads_english_details_only(self):
        self.write_metainfo(METAINFO)
        details = hippos_appstream.read_app_details('org.x.App')
        self.assertEqual(details.description, 'First line wrapped.\n• One')
        self.assertEqual(details.developer, 'New Dev')

    def test_falls_back_to_summary_and_old_developer_tag(self):
        self.write_metainfo('<component><developer_name>Old</developer_name><summary>Short</summary></component>')
        details = hippos_appstream.read_app_details('org.x.App')
        self.assertEqual(details.description, 'Short')
        self.assertEqual(details.developer, 'Old')

    def test_prefers_vector_then_largest_bitmap(self):
        self.write_metainfo(METAINFO)
        self.icon('32x32')
        large = self.icon('512x512')
        self.icon('1024x1024', 'org.x.App-tray.png')
        self.assertEqual(hippos_appstream.read_app_details('org.x.App').icon, large)
        vector = self.icon('scalable', 'org.x.App.svg')
        self.assertEqual(hippos_appstream.read_app_details('org.x.App').icon, vector)

    def test_not_installed_and_bad_metainfo_are_harmless(self):
        self.assertEqual(hippos_appstream.read_app_details('org.none'), hippos_appstream.AppDetails())
        self.write_metainfo('<component><summary>')
        self.assertIsNone(hippos_appstream.read_app_details('org.x.App').description)


if __name__ == '__main__':
    unittest.main()
