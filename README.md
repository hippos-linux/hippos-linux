# HippOS

A console-style gaming OS for x86 PCs. Boot straight into your game library — no desktop, no setup, no fuss.

HippOS is built on Debian Trixie, uses a custom EmulationStation frontend, and bundles a wide range of emulators compiled from source. Plug in a controller and go.

---

## Status

Early access. Check [hippos-linux.org](https://hippos-linux.org) for downloads and updates.

---

## What it is

HippOS turns a PC into a dedicated gaming appliance:

- Boots directly into EmulationStation — no desktop in the way
- Controller-first navigation out of the box
- Games, saves, and settings live on a separate persistent `@userdata` btrfs subvolume and survive OS updates
- OTA updates swap the `@rootfs` subvolume with automatic rollback support
- External drives can be pooled transparently into your ROM library
- Emulator build dependencies never touch the runtime OS — the image stays lean
- Wine runner downloads built into the frontend content store

---

## Emulators

HippOS ships with emulators compiled from source covering a broad range of platforms, including:

RetroArch, Dolphin, PCSX2, RPCS3, Ryujinx, Cemu, DuckStation, PPSSPP, Flycast, melonDS, xemu, ScummVM, MAME, shadPS4, Vita3K, BigPEmu, VICE, openMSX, and many more.

---

## Hardware

- x86-64 PC with UEFI firmware
- A controller (keyboard also works)

AMD and Intel integrated graphics are the primary test targets. NVIDIA support depends on Debian Trixie driver availability.

---

## Installing

Download the latest image from [hippos-linux.org](https://hippos-linux.org). Flash the `.img.zst` to a USB drive or install to an internal disk and boot.

---

## Repository layout

```
overlays/       Files copied verbatim into the rootfs at build time
packages/       Per-emulator build scripts
src/            Source trees (EmulationStation frontend, website)
catalog/        Content store package catalog
docs/           Build and runtime notes
```

---

## Credits

- [EmulationStation](https://github.com/batocera-linux/batocera-emulationstation) — frontend base (GPLv2), heavily modified for HippOS
- [Batocera Linux](https://batocera.org) — inspiration and reference
- All emulator authors and communities

---

## License

The build system and OS integration code in this repository are GPL-3.0 licensed unless otherwise noted. Each bundled emulator carries its own license.
