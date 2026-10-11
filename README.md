# netflix-viewing-history

Export the viewing activity of every profile on **your own** Netflix account to CSV/JSON.

Netflix has no public API for this, so the tool drives a real Chromium browser (Playwright)
through the same pages you'd click through by hand. Your password is never handled by this
tool: you sign in yourself in the browser window, and only the resulting session cookies are
kept in `.netflix-session/` (git-ignored; treat it like a password).

## Setup

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
pass `--date-format` (a `strptime` pattern) to also get an ISO `date` column.

## Caveats

- Run it on your own machine; Netflix may challenge logins from datacenter IPs.
- All page selectors live in `netflix_history/parse.py` and the "Show more" handling in
  `scraper.py`. If Netflix changes its markup, that's where to fix it. The parser is covered
  by offline tests (`pytest`), but the live flow can only be verified against a real account.
- Only the titles/dates Netflix itself shows on the viewing activity page are exported.
