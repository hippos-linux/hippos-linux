# ES build keys

Drop each key into the matching file (one line, no quotes). The frontend
build reads them; a missing or empty file builds EmulationStation without
that scraper or feature. The `.txt` files hold secrets and are gitignored —
only this README is tracked.

| File | Build define | Format | Get it from |
|------|--------------|--------|-------------|
| `screenscraper-login.txt` | `SCREENSCRAPER_DEV_LOGIN` | `devid=NAME&devpassword=PASS` | screenscraper.fr dev account |
| `steamgriddb-apikey.txt` | `STEAMGRIDDB_APIKEY` | the API key | steamgriddb.com/profile/preferences/api |
| `thegamesdb-api-key.txt` | `GAMESDB_APIKEY` | the API key | thegamesdb.net (public key for release builds) |
| `cheevos-dev-login.txt` | `CHEEVOS_DEV_LOGIN` | `z=NAME&y=KEY` | retroachievements.org connect API key |

`cheevos-dev-login.txt` enables the in-ES achievement browser (game lists,
progress, badges). Players earn achievements with their own RA login
regardless of this key; it only powers the web-API display.
