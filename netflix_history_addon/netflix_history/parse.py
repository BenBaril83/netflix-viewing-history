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
# "Who's watching?" screen: one <button data-uia="profile-selector+tile-<PROFILE_ID>"> per profile
# (locked ones also contain a "...+lock" marker). The profile ID is what the activity page URL uses.
GATE_TILE_SELECTOR = "button[data-uia^='profile-selector+tile-']"
ACTIVITY_READY_SELECTOR = "li.retableRow, [data-uia='viewing-activity-header']"

_TITLE_ID = re.compile(r"/title/(\d+)")
_PROFILE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
# 'Show: Season 2: "Episode"' / 'Show: Limited Series: "Episode"' / 'Show: Show: "Episode"'
_EPISODE_TITLE = re.compile(r'^(?P<show>.+?): .+: ".*"$')


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
    """Best effort: 'Show: Season 2: "Ep"' -> 'Show'. Movies (no quoted episode name) return None."""
    m = _EPISODE_TITLE.match(title)
    return m.group("show") if m else None


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


OVERLAP_BLOCK = 10


def entry_key(e: "Entry | dict") -> tuple:
    d = e if isinstance(e, dict) else e.asdict()
    return (d["date_raw"], d["title_id"], d["title"])


def find_overlap(fresh: list[Entry], known: list[dict], block: int = OVERLAP_BLOCK) -> int | None:
    """Where the newest stored entries start inside the freshly read list (newest first).

    Matches a whole block of the newest `block` stored entries, so a lone repeated title (the same
    episode watched twice) can't be mistaken for the join. Returns None when they aren't present.
    """
    if not known or not fresh:
        return None
    m = min(block, len(known))
    want = [entry_key(k) for k in known[:m]]
    keys = [entry_key(e) for e in fresh]
    for off in range(len(keys) - m + 1):
        if keys[off:off + m] == want:
            return off
    return None


def merge_new(fresh: list[Entry], known: list[dict], date_format: str | None) -> list[Entry] | None:
    """Fresh entries above the join + everything already stored, or None if the join wasn't found."""
    off = find_overlap(fresh, known)
    if off is None:
        return None
    old = [
        Entry(**{**k, "date": parse_date(k["date_raw"], date_format) or k.get("date")})  # pick up a newly set format
        for k in known
    ]
    return fresh[:off] + old


def parse_profiles(html: str) -> list[tuple[str, str]]:
    """Return [(name, profile_id)] from the 'Who's watching?' page."""
    soup = BeautifulSoup(html, "html.parser")
    seen, profiles = set(), []
    for tile in soup.select(GATE_TILE_SELECTOR):
        profile_id = tile["data-uia"].split("tile-", 1)[1]
        if profile_id in seen or not _PROFILE_ID.match(profile_id):
            continue
        seen.add(profile_id)
        profiles.append((tile.get_text(" ", strip=True) or profile_id, profile_id))
    return profiles
