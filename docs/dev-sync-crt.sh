#!/usr/bin/env bash
# Deploy CRT overlay changes to a running HippOS test box (rsync over SSH).
# Usage: docs/dev-sync-crt.sh [host]
set -euo pipefail

HOST="${1:-hippos.local}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Syncing CRT scripts to root@${HOST}..."

rsync -av \
  "${ROOT}/overlays/rootfs/usr/lib/hippos/hippos-crt-setup" \
  "${ROOT}/overlays/rootfs/usr/lib/hippos/hippos-crt-teardown" \
  "${ROOT}/overlays/rootfs/usr/lib/hippos/hippos-display-setup" \
  "${ROOT}/overlays/rootfs/usr/lib/hippos/hippos-xorg-setup" \
  "${ROOT}/overlays/rootfs/usr/lib/hippos/hippos-resolution" \
  "root@${HOST}:/usr/lib/hippos/"

rsync -av \
  "${ROOT}/overlays/rootfs/usr/lib/systemd/system/hippos-xserver.service" \
  "root@${HOST}:/usr/lib/systemd/system/"

rsync -av \
  "${ROOT}/overlays/rootfs-amd64/usr/share/hippos/hippos-defaults.conf" \
  "root@${HOST}:/usr/share/hippos/"

ssh "root@${HOST}" 'systemctl daemon-reload'
echo "Done. Reboot to test: ssh root@${HOST} reboot"
