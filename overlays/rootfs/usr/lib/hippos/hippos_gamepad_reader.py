from __future__ import annotations

import selectors
import threading
from typing import Callable

import evdev
import pyudev
from evdev import ecodes
from gi.repository import GLib

from hippos_es_buttons import DPAD_BUTTONS, button_names, es_input_root, joystick_button_maps

ButtonHandler = Callable[[str, bool], bool]
HatHandler = Callable[[int, int], bool]


class GamepadReader(threading.Thread):
    def __init__(self, on_button: ButtonHandler, on_hat: HatHandler) -> None:
        super().__init__(daemon=True)
        self.on_button = on_button
        self.on_hat = on_hat
        self.selector = selectors.DefaultSelector()
        self.devices: dict[str, evdev.InputDevice] = {}
        self.names: dict[str, dict[int, str]] = {}
        self.lock = threading.Lock()
        self.grabbing = False

    def add(self, path: str) -> None:
        with self.lock:
            if path in self.devices:
                return
            try:
                device = evdev.InputDevice(path)
                keys = device.capabilities().get(ecodes.EV_KEY, [])
            except OSError:
                return
            if ecodes.BTN_SOUTH not in keys:
                device.close()
                return
            self.devices[path] = device
            self.names[path] = DPAD_BUTTONS | button_names(device.name, set(keys), joystick_button_maps(es_input_root()))
            self.selector.register(device, selectors.EVENT_READ)
            if self.grabbing:
                self._grab(device)

    def remove(self, path: str) -> None:
        with self.lock:
            device = self.devices.pop(path, None)
            self.names.pop(path, None)
            if device is not None:
                self.selector.unregister(device)
                device.close()

    def set_grab(self, grab: bool) -> None:
        with self.lock:
            self.grabbing = grab
            for device in self.devices.values():
                self._grab(device) if grab else self._ungrab(device)

    @staticmethod
    def _grab(device: evdev.InputDevice) -> None:
        try:
            device.grab()
        except OSError:
            pass

    @staticmethod
    def _ungrab(device: evdev.InputDevice) -> None:
        try:
            device.ungrab()
        except OSError:
            pass

    def run(self) -> None:
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='input')
        monitor.start()
        self.selector.register(monitor, selectors.EVENT_READ)
        for device in context.list_devices(subsystem='input'):
            if device.device_node and device.device_node.startswith('/dev/input/event'):
                self.add(device.device_node)
        while True:
            for selected, _ in self.selector.select():
                if selected.fileobj is monitor:
                    udev_device = monitor.poll(0)
                    node = udev_device.device_node if udev_device else None
                    if node and node.startswith('/dev/input/event'):
                        self.add(node) if udev_device.action == 'add' else self.remove(node)
                    continue
                self.read(selected.fileobj)

    def read(self, device: evdev.InputDevice) -> None:
        try:
            for event in device.read():
                name = self.names.get(device.path, {}).get(event.code)
                if event.type == ecodes.EV_KEY and event.value in (0, 1) and name:
                    GLib.idle_add(self.on_button, name, event.value == 1)
                elif event.type == ecodes.EV_ABS and event.code in (ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y):
                    GLib.idle_add(self.on_hat, event.code, event.value)
        except OSError:
            self.remove(device.path)
