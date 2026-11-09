# HippOS GRUB theme

The boot menu in the ES theme's look: its splash as the background, Sora for
text, and the brand purple for the selected entry, on a panel like the login
screen's.

`theme.txt` is written by hand. Everything else except `terminus-14.pf2` comes
from `tools/generate-grub-theme.sh`, which reads `themes/es-theme-hippos`.

- Background: the ES theme's `assets/splash.jpg` (HippOS artwork).
- Sora fonts: SIL Open Font License 1.1, see
  `themes/es-theme-hippos/assets/fonts/OFL.txt`.
- `terminus-14.pf2`, GRUB's editor and command line font: Terminus Font,
  SIL Open Font License 1.1.

hippos-upgrade's write_grub_cfg copies this directory from the deployment it
boots onto the ESP (`/boot/efi/grub/themes/hippos`) and loads every `.pf2` in
it; a theme can only use fonts GRUB has loaded.
