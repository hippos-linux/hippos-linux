# BC-250 boot bring-up (fork branch notes)

**Branch:** `fix/bc250-boot-dual-kernel` on `net-terminal-gene/hippos-linux` (fork of `hippos-linux/hippos-linux`).  
**Live proof KB:** `Batocera-Development-KB/entries/2026-08-08_hippos-bc250-boot-bringup/`  
**Product UX proposal:** that KB’s `design/proposed-flash-boot-flow.md`

## Problem (short)

On AMD BC-250, stock `0.5.3-dev.3` felt stuck: silent GRUB booted **latest (7.1.7)** only, and systemd sat on network/disk waits. Kernel/console were fine; LTS + shorter waits reached EmulationStation.

## What this branch changes (product-facing)

| Change | Path |
|--------|------|
| Visible GRUB, `saved` default | `overlays/rootfs/etc/default/grub` |
| Label fstab + 5s device timeout | `overlays/rootfs/etc/fstab` |
| Mask `NetworkManager-wait-online` | `overlays/rootfs/etc/systemd/system/NetworkManager-wait-online.service` → `/dev/null` |
| Dual-kernel EFI writer (latest default, LTS selectable) | `overlays/rootfs/usr/lib/hippos/write-dual-kernel-grub` |
| First-boot / `update-grub` call dual writer after `hippos-upgrade` | `update-grub-first-boot`, `usr/sbin/update-grub` |

**Not in this branch (live recovery only):** custom `hippos-debug-init`, masking network-ROM/NFS/nvidia stubs, forced `root`/`linux` SSH drop-in. Those stay documented in the KB caveats file.

## Fresh-flash flow (intended)

1. Flash image built from this branch (or apply overlays in CI image build).
2. GRUB shows **Latest** (default) and **LTS**.
3. Normal users: timeout → latest → ES.
4. BC-250: pick LTS once; `save_env` remembers when supported.
5. First-boot `hippos-update-grub` regenerates dual menu when both kernels exist.

## Proof image

See `docs/bc250-proof-image.md` for the local `.img` artifact meant for team flash testing (recovery-shaped; label clearly).
