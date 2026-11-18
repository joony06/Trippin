<p align="center">
  <img src="public/logo-wordmark.png" alt="Trippin" width="420">
</p>

<p align="center">
  <a href="README.md">영어</a> | <b>한국어</b>
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
| 지도 | Leaflet + OpenStreetMap (MVP) → 이후 네이버 지도 |
| DB | SQLite (파이썬 기본 `sqlite3` 모듈) |
| 데이터 | 공공데이터포털 소상공인 상가정보, 한국관광공사 TourAPI, Google Places API |
| 배포 | Vercel |

## MVP 진행 상황

| # | 기능 | 상태 |
|---|---|---|
| 1 | 필터링 검색 | 하드 필터·S1~S6·정렬·다양성 보정이 샘플 데이터로 동작 |
| 2 | 사업자 대시보드 | 7일 조회수, 찜, 유입 경로, 내·외국인 비율, 많이 걸린 검색어, 업종 평균 비교, 규칙 기반 개선 제안 |
| 3 | 리뷰·평점 | 회원가입·로그인, 1인 1리뷰(수정 가능), 찜, 베이지안 보정 → S6 반영 |
| 4 | 다국어 | 한국어·영어·중국어·일본어 화면 문구 (장소 이름·설명은 아직 한국어) |

`data/sample_places.json`의 13곳은 시연용 데이터입니다. 좌표는 근사값이고, 평점·리뷰 수·요금·영업시간은 예시 값입니다.

## 폴더 구조

```
Trippin/
├─ app.py                 # Flask 라우트 (Vercel이 여기서 app 을 찾음)
├─ db.py                  # SQLite 테이블·조회·대시보드 집계
├─ core/
│  ├─ search.py           # 하드 필터 → S1~S6 → 정렬·다양성 보정
│  ├─ reviews.py          # 베이지안 보정 평점
│  ├─ geo.py              # 하버사인 거리
│  └─ i18n.py             # 번역 문구 찾기
├─ data/
│  ├─ sample_places.json  # 대전 중구 샘플 장소
│  └─ collect_sbiz.py     # 상가정보 API 수집 스크립트 (초안)
├─ i18n/                  # ko / en / zh / ja 화면 문구
├─ templates/             # Jinja2 화면
├─ public/                # CSS, 지도 스크립트, 로고 (Vercel CDN이 제공)
└─ tests/                 # 점수 계산 테스트 (중간보고서 계산 예시 재현)
```

## 로컬 실행

```bash
git clone https://github.com/joony06/Trippin.git
cd Trippin

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

flask --app app run --debug      # http://localhost:5000
```

- 처음 실행하면 샘플 데이터가 들어간 DB(`trippin.db`)가 자동으로 만들어집니다. 초기화하려면 `flask --app app init-db`를 실행합니다.
- 테스트: `pip install pytest` 후 `python -m pytest`

## 환경 변수

`.env.example`을 복사해 `.env`를 만듭니다. **`.env`는 절대 커밋하지 않습니다.**

| 이름 | 용도 | 필요한 곳 |
|---|---|---|
| `SECRET_KEY` | 로그인 세션 암호화 | 로컬 · Vercel |
| `DATA_GO_KR_KEY` | 공공데이터포털 인증키 (수집 스크립트) | 로컬 |
| `NAVER_MAP_CLIENT_ID` | 네이버 지도 (이후) | 로컬 · Vercel |
| `TRIPPIN_DB` | SQLite 파일 위치 (선택) | 로컬 |

## 배포

`main` 브랜치에 push하면 Vercel이 자동으로 배포합니다. Vercel에서는 SQLite 파일이 `/tmp`에 있어 리뷰·회원 정보가 가끔 초기화됩니다. 최종 시연은 로컬 실행으로 하거나, 이후 외부 DB로 옮깁니다.

## 팀 (13팀)

| 러닝페어 | 이름 | 담당 |
|---|---|---|
| 1 · 기획·프론트 | 박한희 | 점수 계산식 검토, 리뷰·평점 설계, 보고서 |
| 1 · 기획·프론트 | 김나연 | 화면 디자인, 검색 조건·점수식 설계, 다국어 화면 |
| 2 · 데이터·백엔드 | 김가연 | 네이버 지도 연동, 필터링 검색 구현, 영업시간 수집 |
| 2 · 데이터·백엔드 | 최원준 | 구글 API 연동, 대시보드 집계, 장소 데이터·설명문 생성 |

> 성균관대학교 「문제해결과컴퓨팅」 프로젝트
