<div align="center">
  <img src="https://raw.githubusercontent.com/hippos-linux/hippos-linux/main/overlays/rootfs/usr/share/icons/hicolor/128x128/apps/distributor-logo.png" width="200" alt="HippOS" /><br>
  <h1>HippOS</h1>
  <p><strong>A gaming OS that boots straight into your library.</strong></p>
</div>

<div align="center">
  <a href="https://hippos-linux.org"><img src="https://img.shields.io/badge/download-hippos--linux.org-blue?style=for-the-badge" alt="Download" /></a>
  <a href="https://github.com/hippos-linux/hippos-linux/stargazers"><img src="https://img.shields.io/github/stars/hippos-linux/hippos-linux?style=for-the-badge&logo=github" alt="Stars" /></a>
  <a href="https://github.com/hippos-linux/hippos-linux/commits/main"><img src="https://img.shields.io/github/last-commit/hippos-linux/hippos-linux?style=for-the-badge&logo=github" alt="Last commit" /></a>
  <a href="https://github.com/hippos-linux/hippos-linux/issues"><img src="https://img.shields.io/github/issues/hippos-linux/hippos-linux?style=for-the-badge&logo=github" alt="Issues" /></a>
</div>

---

## ℹ️ About

HippOS is a Debian-based gaming OS for x86 PCs and handhelds, Raspberry Pi 4/5, and RK3326 handhelds such as the R36S. Power it on and you are in EmulationStation — no desktop, no login screen, no configuration required. Your games, saves, and settings live on a separate persistent `@userdata` btrfs subvolume that survives every OS update.

It ships 85+ emulators built from source, covering 280+ systems — from Atari 2600 to PS4, arcade cabinets to Windows PC arcade hardware — all navigated with a controller from the couch.

Visit **[hippos-linux.org](https://hippos-linux.org)** for downloads and release notes, and **[hippos-linux.org/docs](https://hippos-linux.org/docs/)** for documentation.

---

## 🖥️ Platform Support

| Platform | Support |
|---|---|
| x86-64 (AMD GPU) | ✅ Full |
| x86-64 (Intel GPU) | ✅ Full |
| x86-64 (NVIDIA GPU) | ✅ Drivers built from source |
| Raspberry Pi 5 | ✅ Full |
| Raspberry Pi 4 | ✅ Full |
| PC handhelds (Steam Deck, ROG Ally, Legion Go, AYANEO…) | ✅ Full (InputPlumber for built-in controls) |
| RK3326 handhelds (R36S and clones, RG351M/V, Odroid Go 2/3/Super, RGB10…) | 🧪 Experimental |

> [!NOTE]
> Xbox, Xbox 360, and PS3 emulation are not available on Raspberry Pi. The Pi 5 does not have sufficient GPU resources for these.
> RK3326 handhelds run systems up to PlayStation and most handheld systems.

---

## 🎮 Features

### Frontend

- Boots directly into EmulationStation — no desktop or login screen
- Controller-first navigation with automatic button layout detection and per-controller button icons
- Built-in scraper for game metadata, boxart, and videos
- In-game quick menu (**Hotkey+A**): save/load states, controller-as-mouse, on-screen keyboard, brightness, volume, power mode, CPU/GPU stats, and a live pad-to-keyboard key editor

### Library

- **280+ systems** — 78 consoles, 73 computers, 41 portables, 39 arcade platforms, plus game engines, ports, and more
- **Linux Games** — native games installed via Discover, apt, or the Content Downloader appear automatically with descriptions and artwork
- **Linux Apps** — Flatpak apps, web apps (Netflix, YouTube, Disney+, Spotify, Twitch, and more), and desktop shortcuts
- **AppImage drop-zone** — drop any `.AppImage` into `/roms/appimages`; a launcher appears in Linux Games or Linux Apps based on the app's category
- **Windows 98** — runs in DOSBox Pure, per-game save state, DOSBox-X available as an alternative
- **Steam, Heroic, Lutris, Waydroid** — available from the Apps tab
- **Wine + box64** on Raspberry Pi

### Media Centers

Install **Kodi, Jellyfin, Emby Theater, or Plex HTPC** directly from the main menu. Installed on demand, controller-driven with on-screen keyboard and controller-as-mouse.

> [!NOTE]
> Plex HTPC is available on x86 PC only.

### Controllers

| Feature | Support |
|---|---|
| Xbox One / Series (USB + Bluetooth) | ✅ |
| DualShock 4 / DualSense | ✅ |
| Switch Pro | ✅ |
| Steam Controller 2 | ✅ |
| Generic / XInput | ✅ |
| Light guns (AimTrak, GunCon 2/3, GUN4IR, OpenFIRE, Sinden, and more) | ✅ |
| Racing wheels with force feedback (Logitech, Thrustmaster) | ✅ |
| Per-game TDP and power profiles | ✅ |
| Handheld built-in controls (InputPlumber) | ✅ |

### Updates

- OTA updates swap the `@rootfs` btrfs subvolume with automatic rollback support
- Games, saves, settings, and manually installed apt packages survive every update
- Files you added are kept; changed system files are backed up to `/userdata/system/backups` instead of being overwritten
- Live update progress and notifications in the UI

### Storage and Networking

- SMB and NFS shares discovered on the network and merged into your library in one press
- Saves written back to network shares where permitted
- External USB drives pooled into your library on plug-in
- btrfs `@userdata` subvolume — persistent, update-safe, and easy to back up

---

## 🕹️ Emulators

85+ emulators built from source, including:

| Platform | Emulators |
|---|---|
| Multi-system | RetroArch (100+ cores), MAME |
| PlayStation | DuckStation, PCSX2, RPCS3, shadPS4 |
| Nintendo | Dolphin, Ryujinx, Cemu, melonDS, mupen64plus, NanoBoyAdvance |
| Xbox | xemu (+ Chihiro), Xenia, Xenia Canary, Xenia Edge |
| Sega | Flycast, Redream, Supermodel, Model 2 Emulator |
| Windows Arcade PC | WindowsArcadeLoader — TypeX, RingEdge, RingEdge 2, Nesica, Nesica 2, Lindbergh, Namco ES3, Konami, Wahlap, Raw Thrills, Global VR, Sega NU, Sega Shell, Adrenaline, ALLS, APM3, Europar, Tsunami, UNIS |
| Computers | VICE, openMSX, FS-UAE, Hatari, BasiliskII, GSplus, AppleWin, SAM Coupé |
| Handhelds | PPSSPP, DraStic, EKA2L1, Vita3K |
| Other | ScummVM, BigPEmu, xroar, x16emu, EasyRPG, IKEMEN GO, TIC-80, Quiver, vpinball, and more |

> [!NOTE]
> Many emulators require BIOS files placed in `/userdata/bios/`. Refer to the [docs](https://hippos-linux.org/docs/) for per-system BIOS requirements.

---

## 📦 Installing

> [!WARNING]
> Flashing an image will erase all data on the target drive. Back up anything important before proceeding.

1. Download the image for your hardware from **[hippos-linux.org](https://hippos-linux.org)**: PC and PC handhelds, Raspberry Pi, or RK3326 handhelds
2. Flash the `.img.zst` to a USB drive or microSD card
3. RK3326 handhelds only: set up the screen. The R36S and its clones need the `.dtb` from the original card copied into `stock/` on the HippOS card; some other models need a file from `devices/`. See the **[RK3326 guide](https://hippos-linux.org/docs/devices/rk3326/)**
4. Boot. On a PC, Secure Boot must be off. RK3326 handhelds boot from the first card slot
5. Optionally, on a PC, install to an internal disk from **System Settings**

The full **[install guide](https://hippos-linux.org/install)** covers each step.

---

## ❓ Support

- **Bug reports and feature requests**: [GitHub Issues](https://github.com/hippos-linux/hippos-linux/issues)
- **Downloads**: [hippos-linux.org](https://hippos-linux.org)
- **Documentation**: [hippos-linux.org/docs](https://hippos-linux.org/docs/)

---

## 🤝 Credits

- [EmulationStation (Batocera fork)](https://github.com/batocera-linux/batocera-emulationstation) — frontend base (GPLv2), heavily modified for HippOS
- [Batocera Linux](https://batocera.org) — inspiration and reference
- All emulator authors and communities

---

## 💖 Supporters

HippOS is free and open source. If you find it useful, consider supporting development.

<p align="center">
  <a href="https://github.com/sponsors/hippos-linux"><img src="https://img.shields.io/badge/sponsor-hippos--linux-ea4aaa?style=for-the-badge&logo=github-sponsors" alt="Sponsor on GitHub" /></a>
</p>

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/hippos-linux/hippos-linux@contributors/sponsors.svg" alt="Sponsors" />
</p>

---

## 👥 Contributors

Thank you to everyone who has helped make HippOS better!

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/hippos-linux/hippos-linux@contributors/github.svg" alt="GitHub contributors" />
</p>

---

## 📄 License

Build system and OS integration code in this repository are GPL-3.0 licensed unless otherwise noted. Each bundled emulator carries its own license.

---

## ⭐ Star History

<a href="https://www.star-history.com/?repos=hippos-linux%2Fhippos-linux&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=hippos-linux/hippos-linux&type=date&legend=top-left" />
 </picture>
</a>
