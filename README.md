# HippOS

**A console-style gaming OS for x86 PCs and Raspberry Pi.**
Boot straight into your game library — no desktop, no setup, no fuss.

[hippos-linux.org](https://hippos-linux.org) · [Releases](https://hippos-linux.org) · [Issues](https://github.com/hippos-linux/hippos-linux/issues)

---

HippOS turns any x86-64 PC or Raspberry Pi 4/5 into a dedicated gaming appliance. It boots directly into EmulationStation, keeps your games and saves on a persistent subvolume that survives OS updates, and ships 85+ emulators built from source covering 280+ systems — all controller-driven from the couch.

---

## Features

**Gaming first**
- Boots directly into EmulationStation — no desktop, no login screen
- Controller-first navigation with automatic button layout detection
- In-game quick menu (Hotkey+A): save states, on-screen keyboard, brightness, volume, CPU/GPU stats, pad-to-keyboard key editor
- Scraper, game metadata, and boxart built in

**Library**
- 280+ systems covered — retro consoles, handhelds, computers, arcade, Windows PC arcade cabinets
- AppImage drop-zone: drop `.AppImage` files into `/roms/appimages`, launchers appear in Linux Games or Linux Apps automatically
- Flatpak support with the Content Downloader
- Steam, Heroic, Lutris, and Waydroid available via the Apps tab
- Native Linux games and web apps alongside emulated content

**Updates**
- OTA updates swap the `@rootfs` btrfs subvolume with automatic rollback support
- Games, saves, settings, and manually installed apt packages survive every update
- Live update progress and notifications in the UI

**Media**
- Media center mode: Kodi, Jellyfin, Emby Theater, or Plex HTPC — installed on demand, controller-driven
- Desktop mode available when needed

**Hardware**
- x86-64 PC with UEFI firmware
- Raspberry Pi 4 and Pi 5
- AMD and Intel integrated graphics are primary targets on x86
- NVIDIA support via Debian Trixie driver availability
- Handheld PC controls via InputPlumber

---

## Emulators

85+ emulators built from source, including:

| Category | Emulators |
|---|---|
| Multi-system | RetroArch (100+ cores), MAME |
| PlayStation | DuckStation, PCSX2, RPCS3, shadPS4 |
| Nintendo | Dolphin, Ryujinx, Cemu, melonDS, mupen64plus, NanoBoyAdvance |
| Xbox | xemu, Xenia / Xenia Canary |
| Sega | Flycast, Redream, Supermodel, Model 2 Emulator |
| Arcade PC | WindowsArcadeLoader (TypeX, RingEdge, Nesica, and 15 more) |
| Computers | VICE, openMSX, FS-UAE, Hatari, BasiliskII, GSplus, AppleWin |
| Handhelds | PPSSPP, DraStic, EKA2L1, Vita3K |
| Other | ScummVM, BigPEmu, xroar, x16emu, EasyRPG, ikemen, and more |

---

## Installing

1. Download the latest image from [hippos-linux.org](https://hippos-linux.org)
2. Flash the `.img.zst` to a USB drive or install to an internal disk
3. Boot — that's it

---

## Repository layout

```
overlays/       Files copied verbatim into the rootfs at build time
packages/       Per-emulator build scripts and system definitions
  emulators/    One directory per emulator with build.sh and .emulator.yml
  frontend/     EmulationStation config: systems.yml, themes
src/            EmulationStation frontend source, website
catalog/        Content store package catalog
tools/          Build and development utilities
themes/         ES theme submodules
tests/          Integration and unit tests
docs/           Build and runtime notes
release-notes/  Per-version changelogs
```

---

## Building

Each emulator is built independently via its `packages/emulators/<name>/build.sh`. Build scripts run in Docker (Ubuntu 24.04) and produce artifacts under `artifacts/`.

```sh
./packages/emulators/dolphin-emu/build.sh
```

The full OS image is assembled from the rootfs overlay, built emulator artifacts, and the EmulationStation frontend.

---

## Credits

- [EmulationStation (Batocera fork)](https://github.com/batocera-linux/batocera-emulationstation) — frontend base (GPLv2), heavily modified for HippOS
- [Batocera Linux](https://batocera.org) — inspiration and reference
- All emulator authors and communities

---

## License

Build system and OS integration code in this repository are GPL-3.0 licensed unless otherwise noted. Each bundled emulator carries its own license.

---

## Star History

<a href="https://www.star-history.com/?repos=hippos-linux%2Fhippos-linux&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&legend=top-left" />
 </picture>
</a>
