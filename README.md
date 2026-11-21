<p align="center">
  <img src="public/logo-wordmark.png" alt="Trippin" width="420">
</p>

<p align="center">
  <b>English</b> | <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <b>Local travel beyond Seoul, in the order that fits you, not the order ads pay for.</b><br>
  A map-based local tourism website that connects domestic and international visitors to small businesses in regional Korea.
</p>

<p align="center">
  <a href="https://trippin-map.vercel.app"><b>trippin-map.vercel.app</b></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white">
  <img src="https://img.shields.io/badge/Pilot-Jung--gu%2C%20Daejeon-1E5BD8">
</p>

---

## About

Most inbound tourists, and most of what they spend, stay in Seoul. On existing map apps the top results are ads, so small local shops that can't pay for promotion are easy to miss.

**Trippin** ranks places by **how well they match each visitor's conditions** and shows the score behind every rank, so visitors can see why a place comes first.

- Pilot area: **Jung-gu, Daejeon** — 3,484 places from public data, 3,007 shown on the map
- Stores of large conglomerates and large chains are removed before ranking

## Features

| # | Feature | For | What it does |
|---|---|---|---|
| 1 | **Filtered search** (core) | Visitors | Filters by distance, opening hours, budget, category and chain status, then ranks by six criteria (S1–S6). Results on a map with numbered pins, a per-place score bar, neighborhood summary and category chips |
| 2 | **Small business dashboard** | Owners | Free 7-day views, saves, traffic sources, domestic/international visitors, top keywords, category average and rule-based tips |
| 3 | **Reviews & ratings** | Visitors | One review per member and saves; Bayesian-adjusted ratings feed back into the next search |
| 4 | **Four languages** | Everyone | Korean, English, Chinese and Japanese UI; English place names and descriptions where available, romanized names otherwise |

### Scoring

$$S = 100 \times \sum_{i=1}^{6} w_i \cdot s_i$$

| Criterion | Weight | How |
|---|---|---|
| S1 Category match | 0.35 | Share of the chosen categories the place matches |
| S2 Keyword relevance | 0.20 | Name 1.0 · category 0.7 · description 0.4 (Korean, English and romanized names) |
| S3 Distance | 0.20 | `max(0, 1 − d / 10 km)` from your location, or Jung-gu Office if you are outside Jung-gu |
| S4 Google rating | 0.10 | Bayesian-adjusted rating (m = 50, C = 4.0) |
| S5 Popularity | 0.08 | Log-scaled Google review count |
| S6 Trippin ratings & saves | 0.07 | 70% in-app rating (m = 5) + 30% saves |

- **Hard filters first:** distance, opening hours, budget, conglomerate, large chain, and — when categories are chosen — places that match none of them.
- **Missing data:** unused criteria are dropped and the weights renormalized; places without Google data get a neutral 0.5 for S4 and S5.
- **Diversity:** when k places of the same main category are already listed, the next one is multiplied by `0.9^min(k, 3)`.
- Ties break by distance, then review count.

## Data

| Source | Used for |
|---|---|
| SEMAS store information (data.go.kr) | Restaurants and cafés in Jung-gu; chain detection across Daejeon |
| Korea Tourism Organization TourAPI (Korean & English) | Attractions, photos, English names and overviews |
| Google Places API | Ratings, review counts and opening hours (634 places matched) |
| Gemini API | Short Korean and English descriptions written from TourAPI overviews |
| Team review sheet | 3,490 places checked by hand for conglomerates, chains and non-shops |

`data/build_places.py` merges everything into `data/places.json`. Collection scripts need API keys and are run locally only.

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3.12 |
| Web | Flask, Jinja2, HTML/CSS (SUIT typeface) |
| Map | NAVER Maps API v3, with automatic fallback to Leaflet + OpenStreetMap |
| Database | SQLite via Python's built-in `sqlite3` |
| Hosting | Vercel |

## Project structure

```
Trippin/
├─ app.py                  # Flask routes (Vercel looks for `app` here)
├─ db.py                   # SQLite tables, queries, dashboard stats
├─ core/
│  ├─ search.py            # Hard filters → S1–S6 → ranking & diversity
│  ├─ reviews.py           # Bayesian-adjusted ratings
│  ├─ geo.py               # Distance and starting point
│  ├─ romanize.py          # Korean → Latin letters for non-Korean screens
│  └─ i18n.py              # Translation lookup
├─ data/
│  ├─ collect_sbiz.py      # SEMAS store information
│  ├─ collect_tour.py      # TourAPI
│  ├─ collect_google.py    # Google Places
│  ├─ gen_descriptions.py  # Gemini descriptions
│  ├─ build_places.py      # Merge → places.json
│  ├─ seed_demo.py         # Demo accounts and dashboard data
│  ├─ places.json          # Built place data (committed)
│  └─ store_verdicts.json  # Team review results
├─ i18n/                   # ko / en / zh / ja UI text
├─ templates/              # Pages
├─ public/                 # CSS, map scripts, logo (served by Vercel's CDN)
├─ tests/                  # 21 tests, incl. the mid-term report example (A 67.6, B 46.3)
└─ docs/handoff/           # Team handoff notes
```

## Running locally

```bash
git clone https://github.com/joony06/Trippin.git
cd Trippin

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

flask --app app run --debug      # http://localhost:5000
```

- The database is created on first run from `data/places.json`, with demo data. Reset it with `flask --app app init-db`.
- Without `.env` the site still runs, using the OpenStreetMap map.
- Tests: `pip install pytest`, then `python -m pytest -q`.

**Demo accounts** (password `trippin-demo`): `demo_owner` opens the business dashboard; `demo_kr1`, `demo_us1`, `demo_jp1` and others are visitor accounts.

## Environment variables

Copy `.env.example` to `.env`. **Never commit `.env`.**

| Name | Purpose | Where |
|---|---|---|
| `SECRET_KEY` | Signs login sessions | Local · Vercel |
| `NAVER_MAP_CLIENT_ID` | NAVER map | Local · Vercel |
| `DATA_GO_KR_KEY` | Public Data Portal (collection) | Local only |
| `GOOGLE_PLACES_KEY` | Google Places (collection) | Local only |
| `GEMINI_API_KEY` | Descriptions (collection) | Local only |
| `TRIPPIN_DB` | SQLite file path (optional) | Local |

## Rebuilding the data

```bash
python data/collect_sbiz.py            # Jung-gu stores
python data/collect_sbiz.py --daejeon  # all of Daejeon, for chain detection
python data/collect_tour.py && python data/collect_tour.py --detail
python data/collect_google.py --limit 850
python data/gen_descriptions.py
python data/build_places.py
```

## Deployment

Pushing to `main` deploys to production on Vercel. On Vercel the SQLite file lives in `/tmp`, so new accounts and reviews reset when the server restarts; demo data is added back automatically.

## Team — SKKU *Problem Solving and Computing*, Team 13

| Name | Role |
|---|---|
| Wonjoon Choi | Lead developer: data pipeline, search engine, dashboard, design |
| Gayeon Kim | Developer: current location, NAVER map, neighborhood summary, code review |
| Hanhee Park | Brand and store review, user testing, report |
| Nayun Kim | Brand and store review, translation review, report and slides |

## License

Copyright (c) 2026 Wonjoon Choi and Team Trippin (Gayeon Kim, Nayun Kim, Hanhee Park, Wonjoon Choi). All rights reserved. See [LICENSE](LICENSE).
