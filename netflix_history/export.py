from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .parse import Entry

FIELDS = ["profile", "date_raw", "date", "title", "title_id", "show"]


def write_all(results: dict[str, list[Entry]], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, entries in results.items():
        safe = re.sub(r"[^\w.-]+", "_", name) or "profile"
        path = out_dir / f"{safe}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(e.asdict() for e in entries)
        written.append(path)
    combined = out_dir / "all_profiles.json"
    combined.write_text(
        json.dumps({n: [e.asdict() for e in es] for n, es in results.items()}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return written + [combined]
