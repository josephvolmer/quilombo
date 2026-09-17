#!/usr/bin/env python3
"""Run every source, merge, dedupe, and report coverage."""
from __future__ import annotations

import json
import sys
import time
import concurrent.futures as cf
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from core import (norm_artist, norm_venue, artists_from_title, clean_artist,
                  strip_emoji, format_price, clean_time, is_buenos_aires)
from sources import ALL_SOURCES, UNDATED_SOURCES

OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)


def run_all(only: list[str] | None = None) -> dict[str, list]:
    targets = {k: v for k, v in ALL_SOURCES.items()
               if not only or k in only}
    results: dict[str, list] = {}
    timings: dict[str, float] = {}

    def one(item):
        name, fn = item
        t0 = time.time()
        try:
            evs = fn()
        except Exception as exc:                      # noqa: BLE001
            print(f"  !! {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            evs = []
        return name, evs, time.time() - t0

    with cf.ThreadPoolExecutor(len(targets)) as ex:
        for name, evs, dt in ex.map(one, targets.items()):
            results[name] = evs
            timings[name] = dt
            print(f"  {name:>18}: {len(evs):>4} events  ({dt:.1f}s)")
    return results


def merge(results: dict[str, list]):
    """Collapse duplicates across sources, keeping the richest record."""
    buckets: dict[tuple, list] = defaultdict(list)
    for evs in results.values():
        for e in evs:
            buckets[e.key()].append(e)

    merged = []
    for key, group in buckets.items():
        # Richest = most artists, then most filled fields.
        group.sort(key=lambda e: (len(e.artists),
                                  sum(1 for v in e.as_dict().values() if v)),
                   reverse=True)
        best = group[0]
        d = best.as_dict()
        d["sources"] = sorted({e.source for e in group})
        # Union artists + genres across duplicates.
        seen, arts = set(), []
        for e in group:
            for a in e.artists:
                a = clean_artist(a)
                if not a:
                    continue
                na = norm_artist(a)
                if na and na not in seen:
                    seen.add(na)
                    arts.append(a)
        # Venti and Indie Hoy carry no `performer` field, but bill the
        # artist in the title ("Blair en Deseo"). Fall back to parsing it.
        if not arts:
            arts = [a for a in
                    (clean_artist(x) for x in artists_from_title(best.title))
                    if a]
            d["artist_source"] = "title" if arts else "none"
        else:
            d["artist_source"] = "structured"
        d["artists"] = arts
        d["genres"] = sorted({g for e in group for g in e.genres})
        for fld in ("ticket_url", "price", "image", "lat", "lon"):
            if not d.get(fld):
                for e in group:
                    if getattr(e, fld):
                        d[fld] = getattr(e, fld)
                        break
        # ── display hygiene, applied once on the merged record ──
        d["title"] = strip_emoji(d["title"]) or d["title"]
        d["venue"] = strip_emoji(d["venue"])
        d["artists"] = [x for x in (strip_emoji(a) for a in d["artists"]) if x]
        d["price"] = format_price(d.get("price"), best.source)
        d["start_time"] = clean_time(d.get("start_time"))

        # Buenos Aires only: several feeds are national.
        if not is_buenos_aires(d["venue"], d["title"]):
            continue

        merged.append(d)

    merged.sort(key=lambda d: (d["date"], d["title"]))
    return merged


def report(results, merged):
    today = date.today().isoformat()
    total_raw = sum(len(v) for v in results.values())
    future = [m for m in merged if m["date"] >= today]

    print("\n" + "=" * 62)
    print(f"  RAW rows across sources : {total_raw}")
    print(f"  UNIQUE after dedupe     : {len(merged)}")
    print(f"  ... dated today or later: {len(future)}")
    print(f"  duplicates collapsed    : {total_raw - len(merged)}")

    multi = [m for m in merged if len(m["sources"]) > 1]
    print(f"  confirmed by 2+ sources : {len(multi)}")

    artists = {norm_artist(a) for m in future for a in m["artists"] if norm_artist(a)}
    venues = {norm_venue(m["venue"]) for m in future if norm_venue(m["venue"])}
    print(f"  unique artists (future) : {len(artists)}")
    print(f"  unique venues  (future) : {len(venues)}")

    by_month = Counter(m["date"][:7] for m in future)
    print("\n  Events per month:")
    for mo, n in sorted(by_month.items()):
        print(f"    {mo}  {n:>4}  {'#' * min(n // 3, 50)}")

    print("\n  Contribution by source (unique rows it touched):")
    src_count = Counter(s for m in merged for s in m["sources"])
    for s, n in src_count.most_common():
        solo = sum(1 for m in merged if m["sources"] == [s])
        print(f"    {s:>18}: {n:>4} total, {solo:>4} found ONLY here")

    genres = Counter(g for m in future for g in m["genres"])
    if genres:
        print(f"\n  Top genres: {', '.join(g for g, _ in genres.most_common(12))}")
    return future


def main():
    only = sys.argv[1:] or None
    print("Scraping sources...")
    results = run_all(only)
    merged = merge(results)
    future = report(results, merged)

    (OUT / "events.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

    # Sources that give artist+venue but no date (Ticketek) — kept apart so
    # they never pollute the calendar, but still answer "is X coming?".
    undated = []
    for name, fn in UNDATED_SOURCES.items():
        try:
            rows = fn()
        except Exception as exc:                      # noqa: BLE001
            print(f"  !! {name}: {exc}", file=sys.stderr)
            continue
        print(f"  {name:>18}: {len(rows):>4} undated listings")
        undated.extend(r.as_dict() for r in rows)
    if undated:
        (OUT / "undated.json").write_text(
            json.dumps(undated, ensure_ascii=False, indent=1), encoding="utf-8")
        known = {norm_artist(a) for m in future for a in m["artists"]}
        new = {r["title"] for r in undated
               if norm_artist(r["title"]) and norm_artist(r["title"]) not in known}
        print(f"  {'':>18}  {len(new)} artists not in the dated calendar")

    # Artist-centric index: the thing El Cartel doesn't give you.
    idx = defaultdict(list)
    for m in future:
        for a in m["artists"]:
            if norm_artist(a):
                idx[a].append({"date": m["date"], "venue": m["venue"],
                               "url": m["url"], "title": m["title"]})
    by_artist = {a: sorted(v, key=lambda x: x["date"])
                 for a, v in sorted(idx.items(), key=lambda kv: kv[0].lower())}
    (OUT / "by_artist.json").write_text(
        json.dumps(by_artist, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n  wrote {OUT/'events.json'} and {OUT/'by_artist.json'}")


if __name__ == "__main__":
    main()
