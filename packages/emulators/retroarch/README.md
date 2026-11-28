# retroarch

RetroArch and its libretro cores.

The build script stages artifacts under:

`/artifacts/emulators/retroarch/`

| Folder | Contents | Source |
|---|---|---|
| `bin/retroarch` | RetroArch | Latest release tag of `https://github.com/libretro/RetroArch`, rebuilt only when the tag changes |
| `filters/audio`, `filters/video` | RetroArch's DSP and video filters | Same RetroArch source |
| `info/` | Core info files | `https://buildbot.libretro.com/assets/frontend/info.zip` |
| `cores/` | Libretro cores | libretro buildbot nightlies, plus FreeJ2ME-Plus and OpenCDi built from source |
| `freej2me/` | FreeJ2ME-Plus jar | FreeJ2ME-Plus release |

RetroArch's menu assets come from Debian's `retroarch-assets` package.

## Cores

Only cores that a system in `retroarch.emulator.yml` lists under `as_core` are downloaded, after
`libretro_cores.py` maps replaced cores and aliases. Add a core's `.so` name to `EXCLUDED_CORES` in
`build.sh` to leave it out anyway. The buildbot cores left out are posted to the dev Discord channel when
that list changes.

A core is downloaded again when its buildbot ETag changes, but the file in the package is only replaced
when `core-build-identity.py` reports a different build: nightly rebuilds of unchanged source, which differ
only in build dates and build IDs, keep the current file.

## Updates

The daily emulator build syncs this package at most once every 7 days (`INCREMENTAL_SYNCS` in
`build/build-emulators.sh`). Its version is a hash of the staged files, so devices are offered an update
only when something in the package changed.

To rebuild RetroArch at the same tag, delete `retroarch-core-etags/retroarch.built` next to the artifacts.
