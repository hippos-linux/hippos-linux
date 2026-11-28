from __future__ import annotations

import json
import hashlib
import os
import platform
import sys
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from dataclasses import dataclass
from pathlib import Path

import yaml

from HipposPaths import EMULATORS_ROOT
from libretro_cores import core_file_names

SHARE_DIR = Path('usr/share/hippos/emulators')
PACKAGES_DIR = Path('userdata/emulators')
STATE_DIR = Path('var/lib/hippos/emulators')
BUILD_INFO = Path('etc/hippos-version')

PACKAGE_DIR = 'hippos'
SYSTEMS_FILE = 'systems.yml'
BASE_FEATURES_FILE = 'es_features.cfg'
INSTALLED_SHA256_FILE = '.hippos-sha256'

ES_SYSTEMS = 'es_systems.cfg'
ES_FEATURES = 'es_features.cfg'
LAUNCHER_DEFAULTS = 'defaults.json'
XWAYLAND_EMULATORS = 'xwayland-emulators'
STAMP = 'stamp'
APPLICATIONS_EXPORT = Path('exports') / 'share' / 'applications'

DEFAULT_COMMAND = (
    "emulatorlauncher %CONTROLLERSCONFIG% -system %SYSTEM% -rom %ROM%"
    " -gameinfoxml %GAMEINFOXML% -systemname %SYSTEMNAME%"
)

YML_SUFFIX = '.emulator.yml'


@dataclass(frozen=True)
class EmulatorYml:
    name: str
    path: Path
    data: dict


def device_arch() -> str:
    machine = platform.machine()
    return {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(machine, machine)


def load_yaml(path: Path) -> dict:
    with path.open(encoding='utf-8') as f:
        return yaml.load(f, Loader=yaml.CSafeLoader) or {}


def read_emulator_yml(path: Path) -> EmulatorYml:
    return EmulatorYml(path.name.removesuffix(YML_SUFFIX), path, load_yaml(path))


def installed_packages(packages_root: Path) -> list[Path]:
    if not packages_root.is_dir():
        return []
    return sorted(p for p in packages_root.iterdir() if p.is_dir() and not p.name.endswith('.new'))


def package_emulator_ymls(packages_root: Path) -> list[Path]:
    return [yml for package in installed_packages(packages_root)
            for yml in sorted((package / PACKAGE_DIR).glob(f'*{YML_SUFFIX}'))]


def collect_emulator_ymls(image_ymls: list[Path], package_ymls: list[Path]) -> list[EmulatorYml]:
    by_name: dict[str, EmulatorYml] = {}
    for path in [*image_ymls, *package_ymls]:
        try:
            emulator = read_emulator_yml(path)
        except (OSError, yaml.YAMLError) as e:
            print(f"Skipping {path}: {e}", file=sys.stderr)
            continue
        by_name[emulator.name] = emulator
    return [by_name[name] for name in sorted(by_name)]


def package_present(packages_root: Path | None, name: str) -> bool:
    return packages_root is None or (packages_root / name).is_dir()


def shipped_appstream_ids(root: Path = Path('/')) -> dict[str, str]:
    packages_root = root / PACKAGES_DIR
    emulators = collect_emulator_ymls(sorted((root / SHARE_DIR).glob(f'*{YML_SUFFIX}')),
                                      package_emulator_ymls(packages_root))
    shipped = {}
    for emulator in emulators:
        require = emulator.data.get('requireArtifact')
        if require is not None and not package_present(packages_root, require):
            continue
        for app_id in emulator.data.get('appstream_ids') or []:
            shipped[str(app_id).removesuffix('.desktop').lower()] = emulator.name
    return shipped


def available_core_files(packages_root: Path | None) -> set[str] | None:
    if packages_root is None:
        return None
    return {core.name for core in packages_root.glob('*/cores/*_libretro.so')}


def core_available(core: str, core_files: set[str] | None) -> bool:
    return core_files is None or any(name in core_files for name in core_file_names(core))


def emulator_targets(emulator: EmulatorYml):
    systems = emulator.data.get('systems')
    if isinstance(systems, list):
        for entry in systems:
            if isinstance(entry, str):
                yield entry, [emulator.name]
            elif isinstance(entry, dict) and entry.get('name'):
                cores = entry.get('as_core', [emulator.name])
                yield entry['name'], cores if isinstance(cores, list) else [str(cores)]
    elif isinstance(systems, dict):
        for sysname, sysdata in systems.items():
            if sysdata is None:
                cores = [emulator.name]
            elif isinstance(sysdata, dict):
                cores = sysdata.get('as_core', [emulator.name])
                if not isinstance(cores, list):
                    cores = [str(cores)]
            elif isinstance(sysdata, list):
                cores = sysdata
            elif isinstance(sysdata, (str, int)):
                cores = [str(sysdata)]
            else:
                cores = [emulator.name]
            yield sysname, cores


def system_emulator_map(emulators: list[EmulatorYml], packages_root: Path | None,
                        arch: str) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    core_files = available_core_files(packages_root)

    for emulator in emulators:
        arch_filter = emulator.data.get('arch')
        if arch_filter is not None and arch not in arch_filter:
            continue
        require = emulator.data.get('requireArtifact')
        if require is not None and not package_present(packages_root, require):
            continue

        hosts_cores = packages_root is not None and require is not None and (packages_root / require / 'cores').is_dir()
        for sysname, cores in emulator_targets(emulator):
            names = [str(c) for c in cores]
            if hosts_cores:
                names = [c for c in names if core_available(c, core_files)]
                if not names:
                    continue
            result.setdefault(sysname, {}).setdefault(emulator.name, []).extend(names)

    return result


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def xml_escape(value: object) -> str:
    return saxutils.escape(str(value))


def emit_system(sysname: str, sysdata: dict, emulators: dict[str, list[str]],
                defaults: dict, emu_defaults: dict) -> list[str]:
    if not emulators and not sysdata.get('force'):
        return []

    command = sysdata.get('command', defaults.get('command', DEFAULT_COMMAND))
    path = sysdata.get('path', f'/userdata/roms/{sysname}')
    ext_str = ' '.join(f'.{e}' for e in sysdata.get('extensions', []))
    platform_name = sysdata.get('platform', sysname)
    theme = sysdata.get('theme', sysname)
    group = sysdata.get('group', '')

    lines = ['  <system>']
    lines.append(f"        <fullname>{xml_escape(sysdata['name'])}</fullname>")
    lines.append(f'        <name>{sysname}</name>')
    lines.append(f"        <manufacturer>{xml_escape(sysdata.get('manufacturer', ''))}</manufacturer>")
    lines.append(f"        <release>{xml_escape(sysdata.get('release', ''))}</release>")
    lines.append(f"        <hardware>{xml_escape(sysdata.get('hardware', ''))}</hardware>")

    if path and ext_str:
        lines.append(f'        <path>{xml_escape(path)}</path>')
        lines.append(f'        <extension>{ext_str}</extension>')
        lines.append(f'        <command>{command}</command>')

    if platform_name:
        lines.append(f'        <platform>{xml_escape(platform_name)}</platform>')

    lines.append(f'        <theme>{xml_escape(theme)}</theme>')

    if group:
        lines.append(f'        <group>{xml_escape(group)}</group>')

    if emulators:
        sys_default = emu_defaults.get(sysname, {})
        decl_emu = sys_default.get('emulator', '')
        decl_core = sys_default.get('core', '')
        if decl_emu and decl_core and decl_emu in emulators:
            default_pair = (decl_emu, decl_core)
        else:
            first_emu = min(emulators)
            default_pair = (first_emu, emulators[first_emu][0] if emulators[first_emu] else '')

        lines.append('        <emulators>')
        for emu_name, cores in sorted(emulators.items()):
            lines.append(f'            <emulator name="{xml_escape(emu_name)}">')
            lines.append('                <cores>')
            for core in dedupe(cores):
                default_attr = ' default="true"' if (emu_name, core) == default_pair else ''
                lines.append(f'                    <core{default_attr}>{xml_escape(core)}</core>')
            lines.append('                </cores>')
            lines.append('            </emulator>')
        lines.append('        </emulators>')

    lines.append('  </system>')
    return lines


def split_systems_data(systems_data: dict, arch: str) -> tuple[dict, dict, dict]:
    systems = dict(systems_data)
    defaults = systems.pop('_defaults', {})
    emu_defaults = systems.pop('_emulator_defaults', {})
    arch_defaults = {key: systems.pop(key) for key in list(systems) if key.startswith('_emulator_defaults_')}
    emu_defaults = {**emu_defaults, **arch_defaults.get(f'_emulator_defaults_{arch}', {})}
    return systems, defaults, emu_defaults


def generate_es_systems(systems_data: dict, emulators: list[EmulatorYml],
                        packages_root: Path | None, arch: str) -> str:
    systems, defaults, emu_defaults = split_systems_data(systems_data, arch)
    emulator_map = system_emulator_map(emulators, packages_root, arch)

    lines = ['<?xml version="1.0" encoding="UTF-8" ?>', '<systemList>']
    for sysname, sysdata in systems.items():
        if isinstance(sysdata, dict):
            lines.extend(emit_system(sysname, sysdata, emulator_map.get(sysname, {}), defaults, emu_defaults))
    lines.append('</systemList>')
    return '\n'.join(lines) + '\n'


def generate_launcher_defaults(systems_data: dict, es_systems: str, emulators: list[EmulatorYml]) -> str:
    root = ET.fromstring(es_systems)
    defaults = {name: dict(entry) for name, entry in systems_data['_emulator_defaults'].items()}
    for system in root.iter('system'):
        name = system.findtext('name')
        for emulator in system.iter('emulator'):
            for core in emulator.iter('core'):
                if core.get('default') == 'true':
                    entry = defaults.setdefault(name, {})
                    entry['emulator'], entry['core'] = emulator.get('name'), core.text

    excluded: dict[str, dict[str, list[str]]] = {}
    for emulator in emulators:
        for target in emulator.data.get('systems') or []:
            if isinstance(target, dict) and target.get('exclude_extensions'):
                excluded.setdefault(target['name'], {})[emulator.name] = sorted(
                    f'.{e}' for e in map(str, target['exclude_extensions']))
    for system in root.iter('system'):
        name = system.findtext('name')
        if name not in excluded:
            continue
        defaults.setdefault(name, {})['candidates'] = [
            {'emulator': emulator.get('name'), 'core': core.text,
             **({'exclude_extensions': excluded[name][emulator.get('name')]}
                if emulator.get('name') in excluded[name] else {})}
            for emulator in system.iter('emulator') for core in emulator.iter('core')
        ]
    return json.dumps(defaults, sort_keys=True, indent=2) + '\n'


def generate_xwayland_emulators(emulators: list[EmulatorYml]) -> str:
    return ''.join(f'{emulator.name}\n' for emulator in emulators if emulator.data.get('display') == 'xwayland')


def merge_es_features(base: Path, fragments: list[Path]) -> str:
    tree = ET.parse(base)
    root = tree.getroot()
    for fragment in fragments:
        try:
            emulators = ET.parse(fragment).getroot().findall('emulator')
        except ET.ParseError as e:
            print(f"Skipping {fragment}: {e}", file=sys.stderr)
            continue
        for emulator in emulators:
            for existing in root.findall(f"emulator[@name='{emulator.get('name')}']"):
                root.remove(existing)
            root.append(emulator)
    ET.indent(tree, space='  ')
    return '<?xml version="1.0" encoding="UTF-8" ?>\n' + ET.tostring(root, encoding='unicode') + '\n'


def write_if_changed(path: Path, content: str) -> bool:
    if path.is_file() and path.read_text(encoding='utf-8') == content:
        return False
    tmp = path.with_name(f'.{path.name}.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.chmod(0o644)
    os.replace(tmp, path)
    return True


def export_applications(packages_root: Path, export_dir: Path) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    wanted = {desktop.name: EMULATORS_ROOT / package.name / PACKAGE_DIR / 'applications' / desktop.name
              for package in installed_packages(packages_root)
              for desktop in sorted((package / PACKAGE_DIR / 'applications').glob('*.desktop'))}
    for link in export_dir.iterdir():
        if link.is_symlink() and wanted.get(link.name) != Path(os.readlink(link)):
            link.unlink()
    for name, target in wanted.items():
        link = export_dir / name
        if not link.is_symlink():
            link.symlink_to(target)


def generate(share_dir: Path, packages_root: Path, state_dir: Path, arch: str) -> bool:
    systems_data = load_yaml(share_dir / SYSTEMS_FILE)
    emulators = collect_emulator_ymls(sorted(share_dir.glob(f'*{YML_SUFFIX}')), package_emulator_ymls(packages_root))
    es_systems = generate_es_systems(systems_data, emulators, packages_root, arch)
    fragments = [package / PACKAGE_DIR / ES_FEATURES for package in installed_packages(packages_root)
                 if (package / PACKAGE_DIR / ES_FEATURES).is_file()]

    state_dir.mkdir(parents=True, exist_ok=True)
    changed = write_if_changed(state_dir / ES_SYSTEMS, es_systems)
    changed |= write_if_changed(state_dir / ES_FEATURES, merge_es_features(share_dir / BASE_FEATURES_FILE, fragments))
    changed |= write_if_changed(state_dir / LAUNCHER_DEFAULTS,
                                generate_launcher_defaults(systems_data, es_systems, emulators))
    write_if_changed(state_dir / XWAYLAND_EMULATORS, generate_xwayland_emulators(emulators))
    export_applications(packages_root, state_dir / APPLICATIONS_EXPORT)
    return changed


def build_id(build_info: Path) -> str:
    try:
        lines = build_info.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return ''
    return next((line.split('=', 1)[1].strip() for line in lines if line.startswith('BUILD_ID=')), '')


def inputs_stamp(build_info: Path, packages_root: Path) -> str:
    digest = hashlib.sha256(build_id(build_info).encode())
    for package in installed_packages(packages_root):
        sha_file = package / INSTALLED_SHA256_FILE
        sha = sha_file.read_text(encoding='utf-8').strip() if sha_file.is_file() else '-'
        digest.update(f'\0{package.name}\0{sha}'.encode())
    return digest.hexdigest()


def sync(root: Path = Path('/'), arch: str | None = None, force: bool = False) -> bool:
    packages_root = root / PACKAGES_DIR
    state_dir = root / STATE_DIR
    stamp = inputs_stamp(root / BUILD_INFO, packages_root)
    stamp_file = state_dir / STAMP
    if not force and stamp_file.is_file() and stamp_file.read_text(encoding='utf-8').strip() == stamp:
        return False
    changed = generate(root / SHARE_DIR, packages_root, state_dir, arch or device_arch())
    write_if_changed(stamp_file, stamp + '\n')
    return changed
