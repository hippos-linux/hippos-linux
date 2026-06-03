# Gun help overlay images

Place PNG + JSON info pairs here for gun help overlays.

Filename convention:
- `{gun_name}.png`   — gun image (half screen height, auto-scaled)
- `{gun_name}.infos` — JSON with text layout for button labels

The `{gun_name}` comes from `ctx.game_gun['name']` in the gamelist metadata.
Falls back to `default.png` / `default.infos` if specific gun not found.

Info file format:
```json
{
  "font_size_per_height": 0.04,
  "color": "white",
  "texts": [
    {"x": 0.3, "y": 0.5, "value": "<TRIGGER>", "align": "center"}
  ]
}
```

Button label placeholders: `<TRIGGER>`, `<ACTION>`, `<START>`, `<SELECT>`,
`<SUB1>`, `<SUB2>`, `<SUB3>`, `<UP>`, `<DOWN>`, `<LEFT>`, `<RIGHT>`.
