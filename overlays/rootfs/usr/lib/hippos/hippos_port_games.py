from __future__ import annotations

import platform
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hippos_launcher_sync import GameMetadata

ROMS = Path('/userdata/roms')
BIOS = Path('/userdata/bios')
VOXATRON_PLAYER = BIOS / 'voxatron' / 'vox'
STEAM_ART = 'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{name}'
USER_AGENT = 'HippOS-PortGames/1.0'


@dataclass(frozen=True)
class PortGame:
    system: str
    title: str
    extension: str
    files: tuple[tuple[str, ...], ...]
    metadata: GameMetadata
    folder: str | None = None
    location: Literal['top', 'sub', 'any'] = 'top'
    steam_appid: int | None = None
    entry: str | None = None
    marker_name: str | None = None
    requires: Path | None = None

    def matches(self, folder: Path, system_dir: Path) -> bool:
        if self.location != 'any' and (self.location == 'sub') == (folder == system_dir):
            return False
        if self.folder and not re.search(self.folder, folder.name, re.IGNORECASE):
            return False
        if self.requires and not self.requires.exists():
            return False
        return all(any(find_file(folder, option) for option in group) for group in self.files)


def find_file(folder: Path, relative: str) -> Path | None:
    current = folder
    for part in relative.lower().split('/'):
        if not current.is_dir():
            return None
        current = next((child for child in current.iterdir() if child.name.lower() == part), None)
        if current is None:
            return None
    return current


def _release_date(released: str) -> str:
    return f'{released}0101T000000' if len(released) == 4 else f'{released}T000000'


def _game(system, title, extension, files, developer, publisher, released, genre, players, description,
          metadata_extra=None, **options):
    return PortGame(system, title, extension, tuple((group,) if isinstance(group, str) else group for group in files),
                    GameMetadata(title, description, developer, None, publisher, _release_date(released), genre, players,
                                 **(metadata_extra or {})),
                    **options)


def _id_game(system, title, extension, files, entry, developer, released, description, core, steam_appid=None):
    return _game(system, title, extension, files, developer, 'Activision', released, 'First-person shooter', '1',
                 description, location='any', entry=entry, steam_appid=steam_appid,
                 metadata_extra={'emulator': 'retroarch', 'core': core})


def _tomb_raider(title, files, entry, released, description, steam_appid):
    return _game('openlara', title, Path(entry).suffix.lower(), files, 'Core Design', 'Eidos Interactive', released,
                 'Action-adventure', '1', description, location='sub', entry=entry, steam_appid=steam_appid)


def _keen(title: str, released: str, exe: tuple[str, ...], description: str) -> PortGame:
    return _game('cgenius', title, '.cgenius', [exe], 'id Software', 'Apogee Software', released, 'Platform', '1',
                 description, location='sub', steam_appid=9180)


PORT_GAMES = (
    _game('fallout1-ce', 'Fallout', '.f1ce', ['MASTER.DAT', 'CRITTER.DAT'], 'Interplay Productions',
          'Interplay Productions', '19971010', 'Role-playing', '1',
          'A nuclear war has left California a wasteland. Generations later, the water chip that keeps your '
          'underground Vault alive breaks, and you are sent out into the ruins to find a replacement before the '
          'water runs out. An open, turn-based role-playing game where most problems can be solved by talking, '
          'sneaking or fighting.',
          steam_appid=38400),
    _game('fallout2-ce', 'Fallout 2', '.f2ce', ['master.dat', 'critter.dat'], 'Black Isle Studios',
          'Interplay Productions', '1998', 'Role-playing', '1',
          'Eighty years after the first game, a descendant of the Vault Dweller leaves the tribal village of Arroyo '
          'to find the Garden of Eden Creation Kit and save the village from drought. A larger wasteland, more '
          'towns and factions, and the same turn-based combat and freedom to play your own way.',
          steam_appid=38410),
    _game('sonic-mania', 'Sonic Mania', '.sman', ['Data.rsdk'], 'Christian Whitehead, Headcannon, PagodaWest Games',
          'Sega', '20170815', 'Platform', '1-2',
          'Sonic, Tails and Knuckles race through reimagined classic zones and brand new ones in a 2D platformer '
          'built by fans who became the developers, with Blue Spheres and Special Stages, Competition mode and '
          'Time Attack. Runs on the RSDKv5 decompilation using the Data.rsdk from your own copy of the game.',
          steam_appid=584400),
    _game('sonic3-air', 'Sonic 3 - Angel Island Revisited', '.s3air', ['Sonic_Knuckles_wSonic3.bin'],
          'Eukaryot, Sonic Team', 'Sega', '19941018', 'Platform', '1-2',
          "A fan remaster of Sonic 3 & Knuckles in widescreen, with optional fixes, extra characters and modding "
          "support. It reads the combined Sonic & Knuckles + Sonic 3 ROM from your own copy of the game.",
          steam_appid=71162),
    _game('sonicretro', 'Sonic CD', '.scd', ['Data.rsdk'], 'Sonic Team, Christian Whitehead', 'Sega', '2011',
          'Platform', '1',
          "Sonic travels through time on Little Planet to stop Dr. Robotnik and rescue Amy Rose. Every zone has "
          "past, present and future versions, and the good ending needs you to fix the past. Runs on the RSDKv3 "
          "decompilation using the Data.rsdk from your own copy of the 2011 remaster.",
          folder=r'\bcd\b', location='sub', steam_appid=200940),
    _game('sonicretro', 'Sonic the Hedgehog 2', '.son', ['Data.rsdk'], 'Sonic Team, Christian Whitehead', 'Sega',
          '20131212', 'Platform', '1-2',
          "Sonic and Tails chase Dr. Robotnik to the Death Egg across Emerald Hill, Chemical Plant and the other "
          "classic zones, now in widescreen with the Hidden Palace Zone restored. Runs on the RSDKv4 decompilation "
          "using the Data.rsdk from your own copy of the 2013 remaster.",
          folder=r'2', location='sub', steam_appid=71163),
    _game('sonicretro', 'Sonic the Hedgehog', '.son', ['Data.rsdk'], 'Sonic Team, Christian Whitehead', 'Sega',
          '20130515', 'Platform', '1',
          "The first Sonic, remastered in widescreen with Tails and Knuckles playable, Sonic 2's spin dash and a "
          "smoother frame rate. Runs on the RSDKv4 decompilation using the Data.rsdk from your own copy of the "
          "2013 remaster.",
          location='sub', steam_appid=71113),
    _game('cannonball', 'OutRun', '.cannonball', [('epr-10380b.133', 'epr-10380.133')], 'Sega AM2', 'Sega',
          '1986', 'Racing', '1',
          "Drive a Ferrari Testarossa across five stages of branching coastal roads, picking your route at every "
          "fork and your music on the radio. Cannonball is an enhanced engine for the arcade original and needs "
          "the unzipped OutRun arcade ROMs."),
    _game('reminiscence', 'Flashback', '.rem', [('LEVEL1.MAP', 'LEVEL1.LEV')], 'Delphine Software International',
          'U.S. Gold', '1992', 'Action', '1',
          "Conrad B. Hart wakes up on a jungle moon with no memory and a message from himself. A cinematic "
          "platformer with rotoscoped animation, puzzles and gunfights. REminiscence plays it from the original "
          "DOS game's data files."),
    _keen('Commander Keen 1: Marooned on Mars', '19901214', ('keen1.exe',),
          "Billy Blaze builds a spaceship in his backyard, flies to Mars and has to find the parts the Vorticons "
          "stole from it to get home before his parents notice."),
    _keen('Commander Keen 2: The Earth Explodes', '19901214', ('keen2.exe',),
          "The Vorticon mothership is aiming its cannons at Earth's landmarks, and Keen has to disable them one "
          "by one."),
    _keen('Commander Keen 3: Keen Must Die!', '19901214', ('keen3.exe',),
          "Keen takes the fight to Vorticon VI to find the Grand Intellect behind the invasion."),
    _keen('Commander Keen 4: Secret of the Oracle', '19911215', ('keen4e.exe', 'keen4.exe'),
          "Keen travels to Gnosticus IV to rescue the Elders of the Oracle from the Shikadi, in the first of the "
          "Galaxy episodes with smooth scrolling and a world map."),
    _keen('Commander Keen 5: The Armageddon Machine', '19911215', ('keen5e.exe', 'keen5.exe'),
          "Keen infiltrates the Shikadi's Omegamatic space station to destroy the machine that would blow up the "
          "galaxy."),
    _keen('Commander Keen 6: Aliens Ate My Babysitter!', '1991', ('keen6e.exe', 'keen6.exe'),
          "The Bloogs of Fribbulus Xax have kidnapped Keen's babysitter, and Keen has to rescue her."),
    _keen('Commander Keen in Keen Dreams', '1991', ('kdreams.exe',),
          "Keen falls asleep and wakes up in a dream world ruled by the vegetable King Boobus Tuber, armed only "
          "with flower power."),
    _game('jazz2', 'Jazz Jackrabbit 2', '.game', ['Source/Anims.j2a'], 'Epic MegaGames', 'Gathering of Developers',
          '1998', 'Platform', '1-4',
          "Jazz and his brother Spaz chase Devan Shell through time to get Eva's stolen wedding ring back. Fast "
          "2D platforming with split-screen and network multiplayer, played through Jazz² Resurrection with the "
          "data from your own copy of the game in Source/."),
    _game('openjazz', 'Jazz Jackrabbit', '.game', ['MAINCHAR.000', 'PANEL.000'], 'Epic MegaGames',
          'Epic MegaGames', '1994', 'Platform', '1',
          "A green hare with a blaster sets out to rescue Princess Eva Earlong from the tortoise Devan Shell, "
          "across planets full of speed, secrets and bonus stages. Played through OpenJazz with the data from "
          "the shareware or full game."),
    _id_game('quake2', 'Quake II', '.pak', ['baseq2/pak0.pak'], 'baseq2/pak0.pak', 'id Software', '19971209',
             "Earth strikes back at the Strogg, a cyborg race that harvests humans for parts. You're the one marine "
             "whose pod lands off course, fighting through their home world Stroggos with the shotgun, railgun and "
             "BFG10K. Played through vitaQuake II with the data from your own copy of the game.",
             'vitaquake2', 2320),
    _id_game('quake2', 'Quake II Mission Pack: The Reckoning', '.pak', ['baseq2/pak0.pak', 'xatrix/pak0.pak'],
             'xatrix/pak0.pak', 'Xatrix Entertainment', '19980531',
             "An official expansion: infiltrate a Strogg base on one of Stroggos's moons, with new weapons such as "
             "the ion ripper and phalanx particle cannon, and new enemies. Needs the Quake II data next to it.",
             'vitaquake2-xatrix', 2330),
    _id_game('quake2', 'Quake II Mission Pack: Ground Zero', '.pak', ['baseq2/pak0.pak', 'rogue/pak0.pak'],
             'rogue/pak0.pak', 'Rogue Entertainment', '19980831',
             "An official expansion: stop the Strogg's Gravity Well before it destroys the fleet in orbit, with the "
             "chainfist, ETF rifle and plasma beam. Needs the Quake II data next to it.",
             'vitaquake2-rogue', 2340),
    _id_game('quake2', 'Zaero', '.pak', ['baseq2/pak0.pak', 'zaero/pak0.pak'], 'zaero/pak0.pak', 'Team Evolve',
             '1998',
             "A Quake II expansion with new weapons, enemies and levels, later released by id. Needs the Quake II "
             "data next to it.",
             'vitaquake2-zaero'),
    _id_game('quake3', 'Quake III Arena', '.pk3', ['baseq3/pak0.pk3'], 'baseq3/pak0.pk3', 'id Software', '19991202',
             "Fast arena deathmatch against bots, climbing the tiers of the Arena Eternal to face Xaero. Played "
             "through vitaQuake III with the data from your own copy of the game.",
             'vitaquake3', 2200),
    _id_game('doom3', 'Doom 3', '.pk4', ['base/pak000.pk4'], 'base/pak000.pk4', 'id Software', '20040803',
             "A teleportation experiment at the UAC base on Mars opens a gate to Hell. A survival horror shooter in "
             "dark corridors, with the flashlight as your best friend. Played through the boom3 core with the data "
             "from your own copy of the original game (not the BFG Edition).",
             'boom3', 9050),
    _id_game('doom3', 'Doom 3: Resurrection of Evil', '.pk4', ['base/pak000.pk4', 'd3xp/pak000.pk4'],
             'd3xp/pak000.pk4', 'Nerve Software', '20050403',
             "The official expansion: two years later, a marine finds the Artifact under Mars and with it the "
             "power to slow time, and the double-barrelled shotgun returns. Needs the Doom 3 data next to it.",
             'boom3_xp', 9070),
    _tomb_raider('Tomb Raider', ['DATA/GYM.PHD', 'DATA/TITLE.PHD'], 'DATA/TITLE.PHD', '19961025',
                 "Lara Croft searches lost tombs in Peru, Greece, Egypt and Atlantis for the pieces of the Scion. "
                 "Played through OpenLara with the data from your own copy of the PC game.",
                 224960),
    _tomb_raider('Tomb Raider II', ['data/ASSAULT.TR2', 'data/TITLE.TR2'], 'data/TITLE.TR2', '19971031',
                 "Lara goes after the Dagger of Xian from the Great Wall to Venice and an oil rig. Played through "
                 "OpenLara, where Tomb Raider II is still being worked on, so some levels may have problems.",
                 225300),
    _tomb_raider('Tomb Raider III', ['data/JUNGLE.TR2', 'data/TITLE.TR2'], 'data/TITLE.TR2', '19981120',
                 "Lara hunts the four pieces of a meteorite across India, the South Pacific, London, Nevada and "
                 "Antarctica. Played through OpenLara, where Tomb Raider III is still being worked on, so some "
                 "levels may have problems.",
                 225320),
    _game('voxatron', 'Voxatron', '.vox', [], 'Lexaloffle Games', 'Lexaloffle Games', '2011', 'Action', '1',
          "A voxel world of carts made by players, browsed and downloaded straight from the player with Splore. "
          "Opens Splore; carts you copy here as .vx.png files appear as their own games.",
          marker_name='Splore', requires=VOXATRON_PLAYER),
)

SYSTEMS = tuple(dict.fromkeys(game.system for game in PORT_GAMES))

INSTRUCTIONS = {
    'fallout1-ce': 'Copy the game folder (with MASTER.DAT and CRITTER.DAT) here.',
    'fallout2-ce': 'Copy the game folder (with master.dat and critter.dat) here.',
    'sonic-mania': "Copy Data.rsdk from your copy of Sonic Mania here.",
    'sonic3-air': 'Copy Sonic_Knuckles_wSonic3.bin from your copy of Sonic 3 & Knuckles here.',
    'sonicretro': ('Make a folder per game with its Data.rsdk inside: a name with "CD" for Sonic CD, '
                   'with "2" for Sonic 2, anything else for Sonic 1.'),
    'cannonball': 'Copy the unzipped OutRun arcade ROMs (revision B) here.',
    'reminiscence': "Copy the DOS version's DATA folder files here.",
    'cgenius': 'Make a folder per episode with the game files (KEEN1.EXE, KEEN4E.EXE and so on) inside.',
    'jazz2': 'Copy the game files into a folder called Source here.',
    'openjazz': 'Copy the game files here.',
    'quake2': ('Copy the baseq2 folder from your copy of Quake II here. Mission pack folders (xatrix, rogue, '
               'zaero) go next to it.'),
    'quake3': 'Copy the baseq3 folder from your copy of Quake III Arena here.',
    'doom3': ('Copy the base folder from your copy of Doom 3 (not the BFG Edition) here, and the d3xp folder '
              'for Resurrection of Evil.'),
    'openlara': 'Make a folder per game and copy the PC game files (with the DATA folder) into it.',
    'voxatron': ('Copy the Linux zip of Voxatron from your Lexaloffle or Humble account here to install the player. '
                 'Carts (.vx.png) can go here too.'),
}


def find_games(system_dir: Path, games: tuple[PortGame, ...]) -> dict[Path, PortGame]:
    found: dict[Path, PortGame] = {}
    folders = [system_dir, *sorted(path for path in system_dir.iterdir()
                                   if path.is_dir() and not path.name.startswith(('.', 'images')))]
    for folder in folders:
        has_marker_game = False
        for game in games:
            if not game.matches(folder, system_dir):
                continue
            if game.entry:
                found[find_file(folder, game.entry)] = game
            elif not has_marker_game:
                has_marker_game = True
                existing = sorted(path for path in folder.iterdir() if path.suffix.lower() == game.extension)
                found[existing[0] if existing else folder / f'{game.marker_name or game.title}{game.extension}'] = game
    return found


def hidden_data_files(found: dict[Path, PortGame]) -> list[Path]:
    hidden = []
    for entry, game in found.items():
        if not game.entry:
            continue
        extensions = {other.extension for other in PORT_GAMES if other.system == game.system}
        hidden += sorted(path for path in entry.parent.iterdir()
                         if path.suffix.lower() in extensions and path not in found and path not in hidden)
    return hidden


ELF_MACHINES = {'x86_64': 62, 'aarch64': 183, 'armv7l': 40}


def install_voxatron(system_dir: Path) -> bool:
    if VOXATRON_PLAYER.exists() or not system_dir.is_dir():
        return False
    wanted = ELF_MACHINES.get(platform.machine())
    for archive in sorted(path for path in system_dir.iterdir() if path.suffix.lower() == '.zip'):
        try:
            with zipfile.ZipFile(archive) as bundle:
                player = next((name for name in bundle.namelist() if name.rsplit('/', 1)[-1] == 'vox'
                               and _elf_machine(bundle.read(name)[:20]) == wanted), None)
                if player is None:
                    continue
                prefix = player[:-len('vox')]
                staging = VOXATRON_PLAYER.parent.with_name('voxatron.new')
                shutil.rmtree(staging, ignore_errors=True)
                for name in bundle.namelist():
                    if name.startswith(prefix) and not name.endswith('/'):
                        target = staging / name[len(prefix):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(bundle.read(name))
        except (OSError, zipfile.BadZipFile):
            continue
        (staging / 'vox').chmod(0o755)
        shutil.copytree(staging, VOXATRON_PLAYER.parent, dirs_exist_ok=True)
        shutil.rmtree(staging)
        return True
    return False


def _elf_machine(header: bytes) -> int | None:
    if len(header) < 20 or header[:4] != b'\x7fELF':
        return None
    return int.from_bytes(header[18:20], 'little')


def download_steam_art(appid: int, target_dir: Path) -> tuple[Path | None, Path | None]:
    return tuple(_download(STEAM_ART.format(appid=appid, name=name), target_dir / name)
                 for name in ('header.jpg', 'logo.png'))


def _download(url: str, target: Path) -> Path | None:
    try:
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    except (OSError, ValueError):
        return None
    return target
