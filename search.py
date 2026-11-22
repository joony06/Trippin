# 트립핀 필터링 검색: 하드 필터 → S1~S6 점수 → 정렬·다양성 보정
#
# 버전 기록
# v0.1 검색 흐름 작성 (거리, 베이지안 보정 포함)
# v0.2 다양성 보정 속도 개선
# v0.3 대형 프랜차이즈 제외
# v0.4 현재 위치를 출발점으로
# v0.5 카테고리 불일치는 하드 필터로 제외
# v0.6 다양성 보정 한도 0.9^3, S6·S2 수정
#
# 성능 (n: 장소 수, c: 카테고리 수): 필터 O(n), 점수 O(n), 정렬·보정 O(n log n + n·c)

import math
from collections import deque

from texts import romanize


# 가중치 (합 1)
WEIGHTS = {"s1": 0.35, "s2": 0.20, "s3": 0.20, "s4": 0.10, "s5": 0.08, "s6": 0.07}

D_MAX_KM = 10.0
NEUTRAL = 0.5
DIVERSITY_BASE = 0.9
DIVERSITY_MAX_K = 3  # 0.9^k의 k 최대값

S2_NAME = 1.0
S2_CATEGORY = 0.7
S2_DESCRIPTION = 0.4

# 베이지안 보정 (m: 믿을 만한 리뷰 수, C: 평균)
GOOGLE_M = 50
GOOGLE_C = 4.0
OWN_M = 5
DEFAULT_SITE_AVG = 4.0

EARTH_RADIUS_KM = 6371.0
DEFAULT_ORIGIN = (36.3256, 127.4213)  # 대전 중구청 앞
# 서비스 지역 사각형 (남, 북, 서, 동)
SERVICE_BOUNDS = (36.22, 36.36, 127.36, 127.47)

ORIGIN_CURRENT = "current"
ORIGIN_OUTSIDE = "outside"
ORIGIN_DEFAULT = "default"


class Conditions:

    def __init__(self, categories=None, query="", max_km=10.0, budget=None, day=None, time=None,
                 origin=DEFAULT_ORIGIN, d_max=D_MAX_KM):
        if categories is None:
            categories = []
        self.categories = categories
        self.query = query
        self.max_km = max_km
        self.budget = budget  # None이면 제한 없음
        self.day = day  # 0=월 … 6=일
        self.time = time
        self.origin = origin
        self.d_max = d_max


def haversine_km(lat1, lon1, lat2, lon2):
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def in_service_area(lat, lng):
    south, north, west, east = SERVICE_BOUNDS
    return south <= lat <= north and west <= lng <= east


def to_coord(value, limit):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or abs(x) > limit:
        return None
    return x


def resolve_origin(lat, lng):
    la = to_coord(lat, 90)
    lo = to_coord(lng, 180)
    if la is None or lo is None:
        return DEFAULT_ORIGIN, ORIGIN_DEFAULT
    if not in_service_area(la, lo):
        return DEFAULT_ORIGIN, ORIGIN_OUTSIDE
    return (la, lo), ORIGIN_CURRENT


def bayesian_rating(avg, count, m, c):
    """R′ = (v·R + m·C) / (v + m)"""
    if count <= 0 or avg is None:
        return c
    return (count * avg + m * c) / (count + m)


def rating_to_unit(r):
    """1~5점 → 0~1: (R′ − 1) ÷ 4"""
    return max(0.0, min(1.0, (r - 1) / 4))


def summarize(ratings, site_avg=None):
    if site_avg is not None:
        c = site_avg
    else:
        c = DEFAULT_SITE_AVG
    count = len(ratings)
    if count:
        avg = sum(ratings) / count
    else:
        avg = None
    return {"count": count, "avg": avg, "adjusted": bayesian_rating(avg, count, OWN_M, c), "site_avg": c}


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_open(hours, day, time):
    """영업 중 True, 영업 종료 False, 정보 없음 None"""
    if hours is None or day is None or not time:
        return None
    span = hours.get(str(day))
    if not span:
        return False
    start, end = span.split("-")
    t = to_minutes(time)
    s = to_minutes(start)
    e = to_minutes(end)
    if e <= s:  # 자정을 넘기는 영업
        return t >= s or t < e
    return s <= t < e


def hard_filter(places, cond):
    kept = []
    excluded = []
    chosen = set(cond.categories or [])
    for p in places:
        # 고른 카테고리와 하나도 안 맞으면 제외
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


def s1_category(place_cats, chosen):
    """S1 = 맞는 카테고리 수 ÷ 고른 카테고리 수"""
    if not chosen:
        return None
    k = 0
    for c in chosen:
        if c in place_cats:
            k += 1
    return k / len(chosen)


def s2_query(place, query):
    """S2: 이름 1.0, 카테고리 0.7, 설명문 0.4, 없음 0"""
    q = (query or "").strip()
    if not q:
        return None
    ql = q.lower()
    if q in place["name"] or ql in (place.get("name_en") or "").lower():
        return S2_NAME
    # 로마자 이름 검색 (예: kalguksu)
    q_letters = ql.replace(" ", "")
    if ql.isascii() and len(q_letters) >= 3:
        if q_letters in romanize(place["name"]).lower().replace(" ", ""):
            return S2_NAME
    for c in place["categories"]:
        if q in c or c in q:
            return S2_CATEGORY
    if q in (place.get("description") or ""):
        return S2_DESCRIPTION
    return 0.0


def s3_distance(d, d_max):
    """S3 = max(0, 1 − d / D_max)"""
    return max(0.0, 1 - d / d_max)


def s4_google_rating(rating, count):
    """S4 = (R′ − 1) ÷ 4, 데이터 없으면 0.5"""
    if rating is None or not count:
        return NEUTRAL
    return rating_to_unit(bayesian_rating(rating, count, GOOGLE_M, GOOGLE_C))


def s5_popularity(count, v_max):
    """S5 = log(1 + v) ÷ log(1 + v_max), 데이터 없으면 0.5"""
    if count is None:
        return NEUTRAL
    if not v_max:
        return 0.0
    return math.log(1 + count) / math.log(1 + v_max)


def s6_own(own_avg, own_count, likes, l_max, site_avg):
    """S6 = 0.7 × 평점 부분 + 0.3 × 찜 부분"""
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
    """쓰지 않는 기준(S1·S2) 제외 후 가중치 합 1로 조정"""
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
    reviews = []
    likes = []
    for p in candidates:
        if p.get("google_reviews") is not None:
            reviews.append(p["google_reviews"])
        likes.append(p.get("likes", 0))
    if v_max is None:
        if reviews:
            v_max = max(reviews)
        else:
            v_max = 0
    l_max = 0
    if likes:
        l_max = max(likes)
    avg = site_avg
    if avg is None:
        avg = DEFAULT_SITE_AVG
    return {
        "v_max": v_max,
        "l_max": l_max,
        "site_avg": avg,
        "weights": active_weights(cond),
    }


def score_place(p, cond, ctx):
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


def tie_key(item):
    """동점 시 가까운 거리 → 많은 리뷰 수 → 장소 번호 순"""
    return (item["distance_km"], -(item.get("google_reviews") or 0), item.get("id") or 0)


def order_key(score, item):
    return (-round(score, 9),) + tie_key(item)


def total_order_key(item):
    return order_key(item["result"]["total"], item)


def rank_with_diversity(scored):
    """같은 카테고리가 위에 k곳 있으면 0.9^min(k, 3)을 곱해 비교"""
    groups = {}
    for item in scored:
        cat = item["main_category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(item)

    queues = {}
    taken = {}  # 카테고리별 k
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
            item = queues[cat][0]
            k = taken[cat]
            adjusted = item["result"]["total"] * (DIVERSITY_BASE ** min(k, DIVERSITY_MAX_K))
            key = order_key(adjusted, item)
            if best_key is None or key < best_key:
                best_cat, best_key, best_adjusted = cat, key, adjusted
        if best_cat is None:
            return ranked

        best = queues[best_cat].popleft()
        k = taken[best_cat]
        best["penalty_k"] = min(k, DIVERSITY_MAX_K)
        best["adjusted"] = best_adjusted
        best["same_above"] = k
        taken[best_cat] = k + 1
        best["rank"] = len(ranked) + 1
        ranked.append(best)


def run_search(places, cond, site_avg=None):
    kept, excluded = hard_filter(places, cond)
    ctx = build_context(kept, cond, site_avg=site_avg)
    scored = []
    for p in kept:
        item = dict(p)
        if p["categories"]:
            item["main_category"] = p["categories"][0]
        else:
            item["main_category"] = ""
        item["result"] = score_place(p, cond, ctx)
        scored.append(item)
    return rank_with_diversity(scored), excluded
