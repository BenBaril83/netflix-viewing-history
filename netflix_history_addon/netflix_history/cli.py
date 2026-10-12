from __future__ import annotations

import argparse
from pathlib import Path

from . import export, scraper


def main() -> None:
    ap = argparse.ArgumentParser(prog="netflix-history", description=__doc__)
    ap.add_argument("--session-dir", type=Path, default=Path(".netflix-session"),
                    help="where the browser login is stored (default: .netflix-session)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="open a browser to sign in to Netflix once")

    s = sub.add_parser("scrape", help="export viewing activity for every profile")
    s.add_argument("--out", type=Path, default=Path("output"))
    s.add_argument("--profile", action="append", help="only this profile (repeatable)")
    s.add_argument("--date-format", help="strptime format of Netflix's dates, e.g. '%%m/%%d/%%y'; adds an ISO date column")
    s.add_argument("--show-browser", action="store_true", help="run non-headless (useful for debugging)")

    args = ap.parse_args()
    if args.cmd == "login":
        scraper.login(args.session_dir)
        return
    try:
        results = scraper.scrape(
            args.session_dir, args.profile, headless=not args.show_browser, date_format=args.date_format
        )
    except scraper.NotLoggedIn as e:
        raise SystemExit(f"{e} Run `netflix-history login` first.")
    for path in export.write_all(results, args.out):
        print("wrote", path)
