# BC-250 proof image (team flash artifact)

## Purpose

Binary you can flash to reproduce “ES comes up on BC-250” without rebuilding HippOS from source. This is a **proof / recovery-shaped** image based on `0.5.3-dev.3`, not a promise of final upstream packaging.

## Expected local path

`/Users/mikey/hippos/hippos-amd64-0.5.3-dev.3-bc250-proof.img`

(Built from pristine `.img.zst` + EFI/rootfs injection of the `fix/bc250-boot-dual-kernel` overlays, plus dual-kernel GRUB.)

## What is on it

- Dual-kernel GRUB: **latest default**, **LTS** selectable, LTS verbose recovery entry
- `etc/fstab` label + short timeouts
- `NetworkManager-wait-online` masked
- `write-dual-kernel-grub` + first-boot hooks from the fork branch

## What it is not

- Not a substitute for merging the fork branch into upstream
- Not necessarily identical to the hand-patched live disk (debug-init / extra masks may be omitted on purpose)

## Flash

```bash
# example — use your usual imager; replace DEVICE carefully
sudo dd if=hippos-amd64-0.5.3-dev.3-bc250-proof.img of=/dev/DISK bs=8M status=progress conv=fsync
```

On BC-250: at GRUB, choose **HippOS (LTS)** if latest still misbehaves; otherwise default latest is fine for other hardware.
