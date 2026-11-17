# Contributing to HippOS

## Repository Layout

```
overlays/       Files copied verbatim into the rootfs at build time
packages/
  emulators/    Per-emulator build scripts and .emulator.yml definitions (85+)
  frontend/     systems.yml, theme config
src/            EmulationStation frontend source, website
catalog/        Content Downloader package catalog
tools/          Build and development utilities
themes/         ES theme submodules
tests/          Integration and unit tests
docs/           Build and runtime notes
release-notes/  Per-version changelogs
```

## Building Emulators

Each emulator builds independently inside Docker (Ubuntu 24.04), producing artifacts under `artifacts/`:

```sh
./packages/emulators/dolphin-emu/build.sh
```

The full OS image is assembled from the rootfs overlay, built emulator artifacts, and the EmulationStation frontend.

## Adding an Emulator

1. Create `packages/emulators/<name>/build.sh` — Docker-based build producing artifacts under `artifacts/emulators/<name>/`
2. Create `packages/emulators/<name>/<name>.emulator.yml` — declares `requireArtifact`, `arch`, `features`, and `systems`
3. Add system definitions to `packages/frontend/systems.yml` if adding new systems
4. Add theme art via `tools/generate-theme-art.py` for any new systems

## Submitting Changes

Open a pull request against `main`. Include a description of what changed and why.
