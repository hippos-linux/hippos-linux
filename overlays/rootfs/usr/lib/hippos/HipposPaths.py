from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeUpdating, OpenBinaryModeWriting, OpenTextModeUpdating, OpenTextModeWriting
    from collections.abc import Iterator
    from io import BufferedRandom, BufferedWriter, TextIOWrapper

HIPPOS_SHARE_DIR: Final = Path('/usr/share/hippos')
DATAINIT_DIR: Final = HIPPOS_SHARE_DIR / 'datainit'
USERDATA: Final = Path('/userdata')
# Bind mount of /userdata/emulators: bundled and updated emulator packages.
EMULATORS_ROOT: Final = Path('/opt/emulators')

HOME_INIT: Final = DATAINIT_DIR / 'system'
CONF_INIT: Final = HOME_INIT / 'configs'

HOME: Final = USERDATA / 'system'
CONFIGS: Final = HOME / 'configs'
EVMAPY: Final = CONFIGS / 'evmapy'
SAVES: Final = USERDATA / 'saves'
SCREENSHOTS: Final = USERDATA / 'screenshots'
RECORDINGS: Final = USERDATA / 'recordings'
BIOS: Final = USERDATA / 'bios'
OVERLAYS: Final = USERDATA / 'overlays'
CACHE: Final = USERDATA / 'cache'
ROMS: Final = USERDATA / 'roms'
CHEATS: Final = USERDATA / 'cheats'
LOGS: Final = HOME / 'logs'
HIPPOS_CONF: Final = HOME / 'hippos.conf'

USER_ES_DIR: Final = CONFIGS / 'emulationstation'
HIPPOS_ES_DIR: Final = Path('/usr/share/emulationstation')
EMULATORLAUNCHER_SHARE_DIR: Final = HIPPOS_SHARE_DIR / 'emulatorlauncher'
EMULATORLAUNCHER_DATA_DIR: Final = EMULATORLAUNCHER_SHARE_DIR / 'data'
# Per-system emulator, core and options; generated at build time from
# packages/frontend/systems.yml's _emulator_defaults, which ES also shows.
EMULATORLAUNCHER_DEFAULTS: Final = EMULATORLAUNCHER_SHARE_DIR / 'defaults.yml'

_ES_RESOURCES_DIR: Final = HIPPOS_ES_DIR / 'resources'

ES_SETTINGS: Final = USER_ES_DIR / 'es_settings.cfg'
ES_GUNS_METADATA: Final = _ES_RESOURCES_DIR / 'gungames.xml'
ES_WHEELS_METADATA: Final = _ES_RESOURCES_DIR / 'wheelgames.xml'
ES_GAMES_METADATA: Final = _ES_RESOURCES_DIR / 'gamesdb.xml'

USER_SHADERS: Final = USERDATA / 'shaders'
HIPPOS_SHADERS: Final = Path('/usr/share/libretro/shaders')

USER_DECORATIONS: Final = USERDATA / 'decorations'
SYSTEM_DECORATIONS: Final = DATAINIT_DIR / 'decorations'

USER_SCRIPTS: Final = HOME / 'scripts'


def configure_emulator(rom: Path, /) -> bool:
    return str(rom) == 'config'


def mkdir_if_not_exists(dir: Path, /) -> None:
    if not dir.exists():
        dir.mkdir(parents=True)


@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenTextModeWriting | OpenTextModeUpdating) -> Iterator[TextIOWrapper]:
    ...

@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenBinaryModeUpdating) -> Iterator[BufferedRandom]:
    ...

@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenBinaryModeWriting) -> Iterator[BufferedWriter]:
    ...

@contextmanager
def ensure_parents_and_open(file: Path, mode: str) -> Iterator[IO[Any]]:
    mkdir_if_not_exists(file.parent)
    with file.open(mode) as f:
        yield f
