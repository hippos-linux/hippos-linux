#!/usr/bin/env bash
# generate-grub-theme.sh — build the GRUB theme's art and fonts from the ES
# theme, so the boot menu matches the frontend. theme.txt is hand-written; run
# this after changing the ES theme's splash, colours or fonts.
#
# Needs ImageMagick (magick) and grub-mkfont.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ES_THEME="${REPO}/themes/es-theme-hippos"
OUT="${REPO}/overlays/rootfs/usr/share/hippos/grub/themes/hippos"

INK_PANEL="rgba(18,15,32,0.88)"   # the ES theme's ink, lifted slightly
ACCENT="#7B3FFF"                  # brandPurple
ITEM_HEIGHT=46                    # boot_menu item_height in theme.txt

cd "${OUT}"

# GRUB's JPEG reader handles baseline 4:2:0 only; the splash is progressive.
magick "${ES_THEME}/assets/splash.jpg" -interlace none -sampling-factor 4:2:0 -quality 92 background.jpg

# GRUB only reads 8-bit RGB(A) PNGs, not palette ones, hence PNG32.
slice() {  # slice <source> <name> <x> <y> <w> <h>
    magick "$1" -crop "$5x$6+$3+$4" +repage "PNG32:$2"
}

# Menu panel: a rounded box cut into the nine pieces menu_pixmap_style uses.
panel="$(mktemp --suffix=.png)"
magick -size 48x48 xc:none -fill "${INK_PANEL}" -draw "roundrectangle 0,0 47,47 18,18" "${panel}"
slice "${panel}" menu_nw.png 0 0 18 18;  slice "${panel}" menu_n.png 18 0 12 18;  slice "${panel}" menu_ne.png 30 0 18 18
slice "${panel}" menu_w.png 0 18 18 12;  slice "${panel}" menu_c.png 18 18 12 12; slice "${panel}" menu_e.png 30 18 18 12
slice "${panel}" menu_sw.png 0 30 18 18; slice "${panel}" menu_s.png 18 30 12 18; slice "${panel}" menu_se.png 30 30 18 18

# Selected entry: a pill one item high, in three pieces.
pill="$(mktemp --suffix=.png)"
magick -size "40x${ITEM_HEIGHT}" xc:none -fill "${ACCENT}" \
    -draw "roundrectangle 0,0 39,$((ITEM_HEIGHT - 1)) 13,13" "${pill}"
slice "${pill}" select_w.png 0 0 14 "${ITEM_HEIGHT}"
slice "${pill}" select_c.png 14 0 12 "${ITEM_HEIGHT}"
slice "${pill}" select_e.png 26 0 14 "${ITEM_HEIGHT}"
rm -f "${panel}" "${pill}"

# GRUB fonts are bitmaps at one size each; these are the sizes theme.txt names.
rm -f sora-*.pf2
for size in 16 20 24; do
    grub-mkfont -s "${size}" -o "sora-regular-${size}.pf2" "${ES_THEME}/assets/fonts/Sora-Regular.ttf"
done
# Named apart from Regular, which grub-mkfont would otherwise call it too.
grub-mkfont -s 24 -n "Sora SemiBold" -o sora-semibold-24.pf2 "${ES_THEME}/assets/fonts/Sora-SemiBold.ttf"
