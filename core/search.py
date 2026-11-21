# 필터링 검색: 하드 필터 → 점수 계산(S1~S6) → 정렬·동점 처리·다양성 보정
#
# 버전 기록
# v0.1 (2026-11-18) 중간보고서 계산식으로 필터링 검색 전체 흐름 작성
# v0.2 (2026-11-18) 다양성 보정 속도 개선: 카테고리별 정렬 목록에서 맨 앞만 비교 (결과는 같고, 수천 곳에서도 빠름)
# v0.3 (2026-11-18) 하드 필터에 대형 프랜차이즈 제외 추가 (팀 결정: 대기업 계열 + 대형 프랜차이즈 제외)
# v0.4 (2026-11-21) 카테고리를 고르면 하나도 맞지 않는 곳(S1=0)은 하드 필터로 뺌 (사용자 테스트 1번). 제외 목록에는 넣지 않음

import math
from dataclasses import dataclass, field

from core.geo import DEFAULT_ORIGIN, haversine_km
from core.reviews import (
    DEFAULT_SITE_AVG,
    GOOGLE_C,
    GOOGLE_M,
    OWN_M,
    bayesian_rating,
    rating_to_unit,
)

# 기준별 가중치 (합 1)
WEIGHTS = {"s1": 0.35, "s2": 0.20, "s3": 0.20, "s4": 0.10, "s5": 0.08, "s6": 0.07}

D_MAX_KM = 10.0       # S3 점수가 0이 되는 기준 거리
NEUTRAL = 0.5         # 구글 데이터가 없을 때 S4·S5 중립값
DIVERSITY_BASE = 0.9  # 같은 대표 카테고리가 k개 나왔으면 0.9^k 를 곱한다

# S2 검색어 관련도 점수
S2_NAME, S2_CATEGORY, S2_DESCRIPTION = 1.0, 0.7, 0.4


@dataclass
class Conditions:
    """이용자가 입력한 검색 조건"""
    categories: list = field(default_factory=list)  # 고른 카테고리 (여러 개)
    query: str = ""                                  # 검색어
    max_km: float = 10.0                             # 최대 거리
    budget: int | None = None                        # 예산(원). None이면 제한 없음
    day: int | None = None                           # 방문 요일 0=월 … 6=일
    time: str | None = None                          # 방문 시각 "HH:MM"
    origin: tuple = DEFAULT_ORIGIN                   # 현재 위치 (위도, 경도)
    d_max: float = D_MAX_KM


# ---------------------------------------------------------------- 1단계 하드 필터

def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_open(hours, day, time):
    """영업 여부. True/False, 영업시간 정보가 없거나 방문 시각을 안 넣었으면 None.

    hours 예: {"0": "10:00-18:00", "1": "10:00-18:00", ...}  키가 없는 요일은 휴무
    "00:00-24:00"은 하루 종일 열려 있다는 뜻 (공원 등)
    """
    if hours is None or day is None or not time:
        return None
    span = hours.get(str(day))
    if not span:
        return False
    start, end = span.split("-")
    t = _to_minutes(time)
    s, e = _to_minutes(start), _to_minutes(end)
    if e <= s:  # 자정을 넘기는 영업 (예: 18:00-02:00)
        return t >= s or t < e
    return s <= t < e


def hard_filter(places, cond):
    """조건에 안 맞는 곳을 점수 계산 전에 뺀다. (남은 곳, [(뺀 곳, 이유들)])"""
    kept, excluded = [], []
    chosen = set(cond.categories or [])
    for p in places:
        # 카테고리를 골랐는데 하나도 맞지 않으면 뺀다. 수천 곳이라 제외 목록(화면)에는 넣지 않는다
        if chosen and not chosen & set(p.get("categories") or []):
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
        item = dict(p, distance_km=d)
        if reasons:
            excluded.append((item, reasons))
        else:
            kept.append(item)
    return kept, excluded


# ---------------------------------------------------------------- 2단계 점수 계산

def s1_category(place_cats, chosen):
    """S1 = k / K (K: 고른 카테고리 수, k: 그중 장소와 일치하는 수)"""
    if not chosen:
        return None
    k = sum(1 for c in chosen if c in place_cats)
    return k / len(chosen)


def s2_query(place, query):
    """이름 1.0 · 카테고리 0.7 · 설명문 0.4 · 없음 0 (가장 높은 값 하나)"""
    q = (query or "").strip()
    if not q:
        return None
    if q in place["name"]:
        return S2_NAME
    for c in place["categories"]:
        # 검색어가 카테고리에 포함되거나, 검색어 안에 카테고리 이름이 있어도 인정 ('역사 명소' 등)
        if q in c or c in q:
            return S2_CATEGORY
    if q in (place.get("description") or ""):
        return S2_DESCRIPTION
    return 0.0


def s3_distance(d, d_max):
    """S3 = max(0, 1 − d / D_max)"""
    return max(0.0, 1 - d / d_max)


def s4_google_rating(rating, count):
    """S4 = (R′ − 1) ÷ 4, R′는 m = 50, C = 4.0 베이지안 보정. 데이터 없으면 0.5"""
    if rating is None or not count:
        return NEUTRAL
    return rating_to_unit(bayesian_rating(rating, count, GOOGLE_M, GOOGLE_C))


def s5_popularity(count, v_max):
    """S5 = log(1 + v) ÷ log(1 + v_max). 데이터 없으면 0.5"""
    if count is None:
        return NEUTRAL
    if not v_max:
        return 0.0
    return math.log(1 + count) / math.log(1 + v_max)


def s6_own(own_avg, own_count, likes, l_max, site_avg):
    """S6 = 0.7 × (R′자체 − 1) ÷ 4 + 0.3 × log(1 + L) ÷ log(1 + L_max). 데이터 없으면 0"""
    if not own_count and not likes:
        return 0.0
    r_own = bayesian_rating(own_avg, own_count or 0, OWN_M, site_avg)
    like_part = math.log(1 + likes) / math.log(1 + l_max) if l_max else 0.0
    return 0.7 * rating_to_unit(r_own) + 0.3 * like_part


def active_weights(cond):
    """쓰지 않는 기준을 빼고 나머지 가중치 합을 다시 1로 맞춘다.

    - 검색어가 없으면 S2를 뺀다 (보고서: 나머지를 0.8로 나눔)
    - 카테고리를 하나도 안 고르면 S1을 뺀다 (MVP에서 정한 규칙, 보고서에는 없음)
    """
    w = dict(WEIGHTS)
    if not (cond.query or "").strip():
        w.pop("s2")
    if not cond.categories:
        w.pop("s1")
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


def score_place(p, cond, ctx):
    """장소 하나의 기준별 점수와 총점(0~100)"""
    scores = {
        "s1": s1_category(p["categories"], cond.categories),
        "s2": s2_query(p, cond.query),
        "s3": s3_distance(p["distance_km"], cond.d_max),
        "s4": s4_google_rating(p.get("google_rating"), p.get("google_reviews")),
        "s5": s5_popularity(p.get("google_reviews"), ctx["v_max"]),
        "s6": s6_own(p.get("own_avg"), p.get("own_count", 0), p.get("likes", 0),
                     ctx["l_max"], ctx["site_avg"]),
    }
    weights = ctx["weights"]
    contrib = {k: weights[k] * scores[k] for k in weights}
    return {
        "scores": scores,
        "weights": weights,
        "contrib": contrib,
        "total": 100 * sum(contrib.values()),
    }


def build_context(candidates, cond, site_avg=None, v_max=None):
    """후보 전체를 보고 정해지는 값들 (v_max, L_max, 가중치)"""
    reviews = [p["google_reviews"] for p in candidates if p.get("google_reviews") is not None]
    likes = [p.get("likes", 0) for p in candidates]
    return {
        "v_max": v_max if v_max is not None else (max(reviews) if reviews else 0),
        "l_max": max(likes) if likes else 0,
        "site_avg": site_avg if site_avg is not None else DEFAULT_SITE_AVG,
        "weights": active_weights(cond),
    }


# ---------------------------------------------------------------- 3단계 정렬·보정

def _tie_key(item):
    # 동점이면 거리가 가까운 순 → 리뷰 수가 많은 순 → (그래도 같으면) 장소 번호 순
    return (item["distance_km"], -(item.get("google_reviews") or 0), item.get("id") or 0)


def rank_with_diversity(scored):
    """위에서부터 하나씩 고르며, 같은 대표 카테고리가 k개 나왔으면 0.9^k를 곱해 다시 비교한다.

    같은 카테고리 안에서는 곱하는 값이 같으므로 순서가 바뀌지 않는다.
    그래서 카테고리별로 미리 정렬해 두고, 매번 각 카테고리의 맨 앞 후보끼리만 비교한다.
    """
    groups = {}
    for item in scored:
        groups.setdefault(item["main_category"], []).append(item)
    for items in groups.values():
        items.sort(key=lambda it: (-round(it["result"]["total"], 9), *_tie_key(it)))
    heads = {cat: 0 for cat in groups}  # 카테고리별로 다음에 비교할 위치 (= 이미 나온 개수 k)

    ranked = []
    while True:
        best, best_key, best_cat = None, None, None
        for cat, k in heads.items():
            if k >= len(groups[cat]):
                continue
            item = groups[cat][k]
            adjusted = item["result"]["total"] * (DIVERSITY_BASE ** k)
            key = (-round(adjusted, 9), *_tie_key(item))
            if best_key is None or key < best_key:
                best, best_key, best_cat = item, key, cat
                best["penalty_k"], best["adjusted"] = k, adjusted
        if best is None:
            return ranked
        heads[best_cat] += 1
        best["rank"] = len(ranked) + 1
        ranked.append(best)


def search(places, cond, site_avg=None):
    """전체 흐름: 하드 필터 → 점수 → 정렬·보정. (순위 목록, 제외 목록)"""
    kept, excluded = hard_filter(places, cond)
    ctx = build_context(kept, cond, site_avg=site_avg)
    scored = []
    for p in kept:
        item = dict(p)
        item["main_category"] = p["categories"][0] if p["categories"] else ""
        item["result"] = score_place(p, cond, ctx)
        scored.append(item)
    return rank_with_diversity(scored), excluded
