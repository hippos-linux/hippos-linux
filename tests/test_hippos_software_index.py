import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))

import hippos_software_index as index
import hippos_store_catalog

FLATHUB_XML = '''<?xml version="1.0"?>
<components origin="flathub">
  <component type="desktop">
    <id>org.example.Calc</id>
    <name>Calc</name>
    <name xml:lang="de">Rechner</name>
    <summary>Adds numbers</summary>
    <developer_name>Example Devs</developer_name>
    <project_license>GPL-3.0</project_license>
    <url type="homepage">https://example.org</url>
    <description><p>Does sums.</p><p xml:lang="de">Rechnet.</p><ul><li>Fast</li></ul></description>
    <icon type="cached" height="128" width="128">org.example.Calc.png</icon>
    <categories><category>Utility</category><category>Calculator</category></categories>
    <screenshots><screenshot type="default"><image type="source">https://example.org/shot.png</image></screenshot></screenshots>
    <releases><release version="2.0" timestamp="200"/><release version="1.0" timestamp="100"/></releases>
  </component>
  <component type="runtime"><id>org.example.Platform</id><name>Platform</name></component>
  <component type="desktop">
    <id>org.example.Game</id>
    <name>Game</name>
    <summary>Plays</summary>
    <developer><name>Studio</name></developer>
    <categories><category>Game</category></categories>
  </component>
</components>
'''

DEP11_YAML = '''---
File: DEP-11
Origin: debian-trixie-main
MediaBaseUrl: https://media.example
---
Type: desktop-application
ID: org.example.Calc.desktop
Package: example-calc
Name: {C: Calc}
Summary: {C: Adds numbers in Debian}
Description: {C: '<p>Debian build.</p>'}
Categories: [Utility]
Icon: {cached: [{name: calc.png, width: 64, height: 64}, {name: calc.png, width: 128, height: 128}]}
Launchable: {desktop-id: [org.example.Calc.desktop]}
Releases: [{version: '1.5', unix-timestamp: 150}]
---
Type: desktop-application
ID: org.example.Viewer.desktop
Package: example-viewer
Name: {C: Viewer}
Summary: {C: Shows pictures}
Categories: [Graphics]
Icon: {cached: [{name: viewer.png, width: 64, height: 64}, {name: viewer.png, width: 128, height: 128}]}
---
Type: desktop-application
ID: org.example.System.desktop
Package: system-tool
Name: {C: System tool}
Summary: {C: Part of the image}
---
Type: generic
ID: libexample
Package: libexample1
'''


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        appstream = self.tmp / 'flathub'
        (appstream / 'icons' / '128x128').mkdir(parents=True)
        (appstream / 'icons' / '128x128' / 'org.example.Calc.png').write_bytes(b'png')
        with gzip.open(appstream / 'appstream.xml.gz', 'wt', encoding='utf-8') as stream:
            stream.write(FLATHUB_XML)
        self.appstream = appstream
        yaml_dir = self.tmp / 'yaml'
        yaml_dir.mkdir()
        with gzip.open(yaml_dir / 'debian_main_dep11_Components-amd64.yml.gz', 'wt', encoding='utf-8') as stream:
            stream.write(DEP11_YAML)
        self.yaml_dir = yaml_dir
        arch = mock.patch.object(hippos_store_catalog, 'DEB_ARCH', 'amd64')
        arch.start()
        self.addCleanup(arch.stop)

    def build(self, catalog=()):
        readers = (index.read_catalog(list(catalog)), index.read_flathub(self.appstream),
                   index.read_dep11(self.yaml_dir, self.tmp / 'icons'))
        return index.build(self.tmp / 'index.json', self.tmp / 'details.jsonl', readers)

    def test_flathub_apps_skip_runtimes_and_translations(self):
        apps = {app.key: app for app, _ in index.read_flathub(self.appstream)}
        self.assertEqual(set(apps), {'org.example.calc', 'org.example.game'})
        calc = apps['org.example.calc']
        self.assertEqual((calc.name, calc.summary, calc.released), ('Calc', 'Adds numbers', 200))
        self.assertEqual(calc.categories, ['Utilities'])
        self.assertTrue(calc.icon.endswith('org.example.Calc.png'))
        self.assertEqual(calc.sources[0].flatpak_id, 'org.example.Calc')
        self.assertEqual(calc.sources[0].version, '2.0')

    def test_debian_apps_include_image_packages_and_skip_non_apps(self):
        apps = [app for app, _ in index.read_dep11(self.yaml_dir, self.tmp / 'icons')]
        self.assertEqual([app.sources[0].name for app in apps],
                         ['apt::example-calc', 'apt::example-viewer', 'apt::system-tool'])
        self.assertEqual(apps[0].desktop_id, 'org.example.Calc.desktop')

    def test_debian_icons_prefer_128_and_fall_back_to_64(self):
        icons = self.tmp / 'icons' / 'debian-trixie-main'
        for size, name in ((128, 'calc.png'), (64, 'calc.png'), (64, 'viewer.png')):
            (icons / f'{size}x{size}').mkdir(parents=True, exist_ok=True)
            (icons / f'{size}x{size}' / name).write_bytes(b'png')
        apps = {app.key: app for app, _ in index.read_dep11(self.yaml_dir, self.tmp / 'icons')}
        self.assertTrue(apps['org.example.calc'].icon.endswith('128x128/calc.png'))
        self.assertTrue(apps['org.example.viewer'].icon.endswith('64x64/viewer.png'))
        self.assertEqual(apps['org.example.system'].icon, '')

    def test_same_app_from_flathub_and_debian_is_one_entry(self):
        apps = {app.key: app for app in self.build()}
        calc = apps['org.example.calc']
        self.assertEqual([source.label for source in calc.sources], ['Flathub', 'Debian'])
        self.assertEqual(calc.desktop_id, 'org.example.Calc.desktop')
        self.assertEqual(calc.released, 200)
        self.assertIn('org.example.viewer', apps)

    def test_details_are_read_back_from_the_side_file(self):
        calc = next(app for app in self.build() if app.key == 'org.example.calc')
        details = index.details(calc, self.tmp / 'details.jsonl')
        self.assertEqual(details.description, 'Does sums.\n\n• Fast')
        self.assertEqual((details.developer, details.license, details.homepage),
                         ('Example Devs', 'GPL-3.0', 'https://example.org'))
        self.assertEqual(details.screenshot, 'https://example.org/shot.png')

    def test_catalogue_entry_leads_and_keeps_richer_details(self):
        catalog = [{'id': 'app-calc', 'name': 'Calc (HippOS)', 'category': 'apps', 'type': 'flatpak',
                    'flatpak_id': 'org.example.Calc', 'description': 'Picked. More.'}]
        calc = next(app for app in self.build(catalog) if app.key == 'org.example.calc')
        self.assertEqual([source.kind for source in calc.sources], ['hippos', 'flatpak', 'debian'])
        self.assertEqual(calc.name, 'Calc (HippOS)')
        self.assertIn('HippOS picks', calc.categories)
        self.assertEqual(calc.sources[0].flatpak_id, 'org.example.Calc')
        self.assertEqual(index.details(calc, self.tmp / 'details.jsonl').developer, 'Example Devs')

    def test_catalogue_aliases_absorb_flathub_and_debian_listings(self):
        catalog = [{'id': 'port-calc', 'name': 'Calc Port', 'category': 'ports', 'type': 'apt',
                    'apt_packages': ['example-viewer'], 'appstream_ids': ['org.example.Game'],
                    'description': 'Thin.'}]
        apps = {app.key: app for app in self.build(catalog)}
        self.assertNotIn('org.example.game', apps)
        self.assertNotIn('org.example.viewer', apps)
        port = apps['hippos:port-calc']
        self.assertEqual([source.kind for source in port.sources], ['hippos', 'flatpak', 'debian'])
        self.assertEqual(port.name, 'Calc Port')
        self.assertIn('Ports', port.categories)
        self.assertEqual(index.details(port, self.tmp / 'details.jsonl').developer, 'Studio')

    def test_index_round_trips_through_its_cache(self):
        built = self.build()
        loaded = index.load(self.tmp / 'index.json')
        self.assertEqual([app.key for app in loaded], [app.key for app in built])
        self.assertEqual(loaded[0].sources, built[0].sources)

    def test_search_puts_name_matches_first(self):
        apps = self.build()
        self.assertEqual([app.name for app in index.search(apps, 'calc')], ['Calc'])
        self.assertEqual([app.name for app in index.search(apps, 'pictures')], ['Viewer'])
        self.assertEqual(index.search(apps, '  '), [])


class RankingTests(unittest.TestCase):
    def apps(self):
        return [
            index.App('org.a', 'Alpha', '', component_ids=['org.A'],
                      sources=[index.Source('flatpak', 'flatpak::org.A', '', 'org.A')]),
            index.App('org.b', 'Beta', '', component_ids=['org.B'], desktop_id='org.B.desktop',
                      sources=[index.Source('debian', 'apt::beta')]),
            index.App('org.c', 'Gamma', '', component_ids=['org.C'],
                      sources=[index.Source('flatpak', 'flatpak::org.C', '', 'org.C'),
                               index.Source('debian', 'apt::gamma')]),
        ]

    def test_ratings_use_the_id_with_most_votes(self):
        apps = self.apps()
        index.apply_ratings(apps, {
            'org.C': {'star1': 2, 'total': 2},
            'org.c': {'star5': 9, 'total': 9},
            'org.A': {'star1': 0, 'star5': 1, 'total': 1},
            'org.B': {'star3': 1, 'total': 1},
            'org.B.desktop': {'star4': 3, 'star5': 1, 'total': 4},
        })
        self.assertEqual((apps[0].rating, apps[0].ratings, apps[0].rating_id), (100, 1, 'org.A'))
        self.assertEqual((apps[1].rating, apps[1].ratings, apps[1].rating_id), (85, 4, 'org.B.desktop'))
        self.assertEqual((apps[2].rating, apps[2].ratings, apps[2].rating_id), (100, 9, 'org.c'))

    def test_installs_take_the_larger_source(self):
        apps = self.apps()
        index.apply_installs(apps, {'org.A': 50, 'org.C': 10}, {'beta': 30, 'gamma': 900})
        self.assertEqual([(app.installs, app.installs_source) for app in apps],
                         [(50, 'flatpak'), (30, 'debian'), (900, 'debian')])

    def test_sort_orders(self):
        apps = self.apps()
        apps[0].installs, apps[1].installs, apps[2].installs = 5, 50, 500
        apps[0].rating, apps[0].ratings = 100, 1
        apps[1].rating, apps[1].ratings = 90, 200
        apps[0].released, apps[2].released = 10, 20
        self.assertEqual([a.name for a in index.sort_apps(apps, 'Most installed')], ['Gamma', 'Beta', 'Alpha'])
        self.assertEqual([a.name for a in index.sort_apps(apps, 'Top rated')][0], 'Beta')
        self.assertEqual([a.name for a in index.sort_apps(apps, 'Recently updated')][:2], ['Gamma', 'Alpha'])
        self.assertEqual([a.name for a in index.sort_apps(apps, 'Name')], ['Alpha', 'Beta', 'Gamma'])

    def test_catalogue_updates_need_a_new_published_version(self):
        catalog = [{'id': 'a', 'version': '2'}, {'id': 'b', 'version': 'latest'}, {'id': 'c', 'version': '1'},
                   {'id': 'd', 'version': '3'}]
        state = {'a': {'version': '1'}, 'b': {'version': 'old'}, 'c': {'version': '1'}}
        self.assertEqual(index.catalog_updates(catalog, state), {'a'})

    def test_command_line_packages_join_search(self):
        found = [mock.Mock(name='r1'), mock.Mock(name='r2')]
        found[0].configure_mock(name='apt::ripgrep', title='ripgrep', description='Search tool', version='14',
                                installed=True)
        found[1].configure_mock(name='apt::beta', title='beta', description='', version='', installed=False)
        with mock.patch.object(index, 'debian_results', return_value=found):
            apps, installed = index.package_apps('grep', self.apps())
        self.assertEqual([app.key for app in apps], ['apt:ripgrep'])
        self.assertEqual(installed, {'apt::ripgrep'})

    def test_apt_details_read_the_long_description(self):
        listing = ('Package: ripgrep\nMaintainer: Someone <a@b>\nHomepage: https://rg.example\n'
                   'Description-en: fast search\n Searches files.\n .\n Quickly.\n')
        with mock.patch.object(index.subprocess, 'run', return_value=mock.Mock(stdout=listing)):
            details = index.apt_details('ripgrep')
        self.assertEqual(details.description, 'Searches files.\n\nQuickly.')
        self.assertEqual((details.developer, details.homepage), ('Someone <a@b>', 'https://rg.example'))


class SystemUpdateTests(unittest.TestCase):
    LISTING = [
        {'kind': 'system', 'name': 'HippOS', 'installed': '0.7.0', 'available': '0.7.1', 'command': ['apply'],
         'needs_restart': True},
        {'kind': 'emulator', 'name': 'ppsspp', 'installed': 'v1.19', 'available': 'v1.19',
         'command': ['update-emulator', 'ppsspp'], 'needs_restart': False},
        {'kind': 'patch', 'name': 'fix-1', 'installed': '', 'available': '1', 'command': ['apply-patches'],
         'needs_restart': False, 'detail': 'Fixes audio'},
        {'kind': 'frontend', 'name': 'emulationstation', 'installed': 'a', 'available': 'b',
         'command': ['update-frontend', 'emulationstation'], 'needs_restart': False},
        {'kind': 'emulator', 'name': 'broken'},
    ]

    def updates(self, output):
        result = mock.Mock(stdout=output)
        with mock.patch.object(index.subprocess, 'run', return_value=result) as run:
            updates = index.system_updates()
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0], [index.UPGRADE, 'list-available'])
        return updates

    def test_shown_system_first_and_run_system_last(self):
        updates = self.updates(json.dumps(self.LISTING))
        self.assertEqual([u.kind for u in updates], ['system', 'frontend', 'emulator', 'patch'])
        self.assertTrue(updates[0].needs_restart)
        self.assertEqual([u.kind for u in sorted(updates, key=index.run_position)],
                         ['patch', 'emulator', 'frontend', 'system'])

    def test_several_emulators_become_one_row(self):
        listing = self.LISTING + [{'kind': 'emulator', 'name': 'mame', 'installed': '1', 'available': '2',
                                   'command': ['update-emulator', 'mame'], 'needs_restart': False}]
        updates = self.updates(json.dumps(listing))
        emulators = [u for u in updates if u.kind.startswith('emulator')]
        self.assertEqual(len(emulators), 1)
        self.assertEqual((emulators[0].title, emulators[0].change, emulators[0].command),
                         ('Emulators', '2 updates', ['update-all-emulators']))

    def test_change_text(self):
        updates = {u.name: u for u in self.updates(json.dumps(self.LISTING))}
        self.assertEqual(updates['ppsspp'].change, 'v1.19, rebuilt')
        self.assertEqual(updates['fix-1'].change, 'Fixes audio')
        self.assertEqual(updates['HippOS'].change, '0.7.0 → 0.7.1')
        self.assertEqual(updates['emulationstation'].title, 'EmulationStation')

    def test_unreadable_output_means_no_updates(self):
        self.assertEqual(self.updates('not json'), [])


if __name__ == '__main__':
    unittest.main()
