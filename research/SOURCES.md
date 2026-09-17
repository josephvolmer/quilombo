# Buenos Aires Events — Source Inventory

Status legend: **A** = structured data, verified working · **B** = scrapable, needs parsing work · **C** = blocked / low value

All findings verified by direct HTTP probe on 2026-09-17. Failures record the actual status code / symptom so we don't retry blindly.

---

## Tier A — verified structured data

### 1. Resident Advisor (GraphQL) — deepest horizon, electronic only
- `POST https://ra.co/graphql` with `Content-Type: application/json`, `Referer: https://ra.co/events/ar/buenosaires`, `Origin: https://ra.co`
- **Buenos Aires area ID = `395`** (Argentina-wide = `45`), from RA's own `areas` query.
- Verified **120 events** for 2026-09-17 → 2027-06-30, `pageSize: 100` in one request.
- **Schema introspection is open** (`__type(name: "Event")`). Useful fields beyond the basics:
  - `genres { name }` — 21 distinct on page 1 (Techno, Tech House, Psytrance, Disco, Electro…)
  - `lineup` — raw string, **contains artists missing from `artists[]`** (e.g. `Iglesias`, `Dossom`). Parse both.
  - `promoters { id name }` (19 unique on page 1), `cost`, `isFestival`, `attending`, `flyerFront`, `startTime`, `contentUrl`
- 125 unique artists on page 1; artists have **stable IDs** — backbone for an artist-centric index.

### 2. Indie Hoy — best non-electronic source
- **`https://indiehoy.com/eventos/buenos-aires/` → 201 BA-filtered `/agenda/` links** (use this, not the national `/eventos/` page which returns 365 incl. Córdoba/Rosario/La Plata).
- Each detail page has clean schema.org `Event` JSON-LD: `name`, `startDate`, `location{name,address}`, `image`, **`offers{url, price, priceCurrency}`**.
- Sampled 45 pages: **45/45 parsed.** Range 2026-09 → 2026-12.
- Covers what RA misses: rock, indie, metal, punk, salsa, international tours.
- Sibling pages: `/eventos/cordoba`, `/eventos/rosario`.

**Trap:** `indiehoy.com/events.ics` and `/eventos/?ical=1` return a convincing 6MB iCalendar (3,318 VEVENTs with GEO coords) that **dead-ends in Nov 2017**. Abandoned Events Manager plugin feed. Do **not** wire it up.
`wp-json/wp/v2/event(s)` → **403**; `tribe/events/v1/events` → **403**; `/eventos/feed/` is a *comments* feed (0 items).

### 3. Crobar — best venue-direct source
- `https://crobar.com.ar/` — **13 schema.org `MusicEvent` blocks** inline on the homepage, through end of October.
- Fields: `name`, `startDate`, `description` (**full support-act lineup in prose**), `image`, `location` (`MusicVenue`), stable `@id` anchors.
- Covers both rooms (`/club`, `/studio`). Zero-cost parse, no pagination.

### 4. Songkick (JSON-LD `MusicEvent`)
- `https://www.songkick.com/metro-areas/32911-argentina-buenos-aires` — **50 events**, 51 JSON-LD blocks, artist + venue + `PostalAddress` + **`geo` lat/long** + image + ticket URL.
- **Metro pages only.** Verified back-to-back after a 20s cooldown: metro page = **200**, `venues/2404214-mandarine-park` = **406**, `?page=2` = **406**. This is a deliberate whitelist, not rate-limiting. Horizon ~2 weeks.
- Still the best source of **geocoordinates** for venue normalization.

### 5. Venti (`venti.live` — **not** `venti.com.ar`)
- `https://venti.live/sitemap.xml` — **637 URLs**, `lastmod` current. Event pages carry schema.org `Event` JSON-LD.
- `/api/event/*` is robots-allowed but returns **401 "No token provided"** — use the pages. **`Crawl-delay: 10`.**

---

## Tier B — scrapable, worth building parsers for

| Source | Verified finding |
|---|---|
| **AllAccess** | Runs on **Boletia/Boletius**. `/venue/<slug>` pages list events in HTML: **The Roxy Live alone = 47 events** with dates ("14 de Noviembre 2026"). No JSON-LD, but titles+dates are parseable. Known venue slugs: `the-roxy-bar-live`, `the-roxy-bar-and-grill`, `teatro-vorterix`. **Covers The Roxy + Vorterix from your list.** Site is behind **AWS WAF** (`awsWafCookieDomainList`) — throttle. |
| **Ticketek** | `sitemap-1.xml` = **15,000 URLs** (genre hubs + `/<show>/<venue>` pages) — biggest mainstream inventory, and the only route to Luna Park / Gran Rex / arena shows. **But event pages are a 17KB AngularJS shell**: the single JSON-LD block is empty, no og: tags, no dates in HTML. `core.js` exposes no API host. **Needs browser automation.** |
| **Bebop Club** | Own white-label ticketer at `ticketera.bebopclub.com.ar/evento/<uuid>`. **65 event UUIDs on the homepage.** No `/api/*` (all 404) — parse the homepage links. Jazz coverage, unavailable elsewhere. |
| **Uniclub** | Delegates ticketing to **Alpogo** (72 refs). Covering Alpogo likely covers Uniclub + others. Alpogo has no sitemap (404). |
| **Alternativa Teatral** | `sitemapindex.xml` → **12 sitemaps × ~50k URLs**. Mostly theater + forum noise; needs heavy URL filtering. No `/musica` section (404). |
| **Palermo Groove** | WordPress with **public RSS at `/feed/`**. |
| **Niceto Club** | WordPress with **public RSS at `/feed/`** — cheapest win in the list. |
| **Livepass** | 2 JSON-LD blocks. Confirmed ticket destination for major intl. shows via Indie Hoy `offers.url`. |
| **quehayba.com.ar / quepasaen.com** | **Byte-identical pages — same platform, dedupe them.** Astro; `/api/buscar` + `/api/destacados` exist but `Disallow`ed. |
| **TuEntrada** | 236KB, no JSON-LD / `__NEXT_DATA__`. DOM parsing required. Big venues (La Rural, arenas). |
| **La Trastienda** | 1.29MB page, 1 JSON-LD block. Worth a parser. |
| Alpogo, Flashpass, Tickethoy, Centralticket, Plateanet | Mid-size ticketers from El Cartel's outbound links. |
| Venue-direct | movistararena.com.ar, lunapark.com.ar, vorterix.com, culturalthames.com.ar, ccmatienzo.com.ar, clubsocial911.com, sindicatodemaravillas.com, congoclubcultural.com.ar, gorritiart.center, latangente.com.ar, ccomplejoartmedia.com.ar (C Art Media, 2KB shell — JS-rendered) |

---

## Tier C — blocked or low value (documented so we don't re-test)

| Source | Result |
|---|---|
| **Ticketmaster Argentina** | **Does not exist.** `ticketmaster.com.ar` has **no DNS record** (dig returns nothing, curl `000`). That market is served by Ticketek/AllAccess. Remove from the list. |
| **Passline** | **403 even with browser UA + `Accept-Language: es-AR`** (robots.txt serves, HTML doesn't). Edge-blocked; needs a real browser session. |
| **Bandsintown** | City page **403**; `rest.bandsintown.com` (v3 + legacy) → **explicit IAM deny**. Dead without a partner key. *(Note: its venue pages rank well in search and are a good way to* discover *venue names/IDs manually, but not to ingest.)* |
| **Buenos Aliens** | Legacy ColdFusion electronic-music **magazine** (`/notas.cfm/...`). "Agenda" is an on-page anchor (`/#agenda`), not a feed. No JSON-LD/API. RA covers this niche far better. |
| **Indie Folks** | 71KB static site, no JSON-LD/WP/API. It's a **promoter/label**, not a listings source — their shows surface via Indie Hoy and ticketers. |
| **VuenosaireS** | 77KB, no JSON-LD/WP/API/feed. Low structural value. |
| **Eventworld BA** | Domain does not resolve (`000`). |
| **Rolling Stone AR / La Viola** | Editorial WordPress; JSON-LD is `Article`/`WebPage`, not `Event`. Useful for *announcements* (lead time on tours) but not as an event feed. |
| **Luma** | Works via `__NEXT_DATA__` (12 events, `discplace-wX2J5xGwAJpznew`) but content is **tech/startup meetups, not concerts**. |
| **SeatGeek / JamBase / Songkick official API** | 403 / 403 / 401 (keys closed). |
| **BA Ciudad Agenda Cultural** | `buenosaires.gob.ar/agendacultural` → **302**; `disfrutemosba.buenosaires.gob.ar` returns **empty body** to curl (JS-rendered/geo-gated). Would need a headless browser. |
| **BA open data (CKAN)** | 454 datasets; culture ones exist but **event data is stale** — Teatro Colón `.ics` = **2016**, music CSV = **2017**, despite 2026 metadata timestamps. **Still useful:** `espacios-culturales` CSV/GeoJSON as a **venue reference table** for geocoding + name normalization. |

---

## Venues from your list — where each is actually covered

| Venue | Best route |
|---|---|
| Crobar | **Own site, JSON-LD (Tier A)** |
| Niceto Club | Own WP RSS + Venti + Indie Hoy |
| The Roxy Live | **AllAccess `/venue/the-roxy-bar-live` (47 events)** |
| Teatro Vorterix | AllAccess `/venue/teatro-vorterix` |
| Bebop Club | Own ticketera, 65 UUIDs |
| Uniclub | Via Alpogo |
| Palermo Groove | Own WP RSS |
| La Trastienda | Own site (1 JSON-LD block) |
| Movistar Arena, Luna Park | Songkick metro + Indie Hoy + Ticketek |
| C Art Media | JS-rendered shell; reach via Indie Hoy (confirmed: *Of Monsters and Men*) |
| Mandarine Park, Artlab, Deseo, Konex, Margarita Xirgu | **No usable direct site.** Reach via RA (electronic) / Indie Hoy (confirmed Artlab: *Ignacia en Artlab*) / Ticketek |

Key structural insight: **venues delegate to ticketers** (Uniclub→Alpogo, Bebop→own ticketera, Roxy/Vorterix→AllAccess). Covering ~6 ticketers captures far more venues than scraping 20 venue sites individually.

---

## Do venues publish their own listings? — measured, n=14

A venue-first strategy sounds right ("go to the source") but does not survive testing.
Checked each venue's own homepage for schema.org `Event` JSON-LD, and for which
ticketer it hands off to:

| Venue | Own Event JSON-LD | Delegates to |
|---|---|---|
| Crobar | **13** | ticketera |
| Niceto | 0 | passline, venti.live |
| La Trastienda | 0 | passline |
| Palermo Groove | 0 | passline |
| Cultural Thames | 0 | ticketera |
| Matienzo | 0 | flashpass, ticketera |
| Movistar Arena | 0 | ticketera |
| Bebop | 0 | ticketera (own white-label) |
| Uniclub | 0 | alpogo |
| Club Social 911 | 0 | passline, ticketera |
| Luna Park | 0 | — |
| Vorterix | 0 | — |
| Congo | 0 | — |
| Sindicato de Maravillas | 0 | — |

**13 of 14 publish zero structured event data.** Venue sites are marketing pages
that link out to whoever sells the tickets. "Going to the source" therefore means
going to the **ticketer**, not the venue.

Measured on a real merged run (future-dated events only):

| Strategy | Events |
|---|---|
| Venue-direct only (Crobar + WP feeds) | **11** |
| Aggregators + ticketers | **383** |

### On "aren't RA and Indie Folks just aggregators?"
- **RA is a primary source**, not an aggregator. Promoters submit events directly to
  it — its schema exposes `submissionSource`, `approvalStatus`, `dateCreated`,
  `autoApproved`. For most BA club nights there is no upstream to go to; RA *is* it.
- **Indie Folks is a promoter/label**, not a listings site (hence no structured data
  on its site). Its shows surface via Indie Hoy and the ticketers.
- **Indie Hoy is editorial**, writing up shows it selects — closer to a curated
  primary source than a scraper of others.

---

## Coverage analysis — how we beat El Cartel

El Cartel claims "5.186 eventos / 33 fuentes". No public sources page (`/fuentes`, `/about` → 404); their set was recovered by harvesting outbound hosts and resolving `/go/<uuid>` redirects (302 → original ticket URLs).

**Weaknesses found:**
1. **Day-by-day browsing only** — no artist-level view, no multi-month overview.
2. **Source count inflated** — `quehayba.com.ar` and `quepasaen.com` serve byte-identical pages.
3. **Ticketer-centric** — surfaces what's *on sale*, not what's *announced*.
4. **RA absent** from their outbound hosts → electronic coverage materially thinner than RA's 120-event/9-month window.

**Our advantages:**
- **RA (electronic, 9mo) + Indie Hoy (rock/indie/intl, 3mo) are complementary and barely overlap** — neither is an El Cartel source.
- Both expose **artists as first-class entities** (RA has stable IDs), enabling the artist-first index El Cartel can't do.
- RA `genres` + Indie Hoy categories give **genre filtering** for free.

---

## Recommended build order

1. **RA GraphQL** (area 395) — artist IDs, genres, 9-month horizon. Parse `lineup` *and* `artists[]`.
2. **Indie Hoy `/eventos/buenos-aires/` → 201 `/agenda/` pages** — non-electronic backbone, incl. price + ticket URL.
3. **Crobar JSON-LD** — one request, 13 events, free.
4. **Venti sitemap → JSON-LD** (`Crawl-delay: 10`).
5. **Songkick metro page**, throttled — geocoordinates.
6. **AllAccess `/venue/*`** — Roxy, Vorterix. **Niceto + Palermo Groove RSS.**
7. **Bebop ticketera** (65 UUIDs) — jazz.
8. **Ticketek sitemap** (15k URLs) — mainstream volume, biggest effort.
9. **`espacios-culturales` GeoJSON** — venue normalization table.

### Dedupe design
Key on **normalized artist + date + normalized venue**. Venue aliasing is mandatory:
- RA emits `TBA - Crobar Club, Palermo` vs. Crobar's own `Crobar` → strip `TBA - ` prefix and trailing neighborhood.
- Indie Hoy `Movistar Arena Argentina` / locality `Villa Crespo`; Songkick `Movistar Arena` / `Buenos Aires`.
- Use `offers.url` / ticket host as a secondary join key.

### Known gap
Instagram-first promoters (much of BA's underground) publish nowhere machine-readable. RA's `promoters` field (19 on page 1) is the best proxy for identifying who they are.
