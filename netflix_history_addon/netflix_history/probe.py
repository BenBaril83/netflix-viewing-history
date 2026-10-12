"""Read-only page inspection, for working out what Netflix's real pages look like.

Deliberately limited: it can navigate to paths on the Netflix host and read structure back (sanitised
HTML, links, visible text). It cannot click, type, or run script, and it is disabled unless the
`debug_probe` add-on option is switched on.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext

from . import scraper

MAX_STEPS = 12
MAX_HTML = 8000
MAX_WAIT_MS = 8000
_DROP_TAGS = ["script", "style", "svg", "noscript", "img", "picture", "source", "link", "meta", "iframe"]


class ProbeError(ValueError):
    pass


def check_path(path: str) -> str:
    """Only plain paths on the Netflix host: no scheme, no host, no protocol-relative or backslash tricks."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "\\" in path or "@" in path:
        raise ProbeError(f"Only plain Netflix paths are allowed, got {path!r}")
    return path


def sanitize_html(html: str, limit: int = MAX_HTML) -> str:
    """Keep structure (tags, classes, roles, data-*, aria-*), drop scripts/styles/images and query strings."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for el in soup.find_all(True):
        for attr in list(el.attrs):
            if attr in ("href", "src", "action"):
                el.attrs[attr] = str(el.attrs[attr]).split("?")[0]
            elif attr == "style" or attr.startswith("on"):
                del el.attrs[attr]
    return re.sub(r"\s+", " ", str(soup)).strip()[:limit]


def run(ctx: BrowserContext, steps: list[dict]) -> list[dict]:
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise ProbeError(f"steps must be a list of at most {MAX_STEPS}")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    out: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            raise ProbeError("each step must be an object")
        if "goto" in step:
            path = check_path(step["goto"])
            page.goto(f"{scraper.BASE}{path}", wait_until="domcontentloaded")
            page.wait_for_timeout(min(int(step.get("wait_ms", 1500)), MAX_WAIT_MS))
            out.append({"goto": path, "url": page.url.split("?")[0], "title": page.title()})
        elif "html" in step:
            sel = str(step["html"])
            els = page.query_selector_all(sel)
            out.append({
                "html": sel,
                "matches": len(els),
                "first": sanitize_html(els[0].evaluate("e => e.outerHTML")) if els else None,
            })
        elif step.get("links"):
            out.append({"links": scraper.describe_page(page, limit=int(step.get("limit", 60)))})
        elif step.get("text"):
            out.append({"text": " ".join(page.inner_text("body").split())[:2000]})
        else:
            raise ProbeError(f"unknown step {sorted(step)}")
    return out
