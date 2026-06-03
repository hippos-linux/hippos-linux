# HippOS Qt 6.10 Isolated Runtime

## Why

Debian Trixie ships Qt 6.8.x. Some emulators (e.g. duckstation) require Qt 6.10+
due to API changes or prebuilt dependency bundles that link against newer Qt symbols.

Rather than replacing or conflicting with the system Qt, HippOS builds an isolated
Qt 6.10 runtime installed to `/opt/hippos/qt/6.10`. System Qt at `/usr` is untouched.
The two coexist cleanly.

At runtime, `/etc/ld.so.conf.d/hippos-qt.conf` adds `/opt/hippos/qt/6.10/lib` to the
dynamic linker cache so emulators linked against Qt 6.10 resolve their symbols correctly.
The system Qt 6.8 libs remain available for everything else.

## Build

```bash
./build/build-qt.sh
```

Builds Qt from source inside Docker, produces:

```
artifacts/qt/qt-6.10-hippos-x86_64.tar.xz
```

Build takes ~40 minutes. Run once; the tarball is cached. Pass `--force` to rebuild.

To build a specific patch version:

```bash
QT_VERSION=6.10.1 ./build/build-qt.sh
```

## Update

1. Delete the old tarball: `rm artifacts/qt/qt-6.10-hippos-x86_64.tar.xz`
2. Delete the extracted work copy: `rm -rf work/qt/6.10`
3. Run `./build/build-qt.sh --force`
4. Rebuild any emulators that use Qt 6.10
5. Re-run `./build/configure-rootfs.sh` to install the new runtime into the rootfs

If upgrading to Qt 6.11+, update:
- `docker/qt/qt610.Dockerfile` — `ARG QT_VERSION`
- `build/build-qt.sh` — tarball filename and `QT_MINOR`
- `build/qt610-env.sh` — `QT_ROOT` path
- `overlays/rootfs/etc/ld.so.conf.d/hippos-qt.conf` — lib path

## Opting in (emulator build scripts)

Add this near the top of `packages/emulators/<name>/build.sh`, before cmake:

```bash
source "/work/build/qt610-env.sh"
```

This sets:

```bash
QT_ROOT=/opt/hippos/qt/6.10
PATH=$QT_ROOT/bin:$PATH
CMAKE_PREFIX_PATH=$QT_ROOT:...
LD_LIBRARY_PATH=$QT_ROOT/lib:...
Qt6_DIR=$QT_ROOT/lib/cmake/Qt6
```

cmake then finds Qt 6.10 automatically via `find_package(Qt6 ...)`.

The emulator binary is linked against Qt 6.10 shared libs. At runtime on HippOS,
ldconfig resolves them from `/opt/hippos/qt/6.10/lib`.

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
