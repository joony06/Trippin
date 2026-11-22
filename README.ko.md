<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="public/logo-wordmark-card.png">
    <img src="public/logo-wordmark-card.png" alt="Trippin" width="420">
  </picture>
</p>

<p align="center">
  <a href="README.md">English</a> | <b>한국어</b>
</p>

<p align="center">
  <b>광고가 아닌, 나에게 맞는 순서로 찾는 지방 로컬 여행</b><br>
  국내외 관광객을 지방의 소상공인·중소기업 점포로 연결하는 지도 기반 로컬 관광 웹사이트
</p>

<p align="center">
  <a href="https://trippin-map.vercel.app"><b>trippin-map.vercel.app</b></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white">
  <img src="https://img.shields.io/badge/시범구역-대전%20중구-1E5BD8">
</p>

---

## 소개

방한 관광객과 관광 소비는 서울에 몰려 있고, 기존 지도 앱은 검색 결과 위쪽이 광고라서 홍보비를 내기 어려운 작은 가게가 잘 보이지 않습니다.

**트립핀(Trippin)** 은 광고비가 아니라 **이용자 조건과 얼마나 잘 맞는지**로 순위를 정하고, 순위마다 점수 구성을 공개해 왜 이 순서인지 보여 줍니다.

- 시범 구역: **대전 중구** — 공공데이터 3,484곳 중 지도에 3,007곳 표시
- 대기업 계열과 대형 체인은 순위를 매기기 전에 뺍니다

## 주요 기능

| # | 기능 | 사용자 | 설명 |
|---|---|---|---|
| 1 | **필터링 검색** (핵심) | 관광객 | 거리·영업시간·예산·카테고리·체인 여부로 거른 뒤 6개 기준(S1~S6)으로 순위. 번호 핀 지도, 장소별 점수 구성 막대, 동네별 요약, 카테고리 칩 |
| 2 | **소상공인·중소기업 대시보드** | 사업자 | 최근 7일 조회수, 찜, 유입 경로, 내·외국인, 많이 걸린 검색어, 업종 평균, 개선 제안을 무료로 |
| 3 | **리뷰·평점** | 관광객 | 회원 1인 1리뷰와 찜, 베이지안 보정 평점이 다음 검색에 반영 |
| 4 | **4개 국어** | 모두 | 한국어·영어·중국어·일본어 화면. 영문 장소 이름·설명이 있으면 보여 주고, 없으면 로마자로 표시 |

### 점수 계산

$$S = 100 \times \sum_{i=1}^{6} w_i \cdot s_i$$

| 기준 | 가중치 | 계산 |
|---|---|---|
| S1 카테고리 일치도 | 0.35 | 고른 카테고리 중 장소와 맞는 비율 |
| S2 검색어 관련도 | 0.20 | 이름 1.0 · 카테고리 0.7 · 설명 0.4 (한글·영문·로마자 이름) |
| S3 거리 | 0.20 | `max(0, 1 − d / 10km)`. 내 위치 기준, 대전 중구 밖이면 중구청 앞 기준 |
| S4 구글 평점 | 0.10 | 베이지안 보정 평점 (m = 50, C = 4.0) |
| S5 인기도 | 0.08 | 구글 리뷰 수 로그 비율 |
| S6 트립핀 평점·찜 | 0.07 | 자체 평점 70% (m = 5) + 찜 30% |

- **하드 필터 먼저:** 거리, 영업시간, 예산, 대기업 계열, 대형 체인, 그리고 카테고리를 골랐다면 하나도 맞지 않는 곳.
- **데이터가 없을 때:** 쓰지 않는 기준은 빼고 가중치를 다시 나누며, 구글 데이터가 없으면 S4·S5에 중립값 0.5.
- **다양성 보정:** 같은 대표 카테고리가 위에 k곳 있으면 `0.9^min(k, 3)`을 곱합니다.
- 동점이면 거리 → 리뷰 수 순.

## 데이터

| 출처 | 쓰임 |
|---|---|
| 소상공인시장진흥공단 상가(상권)정보 (공공데이터포털) | 대전 중구 음식점·카페, 대전 전체로 대형 체인 판정 |
| 한국관광공사 TourAPI (국문·영문) | 관광지, 사진, 영문 이름·개요 |
| Google Places API | 평점, 리뷰 수, 영업시간 (634곳 매칭) |
| Gemini API | TourAPI 개요로 짧은 한국어·영어 소개문 생성 |
| 팀 검수표 | 3,490곳을 사람이 직접 확인 (대기업·대형 체인·기관) |

`data/tools/build_places.py`가 모두 합쳐 `data/places.json`을 만듭니다. 수집 스크립트는 API 키가 필요해 로컬에서만 실행합니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3.12 |
| 웹 | Flask, Jinja2, HTML/CSS (SUIT 글꼴) |
| 지도 | 네이버 지도 API v3, 실패하면 Leaflet + OpenStreetMap으로 자동 전환 |
| DB | 파이썬 기본 `sqlite3` |
| 배포 | Vercel |

## 폴더 구조

```
Trippin/
├─ app.py                  # 실행 파일. 화면 주소(라우트)마다 무엇을 보여 줄지 (Vercel도 여기서 `app`을 찾음)
├─ search.py               # 필터링 검색: 하드 필터 → S1~S6 → 정렬·다양성 보정, 거리·베이지안 보정
├─ database.py             # SQLite 저장·조회, 대시보드 집계, 데모 계정·데이터
├─ texts.py                # 한·영·중·일 번역 문구, 한글 → 로마자
├─ data/
│  ├─ places.json          # 완성된 장소 데이터 3,484곳 (실행에 필요한 유일한 데이터)
│  ├─ store_verdicts.json  # 팀 검수 결과
│  ├─ conglomerate_brands.txt, chain_brands.txt   # 대기업·대형 체인 브랜드
│  ├─ descriptions.json    # Gemini 소개문
│  └─ tools/               # 데이터를 만든 스크립트 (API 키 필요, 실행에는 필요 없음)
│     ├─ apiutil.py        #   공통 도구 (.env, API 호출)
│     ├─ collect_sbiz.py   #   상가정보 수집
│     ├─ collect_tour.py   #   TourAPI 수집
│     ├─ collect_google.py #   구글 평점·영업시간
│     ├─ gen_descriptions.py # Gemini 소개문
│     └─ build_places.py   #   합치기 → places.json
├─ i18n/                   # 화면 문구 (ko·en·zh·ja.json)
├─ templates/              # 화면 (HTML)
├─ public/                 # CSS, 지도 스크립트, 서비스 지역 경계, 로고 (Vercel CDN)
├─ tests/test_trippin.py   # 테스트 22개 (중간보고서 예시 A 67.6점·B 46.3점 재현 포함)
└─ docs/handoff/           # 팀 인수인계 문서
```

## 로컬 실행

Python 3.10 이상이 필요합니다.

```bash
pip install flask
python app.py                    # 브라우저가 자동으로 열립니다 (http://127.0.0.1:5000)
```

- VS Code에서는 `app.py`를 열고 오른쪽 위 ▶(Run Python File)를 눌러도 됩니다.
- 5000번 포트를 다른 프로그램이 쓰고 있으면 5001, 5002 … 중 비어 있는 번호로 자동으로 켜집니다.
- 처음 실행하면 `data/places.json`과 데모 데이터로 `trippin.db`가 만들어집니다. 처음 상태로 되돌리려면 `trippin.db`를 지우고 다시 실행하세요.
- `.env`가 없어도 실행되며, 지도는 OpenStreetMap으로 나옵니다.
- 테스트: `python tests/test_trippin.py` (pytest 없이 실행됨)

**데모 계정** (비밀번호 `trippin-demo`): `demo_owner`는 사업자 대시보드, `demo_kr1`·`demo_us1`·`demo_jp1` 등은 관광객 계정입니다.

## 환경 변수

`.env.example`을 `.env`로 복사해 채웁니다. **`.env`는 절대 커밋하지 않습니다.**

| 이름 | 용도 | 위치 |
|---|---|---|
| `SECRET_KEY` | 로그인 세션 서명 | 로컬 · Vercel |
| `NAVER_MAP_CLIENT_ID` | 네이버 지도 | 로컬 · Vercel |
| `DATA_GO_KR_KEY` | 공공데이터포털 (수집) | 로컬만 |
| `GOOGLE_PLACES_KEY` | 구글 Places (수집) | 로컬만 |
| `GEMINI_API_KEY` | 소개문 생성 (수집) | 로컬만 |
| `TRIPPIN_DB` | SQLite 파일 경로 (선택) | 로컬 |

## 데이터 다시 만들기

```bash
python data/tools/collect_sbiz.py            # 대전 중구 상가
python data/tools/collect_sbiz.py --daejeon  # 대전 전체 (체인 판정용)
python data/tools/collect_tour.py && python data/tools/collect_tour.py --detail
python data/tools/collect_google.py --limit 850
python data/tools/gen_descriptions.py
python data/tools/build_places.py
```

## 배포

`main`에 push하면 Vercel에 자동으로 배포됩니다. Vercel에서는 SQLite 파일이 `/tmp`에 있어서 서버가 다시 시작되면 새 계정·리뷰가 초기화되고, 데모 데이터는 자동으로 다시 들어갑니다.

## 팀 — 성균관대학교 문제해결과컴퓨팅 13팀

| 이름 | 역할 |
|---|---|
| 최원준 | 개발 총괄: 데이터 수집·가공, 검색 엔진, 대시보드, 디자인 |
| 김가연 | 개발: 현재 위치, 네이버 지도, 동네별 요약, 코드 검토 |
| 박한희 | 브랜드·가게 검수, 사용자 테스트, 보고서 |
| 김나연 | 브랜드·가게 검수, 번역 검수, 보고서·발표 자료 |

## 라이선스

Copyright (c) 2026 Wonjoon Choi and Team Trippin (Gayeon Kim, Nayun Kim, Hanhee Park, Wonjoon Choi). All rights reserved. 자세한 내용은 [LICENSE](LICENSE)를 보세요.
