<p align="center">
  <img src="public/logo-wordmark.png" alt="Trippin" width="420">
</p>

<p align="center">
  <b>English</b> | <a href="README.ko.md">Korean</a>
</p>

<p align="center">
  <b>Discover local Korea in the order that fits you, not the order ads pay for.</b><br>
  A map-based local tourism website that connects domestic and international tourists to small businesses and SMEs in regional Korea.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white">
  <img src="https://img.shields.io/badge/Pilot-Jung--gu%2C%20Daejeon-1E5BD8">
</p>

---

## About

Inbound tourists and their spending are heavily concentrated in Seoul, and on existing map services, small shops that can't afford advertising are easily buried.
**Trippin** ranks places by **how well they match each visitor's conditions** instead of by ad spend, helping tourists discover the local streets and shops of regional cities.

- Pilot area: **Jung-gu, Daejeon**
- Stores run by large conglomerates are excluded, and local small businesses and SMEs are surfaced first.

## Features

| # | Feature | For | Description |
|---|---|---|---|
| 1 | **Filtered search** (core) | Tourists | Filters by distance, budget, opening hours and conglomerate affiliation, then ranks by a weighted sum of six criteria (S1–S6) |
| 2 | **Small business dashboard** | Business owners | Free stats on views, saves, traffic sources and visitor makeup |
| 3 | **Reviews & ratings** | Tourists | One review per user; Bayesian averaging keeps places with few reviews from being over- or under-rated |
| 4 | **Multilingual UI** | Tourists & owners | Korean, English, Chinese and Japanese |

### Scoring at a glance

$$S = 100 \times \sum_{i=1}^{6} w_i \cdot s_i$$

| Criterion | Weight | Description |
|---|---|---|
| S1 Category match | 0.35 | Share of the selected categories the place matches |
| S2 Keyword relevance | 0.20 | Name 1.0 · Category 0.7 · Description 0.4 |
| S3 Distance | 0.20 | `max(0, 1 − d / D_max)`, D_max = 10 km |
| S4 External rating | 0.10 | Bayesian-adjusted Google rating (m = 50) |
| S5 Popularity | 0.08 | Log-scaled review count |
| S6 Own ratings & saves | 0.07 | 70% in-app rating (m = 5) + 30% saves |

After sorting, a **diversity adjustment** multiplies the next candidate's score by `0.9^k` when k places of the same main category have already been listed.

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3.12 |
| Web | Flask, Jinja2 templates, HTML/CSS |
| Map | Leaflet + OpenStreetMap (MVP) → NAVER Maps later |
| Database | SQLite via Python's built-in `sqlite3` |
| Data | Public Data Portal (small business store info), Korea Tourism Organization TourAPI, Google Places API |
| Hosting | Vercel |

## MVP status

| # | Feature | Status |
|---|---|---|
| 1 | Filtered search | Hard filters, S1–S6, ranking and diversity adjustment work on sample data |
| 2 | Business dashboard | Views (7 days), saves, traffic sources, domestic/international ratio, top keywords, category average, rule-based tips |
| 3 | Reviews & ratings | Sign-up/login, one review per user (editable), saves, Bayesian adjustment fed into S6 |
| 4 | Multilingual UI | Korean, English, Chinese and Japanese UI text (place names and descriptions are Korean for now) |

The 13 places in `data/sample_places.json` are demo data: coordinates are approximate, and ratings, review counts, fees and hours are example values.

## Project structure

```
Trippin/
├─ app.py                 # Flask routes (Vercel looks for `app` here)
├─ db.py                  # SQLite tables, queries, dashboard aggregation
├─ core/
│  ├─ search.py           # Hard filters → S1–S6 → ranking & diversity adjustment
│  ├─ reviews.py          # Bayesian-adjusted ratings
│  ├─ geo.py              # Haversine distance
│  └─ i18n.py             # Translation lookup
├─ data/
│  ├─ sample_places.json  # Demo places in Jung-gu, Daejeon
│  └─ collect_sbiz.py     # Store-info API collection script (draft)
├─ i18n/                  # ko / en / zh / ja UI text
├─ templates/             # Jinja2 pages
├─ public/                # CSS, map script, logo (served by Vercel's CDN)
└─ tests/                 # Scoring tests (reproduces the mid-term report example)
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

- The database (`trippin.db`) is created with sample data on first run. Reset it with `flask --app app init-db`.
- Run tests with `pip install pytest` and then `python -m pytest`.

## Environment variables

Copy `.env.example` to `.env`. **Never commit `.env`.**

| Name | Purpose | Needed in |
|---|---|---|
| `SECRET_KEY` | Signs login sessions | Local · Vercel |
| `DATA_GO_KR_KEY` | Public Data Portal key for collection scripts | Local only |
| `NAVER_MAP_CLIENT_ID` | NAVER map (later) | Local · Vercel |
| `TRIPPIN_DB` | SQLite file path (optional) | Local |

## Deployment

Pushing to `main` deploys to production on Vercel automatically. On Vercel the SQLite file lives in `/tmp`, so reviews and accounts reset from time to time; use a local run for the final demo, or move to a hosted database later.

## Team (Team 13)

| Learning pair | Name | Role |
|---|---|---|
| 1 · Planning & frontend | Hanhee Park | Scoring review, review/rating system design, reports |
| 1 · Planning & frontend | Nayun Kim | UI design, search conditions & scoring design, multilingual UI |
| 2 · Data & backend | Gayeon Kim | NAVER Maps integration, filtered search, opening-hours collection |
| 2 · Data & backend | Wonjoon Choi | Google API integration, dashboard aggregation, place data & descriptions |

> A project for *Problem Solving and Computing* at Sungkyunkwan University

## License

Copyright (c) 2026 최원준 (Wonjoon Choi) and the Trippin team (김가연, 김나연, 박한희, 최원준). All rights reserved. See [LICENSE](LICENSE).
