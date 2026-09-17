"""One function per source. Each returns list[Event].

Sources are independent: a failure in one must not take down a run.
"""
from __future__ import annotations

import re
import json
import concurrent.futures as cf
from pathlib import Path

import requests

from core import (Event, polite_get, iter_jsonld, is_event_node,
                  event_from_jsonld, parse_date, clean_artist, HEADERS)

# --------------------------------------------------------------------- RA

RA_GQL = "https://ra.co/graphql"
RA_HEADERS = {
    **HEADERS,
    "Content-Type": "application/json",
    "Referer": "https://ra.co/events/ar/buenosaires",
    "Origin": "https://ra.co",
}
RA_QUERY = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int, $sort: SortInputDtoInput) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page, sort: $sort) {
    totalResults
    data {
      event {
        id title date startTime cost isFestival contentUrl flyerFront lineup
        venue { name }
        artists { id name }
        promoters { id name }
        genres { name }
      }
    }
  }
}
"""

_RA_LINEUP_TAG = re.compile(r"<artist[^>]*>(.*?)</artist>", re.I | re.S)


def _ra_lineup_names(lineup: str | None) -> list[str]:
    """RA's `lineup` holds names the artists[] array omits."""
    if not lineup:
        return []
    names = _RA_LINEUP_TAG.findall(lineup)
    plain = _RA_LINEUP_TAG.sub("\n", lineup)
    for line in plain.split("\n"):
        line = re.sub(r"<[^>]+>", "", line).strip(" ,-\t")
        if 1 < len(line) < 60:
            names.append(line)
    out, seen = [], set()
    for n in names:
        n = clean_artist(n)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def scrape_ra(date_from: str, date_to: str, area: int = 395) -> list[Event]:
    events, page = [], 1
    while page <= 12:
        payload = {
            "query": RA_QUERY,
            "variables": {
                "filters": {"areas": {"eq": area},
                            "listingDate": {"gte": date_from, "lte": date_to}},
                "pageSize": 100, "page": page,
                "sort": {"listingDate": {"order": "ASCENDING"}},
            },
        }
        try:
            r = requests.post(RA_GQL, headers=RA_HEADERS, json=payload, timeout=40)
            data = r.json()["data"]["eventListings"]
        except Exception:
            break
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            e = row.get("event") or {}
            d = parse_date(e.get("date"))
            if not d:
                continue
            artists = [a["name"] for a in (e.get("artists") or []) if a.get("name")]
            for n in _ra_lineup_names(e.get("lineup")):
                if n.lower() not in {a.lower() for a in artists}:
                    artists.append(n)
            events.append(Event(
                source="resident-advisor",
                title=e.get("title", ""),
                date=d,
                venue=(e.get("venue") or {}).get("name", ""),
                artists=artists,
                genres=[g["name"] for g in (e.get("genres") or []) if g.get("name")],
                url="https://ra.co" + (e.get("contentUrl") or ""),
                price=(e.get("cost") or "").strip(),
                image=e.get("flyerFront") or "",
                start_time=str(e.get("startTime") or "")[11:16],
            ))
        if len(rows) < 100 or len(events) >= data.get("totalResults", 0):
            break
        page += 1
    return events


# -------------------------------------------------------------- Indie Hoy

IH_LIST = "https://indiehoy.com/eventos/buenos-aires/"


def scrape_indiehoy(max_workers: int = 3) -> list[Event]:
    r = polite_get(IH_LIST, timeout=40)
    if not r:
        return []
    links = sorted(set(re.findall(
        r'href="(https://indiehoy\.com/agenda/[^"#?]+)"', r.text)))
    if not links:
        return []

    sess = requests.Session()

    def one(url: str) -> Event | None:
        rr = polite_get(url, session=sess, timeout=25)
        if not rr:
            return None
        for node in iter_jsonld(rr.text):
            if is_event_node(node):
                ev = event_from_jsonld(node, "indiehoy", url)
                if ev:
                    return ev
        return None

    out = []
    with cf.ThreadPoolExecutor(max_workers) as ex:
        for ev in ex.map(one, links):
            if ev:
                out.append(ev)
    return out


# ----------------------------------------------------------------- Crobar

def scrape_crobar() -> list[Event]:
    out = []
    for url in ("https://crobar.com.ar/", "https://www.crobar.com.ar/club",
                "https://www.crobar.com.ar/studio"):
        r = polite_get(url, timeout=25)
        if not r:
            continue
        for node in iter_jsonld(r.text):
            if is_event_node(node):
                ev = event_from_jsonld(node, "crobar", url)
                if ev:
                    # Support acts live in the prose description.
                    desc = node.get("description") or ""
                    m = re.match(r"(.+?)\s+en\s+Crobar", desc)
                    if m:
                        names = re.split(r",\s*|\s+&\s+|\s+B2B\s+", m.group(1))
                        ev.artists = [n.strip() for n in names if n.strip()]
                    out.append(ev)
    # de-dup by @id across the three pages
    seen, uniq = set(), []
    for e in out:
        k = (e.date, e.title)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


# --------------------------------------------------------------- Songkick

SK_METRO = "https://www.songkick.com/metro-areas/32911-argentina-buenos-aires"


def scrape_songkick() -> list[Event]:
    out = []
    r = polite_get(SK_METRO, timeout=30)
    if not r:
        return out
    for node in iter_jsonld(r.text):
        if is_event_node(node):
            ev = event_from_jsonld(node, "songkick")
            if not ev:
                continue
            # "Artist @ Venue" -> artist
            if " @ " in ev.title and not ev.artists:
                ev.artists = [ev.title.split(" @ ")[0].strip()]
            out.append(ev)
    return out


# ------------------------------------------------------------------ Venti

VENTI_SITEMAP = "https://venti.live/sitemap.xml"


VENTI_CACHE = Path(__file__).resolve().parent.parent / "data" / "venti_cache.json"


def scrape_venti(since: str = "2026-09-01", limit: int = 400,
                 max_workers: int = 2, budget_s: float = 420.0) -> list[Event]:
    """Venti's robots.txt asks for Crawl-delay: 10, so a full sweep is
    expensive: 226 URLs / 2 workers = ~19 minutes.

    Three mitigations: only consider URLs whose sitemap `lastmod` is
    recent; cache per-URL results keyed by that lastmod so repeat runs
    only pay for pages that actually changed; and cap each run at
    `budget_s`, newest-first, so a cold start degrades gracefully instead
    of blocking the pipeline. Anything not reached this run stays stale
    in the cache and is picked up by the next one.
    """
    import time as _t
    started = _t.time()
    r = polite_get(VENTI_SITEMAP, timeout=40)
    if not r:
        return []
    entries = re.findall(
        r"<url>\s*<loc>(https://venti\.live/evento/[^<]+)</loc>\s*"
        r"<lastmod>([^<]+)</lastmod>", r.text, re.S)
    entries = [(u, d) for u, d in entries if d >= since]
    entries.sort(key=lambda t: t[1], reverse=True)
    entries = entries[:limit]

    cache: dict = {}
    if VENTI_CACHE.exists():
        try:
            cache = json.loads(VENTI_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    stale = [(u, d) for u, d in entries
             if cache.get(u, {}).get("lastmod") != d]
    sess = requests.Session()

    def one(item):
        url, lastmod = item
        if _t.time() - started > budget_s:
            return url, None, None          # out of budget; leave it stale
        rr = polite_get(url, session=sess, timeout=25)
        if not rr:
            return url, lastmod, None
        for node in iter_jsonld(rr.text):
            if is_event_node(node):
                ev = event_from_jsonld(node, "venti", url)
                if ev:
                    return url, lastmod, ev.as_dict()
        return url, lastmod, None

    if stale:
        done = 0
        with cf.ThreadPoolExecutor(max_workers) as ex:
            for url, lastmod, payload in ex.map(one, stale):
                if lastmod is None:         # skipped: keep prior cache entry
                    continue
                cache[url] = {"lastmod": lastmod, "event": payload}
                done += 1
        if done < len(stale):
            print(f"    venti: {done}/{len(stale)} refreshed "
                  f"({len(stale) - done} deferred to next run)")
        VENTI_CACHE.parent.mkdir(exist_ok=True)
        VENTI_CACHE.write_text(json.dumps(cache, ensure_ascii=False),
                               encoding="utf-8")

    out = []
    for url, _ in entries:
        payload = cache.get(url, {}).get("event")
        if payload:
            out.append(Event(**payload))
    return out


# -------------------------------------------------------------- AllAccess

AA_VENUES = {
    "the-roxy-bar-live": "The Roxy Live",
    "the-roxy-bar-and-grill": "The Roxy Bar and Grill",
    "teatro-vorterix": "Teatro Vorterix",
}
# Cards render as: <div class='show-info'> <h3>DATE</h3> <h2>TITLE</h2> </div>
_AA_CARD = re.compile(
    r"<a\s+href='\.\./(event/[^']+)'.*?"
    r"class='show-info'>\s*<h3>\s*([^<]+?)\s*</h3>\s*<h2>\s*([^<]+?)\s*</h2>",
    re.S | re.I)


def scrape_allaccess() -> list[Event]:
    import html as _html
    out = []
    for slug, venue in AA_VENUES.items():
        url = f"https://www.allaccess.com.ar/venue/{slug}"
        r = polite_get(url, timeout=30)
        if not r:
            continue
        for path, raw_date, raw_title in _AA_CARD.findall(r.text):
            d = parse_date(raw_date)
            if not d:
                continue
            title = _html.unescape(raw_title).strip()
            out.append(Event(
                source="allaccess", title=title, date=d, venue=venue,
                artists=[title],
                url=f"https://www.allaccess.com.ar/{path}",
                ticket_url=f"https://www.allaccess.com.ar/{path}"))
    return out


# ------------------------------------------------------------ Bebop Club

BEBOP = "https://bebopclub.com.ar/"


def scrape_bebop(max_workers: int = 4) -> list[Event]:
    """Bebop's cards are flyer images: the artist is only in the img `alt`,
    and the date only on the ticketera page's <title>/og:title, shaped
    "ARTIST | 3 y 4 de Octubre | Bebop Club"."""
    import html as _html
    r = polite_get(BEBOP, timeout=30)
    if not r:
        return []
    urls = sorted(set(re.findall(
        r'href="(https://ticketera\.bebopclub\.com\.ar/evento/[a-f0-9-]+)"',
        r.text)))
    sess = requests.Session()

    def one(url: str) -> list[Event]:
        rr = polite_get(url, session=sess, timeout=30)
        if not rr:
            return []
        m = (re.search(r'property="og:title" content="([^"]+)"', rr.text)
             or re.search(r"<title>([^<]+)</title>", rr.text))
        if not m:
            return []
        raw = _html.unescape(m.group(1))
        parts = [p.strip() for p in raw.split("|")]
        title = parts[0] if parts else raw
        # A card can cover several nights: "3 y 4 de Octubre".
        dates: list[str] = []
        for seg in parts[1:]:
            mm = re.search(r"de\s+([A-Za-zéó]+)", seg)
            if not mm:
                continue
            month = mm.group(1)
            for day in re.findall(r"\b(\d{1,2})\b", seg):
                d = parse_date(f"{day} de {month}")
                if d and d not in dates:
                    dates.append(d)
        if not dates:
            for iso in re.findall(r"\d{4}-\d{2}-\d{2}", rr.text):
                dates = [iso]
                break
        return [Event(source="bebop", title=title, date=d, venue="Bebop Club",
                      artists=[title], genres=["Jazz"], url=url, ticket_url=url)
                for d in dates]

    out = []
    with cf.ThreadPoolExecutor(max_workers) as ex:
        for evs in ex.map(one, urls):
            out.extend(evs)
    return out


# --------------------------------------------------- WordPress venue feeds

WP_FEEDS = {
    "niceto": "https://nicetoclub.com/feed/",
    "palermo-groove": "https://www.palermogroove.com.ar/feed/",
}
VENUE_OF = {"niceto": "Niceto Club", "palermo-groove": "Palermo Groove"}


def scrape_wp_feeds() -> list[Event]:
    out = []
    for name, url in WP_FEEDS.items():
        r = polite_get(url, timeout=25)
        if not r:
            continue
        for item in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            title_m = re.search(
                r"<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", item, re.S)
            link_m = re.search(r"<link>\s*(.*?)\s*</link>", item, re.S)
            if not title_m:
                continue
            title = re.sub(r"\s+", " ", title_m.group(1)).strip()
            d = parse_date(title) or parse_date(
                re.search(r"<pubDate>(.*?)</pubDate>", item, re.S).group(1)
                if re.search(r"<pubDate>", item) else None)
            # Only keep posts that actually name a date in the title;
            # pubDate alone is a publish date, not an event date.
            if not parse_date(title):
                continue
            out.append(Event(source=f"wp-{name}", title=title, date=d,
                             venue=VENUE_OF.get(name, name),
                             artists=[title],
                             url=link_m.group(1).strip() if link_m else url))
    return out


# --------------------------------------------------------------- Ticketek

# The public site is an AngularJS shell (identical bytes for every URL), but
# app.settings_prod.js leaks the CMS backends and search/search.factory.js
# gives the path. No browser required.
TK_SEARCH = "https://prod-cms-search.ticketek.com.ar/api/1.1/search/"
TK_HEADERS = {**HEADERS, "Referer": "https://www.ticketek.com.ar/",
              "Accept": "application/json"}
# There is no "list everything" call, so enumerate by seed terms.
TK_TERMS = ["musica", "rock", "pop", "tango", "jazz", "folklore", "cumbia",
            "festival", "teatro", "recital", "vivo", "tour", "show",
            "internacional", "electronica", "reggaeton", "trap", "metal",
            "sinfonico", "ballet", "humor", "stand up"]


def scrape_ticketek(terms: list[str] | None = None) -> list[Event]:
    """NOTE: the search API's `date` field is always empty and the companion
    node API (api/1.0/node/...) returns 500, so Ticketek yields artist +
    venue + on-sale state but NO event date. These rows are therefore kept
    out of the dated calendar and exposed separately as "announced, date
    TBC" — useful for catching arena/theatre shows the other sources miss,
    and for knowing an artist is coming at all."""
    import time as _t
    sess = requests.Session()
    out, seen = [], set()
    for term in (terms or TK_TERMS):
        # This API briefly returns non-JSON under rapid fire; keep it slow.
        _t.sleep(1.5)
        try:
            r = sess.get(TK_SEARCH + term, headers=TK_HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:
            continue
        for row in data.get("resultados") or []:
            slug = row.get("url") or ""
            for show in (row.get("shows") or [{}]):
                venue = show.get("venue") or show.get("lugar") or ""
                key = (slug, show.get("showcode"))
                if not slug or key in seen:
                    continue
                seen.add(key)
                img = row.get("imagen") or ""
                if img.startswith("//"):
                    img = "https:" + img
                out.append(Event(
                    source="ticketek",
                    title=row.get("titulo", ""),
                    # The search API carries no date; the slug identifies the
                    # show and `estado` says whether it is on sale.
                    date="",
                    venue=venue,
                    artists=[row["titulo"]] if row.get("titulo") else [],
                    url=f"https://www.ticketek.com.ar/{slug}",
                    ticket_url=f"https://www.ticketek.com.ar/{slug}",
                    image=img,
                ))
    return out


ALL_SOURCES = {
    "resident-advisor": lambda: scrape_ra("2026-09-17", "2027-06-30"),
    "indiehoy": scrape_indiehoy,
    "crobar": scrape_crobar,
    "songkick": scrape_songkick,
    "venti": scrape_venti,
    "allaccess": scrape_allaccess,
    "bebop": scrape_bebop,
    "wp-feeds": scrape_wp_feeds,
}

# Dateless sources: real events, but no date, so they cannot join the
# calendar merge. Surfaced separately.
UNDATED_SOURCES = {
    "ticketek": scrape_ticketek,
}
