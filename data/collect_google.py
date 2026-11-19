# Google Places API (New)로 평점·리뷰 수·영업시간 수집 (S4·S5·영업시간 필터용)
#
# 버전 기록
# v0.1 (2026-11-19) 관광공사 장소 + 카테고리별 점수 상위 후보를 Text Search로 찾아 평점·리뷰 수·영업시간 수집, 캐시·한도·매칭 검증
# v0.2 (2026-11-19) 캐시에 검색 결과 원본을 저장(매칭 기준을 바꿔도 다시 요청 안 함), 이름 기준 0.75로 강화, 이름이 같으면 800m까지 허용(공원·테마파크)
#
# 실행 (프로젝트 루트에서, .env에 GOOGLE_PLACES_KEY 필요):
#   python data/collect_google.py --limit 5     # 시험: 5곳만 요청하고 결과를 화면에 보여 줌
#   python data/collect_google.py --limit 850   # 본 수집 (이미 받은 곳은 다시 요청하지 않음)
#   python data/collect_google.py --dry-run     # 요청 없이 대상 목록·개수만 확인
# 결과: data/raw/google_raw.json (저장소에 올리지 않음) → build_places.py가 읽어서 places.json에 합침
#
# 요금 주의: 평점·리뷰 수·영업시간 필드를 요청하면 Text Search가 Enterprise 등급으로 계산된다.
# 한 곳에 요청 1번. 무료 범위 안에서 쓰도록 --limit과 Google Cloud 콘솔의 하루 한도를 함께 건다.

import argparse
import difflib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apiutil import RAW_DIR, ROOT, load_env  # noqa: E402

sys.path.insert(0, ROOT)
from core.geo import DEFAULT_ORIGIN, haversine_km  # noqa: E402
from core.search import Conditions, search  # noqa: E402

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.location",
    "places.rating", "places.userRatingCount", "places.regularOpeningHours",
])
CACHE = os.path.join(RAW_DIR, "google_raw.json")
PLACES = os.path.join(ROOT, "data", "places.json")

MATCH_MAX_M = 150          # 좌표가 이 거리(m) 안이어야 같은 곳으로 본다
MATCH_MAX_M_SAME_NAME = 800  # 이름이 같으면(공원·테마파크처럼 넓은 곳) 이 거리까지 허용
MATCH_MIN_NAME = 0.75      # 이름 유사도 (0~1). 한쪽이 다른 쪽을 포함하면 1.0
TOP_PER_CATEGORY = 60      # 카테고리별 점수 상위 몇 곳을 후보로 할지
MAX_TARGETS = 850          # 전체 대상 상한 (무료 1,000건 안에서 시험 요청 여유를 남김)
CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]


def place_key(p):
    return f"{p.get('source', 'sample')}:{p.get('source_id') or p['id']}"


def norm(s):
    return "".join((s or "").split()).lower()


def meters(a_lat, a_lng, b_lat, b_lng):
    r = 6371000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load_places():
    with open(PLACES, encoding="utf-8") as f:
        return json.load(f)["places"]


def pick_targets(places):
    """관광공사 장소 전부 → 카테고리별 기본 검색(3km) 점수 상위 → 기본 위치(중구청)에서 가까운 순으로
    MAX_TARGETS까지 채운다. 앞에 올수록 먼저 수집 (한도에 걸려도 중요한 곳부터 채워짐)."""
    targets, seen = [], set()

    def add(p):
        k = place_key(p)
        if k not in seen and not p.get("is_conglomerate") and not p.get("is_franchise"):
            seen.add(k)
            targets.append(p)

    for p in places:
        if p.get("source") == "tour":
            add(p)
    rows = [dict(p, own_avg=None, own_count=0, likes=0) for p in places]
    for cat in CATEGORIES:
        ranked, _ = search(rows, Conditions(categories=[cat], max_km=3))
        for p in ranked[:TOP_PER_CATEGORY]:
            add(p)
    nearest = sorted(places, key=lambda p: haversine_km(DEFAULT_ORIGIN[0], DEFAULT_ORIGIN[1], p["lat"], p["lng"]))
    for p in nearest:
        if len(targets) >= MAX_TARGETS:
            break
        add(p)
    return targets[:MAX_TARGETS]


def request(key, p):
    body = {
        "textQuery": f"{p['name']} 대전 중구",
        "languageCode": "ko",
        "regionCode": "KR",
        "pageSize": 3,
        "locationBias": {"circle": {"center": {"latitude": p["lat"], "longitude": p["lng"]},
                                    "radius": 300.0}},
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                 "X-Goog-FieldMask": FIELD_MASK})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "ignore")
        if e.code == 429:
            sys.exit("하루 한도(또는 분당 한도)에 걸렸어요. 지금까지 받은 것은 저장돼 있으니 나중에 다시 실행하면 이어서 받습니다.")
        sys.exit(f"HTTP {e.code} 오류: {text[:500]}")


def best_match(p, result):
    """이름과 좌표가 함께 맞는 결과만 채택. 애매하면 None (→ 중립값 0.5)."""
    best = None
    for c in result.get("places", []):
        loc = c.get("location") or {}
        if "latitude" not in loc:
            continue
        d = meters(p["lat"], p["lng"], loc["latitude"], loc["longitude"])
        a, b = norm(p["name"]), norm((c.get("displayName") or {}).get("text"))
        sim = 1.0 if (a and b and (a in b or b in a)) else difflib.SequenceMatcher(None, a, b).ratio()
        limit = MATCH_MAX_M_SAME_NAME if sim >= 0.95 else MATCH_MAX_M
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


def convert_hours(roh):
    """구글 영업시간 → 앱 형식 {"0": "HH:MM-HH:MM", ...} (0=월). 하루에 여러 구간이면 가장 이른 시작~가장 늦은 끝."""
    if not roh or not roh.get("periods"):
        return None
    periods = roh["periods"]
    if len(periods) == 1 and "close" not in periods[0]:  # 24시간 영업
        return {str(d): "00:00-24:00" for d in range(7)}
    spans = {}  # 요일 → [(시작분, 끝분)], 끝이 다음 날이면 24시간(1440분)을 더해 둔다
    for per in periods:
        o, c = per.get("open"), per.get("close")
        if not o or not c:
            continue
        day = (o["day"] + 6) % 7  # 구글 0=일요일 → 앱 0=월요일
        start = o.get("hour", 0) * 60 + o.get("minute", 0)
        end = c.get("hour", 0) * 60 + c.get("minute", 0)
        if c["day"] != o["day"]:
            end += 1440
        spans.setdefault(day, []).append((start, end))

    def fmt(m):
        return "24:00" if m == 1440 else f"{(m % 1440) // 60:02d}:{m % 60:02d}"

    out = {}
    for day, items in sorted(spans.items()):
        s, e = min(a for a, _ in items), max(b for _, b in items)
        out[str(day)] = f"{fmt(s)}-{fmt(e)}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="이번 실행에서 새로 요청할 최대 개수 (기본 5)")
    ap.add_argument("--dry-run", action="store_true", help="요청하지 않고 대상만 확인")
    args = ap.parse_args()

    targets = pick_targets(load_places())
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    # 옛 형식(매칭 결과만 저장한 v0.1)은 다시 받는다
    cache = {k: v for k, v in cache.items() if isinstance(v, dict) and "places" in v}
    todo = [p for p in targets if place_key(p) not in cache]
    tour_n = sum(1 for p in targets if p.get("source") == "tour")
    print(f"대상 {len(targets)}곳 (관광공사 {tour_n} + 상위 후보 {len(targets) - tour_n}) · "
          f"이미 받음 {len(targets) - len(todo)} · 남음 {len(todo)} · 이번 요청 최대 {args.limit}")
    if args.dry_run:
        return

    load_env()
    key = os.environ.get("GOOGLE_PLACES_KEY")
    if not key:
        sys.exit(".env 파일에 GOOGLE_PLACES_KEY=... 를 넣어 주세요.")

    os.makedirs(RAW_DIR, exist_ok=True)
    matched = 0
    for i, p in enumerate(todo[:args.limit], start=1):
        raw = request(key, p)
        cache[place_key(p)] = {"places": raw.get("places", [])}  # 원본 저장 (못 찾은 곳도 저장해서 다시 요청하지 않음)
        m = best_match(p, raw)
        matched += m is not None
        if args.limit <= 10:
            print(f"  {p['name']} → {m['google_name'] + ' ★' + str(m['rating']) + ' (' + str(m['reviews']) + ')' if m else '매칭 안 됨 (중립값)'}")
        if i % 20 == 0:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
            print(f"  {i}곳 요청 (매칭 {matched})")
        time.sleep(0.1)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"완료: 이번에 {min(len(todo), args.limit)}곳 요청, {matched}곳 매칭 → {CACHE}")


if __name__ == "__main__":
    main()
