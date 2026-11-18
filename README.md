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
| Map | NAVER Maps (Web Dynamic Map) |
| Database | SQLite (local) / PostgreSQL (production) + SQLAlchemy |
| Data | Google Places API, Public Data Portal (data.go.kr), Korea Tourism Organization TourAPI |
| Dashboard | pandas, Plotly |
| Hosting | Vercel |

## Project structure

```
Trippin/
├─ app.py              # Flask entry point (Vercel looks for `app` here)
├─ requirements.txt    # Dependencies
├─ public/             # Static files (logo, favicon, CSS, JS), served by Vercel's CDN
├─ templates/          # Jinja2 pages (planned)
├─ core/               # Filtering, scoring, ranking and review logic (planned)
├─ data/               # Data collection scripts, run locally only (planned)
└─ i18n/               # Translation files per language (planned)
```

## Running locally

```bash
git clone https://github.com/joony06/Trippin.git
cd Trippin

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # fill in the values
flask --app app run --debug      # http://localhost:5000
```

## Environment variables

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**

| Name | Purpose | Needed in |
|---|---|---|
| `SECRET_KEY` | Signs login sessions | Local · Vercel |
| `DATABASE_URL` | PostgreSQL URL (leave empty to use local SQLite) | Vercel |
| `NAVER_MAP_CLIENT_ID` | Displays the NAVER map | Local · Vercel |
| `GOOGLE_PLACES_KEY` | Collects ratings and opening hours | Local (collection scripts only) |

## Deployment

Pushing to `main` deploys to production on Vercel automatically. Other branches and pull requests get preview deployments.

## Team (Team 13)

| Learning pair | Name | Role |
|---|---|---|
| 1 · Planning & frontend | Hanhee Park | Scoring review, review/rating system design, reports |
| 1 · Planning & frontend | Nayeon Kim | UI design, search conditions & scoring design, multilingual UI |
| 2 · Data & backend | Gayeon Kim | NAVER Maps integration, filtered search, opening-hours collection |
| 2 · Data & backend | Wonjun Choi | Google API integration, dashboard aggregation, place data & descriptions |

> A project for *Problem Solving and Computing* at Sungkyunkwan University
