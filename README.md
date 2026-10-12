# netflix-viewing-history

Export the viewing activity of every profile on **your own** Netflix account to CSV/JSON.

Netflix has no public API for this, so the tool drives a real Chromium browser (Playwright)
through the same pages you'd click through by hand. Your password is never handled by this
tool: you sign in yourself in the browser window, and only the resulting session cookies are
kept in `.netflix-session/` (git-ignored; treat it like a password).

## Home Assistant (add-on + integration)

Two parts, both in this repo:

- **Add-on** (`netflix_history_addon/`): runs the scraper in a container with Chromium. You sign in once inside
  a noVNC browser embedded in the HA sidebar panel (MFA/captcha work; only session cookies are stored).
  It re-scrapes every `scrape_interval_hours` (default 24) and serves the data on a token-protected API
  on port 8100 (internal network only, not published on the host).
- **Integration** (`custom_components/netflix_viewing_history/`): config-flow setup (host + token, both shown
  in the add-on panel). Per profile it creates a device with sensors *Last watched* (recent list in
  attributes), *Titles watched* and *Watched in last 7 days*, plus a *Refresh* button.

Install: Settings → Add-ons → Add-on store → ⋮ → Repositories → add this repo's URL, install
**Netflix Viewing History**, start it, open the sidebar panel and sign in. Then copy `custom_components/netflix_viewing_history`
into your HA config (or add the repo to HACS as a custom *Integration* repository) and add the integration.
Set the add-on's `date_format` (e.g. `%y-%m-%d`, matching how Netflix shows dates for your account) to get the *Watched in last 7 days* sensor; without it that sensor is unknown.

**Engine option.** `engine: chromium` (default) scrapes with the same Chromium used for login. `engine: obscura`
scrapes through [Obscura](https://github.com/h4ckf0r0day/obscura), a lightweight headless browser (about 30 MB RAM vs 200+),
pinned to v0.2.4 in the Dockerfile. Obscura has no window, so you still sign in with Chromium; the Netflix
session cookies are copied to Obscura for each scrape and refreshed afterwards. Trade-offs: your session
cookies are handed to a third-party binary (upstream publishes no checksums, so the Dockerfile pins hashes
taken from the v0.2.4 download), and Obscura's web platform coverage is incomplete. Obscura's stealth mode is
deliberately not enabled; it's not needed for your own account. Switch back to `chromium` if scrapes fail.

Not verified against real hardware: the Docker build, the noVNC login flow, and the live Netflix pages (including whether Obscura renders them). Both engines are tested against a local fake site (`tests/fake_netflix.py`); set `OBSCURA_BIN` and `NETFLIX_CHROMIUM_PATH` to run those tests.

## Standalone CLI setup

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
```

## Use

```sh
netflix-history login                    # once: sign in, then press Enter
netflix-history scrape                   # all profiles -> output/<profile>.csv + all_profiles.json
netflix-history scrape --profile Ben --date-format '%m/%d/%y'
netflix-history scrape --show-browser    # watch it work / debug
```

Netflix's date format depends on your account locale, so `date_raw` is always kept as-is;
pass `--date-format` (a `strptime` pattern, e.g. `%y-%m-%d` for Netflix's `26-8-25`) to also get an ISO `date` column.

## How often, and how much

The add-on checks every `scrape_interval_hours` (default 24) and on **Check for new entries** / the integration's refresh button. The first run reads the whole history; after that it only fetches what's new: it stops clicking "Show More" as soon as your newest stored entries appear and adds anything above them. If they don't appear (history was changed on Netflix) it falls back to a full read. **Full rescan** (panel button, or `POST /api/scrape?full=1`) forces a full read, e.g. to pick up entries you hid on Netflix.

## How it reads Netflix

It reads the "Who's watching?" screen for each profile's ID, then opens `/settings/viewed/<ID>` directly and clicks only "Show More" until the list is complete. There is no profile switching, so Profile Lock PINs are not needed, and it never touches the per-row "Hide from viewing history" controls.

## Caveats

- Run it on your own machine; Netflix may challenge logins from datacenter IPs.
- All page selectors live in `netflix_history_addon/netflix_history/parse.py` and the "Show more" handling in
  `scraper.py`. If Netflix changes its markup, that's where to fix it. The parser is covered
  by offline tests (`pytest`), but the live flow can only be verified against a real account.
- Only the titles/dates Netflix itself shows on the viewing activity page are exported.
