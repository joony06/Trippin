<p align="center">
  <img src="public/logo-wordmark.png" alt="Trippin" width="420">
</p>

<p align="center">
  <a href="README.md">English</a> | <b>한국어</b>
</p>

<p align="center">
  <b>광고가 아닌, 나에게 맞는 순서로 찾는 지방 로컬 여행</b><br>
  국내외 관광객을 지방의 소상공인·중소기업 점포로 연결하는 지도 기반 로컬 관광 웹사이트
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white">
  <img src="https://img.shields.io/badge/시범구역-대전%20중구-1E5BD8">
</p>

---

## 소개

방한 관광객과 관광 소비는 서울에 몰려 있고, 기존 지도 서비스에서는 광고비를 내지 못하는 작은 가게가 잘 보이지 않습니다.
**트립핀(Trippin)** 은 광고비가 아니라 **이용자 조건과 얼마나 잘 맞는지**로 장소의 순위를 정해, 관광객이 지방의 골목 상권을 발견하도록 돕습니다.

- 시범 구역: **대전 중구**
- 대기업 계열 점포는 결과에서 제외하고, 지역 소상공인·중소기업을 우선 노출합니다.

## 주요 기능

| # | 기능 | 사용자 | 설명 |
|---|---|---|---|
| 1 | **필터링 검색** (핵심) | 관광객 | 거리·예산·영업시간·대기업 여부로 거른 뒤, 6개 기준(S1~S6) 가중합으로 점수를 매겨 정렬 |
| 2 | **소상공인·중소기업 대시보드** | 사업자 | 조회수·관심등록·유입 경로·이용자 구성을 무료로 제공 |
| 3 | **리뷰·평점** | 관광객 | 1인 1리뷰, 베이지안 평균으로 리뷰가 적은 곳의 평점 왜곡 보정 |
| 4 | **다국어** | 관광객·사업자 | 한국어·영어·중국어·일본어 |

### 점수 계산 요약

$$S = 100 \times \sum_{i=1}^{6} w_i \cdot s_i$$

| 기준 | 가중치 | 내용 |
|---|---|---|
| S1 카테고리 일치도 | 0.35 | 고른 카테고리 중 일치하는 비율 |
| S2 검색어 관련도 | 0.20 | 이름 1.0 · 카테고리 0.7 · 설명문 0.4 |
| S3 거리 | 0.20 | `max(0, 1 − d / D_max)`, D_max = 10km |
| S4 외부 평점 | 0.10 | 구글 평점의 베이지안 보정 (m = 50) |
| S5 인기도 | 0.08 | 리뷰 수의 로그 스케일 |
| S6 자체 평점·찜 | 0.07 | 자체 별점(m = 5) 70% + 찜 30% |

정렬 후 같은 대표 카테고리가 k개 이미 나왔으면 다음 후보 점수에 `0.9^k`를 곱하는 **다양성 보정**을 적용합니다.

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 언어 | Python 3.12 |
| 웹 | Flask, Jinja2 템플릿, HTML/CSS |
| 지도 | NAVER Maps (Web Dynamic Map) |
| DB | SQLite (로컬) / PostgreSQL (배포) + SQLAlchemy |
| 데이터 | Google Places API, 공공데이터포털, 한국관광공사 TourAPI |
| 대시보드 | pandas, Plotly |
| 배포 | Vercel |

## 폴더 구조

```
Trippin/
├─ app.py              # Flask 진입 파일 (Vercel이 여기서 app 을 찾음)
├─ requirements.txt    # 의존성
├─ public/             # 정적 파일 (로고, 파비콘, CSS, JS) - Vercel CDN이 제공
├─ templates/          # Jinja2 화면 (예정)
├─ core/               # 필터·점수·정렬·리뷰 계산 로직 (예정)
├─ data/               # 데이터 수집 스크립트 (예정, 로컬에서만 실행)
└─ i18n/               # 언어별 번역 파일 (예정)
```

## 로컬 실행

```bash
git clone https://github.com/joony06/Trippin.git
cd Trippin

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # 값 채우기
flask --app app run --debug      # http://localhost:5000
```

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다. **`.env`는 절대 커밋하지 않습니다.**

| 이름 | 용도 | 필요한 곳 |
|---|---|---|
| `SECRET_KEY` | 로그인 세션 암호화 | 로컬 · Vercel |
| `DATABASE_URL` | PostgreSQL 주소 (비우면 로컬 SQLite) | Vercel |
| `NAVER_MAP_CLIENT_ID` | 네이버 지도 표시 | 로컬 · Vercel |
| `GOOGLE_PLACES_KEY` | 장소 평점·영업시간 수집 | 로컬 (수집 스크립트만) |

## 배포

`main` 브랜치에 push하면 Vercel이 자동으로 배포합니다. 다른 브랜치나 PR은 Preview 주소로 배포됩니다.

## 팀 (13팀)

| 러닝페어 | 이름 | 담당 |
|---|---|---|
| 1 · 기획·프론트 | 박한희 | 점수 계산식 검토, 리뷰·평점 설계, 보고서 |
| 1 · 기획·프론트 | 김나연 | 화면 디자인, 검색 조건·점수식 설계, 다국어 화면 |
| 2 · 데이터·백엔드 | 김가연 | 네이버 지도 연동, 필터링 검색 구현, 영업시간 수집 |
| 2 · 데이터·백엔드 | 최원준 | 구글 API 연동, 대시보드 집계, 장소 데이터·설명문 생성 |

> 성균관대학교 「문제해결과컴퓨팅」 프로젝트
