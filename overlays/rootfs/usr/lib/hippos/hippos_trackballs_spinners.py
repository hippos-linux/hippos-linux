#!/usr/bin/env python3
"""Usage: hippos-trackballs-spinners --list [--xml]
       hippos-trackballs-spinners --detect-trackball|--detect-spinner [--save-detection] [--detection-duration SECONDS]
       hippos-trackballs-spinners --unregister KEY
"""
from __future__ import annotations

import argparse
import os
import re
import select
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import evdev
import yaml
from evdev import ecodes

SYSTEM_DB = Path('/usr/share/hippos/trackballspinners.yaml')
USER_DB = Path('/userdata/system/configs/hippos/trackballspinners.yaml')
UDEV_DATA = Path('/run/udev/data')

AXES = {ecodes.REL_X: 'REL_X', ecodes.REL_Y: 'REL_Y'}
EVENT_NODE = re.compile(r'^/dev/input/event(\d+)$')
MIN_DETECTION_MOTION = 50


@dataclass(frozen=True)
class InputNode:
    path: str
    name: str
    vendor: int
    product: int
    version: int
    interface: int
    axes: tuple[str, ...]
    mouse_index: int | None


@dataclass(frozen=True)
class Control:
    name: str
    type: str
    axes: tuple[str, ...]
    source: str
    node: InputNode

    @property
    def key(self) -> str:
        n = self.node
        return f'{self.type}-{n.vendor:04x}-{n.product:04x}-{n.version:04x}-{n.interface}-{"+".join(self.axes)}'


def _udev_properties(path: str) -> dict[str, str]:
    minor = os.minor(os.stat(path).st_rdev)
    try:
        lines = (UDEV_DATA / f'c13:{minor}').read_text().splitlines()
    except OSError:
        return {}
    return dict(line[2:].partition('=')[::2] for line in lines if line.startswith('E:'))


def input_nodes() -> list[InputNode]:
    found = []
    for path in sorted(evdev.list_devices(), key=lambda p: int(EVENT_NODE.match(p).group(1))):
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        rel = device.capabilities().get(ecodes.EV_REL, [])
        props = _udev_properties(path)
        found.append((device, tuple(AXES[c] for c in sorted(AXES) if c in rel), props))
        device.close()

    nodes = []
    mouse_index = 0
    for device, axes, props in found:
        index = None
        if props.get('ID_INPUT_MOUSE') == '1':
            index = mouse_index
            mouse_index += 1
        if not axes:
            continue
        nodes.append(InputNode(
            path=device.path, name=device.name,
            vendor=device.info.vendor, product=device.info.product, version=device.info.version,
            interface=int(props.get('ID_USB_INTERFACE_NUM', '0'), 16),
            axes=axes, mouse_index=index,
        ))
    return nodes


def _load_db(path: Path) -> list[dict]:
    try:
        return yaml.load(path.read_text(), Loader=yaml.CSafeLoader) or []
    except FileNotFoundError:
        return []


def _entry_matches(entry: dict, node: InputNode) -> bool:
    return (entry['vendor'] == node.vendor and entry['product'] == node.product
            and entry.get('version', node.version) == node.version
            and entry.get('interface', node.interface) == node.interface
            and set(entry['axis']) <= set(node.axes))


def registered(nodes: list[InputNode] | None = None) -> list[Control]:
    nodes = input_nodes() if nodes is None else nodes
    controls = []
    for source, path in (('user', USER_DB), ('system', SYSTEM_DB)):
        for entry in _load_db(path):
            for node in nodes:
                if _entry_matches(entry, node):
                    control = Control(entry['name'], entry['type'], tuple(entry['axis']), source, node)
                    if all(c.key != control.key for c in controls):
                        controls.append(control)
    return sorted(controls, key=lambda c: (c.node.mouse_index is None, c.node.mouse_index or 0, c.axes))


def mouse_indexes(control_type: str) -> list[int]:
    return [c.node.mouse_index for c in registered()
            if c.type == control_type and c.node.mouse_index is not None]


def candidates(control_type: str, nodes: list[InputNode]) -> list[Control]:
    known = {c.key for c in registered(nodes)}
    if control_type == 'trackball':
        found = [Control(n.name, 'trackball', ('REL_X', 'REL_Y'), 'user', n)
                 for n in nodes if n.axes == ('REL_X', 'REL_Y')]
    else:
        found = [Control(n.name if axis == 'REL_X' else f'{n.name} ({axis})', 'spinner', (axis,), 'user', n)
                 for n in nodes for axis in n.axes]
    return [c for c in found if c.key not in known]


def detect(control_type: str, duration: int) -> Control | None:
    options = candidates(control_type, input_nodes())
    devices = {}
    for path in {c.node.path for c in options}:
        try:
            devices[path] = evdev.InputDevice(path)
        except OSError:
            pass
    motion: dict[tuple[str, str], int] = {}
    deadline = time.monotonic() + duration
    try:
        while devices and (remaining := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select(list(devices.values()), [], [], remaining)
            for device in ready:
                for event in device.read():
                    if event.type == ecodes.EV_REL and event.code in AXES:
                        axis_key = (device.path, AXES[event.code])
                        motion[axis_key] = motion.get(axis_key, 0) + abs(event.value)
            if motion:
                best = _best_match(control_type, options, motion)
                if best is not None:
                    return best
    finally:
        for device in devices.values():
            device.close()
    return None


def _best_match(control_type: str, options: list[Control], motion: dict[tuple[str, str], int]) -> Control | None:
    scored = []
    for control in options:
        moved = [motion.get((control.node.path, axis), 0) for axis in control.axes]
        if control_type == 'trackball' and min(moved) < MIN_DETECTION_MOTION:
            continue
        if control_type == 'spinner':
            other = sum(v for (path, axis), v in motion.items() if path == control.node.path and axis not in control.axes)
            if moved[0] < MIN_DETECTION_MOTION or other > moved[0]:
                continue
        scored.append((sum(moved), control))
    return max(scored, key=lambda s: s[0])[1] if scored else None


def save(control: Control) -> None:
    entries = _load_db(USER_DB)
    n = control.node
    entries.append({'name': control.name, 'type': control.type, 'vendor': n.vendor, 'product': n.product,
                    'version': n.version, 'interface': n.interface, 'axis': list(control.axes)})
    USER_DB.parent.mkdir(parents=True, exist_ok=True)
    USER_DB.write_text(yaml.safe_dump(entries, sort_keys=False))


def unregister(key: str) -> bool:
    nodes = input_nodes()
    entries = _load_db(USER_DB)
    kept = [e for e in entries
            if not any(c.key == key and c.source == 'user' and _entry_matches(e, c.node) and tuple(e['axis']) == c.axes
                       for c in registered(nodes))]
    if len(kept) == len(entries):
        return False
    USER_DB.write_text(yaml.safe_dump(kept, sort_keys=False))
    return True


def print_list(as_xml: bool) -> None:
    controls = registered()
    if as_xml:
        root = ET.Element('trackballspinners')
        for c in controls:
            ET.SubElement(root, 'trackballspinner', name=c.name, type=c.type, key=c.key,
                          axis=', '.join(c.axes), source=c.source)
        ET.indent(root)
        print(ET.tostring(root, encoding='unicode'))
        return
    for c in controls:
        print(f'{c.type}\t{c.name}\t{c.node.path}\tmouse {c.node.mouse_index}\t{c.source}\t{c.key}')


def main() -> int:
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--xml', action='store_true')
    parser.add_argument('--detect-trackball', action='store_true')
    parser.add_argument('--detect-spinner', action='store_true')
    parser.add_argument('--save-detection', action='store_true')
    parser.add_argument('--detection-duration', type=int, default=8)
    parser.add_argument('--unregister', metavar='KEY')
    args = parser.parse_args()

    if args.list:
        print_list(args.xml)
    elif args.detect_trackball or args.detect_spinner:
        control_type = 'trackball' if args.detect_trackball else 'spinner'
        if sys.stdout.isatty():
            print(f'Move the {control_type}...', file=sys.stderr)
        control = detect(control_type, args.detection_duration)
        if control is None:
            print(f'No {control_type} detected', file=sys.stderr)
            return 1
        print(f'{control.name} detected')
        if args.save_detection:
            save(control)
    elif args.unregister:
        return 0 if unregister(args.unregister) else 1
    else:
        parser.print_usage()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
