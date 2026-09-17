# Cartelera BA

Concert aggregator for Buenos Aires. Scrapes 9 sources, merges and dedupes them,
and ships the whole thing as a static site — **no backend, no database, no API**.

Current output: **631 future events · 895 artists · 190 venues**, up to 9 months ahead.

## How it works

```
GitHub Actions (daily cron)
  └─ scrapers/run.py         fetch every source, merge, dedupe  → data/*.json
  └─ scrapers/build_site.py  compact payload + static shell     → public/
  └─ wrangler pages deploy   publish public/                    → Cloudflare Pages
```

The entire dataset is **~45KB gzipped**, so the browser downloads it once and does
all filtering, searching and grouping client-side. That is what removes the need for
a server: there is nothing to query.

## Views

- **Por fecha** — every show grouped by day, months visible in one scroll.
- **Por artista** — one entry per artist with all their dates. This is the view
  El Cartel doesn't have, and the reason the project exists.

Filters: free-text search, month, venue, genre. All instant, all client-side.

## Sources

| Source | Method | Notes |
|---|---|---|
| Resident Advisor | GraphQL (area 395) | Primary source, artist IDs + genres, 9mo horizon |
| Venti | sitemap → JSON-LD | Cached by `lastmod`; respects `Crawl-delay: 10` |
| Indie Hoy | `/eventos/buenos-aires/` → JSON-LD | Rock/indie/intl, carries price + ticket URL |
| AllAccess | venue pages | The Roxy, Vorterix |
| Bebop Club | own ticketera | Jazz; artist in `og:title` |
| Songkick | JSON-LD metro page | Geocoordinates; page 1 only (`?page=2` → 406) |
| Crobar | JSON-LD on homepage | Only venue that self-publishes structured data |
| WordPress feeds | RSS | Niceto, Palermo Groove |
| Ticketek | undocumented JSON API | **No dates** → kept in `undated.json` |

Full notes, including what's blocked and why, in [`research/SOURCES.md`](research/SOURCES.md).

## Running locally

```bash
pip install requests
python scrapers/run.py          # scrape + merge  (~2 min warm, ~20 min cold)
python scrapers/build_site.py   # build public/
cd public && python -m http.server 8000
```

The first run is slow because Venti asks for a 10-second crawl delay across ~226
pages. `data/venti_cache.json` makes every later run ~1s.

## Deploying

Live at **[quilombo.vip](https://quilombo.vip)**, hosted on Cloudflare Pages.

Cloudflare Pages is connected to this repo and watches `main`:

```
cron (09:00 UTC daily)
  └─ scrapers/run.py        → data/*.json
  └─ scrapers/build_site.py → public/
  └─ git push               → Cloudflare rebuilds automatically
```

No API tokens, no deploy step, no secrets. The workflow's only job is to
scrape, rebuild `public/`, and commit; pushing to `main` is what publishes.

Pages settings (set once, at project creation):

| Setting | Value |
|---|---|
| Production branch | `main` |
| Framework preset | None |
| Build command | *(empty)* |
| Build output directory | `public` |

The site is prebuilt and committed, so Cloudflare only serves static files —
there is no build step to break.

## Caveats

- **Ticketek has no dates.** Its search API's `date` field is always empty and the
  node API 500s, so those 88 listings live in `undated.json` and are excluded from
  the calendar rather than faked.
- **Passline is unreachable.** Cloudflare bot challenge (`cf-mitigated: challenge`),
  which specifically targets datacenter IPs — a CI runner will never get past it.
  Its key venues (Niceto, La Trastienda, Palermo Groove) are covered via other sources.
- **Sources barely overlap** — only ~20 events are confirmed by 2+ sources. That
  fragmentation is the problem this project solves, but it also means a single
  source breaking silently loses real coverage. The workflow fails the run if future
  events drop below 200 or fewer than 5 sources report.
