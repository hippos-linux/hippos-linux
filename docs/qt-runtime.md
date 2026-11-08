# HippOS Qt Runtime

## Why

Debian Trixie ships Qt 6.8. Some emulators need a newer Qt, for example
DuckStation, whose prebuilt dependencies are built against a specific Qt
release. HippOS builds its own Qt and installs it to `/opt/hippos/qt/6`, beside
the system Qt in `/usr`.

The path names only the major version. Qt keeps binary compatibility across
minor releases of Qt 6, so a bump to a newer 6.x doesn't change the path
emulators link against. Emulators find the libraries through their RPATH
(`QT_RPATH`), not the linker cache.

The image also links `/opt/hippos/qt/6.11` to `6`, because emulator packages
built before 0.6.8 link to that path and stay installed across OS updates until
each one is updated.

## Build

```bash
./build/build-qt.sh
```

Builds Qt from source inside Docker (`docker/qt/qt.Dockerfile`) and produces
`artifacts/qt/qt-<version>-hippos-x86_64.tar.xz`. The tarball is cached; pass
`--force` to rebuild. arm64 is cross-compiled with `ARCH=arm64` and needs the
amd64 tarball first, for host tools.

## Update

1. Set `QT_VERSION` in `build/common.sh`.
2. Run `./build/build-qt.sh` (and `ARCH=arm64 ./build/build-qt.sh`).
3. Rebuild every emulator whose `build.sh` sources `qt-env.sh`.
4. Run `./build/configure-rootfs.sh` to install the new runtime into the rootfs.

## Using it in an emulator build

After `common.sh`, source the env script:

```bash
source "/work/build/qt-env.sh"
```

It sets `QT_ROOT`, `QT_RPATH`, `PATH`, `CMAKE_PREFIX_PATH`, `LD_LIBRARY_PATH`
and `Qt6_DIR`, so `find_package(Qt6 ...)` finds HippOS's Qt. Put `QT_RPATH`
in the install RPATH:

```bash
-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
-DCMAKE_INSTALL_RPATH="${QT_RPATH}:\$ORIGIN/../lib"
```

## Modules built

| Module | Purpose |
|---|---|
| qtbase | Core, Gui, Widgets, Network, XCB/Wayland platform plugins |
| qttools | linguist, uic, moc (needed for some emulator cmake builds) |
| qtsvg | SVG rendering |
| qtmultimedia | Audio/video playback (FFmpeg backend) |
| qtwayland | Wayland compositor/client support |
| qtdeclarative | QML engine |

`qtwebengine` is intentionally excluded — it embeds Chromium and adds ~500MB.
