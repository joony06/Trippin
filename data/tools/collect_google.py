# Google Places로 평점·리뷰 수·영업시간 수집
#
# 버전 기록
# v0.1 Text Search 수집, 캐시·한도·매칭 검증
# v0.2 검색 원본 캐시, 매칭 기준 강화
#
# 실행: python data/tools/collect_google.py [--limit N] [--dry-run]  (.env에 GOOGLE_PLACES_KEY)

import difflib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

import apiutil

sys.path.insert(0, apiutil.ROOT)
import search

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(["places.id", "places.displayName", "places.location",
                       "places.rating", "places.userRatingCount", "places.regularOpeningHours"])
CACHE = os.path.join(apiutil.RAW_DIR, "google_raw.json")
PLACES = os.path.join(apiutil.DATA_DIR, "places.json")

MATCH_MAX_M = 150
MATCH_MAX_M_SAME_NAME = 800  # 이름이 같은 경우 (넓은 장소)
MATCH_MIN_NAME = 0.75
TOP_PER_CATEGORY = 60
MAX_TARGETS = 850
CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DAY_MINUTES = 1440


def place_key(p):
    return f"{p.get('source', 'sample')}:{p.get('source_id') or p['id']}"


def norm(s):
    return "".join((s or "").split()).lower()


def meters(a_lat, a_lng, b_lat, b_lng):
    r = 6371000
    p1 = math.radians(a_lat)
    p2 = math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load_places():
    return apiutil.read_json(PLACES)["places"]


def distance_from_office(p):
    return search.haversine_km(search.DEFAULT_ORIGIN[0], search.DEFAULT_ORIGIN[1], p["lat"], p["lng"])


def add_target(p, targets, seen):
    k = place_key(p)
    if k not in seen and not p.get("is_conglomerate") and not p.get("is_franchise"):
        seen.add(k)
        targets.append(p)


def pick_targets(places):
    """관광공사 장소 → 카테고리별 상위 → 가까운 순, MAX_TARGETS까지"""
    targets = []
    seen = set()
    for p in places:
        if p.get("source") == "tour":
            add_target(p, targets, seen)
    rows = []
    for p in places:
        row = dict(p)
        row["own_avg"], row["own_count"], row["likes"] = None, 0, 0
        rows.append(row)
    for cat in CATEGORIES:
        ranked, _ = search.run_search(rows, search.Conditions(categories=[cat], max_km=3))
        for p in ranked[:TOP_PER_CATEGORY]:
            add_target(p, targets, seen)
    for p in sorted(places, key=distance_from_office):
        if len(targets) >= MAX_TARGETS:
            break
        add_target(p, targets, seen)
    return targets[:MAX_TARGETS]


def request(key, p):
    body = {
        "textQuery": f"{p['name']} 대전 중구",
        "languageCode": "ko",
        "regionCode": "KR",
        "pageSize": 3,
        "locationBias": {"circle": {"center": {"latitude": p["lat"], "longitude": p["lng"]}, "radius": 300.0}},
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK})
    try:
        res = urllib.request.urlopen(req, timeout=30)
        try:
            return json.loads(res.read().decode("utf-8"))
        finally:
            res.close()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "ignore")
        if e.code == 429:
            sys.exit("하루 한도(또는 분당 한도)에 걸렸어요. 지금까지 받은 것은 저장돼 있으니 나중에 다시 실행하면 이어서 받습니다.")
        sys.exit(f"HTTP {e.code} 오류: {text[:500]}")


def name_similarity(a, b):
    if a and b and (a in b or b in a):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(p, result):
    """이름과 좌표가 함께 맞는 결과만 채택"""
    best = None
    for c in result.get("places", []):
        loc = c.get("location") or {}
        if "latitude" not in loc:
            continue
        d = meters(p["lat"], p["lng"], loc["latitude"], loc["longitude"])
        sim = name_similarity(norm(p["name"]), norm((c.get("displayName") or {}).get("text")))
        if sim >= 0.95:
            limit = MATCH_MAX_M_SAME_NAME
        else:
            limit = MATCH_MAX_M
        if d <= limit and sim >= MATCH_MIN_NAME:
            score = sim - d / 1000
            if best is None or score > best[0]:
                best = (score, c, d, sim)
    if not best:
        return None
    _, c, d, sim = best
    return {
        "google_id": c.get("id"),
        "google_name": (c.get("displayName") or {}).get("text"),
        "rating": c.get("rating"),
        "reviews": c.get("userRatingCount"),
        "hours": convert_hours(c.get("regularOpeningHours")),
        "distance_m": round(d),
        "name_similarity": round(sim, 2),
    }


def format_minutes(m):
    """810 → '13:30', 1440 → '24:00'"""
    if m == DAY_MINUTES:
        return "24:00"
    return f"{(m % DAY_MINUTES) // 60:02d}:{m % 60:02d}"


def convert_hours(roh):
    if not roh or not roh.get("periods"):
        return None
    periods = roh["periods"]
    if len(periods) == 1 and "close" not in periods[0]:  # 24시간 영업
        out = {}
        for d in range(7):
            out[str(d)] = "00:00-24:00"
        return out

    spans = {}
    for per in periods:
        o, c = per.get("open"), per.get("close")
        if not o or not c:
            continue
        day = (o["day"] + 6) % 7  # 구글 0=일 → 앱 0=월
        start = o.get("hour", 0) * 60 + o.get("minute", 0)
        end = c.get("hour", 0) * 60 + c.get("minute", 0)
        if c["day"] != o["day"]:
            end += DAY_MINUTES
        if day not in spans:
            spans[day] = []
        spans[day].append((start, end))

    out = {}
    for day in sorted(spans):
        starts = []
        ends = []
        for a, b in spans[day]:
            starts.append(a)
            ends.append(b)
        out[str(day)] = format_minutes(min(starts)) + "-" + format_minutes(max(ends))
    return out


def option_value(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


def save_cache(cache):
    f = open(CACHE, "w", encoding="utf-8")
    try:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    finally:
        f.close()


def main():
    limit = option_value("--limit", 5)
    targets = pick_targets(load_places())
    cache = {}
    for k, v in apiutil.read_json(CACHE, {}).items():
        if isinstance(v, dict) and "places" in v:  # 옛 형식은 재수집
            cache[k] = v
    todo = []
    tour_n = 0
    for p in targets:
        if place_key(p) not in cache:
            todo.append(p)
        if p.get("source") == "tour":
            tour_n += 1
    print(f"대상 {len(targets)}곳 (관광공사 {tour_n} + 상위 후보 {len(targets) - tour_n}) · "
          f"이미 받음 {len(targets) - len(todo)} · 남음 {len(todo)} · 이번 요청 최대 {limit}")
    if "--dry-run" in sys.argv:
        return

    apiutil.load_env()
    key = os.environ.get("GOOGLE_PLACES_KEY")
    if not key:
        sys.exit(".env 파일에 GOOGLE_PLACES_KEY=... 를 넣어 주세요.")

    os.makedirs(apiutil.RAW_DIR, exist_ok=True)
    matched = 0
    for i, p in enumerate(todo[:limit], start=1):
        raw = request(key, p)
        cache[place_key(p)] = {"places": raw.get("places", [])}
        m = best_match(p, raw)
        if m is not None:
            matched += 1
        if limit <= 10:
            if m:
                print(f"  {p['name']} → {m['google_name']} ★{m['rating']} ({m['reviews']})")
            else:
                print(f"  {p['name']} → 매칭 안 됨 (중립값)")
        if i % 20 == 0:
            save_cache(cache)
            print(f"  {i}곳 요청 (매칭 {matched})")
        time.sleep(0.1)
    save_cache(cache)
    print(f"완료: 이번에 {min(len(todo), limit)}곳 요청, {matched}곳 매칭 → {CACHE}")


if __name__ == "__main__":
    main()
