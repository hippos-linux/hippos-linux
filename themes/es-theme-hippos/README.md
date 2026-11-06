# HippOS theme

Every system is a world: an original generated planet in that system's colours,
lit from behind so its crescent frames the text. The carousel cross-fades between
worlds while the planet drifts and its sun pulses.

## Regenerating art

`worlds/` and the generated files in `assets/` come from `tools/generate-theme-art.py`.
Output is deterministic per system name. Palettes live in `WORLDS` in that script;
systems not listed get a fallback palette chosen from their name.

```bash
tools/generate-theme-art.py themes/es-theme-hippos chrome       # assets
tools/generate-theme-art.py themes/es-theme-hippos snes nes     # named worlds
tools/generate-theme-art.py themes/es-theme-hippos              # one per logo in art/
```

The last form only covers systems with a logo. Systems without one need naming
explicitly, using their `<theme>` value from `es_systems.cfg`. Anything without a
world shows `worlds/default.jpg`.

## Licences

- System logos in `art/`: from es-theme-minimal by Lilbud / crcerror, CC-BY-NC-SA.
- Sora font: SIL Open Font License, see `assets/fonts/OFL.txt`.
