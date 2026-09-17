"""Shared plumbing for all Buenos Aires event scrapers.

Every scraper returns a list of Event dicts with the same shape so the
merge step doesn't need to know where a row came from.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Iterable

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

# Per-host politeness. venti.live and ra.co ask for it explicitly;
# songkick soft-blocks under load.
CRAWL_DELAY = {
    "venti.live": 10.0,
    "www.songkick.com": 6.0,
    "ra.co": 1.0,
    "www.allaccess.com.ar": 3.0,
    "indiehoy.com": 1.0,
}
_last_hit: dict[str, float] = {}


def polite_get(url: str, session: requests.Session | None = None,
               timeout: int = 30, **kw) -> requests.Response | None:
    """GET with per-host rate limiting. Returns None on failure."""
    host = re.sub(r"^https?://([^/]+).*", r"\1", url)
    delay = CRAWL_DELAY.get(host, 0.5)
    since = time.time() - _last_hit.get(host, 0)
    if since < delay:
        time.sleep(delay - since)
    _last_hit[host] = time.time()

    s = session or requests
    try:
        r = s.get(url, headers=HEADERS, timeout=timeout, **kw)
        if r.status_code != 200:
            return None
        return r
    except Exception:
        return None


# ---------------------------------------------------------------- normalizing

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


_VENUE_NOISE = re.compile(
    r"^\s*(tba\s*[-–]\s*|secret\s+location\s*[-–]?\s*)", re.I)
# Neighborhoods that get appended to venue names by RA et al.
_BARRIOS = {
    "palermo", "san telmo", "villa crespo", "chacarita", "colegiales",
    "costanera", "microcentro", "recoleta", "belgrano", "caballito",
    "almagro", "balvanera", "barracas", "boedo", "constitucion",
    "flores", "la boca", "monserrat", "nunez", "once", "paternal",
    "puerto madero", "retiro", "saavedra", "san nicolas", "abasto",
    "villa urquiza", "la plata", "cordoba", "rosario", "buenos aires",
    "caba", "capital federal", "haedo", "olivos", "vicente lopez",
}


def norm_venue(name: str | None) -> str:
    """Canonical venue key: lowercase, unaccented, no TBA prefix, no barrio."""
    if not name:
        return ""
    v = _VENUE_NOISE.sub("", name.strip())
    v = strip_accents(v).lower()
    v = re.sub(r"[''`´]", "", v)
    # Drop trailing ", barrio" segments
    parts = [p.strip() for p in v.split(",")]
    while len(parts) > 1 and parts[-1] in _BARRIOS:
        parts.pop()
    v = ", ".join(parts)
    # Common aliases
    # "crobar - buenos aires" / "crobar club" all collapse to "crobar"
    v = re.sub(r"\s*[-–]\s*buenos aires\b", "", v)
    v = re.sub(r"\bmovistar arena( argentina)?\b", "movistar arena", v)
    v = re.sub(r"\bteatro vorterix\b", "vorterix", v)
    v = re.sub(r"\bthe roxy( bar)?( live)?\b", "the roxy", v)
    v = re.sub(r"\bc (complejo )?art media\b", "c art media", v)
    v = re.sub(r"\bniceto( club)?\b", "niceto club", v)
    v = re.sub(r"\bcrobar( club)?( studio)?\b", "crobar", v)
    v = re.sub(r"\s+", " ", v).strip(" ,-")
    return v


_ARTIST_NOISE = re.compile(
    r"\s*\((uk|us|usa|ar|arg|de|nl|it|fr|es|br|cl|uy|mx|jp|be|se)\)\s*$", re.I)

# Fragments that are never an artist name. Matched against the whole string
# after cleaning, so "TBA" is dropped but "Tbar" survives.
_NOT_AN_ARTIST = re.compile(
    r"^(?:"
    r"[\W_]+"                                    # "&", "+", "-", "..."
    r"|(?:and\s+|y\s+|&\s*|\+\s*)?(?:more|m[aá]s)"
    r"(?:\s+(?:artists?|djs?|acts?|tba|tbc))?"    # "& MORE ARTISTS", "more djs TBA"
    r"|(?:more\s+)?(?:artists?|djs?|acts?|guests?)\s*(?:tba|tbc)?"
    r"|tba|tbc|tba\.|to be announced|a confirmar"
    r"|(?:very\s+)?special\s+guests?"
    r"|invitad[oa]s?(?:\s+internacional(?:es)?)?"
    r"|guests?|line ?up|vivo|b2b|b3b|b4b|vs|dj|djs"
    r"|live(?:\s*[\(\[][^\)\]]{0,6}[\)\]])?"      # "live", "LIVE [CO]"
    r"|y\s+m[aá]s|and\s+more|etc\.?"
    r")$", re.I)

# Performance markers that trail a real name: "Artist (live)", "Artist [CO]".
_PERF_MARKER = re.compile(
    r"\s*[\(\[]\s*(?:live|dj ?set|b2b|b3b|hybrid|vinyl only|all night long|"
    r"live [ab]/?v|a/?v)\s*[\)\]]\s*$", re.I)


def clean_artist(name: str | None) -> str | None:
    """Return a usable artist name, or None if the fragment isn't one.

    RA's `lineup` is free text ("Artist\\n+ TBA\\n& MORE ARTISTS"), so
    splitting it yields separators and placeholders that must be dropped
    rather than indexed as performers.
    """
    if not name:
        return None
    s = str(name).replace("\xa0", " ").strip()
    # Strip leading separators: "+ DREY" -> "DREY", "& Foo" -> "Foo".
    s = re.sub(r"^[\s&+/,;·\-–—]+", "", s)
    s = re.sub(r"[\s&+/,;·\-–—]+$", "", s)
    s = _PERF_MARKER.sub("", s).strip()
    s = re.sub(r"\s{2,}", " ", s)
    if len(s) < 2 or len(s) > 80:
        return None
    if _NOT_AN_ARTIST.match(s):
        return None
    # Reject anything with no letters at all.
    if not re.search(r"[^\W\d_]", s):
        return None
    return s


def norm_artist(name: str | None) -> str:
    if not name:
        return ""
    a = _ARTIST_NOISE.sub("", name.strip())
    a = strip_accents(a).lower()
    a = re.sub(r"[''`´]", "", a)
    a = re.sub(r"\s*\b(b2b|vs|&|\+)\b\s*", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a


# Titles carry the artist when JSON-LD has no `performer` (Venti, Indie Hoy).
# Order matters: strip trailing venue/date noise first, then split.
_TITLE_DATE_TAIL = re.compile(
    r"\s*[|(\[]?\s*\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?.*$|"
    r"\s*\d{1,2}\s+(?:de\s+)?(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\w*.*$",
    re.I)
# Leading "18.09 | ", "17/09 - ", "Vie 19 | " etc.
_TITLE_DATE_HEAD = re.compile(
    r"^\s*(?:(?:lun|mar|mi[eé]|jue|vie|s[aá]b|dom)\w*\s*)?"
    r"\d{1,2}(?:[./-]\d{1,2}(?:[./-]\d{2,4})?)?\s*[|·\-–—]\s*", re.I)
# Trailing weekday abbreviations left behind after the date is stripped.
_TITLE_DAY_TAIL = re.compile(
    r"\s+(?:lun|mar|mi[eé]|jue|vie|s[aá]b|dom)\w*\.?\s*$", re.I)
_TITLE_VENUE_SPLIT = re.compile(
    r"\s+(?:en vivo en|en el|en la|en)\s+|\s+@\s+|\s+[–—]\s+", re.I)
_TITLE_NOISE = re.compile(
    r"^\s*(presentaci[oó]n del libro|ciclo|fiesta|festival)\b\s*:?\s*", re.I)


def artists_from_title(title: str) -> list[str]:
    """Best-effort artist extraction for sources with no performer field.

    Conservative on purpose: returns [] rather than guess when the title
    looks like an event name rather than an artist billing.
    """
    if not title:
        return []
    t = _TITLE_DATE_HEAD.sub("", title)
    t = _TITLE_DATE_TAIL.sub("", t).strip(" |-–—·")
    t = _TITLE_DAY_TAIL.sub("", t)
    t = _TITLE_NOISE.sub("", t)
    # Drop anything after " en <venue>" / " @ <venue>".
    head = _TITLE_VENUE_SPLIT.split(t)[0].strip(" |-–—·,")
    if not head or len(head) < 2 or len(head) > 70:
        return []
    # Split co-billings, but not names that merely contain "y".
    parts = re.split(r"\s*(?:,|\+|\sy\s|\s&\s|\sb2b\s|\svs\.?\s)\s*", head,
                     flags=re.I)
    out = []
    for p in parts:
        p = p.strip(" |-–—·\"'")
        # Reject pure noise / all-digit / overly generic fragments.
        if (len(p) < 2 or p.isdigit()
                or re.fullmatch(
                    r"(amigos|invitados|more|m[aá]s|djs?|live|tba|tbc|"
                    r"secret|sorpresa|line ?up|artistas?)", p, re.I)):
            continue
        out.append(p)
    return out[:6]


def parse_date(raw) -> str | None:
    """Return YYYY-MM-DD or None. Accepts ISO strings and a few ES formats."""
    if not raw:
        return None
    if isinstance(raw, (datetime, date)):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
             "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
             "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    m = re.search(r"(\d{1,2})\s+de\s+([a-zA-Zéó]+)\s*(?:de\s*)?(\d{4})?", s, re.I)
    if m:
        d = int(m.group(1))
        mo = MESES.get(strip_accents(m.group(2)).lower())
        y = int(m.group(3)) if m.group(3) else date.today().year
        if mo:
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------- event model

@dataclass
class Event:
    source: str
    title: str
    date: str                      # YYYY-MM-DD
    venue: str = ""
    artists: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    url: str = ""
    ticket_url: str = ""
    price: str = ""
    image: str = ""
    lat: float | None = None
    lon: float | None = None
    start_time: str = ""

    def key(self) -> tuple:
        """Dedupe key: date + venue + lead artist (or title fallback)."""
        lead = norm_artist(self.artists[0]) if self.artists else ""
        if not lead:
            lead = norm_artist(re.split(r"[@|–—-]| en ", self.title)[0])
        return (self.date, norm_venue(self.venue), lead)

    def as_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------- json-ld

def iter_jsonld(html: str) -> Iterable[dict]:
    """Yield every JSON-LD node in a page, flattening @graph."""
    for blob in re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.S | re.I):
        blob = blob.strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node:
                    stack.extend(node["@graph"] if isinstance(node["@graph"], list)
                                 else [node["@graph"]])
                yield node


def is_event_node(node: dict) -> bool:
    t = node.get("@type", "")
    if isinstance(t, list):
        return any("Event" in str(x) for x in t)
    return "Event" in str(t)


def event_from_jsonld(node: dict, source: str, fallback_url: str = "") -> Event | None:
    """Build an Event from a schema.org Event node."""
    d = parse_date(node.get("startDate"))
    if not d:
        return None
    loc = node.get("location") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    venue = loc.get("name", "") if isinstance(loc, dict) else str(loc)

    lat = lon = None
    geo = loc.get("geo") if isinstance(loc, dict) else None
    if isinstance(geo, dict):
        try:
            lat = float(geo.get("latitude"))
            lon = float(geo.get("longitude"))
        except (TypeError, ValueError):
            pass

    offers = node.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    ticket = offers.get("url", "") if isinstance(offers, dict) else ""
    price = str(offers.get("price", "")) if isinstance(offers, dict) else ""

    img = node.get("image") or ""
    if isinstance(img, list):
        img = img[0] if img else ""
    if isinstance(img, dict):
        img = img.get("url", "")

    perf = node.get("performer") or []
    if isinstance(perf, dict):
        perf = [perf]
    artists = [p.get("name") for p in perf
               if isinstance(p, dict) and p.get("name")]

    return Event(
        source=source,
        title=(node.get("name") or "").strip(),
        date=d,
        venue=venue,
        artists=[a for a in artists if a],
        url=node.get("url") or fallback_url,
        ticket_url=ticket,
        price=price,
        image=img if isinstance(img, str) else "",
        lat=lat, lon=lon,
        start_time=str(node.get("startDate", ""))[11:16],
    )

# ── display hygiene ────────────────────────────────────────────────

# Emoji, dingbats, variation selectors. Promoters pepper flyers with these
# ("TOTAL BLACK x ARZ 🏴"); they add nothing in a dense listing and break
# alphabetical sorting in the artist view.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F900-\U0001F9FF"
    "\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF"
    "\uFE0F\u20E3\u200D]+")


def strip_emoji(text: str | None) -> str:
    if not text:
        return ""
    t = _EMOJI.sub(" ", str(text))
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" -–—|·,")


# Several sources emit a bare integer for price with no currency. In ARS a
# number like 15000 is meaningless on its own next to a start time, so we
# format it; anything already carrying a symbol or words is left alone.
def format_price(raw, source: str = "") -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if re.search(r"[^\d.,\s]", s):      # already has $, "Desde", "Gratis"…
        return s
    digits = s.replace(".", "").replace(",", "").strip()
    if not digits.isdigit():
        return s
    n = int(digits)
    if n == 0:
        return ""                       # 0 means "unknown", not "free"
    if n < 1000:
        # Ambiguous: too low for ARS in 2026, probably USD or a typo.
        return ""
    return "$" + f"{n:,}".replace(",", ".")


# Sale-window artefacts, not door times: Venti stamps 02:59 / 23:59 on the
# ticket listing and RA uses 23:59 as an end-of-day default.
_JUNK_TIMES = {"02:59", "23:59", "00:00", "02:45"}


def clean_time(t: str | None) -> str:
    if not t:
        return ""
    t = str(t).strip()[:5]
    if not re.fullmatch(r"\d{2}:\d{2}", t):
        return ""
    return "" if t in _JUNK_TIMES else t


# The site is Buenos Aires only; several feeds are national.
_NON_BA = re.compile(
    r"\b(mar del plata|c[oó]rdoba|rosario|mendoza|la plata|salta|tucum[aá]n|"
    r"neuqu[eé]n|bariloche|san juan|santa fe|paran[aá]|corrientes|"
    r"villa carlos paz|pinamar|carilo|caril[oó]|ezeiza|montevideo|punta del este)\b",
    re.I)


def is_buenos_aires(venue: str | None, title: str | None = "") -> bool:
    """False when a row is clearly for another city."""
    blob = f"{venue or ''} {title or ''}"
    return not _NON_BA.search(blob)
