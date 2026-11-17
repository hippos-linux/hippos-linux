<div align="center">

# HippOS

### A gaming OS that boots straight into your library

**[Download](https://hippos-linux.org) · [Website](https://hippos-linux.org) · [Issues](https://github.com/hippos-linux/hippos-linux/issues)**

</div>

---

HippOS is a Debian-based gaming OS for x86 PCs and Raspberry Pi 4/5. Power it on and you're in EmulationStation — no desktop, no login screen, no configuration required. Your games, saves, and settings live on a separate persistent partition and survive every OS update.

---

## Platforms

| Platform | Support |
|---|---|
| x86-64 PC (AMD / Intel GPU) | Full |
| x86-64 PC (NVIDIA) | Via Debian Trixie drivers |
| Raspberry Pi 5 | Full |
| Raspberry Pi 4 | Full |
| Handheld PCs | Full (InputPlumber for built-in controls) |

---

## What's included

### 280+ systems

78 consoles · 73 computers · 41 portables · 39 arcade platforms · game engines · ports · and more.

Covering everything from Atari 2600 to PS4, Commodore 64 to Amiga, Game Boy to PS Vita, MAME arcade to Windows PC arcade cabinets (TypeX, RingEdge, Nesica, Lindbergh, and 15 more via WindowsArcadeLoader).

### 85+ emulators built from source

| Platform | Emulators |
|---|---|
| Multi-system | RetroArch (100+ cores), MAME |
| PlayStation | DuckStation, PCSX2, RPCS3, shadPS4 |
| Nintendo | Dolphin, Ryujinx, Cemu, melonDS, mupen64plus, NanoBoyAdvance |
| Xbox | xemu (+ Chihiro), Xenia, Xenia Canary |
| Sega | Flycast, Redream, Supermodel, Model 2 Emulator |
| Windows Arcade PC | WindowsArcadeLoader (TypeX, RingEdge, Nesica, Lindbergh, and more) |
| Computers | VICE, openMSX, FS-UAE, Hatari, BasiliskII, GSplus, AppleWin |
| Handhelds | PPSSPP, DraStic, EKA2L1, Vita3K |
| Other | ScummVM, BigPEmu, xroar, x16emu, EasyRPG, IKEMEN GO, and more |

### App support

- **Linux Games** — native games installed via Discover, apt, or the Content Downloader
- **Linux Apps** — Flatpak apps, web apps (Netflix, YouTube, Spotify, etc.), and desktop shortcuts
- **AppImage drop-zone** — drop any `.AppImage` into `/roms/appimages`, a launcher appears automatically in Linux Games or Linux Apps based on its category
- **Steam, Heroic, Lutris, Waydroid** — available from the Apps tab
- **Windows 98** — runs in DOSBox Pure, per-game save state
- **Wine + box64** on Raspberry Pi

### In-game quick menu

Press **Hotkey+A** in any game to open the quick menu:

- Save and load states
- Controller-as-mouse toggle
- On-screen keyboard
- Brightness, volume, and power mode
- CPU/GPU stats
- Per-game pad-to-keyboard key editor

### Media centers

Install **Kodi, Jellyfin, Emby Theater, or Plex HTPC** directly from the main menu. Controller-driven, with on-screen keyboard and controller-as-mouse.

### OTA updates

- Updates swap the `@rootfs` btrfs subvolume with automatic rollback support
- Games, saves, and settings on `@userdata` are never touched
- apt packages you installed survive updates — reinstalled automatically
- Files you added to the system are kept; changed system files are backed up instead of overwritten
- Live update progress and notifications in the UI

### Controllers

- Automatic button layout detection — face buttons show as your controller's icons
- Xbox One/Series, DualShock, DualSense, Switch Pro, Steam Controller 2 — all supported
- Xbox controllers work over Bluetooth
- Light guns: AimTrak, GunCon 2/3, GUN4IR, OpenFIRE, Sinden, and more
- Racing wheels: force feedback for Logitech and Thrustmaster
- Per-game TDP and power profiles

### Storage and network

- SMB and NFS shares discovered and merged into your library in one press
- Saves written back to network shares where permitted
- External USB drives pooled into your library on plug-in
- btrfs `@userdata` subvolume — persistent, update-safe, easy to back up

---

## Installing

1. Download the latest image from **[hippos-linux.org](https://hippos-linux.org)**
2. Flash the `.img.zst` to a USB drive or install to an internal disk
3. Boot

---

## Repository layout

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

---

## Building

Emulators build independently inside Docker (Ubuntu 24.04), producing artifacts under `artifacts/`:

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
