# แผนที่ความเสี่ยง กรุงเทพฯ–ภาคตะวันออก · Bangkok–Eastern Risk & Incident Map

A static website that plots road **accidents, construction, weather, flooding, closures and fires**
on a Google-Maps-style map, keeps a **rolling 7-day history**, and refreshes **twice a day**
via GitHub Actions. Built to run for free on **GitHub Pages** — no server, no API keys, no billing.

**Coverage:** Bangkok through the eastern seaboard — Chonburi, Pattaya, Si Racha, Laem Chabang,
Rayong / Map Ta Phut — plus the corridor between them (Motorway 7 and the Bang Na–Trat Highway).
Change the framed area via `COVERAGE` in `assets/app.js`.

Sources it is designed to aggregate: **JS100**, **สวพ.91 (FM91 Trafficpro)**, **ศูนย์วิทยุพระราม 9**.

---

## What's in the box

```
risk-incident-map/
├── index.html                  # the map page
├── assets/
│   ├── style.css               # layout + light/dark theme
│   └── app.js                  # Leaflet map, filters, 7-day history, list
├── data/
│   ├── incidents.json          # the live data the site reads (seeded with samples)
│   └── manual_incidents.csv    # curated input you edit — the reliable data path
├── scripts/
│   ├── fetch_incidents.py      # builds/refreshes incidents.json (geocode, merge, prune)
│   ├── preview.ps1             # local preview server (used by preview.cmd)
│   └── requirements.txt
├── preview.cmd                 # double-click to preview locally (Windows, no tools)
├── .github/workflows/update.yml# cron: 06:00 & 18:00 Asia/Bangkok
└── README.md
```

The map uses **Leaflet + CARTO Voyager tiles** (free, key-less, OpenStreetMap-based) — this gives
the Google-Maps look with clickable icon pins without needing a paid Google Maps API key. See
[Using real Google Maps](#optional-real-google-maps) if you specifically want Google's tiles.

---

## See it locally

The page loads `data/incidents.json` with `fetch()`, which browsers block on `file://`,
so it must be served over HTTP. Easiest options:

- **Windows, no tools needed:** double-click **`preview.cmd`** — it starts a tiny local server
  and opens `http://localhost:8000/`. Close the window to stop it.
- **Have Python:** `python -m http.server 8000`, then open `http://localhost:8000/`.
- **VS Code:** install the *Live Server* extension → right-click `index.html` → *Open with Live Server*.

---

## Deploy to GitHub Pages (free hosting)

1. Create a new GitHub repo and put **the contents of this folder at the repo root**
   (so `index.html` is at the top level).
2. Push it to the `main` branch.
3. Repo **Settings → Pages** → *Build and deployment* → **Deploy from a branch** →
   Branch `main`, folder `/ (root)` → **Save**.
4. Your site goes live at `https://<username>.github.io/<repo>/`.

That's it for hosting. The twice-daily automation is next.

---

## The twice-a-day update

`.github/workflows/update.yml` runs on this cron:

```
0 11,23 * * *      # 11:00 & 23:00 UTC  = 18:00 & 06:00 Asia/Bangkok
```

Each run it: installs deps → runs `fetch_incidents.py` → commits `data/incidents.json`
back to the repo (which re-publishes the Pages site). You can also trigger it by hand from the
**Actions** tab → *Update incidents* → **Run workflow**.

**To change the times**, edit the cron (times are UTC; Bangkok = UTC + 7).
**Nothing needs installing on your PC** — GitHub's runner provides Python.

> First-time note: the workflow needs write access. It's already set via
> `permissions: contents: write`. If a push is rejected, check
> **Settings → Actions → General → Workflow permissions → Read and write**.

---

## How incidents get onto the map

There are three layers, in order of reliability:

### 1. `data/manual_incidents.csv` — the dependable path (recommended)
Add a row per incident and the updater geocodes + publishes it. Columns:

| column         | required | notes                                                        |
|----------------|----------|--------------------------------------------------------------|
| `source`       | yes      | `JS100` · `FM91` · `RAMA9` · `MANUAL`                         |
| `category`     | yes      | `accident` `construction` `weather` `flood` `closure` `fire` `other` |
| `severity`     | no       | `low` `medium` `high` (default `medium`)                     |
| `title_th`     | yes      | Thai headline shown on the pin/list                          |
| `title_en`     | no       | English subtitle                                             |
| `location_text`| yes*     | e.g. `อโศก`, `พระราม 9` — used to geocode if lat/lng blank    |
| `lat`, `lng`   | no       | fill these to place exactly; otherwise auto-geocoded         |
| `reported_at`  | no       | ISO time e.g. `2026-08-15T05:40:00+07:00` (default: now)     |
| `url`          | no       | link back to the source post                                 |
| `status`       | no       | `active`/`cleared`; leave blank to auto-clear after 8h        |

\* Provide **either** `location_text` (for geocoding) **or** `lat`+`lng`.
Geocoding uses a built-in Bangkok gazetteer first (instant, offline), then falls back to
free OpenStreetMap Nominatim. Add your frequent spots to `GAZETTEER` in the script.

### 2. Source scrapers — best-effort (off by default)
`fetch_js100() / fetch_fm91() / fetch_rama9()` in `scripts/fetch_incidents.py` are stubs.
**None of the three sources publishes a public API** — they push through their apps and social
accounts (JS100 → js100.com & X `@js100radio`; FM91 → Facebook/TikTok/YouTube; Rama 9 → rescue
radio net). To automate one, implement its function and set `ENABLE_SCRAPERS: "1"` in the workflow.
For an X-based JS100 feed, add an `X_BEARER` repo secret and read it via `os.getenv("X_BEARER")`.
The scrapers are wrapped so a failure never breaks the scheduled run.

### 3. The seed data
`data/incidents.json` ships with realistic sample incidents so the map looks right immediately.
The first real updater run replaces them.

---

## Data model

```jsonc
{
  "updated": "2026-08-15T06:05:00+07:00",
  "incidents": [
    {
      "id": "js100-20260815-0540-ab12cd",
      "source": "JS100",              // JS100 | FM91 | RAMA9 | MANUAL
      "category": "accident",         // accident|construction|weather|flood|closure|fire|other
      "severity": "high",             // low | medium | high
      "title_th": "…", "title_en": "…",
      "location_text": "ดินแดง",
      "lat": 13.7695, "lng": 100.5497,
      "reported_at": "2026-08-15T05:40:00+07:00",
      "status": "active",             // active | cleared (auto after 8h)
      "url": "https://…"
    }
  ]
}
```

The site's time filter: **Active** (status active / within 8h) · **24h** · **7 วัน** (full history).
Cleared/older pins render faded. History older than 7 days is pruned automatically.

---

## Customize

- **Categories / colors / icons** — edit `CATEGORIES` in `assets/app.js` (mirror in the script's
  `VALID_CATEGORIES`).
- **Coverage / map framing** — `COVERAGE` (SW/NE corners) and `REGION_CENTER` in `assets/app.js`.
- **Active window / history length** — `ACTIVE_WINDOW_HOURS` and `HISTORY_DAYS` env vars
  (in the workflow, or `assets/app.js` `ACTIVE_WINDOW_H`).
- **Map style** — swap the CARTO tile URL for `positron` (lighter) or a standard OSM URL.

### Optional: real Google Maps
Google Maps JS API needs an API key with billing enabled and domain restrictions — heavier for a
static Pages site, which is why this ships with key-less CARTO/Leaflet. If you still want it, replace
the Leaflet tile layer with the Google Maps JS SDK and reuse the same `data/incidents.json`.

---

## Notes & attribution

- Basemap © OpenStreetMap contributors, © CARTO.
- Incident content belongs to the respective broadcasters (JS100, สวพ.91, ศูนย์วิทยุพระราม 9);
  always credit the source and link back where possible.
- This is an information/aggregation tool — verify before acting on any incident.
