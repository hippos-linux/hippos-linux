# evmapy key files

Place `.keys` JSON files here to define pad-to-keyboard mappings.

Search priority (highest first):
1. `{rom}.keys` alongside the ROM file
2. `/userdata/system/evmapy/{system}.{emulator}.keys`
3. `/userdata/system/evmapy/{system}.keys`
4. `/userdata/system/evmapy/{emulator}.keys`
5. `/userdata/system/evmapy/any.keys`
6. `/usr/share/hippos/evmapy/{system}.{emulator}.keys`  ← here
7. `/usr/share/hippos/evmapy/{system}.keys`              ← here
8. `/usr/share/hippos/evmapy/{emulator}.keys`            ← here
9. `/usr/share/hippos/evmapy/any.keys`                   ← here
10. `/userdata/system/evmapy/hotkeys.keys` or `/usr/share/hippos/evmapy/hotkeys.keys`

Format: JSON with player action arrays, e.g.:
```json
{
  "actions_player1": [
    {"trigger": "hotkey+start", "type": "key",  "target": "KEY_ESC"},
    {"trigger": "hotkey+b",     "type": "exec", "target": "/usr/bin/hippos-screenshot"}
  ]
}
```

See https://github.com/kempniu/evmapy for full documentation.
