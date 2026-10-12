"""Pure HTML parsing, kept separate from the browser so it can be tested offline.

Netflix changes its markup from time to time. Every selector lives in this
file so that a layout change means editing only this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime

from bs4 import BeautifulSoup

ROW_SELECTOR = "li.retableRow"
DATE_SELECTOR = ".date"
TITLE_LINK_SELECTOR = ".title a"
PROFILE_LINK_SELECTOR = "a[href*='tkn=']"
PROFILE_NAME_SELECTOR = ".profile-name"

_TITLE_ID = re.compile(r"/title/(\d+)")
_TOKEN = re.compile(r"tkn=([^&\"']+)")


@dataclass
class Entry:
    profile: str
    date_raw: str
    date: str | None  # ISO date, only set when a date format was supplied
    title: str
    title_id: str | None
    show: str | None  # series name when the title looks like "Show: Season: Episode"

    def asdict(self) -> dict:
        return asdict(self)


def parse_date(raw: str, fmt: str | None) -> str | None:
    if not fmt:
        return None
    try:
        return datetime.strptime(raw.strip(), fmt).date().isoformat()
    except ValueError:
        return None


def split_show(title: str) -> str | None:
    """Best effort: 'Show: Season 2: "Ep"' -> 'Show'. Movies return None."""
    parts = title.split(": ")
    if len(parts) >= 2 and re.search(r"season|series|part|volume|limited|chapter|book", parts[1], re.I):
        return parts[0]
    return None


def parse_entries(html: str, profile: str, date_format: str | None = None) -> list[Entry]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for row in soup.select(ROW_SELECTOR):
        date_el = row.select_one(DATE_SELECTOR)
        link = row.select_one(TITLE_LINK_SELECTOR)
        if not date_el or not link:
            continue
        date_raw = date_el.get_text(strip=True)
        title = link.get_text(strip=True)
        m = _TITLE_ID.search(link.get("href", ""))
        entries.append(
            Entry(
                profile=profile,
                date_raw=date_raw,
                date=parse_date(date_raw, date_format),
                title=title,
                title_id=m.group(1) if m else None,
                show=split_show(title),
            )
        )
    return entries


def parse_profiles(html: str) -> list[tuple[str, str]]:
    """Return [(name, switch_token)] from the 'Who's watching?' page."""
    soup = BeautifulSoup(html, "html.parser")
    seen, profiles = set(), []
    for a in soup.select(PROFILE_LINK_SELECTOR):
        m = _TOKEN.search(a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        name_el = a.select_one(PROFILE_NAME_SELECTOR)
        name = (name_el or a).get_text(strip=True)
        seen.add(m.group(1))
        profiles.append((name or m.group(1), m.group(1)))
    return profiles
