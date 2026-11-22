# 트립핀 필터링 검색: 하드 필터 → 점수 계산(S1~S6) → 정렬·동점 처리·다양성 보정
#
# 버전 기록
# v0.1 (2026-11-18) 중간보고서 계산식으로 필터링 검색 전체 흐름 작성 (core/search.py), 거리 계산(core/geo.py), 베이지안 보정(core/reviews.py)
# v0.2 (2026-11-18) 다양성 보정 속도 개선: 카테고리별 정렬 목록에서 맨 앞만 비교 (결과는 같고, 수천 곳에서도 빠름)
# v0.3 (2026-11-18) 하드 필터에 대형 프랜차이즈 제외 추가 (팀 결정: 대기업 계열 + 대형 프랜차이즈 제외)
# v0.4 (2026-11-19) 현재 위치 반영: 브라우저 위치가 대전 중구 안이면 사용, 없거나 밖이면 기본 위치
# v0.5 (2026-11-21) 카테고리를 고르면 하나도 맞지 않는 곳(S1=0)은 하드 필터로 뺌. 제외 목록에는 넣지 않음
# v0.6 (2026-11-21) 다양성 보정 한도 0.9^3, S6 리뷰 0개면 평점 부분 0, S2 영문 이름·설명·로마자 이름도 검색
# v0.7 (2026-11-22) 수업 수준으로 다시 정리: core/search.py + geo.py + reviews.py를 이 파일 하나로 합침
#                   - 검색 조건은 클래스(9주차), 기준마다 함수 하나(9주차), 잘못된 위치 값은 try/except(9주차)
#                   - 카테고리 일치는 집합의 교집합(5주차), 다양성 보정은 카테고리별 대기열(큐, 11주차)
#                   - 각 단계의 성능(빅오, 12주차)을 주석으로 적음. 계산 결과는 v0.6과 소수점까지 같다
#
# 전체 흐름 (장소 n곳, 카테고리 c개)
#   1단계 hard_filter()        조건에 안 맞는 곳 빼기                 O(n)
#   2단계 score_place()        남은 곳마다 S1~S6 점수와 총점 계산      O(n)
#   3단계 rank_with_diversity() 정렬 + 같은 카테고리가 몰리지 않게 보정  O(n log n + n·c)

import math
from collections import deque

from texts import romanize  # 한글 이름 → 로마자 (외국인 검색어 비교용)

# ---------------------------------------------------------------- 상수

# 기준별 가중치 (합 1): S1 카테고리, S2 검색어, S3 거리, S4 구글 평점, S5 구글 리뷰 수, S6 트립핀 리뷰·찜
WEIGHTS = {"s1": 0.35, "s2": 0.20, "s3": 0.20, "s4": 0.10, "s5": 0.08, "s6": 0.07}

D_MAX_KM = 10.0       # S3 점수가 0이 되는 거리
NEUTRAL = 0.5         # 구글 데이터가 없을 때 S4·S5에 넣는 중립값
DIVERSITY_BASE = 0.9  # 같은 대표 카테고리가 위에 k곳 있으면 0.9^k 를 곱한다
DIVERSITY_MAX_K = 3   # k는 3까지만 (0.9^3 ≈ 0.73). 한도가 없으면 10곳쯤 지나 점수가 1/3이 되어 무관한 곳이 앞에 옴

# S2 검색어 관련도: 이름에 있으면 1.0, 카테고리면 0.7, 설명문에 있으면 0.4
S2_NAME = 1.0
S2_CATEGORY = 0.7
S2_DESCRIPTION = 0.4

# 베이지안 보정: 리뷰가 적으면 평균(C) 쪽으로 당긴다. m은 '믿을 만한 리뷰 수'
GOOGLE_M = 50
GOOGLE_C = 4.0
OWN_M = 5               # 트립핀 자체 리뷰는 사용자가 적어서 m을 작게 둔다
DEFAULT_SITE_AVG = 4.0  # 사이트에 리뷰가 하나도 없을 때 쓰는 C

# 거리 계산
EARTH_RADIUS_KM = 6371.0
DEFAULT_ORIGIN = (36.3256, 127.4213)  # 기본 출발점: 대전 중구청 앞 (근사 좌표)
# 서비스 지역(대전 중구)을 감싸는 사각형 (남, 북, 서, 동). 장소 좌표 범위에 여유 0.01도를 더한 값.
# 이 밖(예: 서울)에서 접속하면 거리 점수가 의미 없으므로 기본 위치로 계산한다.
SERVICE_BOUNDS = (36.22, 36.36, 127.36, 127.47)

# 출발점 상태 (화면 안내 문구를 고르는 데 쓴다)
ORIGIN_CURRENT = "current"   # 브라우저 위치를 사용함
ORIGIN_OUTSIDE = "outside"   # 위치는 받았지만 대전 중구 밖이라 기본 위치 사용
ORIGIN_DEFAULT = "default"   # 위치를 못 받음(거부·미지원·시간 초과) → 기본 위치 사용


# ---------------------------------------------------------------- 검색 조건

class Conditions:
    """이용자가 입력한 검색 조건"""

    def __init__(self, categories=None, query="", max_km=10.0, budget=None, day=None, time=None,
                 origin=DEFAULT_ORIGIN, d_max=D_MAX_KM):
        if categories is None:
            categories = []
        self.categories = categories  # 고른 카테고리 목록 (여러 개 가능)
        self.query = query            # 검색어
        self.max_km = max_km          # 최대 거리(km)
        self.budget = budget          # 예산(원). None이면 제한 없음
        self.day = day                # 방문 요일 0=월 … 6=일. None이면 확인 안 함
        self.time = time              # 방문 시각 "HH:MM". None이면 확인 안 함
        self.origin = origin          # 출발점 (위도, 경도)
        self.d_max = d_max            # S3 기준 거리


# ---------------------------------------------------------------- 거리·위치

def haversine_km(lat1, lon1, lat2, lon2):
    """두 지점 사이의 거리(km). 지구를 공으로 보고 하버사인 공식으로 계산한다."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def in_service_area(lat, lng):
    """좌표가 서비스 지역(대전 중구 근사 범위) 안에 있으면 True"""
    south, north, west, east = SERVICE_BOUNDS
    return south <= lat <= north and west <= lng <= east


def to_coord(value, limit):
    """문자열을 위도·경도 숫자로 바꾼다. 숫자가 아니거나 범위를 벗어나면 None"""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or abs(x) > limit:
        return None
    return x


def resolve_origin(lat, lng):
    """브라우저가 보낸 위치로 출발점을 정한다. 돌려주는 값: ((위도, 경도), 상태)"""
    la = to_coord(lat, 90)
    lo = to_coord(lng, 180)
    if la is None or lo is None:
        return DEFAULT_ORIGIN, ORIGIN_DEFAULT
    if not in_service_area(la, lo):
        return DEFAULT_ORIGIN, ORIGIN_OUTSIDE
    return (la, lo), ORIGIN_CURRENT


# ---------------------------------------------------------------- 평점 보정

def bayesian_rating(avg, count, m, c):
    """R′ = (v·R + m·C) / (v + m). 리뷰 수(v)가 적을수록 전체 평균 C 쪽으로 당겨진다."""
    if count <= 0 or avg is None:
        return c
    return (count * avg + m * c) / (count + m)


def rating_to_unit(r):
    """1~5점을 0~1로 바꾼다: (R′ − 1) ÷ 4"""
    return max(0.0, min(1.0, (r - 1) / 4))


def summarize(ratings, site_avg=None):
    """리뷰 별점 목록 → 개수·평균·보정 평점 (상세 화면 리뷰 요약)"""
    c = site_avg if site_avg is not None else DEFAULT_SITE_AVG
    count = len(ratings)
    avg = sum(ratings) / count if count else None
    return {"count": count, "avg": avg, "adjusted": bayesian_rating(avg, count, OWN_M, c), "site_avg": c}


# ---------------------------------------------------------------- 1단계 하드 필터

def to_minutes(hhmm):
    """'13:30' → 810 (자정부터 몇 분인지)"""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_open(hours, day, time):
    """영업 중이면 True, 아니면 False. 영업시간 정보가 없거나 방문 시각을 안 넣었으면 None.

    hours 예: {"0": "10:00-18:00", "1": "10:00-18:00", ...}  키가 없는 요일은 휴무
    """
    if hours is None or day is None or not time:
        return None
    span = hours.get(str(day))
    if not span:
        return False
    start, end = span.split("-")
    t = to_minutes(time)
    s = to_minutes(start)
    e = to_minutes(end)
    if e <= s:  # 자정을 넘기는 영업 (예: 18:00-02:00)
        return t >= s or t < e
    return s <= t < e


def hard_filter(places, cond):
    """조건에 안 맞는 곳을 점수 계산 전에 뺀다. 돌려주는 값: (남은 곳, [(뺀 곳, 이유 목록)])  — O(n)"""
    kept = []
    excluded = []
    chosen = set(cond.categories or [])
    for p in places:
        # 카테고리를 골랐는데 하나도 맞지 않으면(교집합이 비면) 뺀다. 수천 곳이라 제외 목록에는 넣지 않는다
        if chosen and not (chosen & set(p.get("categories") or [])):
            continue
        d = haversine_km(cond.origin[0], cond.origin[1], p["lat"], p["lng"])
        reasons = []
        if d > cond.max_km:
            reasons.append("distance")
        if is_open(p.get("hours"), cond.day, cond.time) is False:
            reasons.append("closed")
        if cond.budget is not None and (p.get("fee") or 0) > cond.budget:
            reasons.append("budget")
        if p.get("is_conglomerate"):
            reasons.append("conglomerate")
        elif p.get("is_franchise"):
            reasons.append("franchise")

        item = dict(p)
        item["distance_km"] = d
        if reasons:
            excluded.append((item, reasons))
        else:
            kept.append(item)
    return kept, excluded


# ---------------------------------------------------------------- 2단계 점수 계산 (기준마다 함수 하나)

def s1_category(place_cats, chosen):
    """S1 = k / K (K: 고른 카테고리 수, k: 그중 장소와 맞는 수). 카테고리를 안 골랐으면 None"""
    if not chosen:
        return None
    k = 0
    for c in chosen:
        if c in place_cats:
            k += 1
    return k / len(chosen)


def s2_query(place, query):
    """검색어가 이름 1.0 · 카테고리 0.7 · 설명문 0.4 · 없음 0 (가장 높은 값 하나). 검색어가 없으면 None"""
    q = (query or "").strip()
    if not q:
        return None
    ql = q.lower()
    if q in place["name"] or ql in (place.get("name_en") or "").lower():
        return S2_NAME
    # 외국인이 'kalguksu'처럼 로마자로 찾아도 이름으로 인정 (띄어쓰기 무시, 3글자 이상)
    q_letters = ql.replace(" ", "")
    if ql.isascii() and len(q_letters) >= 3:
        if q_letters in romanize(place["name"]).lower().replace(" ", ""):
            return S2_NAME
    for c in place["categories"]:
        # 검색어가 카테고리에 포함되거나, 검색어 안에 카테고리 이름이 있어도 인정 ('역사 명소' 등)
        if q in c or c in q:
            return S2_CATEGORY
    if q in (place.get("description") or "") or ql in (place.get("description_en") or "").lower():
        return S2_DESCRIPTION
    return 0.0


def s3_distance(d, d_max):
    """S3 = max(0, 1 − d / D_max)"""
    return max(0.0, 1 - d / d_max)


def s4_google_rating(rating, count):
    """S4 = (R′ − 1) ÷ 4, R′는 m = 50, C = 4.0 베이지안 보정. 구글 데이터가 없으면 0.5"""
    if rating is None or not count:
        return NEUTRAL
    return rating_to_unit(bayesian_rating(rating, count, GOOGLE_M, GOOGLE_C))


def s5_popularity(count, v_max):
    """S5 = log(1 + v) ÷ log(1 + v_max). 구글 데이터가 없으면 0.5"""
    if count is None:
        return NEUTRAL
    if not v_max:
        return 0.0
    return math.log(1 + count) / math.log(1 + v_max)


def s6_own(own_avg, own_count, likes, l_max, site_avg):
    """S6 = 0.7 × 트립핀 평점 부분 + 0.3 × 찜 부분. 리뷰가 없으면 평점 부분 0, 둘 다 없으면 0"""
    if not own_count and not likes:
        return 0.0
    rating_part = 0.0
    if own_count:
        rating_part = rating_to_unit(bayesian_rating(own_avg, own_count, OWN_M, site_avg))
    like_part = 0.0
    if l_max:
        like_part = math.log(1 + likes) / math.log(1 + l_max)
    return 0.7 * rating_part + 0.3 * like_part


def active_weights(cond):
    """쓰지 않는 기준을 빼고 나머지 가중치 합을 다시 1로 맞춘다.
    검색어가 없으면 S2를, 카테고리를 안 골랐으면 S1을 뺀다."""
    w = dict(WEIGHTS)
    if not (cond.query or "").strip():
        w.pop("s2")
    if not cond.categories:
        w.pop("s1")
    total = sum(w.values())
    result = {}
    for k in w:
        result[k] = w[k] / total
    return result


def build_context(candidates, cond, site_avg=None, v_max=None):
    """후보 전체를 보고 정해지는 값: 최대 리뷰 수(v_max), 최대 찜 수(L_max), 사이트 평균, 가중치"""
    reviews = []
    likes = []
    for p in candidates:
        if p.get("google_reviews") is not None:
            reviews.append(p["google_reviews"])
        likes.append(p.get("likes", 0))
    if v_max is None:
        v_max = max(reviews) if reviews else 0
    return {
        "v_max": v_max,
        "l_max": max(likes) if likes else 0,
        "site_avg": site_avg if site_avg is not None else DEFAULT_SITE_AVG,
        "weights": active_weights(cond),
    }


def score_place(p, cond, ctx):
    """장소 하나의 기준별 점수(0~1), 반영 점수(가중치 × 점수), 총점(0~100)"""
    scores = {
        "s1": s1_category(p["categories"], cond.categories),
        "s2": s2_query(p, cond.query),
        "s3": s3_distance(p["distance_km"], cond.d_max),
        "s4": s4_google_rating(p.get("google_rating"), p.get("google_reviews")),
        "s5": s5_popularity(p.get("google_reviews"), ctx["v_max"]),
        "s6": s6_own(p.get("own_avg"), p.get("own_count", 0), p.get("likes", 0), ctx["l_max"], ctx["site_avg"]),
    }
    weights = ctx["weights"]
    contrib = {}
    for k in weights:
        contrib[k] = weights[k] * scores[k]
    return {"scores": scores, "weights": weights, "contrib": contrib, "total": 100 * sum(contrib.values())}


# ---------------------------------------------------------------- 3단계 정렬·다양성 보정

def tie_key(item):
    """동점이면 거리가 가까운 순 → 리뷰 수가 많은 순 → 장소 번호 순"""
    return (item["distance_km"], -(item.get("google_reviews") or 0), item.get("id") or 0)


def order_key(score, item):
    """정렬 기준: 점수가 높은 순(그래서 음수), 같으면 tie_key. 소수 9자리에서 반올림해 계산 오차를 없앤다"""
    return (-round(score, 9),) + tie_key(item)


def total_order_key(item):
    return order_key(item["result"]["total"], item)


def rank_with_diversity(scored):
    """위에서부터 하나씩 고르며, 같은 대표 카테고리가 위에 k곳 있으면 0.9^min(k, 3)을 곱해 다시 비교한다.

    같은 카테고리 안에서는 곱하는 값이 같아 순서가 바뀌지 않는다. 그래서
    카테고리별 대기열(큐)을 점수순으로 만들어 두고, 매번 각 대기열의 맨 앞끼리만 비교해 하나를 꺼낸다.
    - 모든 후보를 매번 다시 비교하면 O(n²)
    - 대기열 맨 앞만 비교하면 O(n log n) 정렬 + O(n·c) 꺼내기 (c: 카테고리 수, 최대 10)
    """
    groups = {}  # 대표 카테고리 → 그 카테고리 후보 목록
    for item in scored:
        cat = item["main_category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(item)

    queues = {}  # 대표 카테고리 → 점수순 대기열
    taken = {}   # 대표 카테고리 → 지금까지 순위에 나온 수 (= k)
    for cat in groups:
        groups[cat].sort(key=total_order_key)
        queues[cat] = deque(groups[cat])
        taken[cat] = 0

    ranked = []
    while True:
        best_cat, best_key, best_adjusted = None, None, None
        for cat in queues:
            if not queues[cat]:
                continue
            item = queues[cat][0]  # 이 카테고리에서 다음 차례 (맨 앞)
            k = taken[cat]
            adjusted = item["result"]["total"] * (DIVERSITY_BASE ** min(k, DIVERSITY_MAX_K))
            key = order_key(adjusted, item)
            if best_key is None or key < best_key:
                best_cat, best_key, best_adjusted = cat, key, adjusted
        if best_cat is None:  # 모든 대기열이 비었다
            return ranked

        best = queues[best_cat].popleft()
        k = taken[best_cat]
        best["penalty_k"] = min(k, DIVERSITY_MAX_K)
        best["adjusted"] = best_adjusted
        best["same_above"] = k  # 위에 같은 대표 카테고리가 몇 곳 있었는지 (화면 안내용)
        taken[best_cat] = k + 1
        best["rank"] = len(ranked) + 1
        ranked.append(best)


# ---------------------------------------------------------------- 전체 흐름

def run_search(places, cond, site_avg=None):
    """하드 필터 → 점수 → 정렬·보정. 돌려주는 값: (순위 목록, 제외 목록)"""
    kept, excluded = hard_filter(places, cond)
    ctx = build_context(kept, cond, site_avg=site_avg)
    scored = []
    for p in kept:
        item = dict(p)
        item["main_category"] = p["categories"][0] if p["categories"] else ""
        item["result"] = score_place(p, cond, ctx)
        scored.append(item)
    return rank_with_diversity(scored), excluded
