#!/usr/bin/env python3
"""Turn the scraped data into the static payload the site ships.

The whole dataset is ~55KB gzipped, so the site loads it in one request
and does all filtering client-side. No API, no pagination, no backend.
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
PUBLIC = ROOT / "public"


def main() -> None:
    today = date.today().isoformat()
    events = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    future = [e for e in events if e["date"] >= today]
    future.sort(key=lambda e: (e["date"], e["start_time"] or "99:99"))

    # Venue list is small and highly repeated -> intern it as an index.
    venues: list[str] = []
    venue_ix: dict[str, int] = {}
    for e in future:
        v = e["venue"] or "?"
        if v not in venue_ix:
            venue_ix[v] = len(venues)
            venues.append(v)

    rows = []
    for e in future:
        row = {
            "t": e["title"],
            "d": e["date"],
            "v": venue_ix[e["venue"] or "?"],
            "a": e["artists"],
            "u": e["url"],
        }
        # Only emit optional fields when present — keeps the payload lean.
        if e.get("start_time"):
            row["h"] = e["start_time"]
        if e.get("genres"):
            row["g"] = e["genres"]
        if e.get("image"):
            row["i"] = e["image"]
        if e.get("price"):
            row["p"] = e["price"]
        if e.get("ticket_url") and e["ticket_url"] != e["url"]:
            row["k"] = e["ticket_url"]
        if e.get("lat"):
            row["ll"] = [round(e["lat"], 5), round(e["lon"], 5)]
        row["s"] = e["sources"]
        rows.append(row)

    undated = []
    up = DATA / "undated.json"
    if up.exists():
        known = {a.lower() for e in future for a in e["artists"]}
        for r in json.loads(up.read_text(encoding="utf-8")):
            if r["title"].lower() not in known:
                undated.append({"t": r["title"], "v": r["venue"],
                                "u": r["url"], "s": r["source"]})

    genres = sorted({g for e in future for g in e.get("genres") or []})
    payload = {
        "generated": today,
        "venues": venues,
        "genres": genres,
        "events": rows,
        "undated": undated,
    }

    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    # Copy the static shell over.
    for f in SITE.iterdir():
        if f.is_file():
            shutil.copy2(f, PUBLIC / f.name)

    size = (PUBLIC / "data.json").stat().st_size
    print(f"  events:   {len(rows)}")
    print(f"  venues:   {len(venues)}")
    print(f"  artists:  {len({a.lower() for e in future for a in e['artists']})}")
    print(f"  undated:  {len(undated)}")
    print(f"  data.json {size/1024:.0f}KB raw")


if __name__ == "__main__":
    main()
