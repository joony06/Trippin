# Google Places API (New)로 평점·리뷰 수·영업시간 수집 (S4·S5·영업시간 필터용)
#
# 버전 기록
# v0.1 (2026-11-19) 관광공사 장소 + 카테고리별 점수 상위 후보를 Text Search로 찾아 평점·리뷰 수·영업시간 수집, 캐시·한도·매칭 검증
# v0.2 (2026-11-19) 캐시에 검색 결과 원본을 저장(매칭 기준을 바꿔도 다시 요청 안 함), 이름 기준 0.75로 강화, 이름이 같으면 800m까지 허용
# v0.3 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, argparse 대신 sys.argv로 옵션을 읽음, 캐시 저장을 함수로 분리.
#                   대상·매칭·영업시간 변환 결과는 v0.2와 같다
#
# 실행 (프로젝트 폴더에서, .env에 GOOGLE_PLACES_KEY 필요):
#   python data/tools/collect_google.py --limit 5     # 시험: 5곳만 요청하고 결과를 화면에 보여 줌
#   python data/tools/collect_google.py --limit 850   # 본 수집 (이미 받은 곳은 다시 요청하지 않음)
#   python data/tools/collect_google.py --dry-run     # 요청 없이 대상 목록·개수만 확인
# 결과: data/raw/google_raw.json (저장소에 올리지 않음) → build_places.py가 읽어서 places.json에 합침
#
# 요금 주의: 평점·리뷰 수·영업시간 필드를 요청하면 Text Search가 Enterprise 등급으로 계산된다.
# 한 곳에 요청 1번. 무료 범위 안에서 쓰도록 --limit과 Google Cloud 콘솔의 하루 한도를 함께 건다.

import difflib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

import apiutil

sys.path.insert(0, apiutil.ROOT)  # 프로젝트 폴더의 search.py를 불러오기 위해
import search  # noqa: E402

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(["places.id", "places.displayName", "places.location",
                       "places.rating", "places.userRatingCount", "places.regularOpeningHours"])
CACHE = os.path.join(apiutil.RAW_DIR, "google_raw.json")
PLACES = os.path.join(apiutil.DATA_DIR, "places.json")

MATCH_MAX_M = 150            # 좌표가 이 거리(m) 안이어야 같은 곳으로 본다
MATCH_MAX_M_SAME_NAME = 800  # 이름이 같으면(공원·테마파크처럼 넓은 곳) 이 거리까지 허용
MATCH_MIN_NAME = 0.75        # 이름 유사도 (0~1). 한쪽이 다른 쪽을 포함하면 1.0
TOP_PER_CATEGORY = 60        # 카테고리별 점수 상위 몇 곳을 후보로 할지
MAX_TARGETS = 850            # 전체 대상 상한 (무료 1,000건 안에서 시험 요청 여유를 남김)
CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DAY_MINUTES = 1440


def place_key(p):
    """캐시에서 장소를 찾는 열쇠: '출처:원본 번호'"""
    return f"{p.get('source', 'sample')}:{p.get('source_id') or p['id']}"


def norm(s):
    """비교용 이름: 띄어쓰기를 모두 없애고 소문자로"""
    return "".join((s or "").split()).lower()


def meters(a_lat, a_lng, b_lat, b_lng):
    """두 지점 사이 거리(m), 하버사인 공식"""
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
    """대기업·대형체인이 아니고 아직 안 넣은 장소면 대상 목록에 넣는다"""
    k = place_key(p)
    if k not in seen and not p.get("is_conglomerate") and not p.get("is_franchise"):
        seen.add(k)
        targets.append(p)


def pick_targets(places):
    """관광공사 장소 전부 → 카테고리별 기본 검색(3km) 점수 상위 → 기본 위치(중구청)에서 가까운 순으로
    MAX_TARGETS까지 채운다. 앞에 올수록 먼저 수집 (한도에 걸려도 중요한 곳부터 채워짐)."""
    targets = []
    seen = set()  # 이미 넣은 장소의 열쇠 (집합이라 중복 확인이 빠르다)
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
    """장소 이름으로 구글 Text Search 요청 1번. 한도에 걸리면 멈춘다 (받은 것은 캐시에 남아 있음)."""
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
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "ignore")
        if e.code == 429:
            sys.exit("하루 한도(또는 분당 한도)에 걸렸어요. 지금까지 받은 것은 저장돼 있으니 나중에 다시 실행하면 이어서 받습니다.")
        sys.exit(f"HTTP {e.code} 오류: {text[:500]}")


def name_similarity(a, b):
    """이름 유사도 0~1. 한쪽이 다른 쪽을 포함하면 1.0, 아니면 difflib(10주차 표준 라이브러리)의 비율"""
    if a and b and (a in b or b in a):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(p, result):
    """이름과 좌표가 함께 맞는 결과만 채택. 애매하면 None (→ S4·S5 중립값 0.5)."""
    best = None
    for c in result.get("places", []):
        loc = c.get("location") or {}
        if "latitude" not in loc:
            continue
        d = meters(p["lat"], p["lng"], loc["latitude"], loc["longitude"])
        sim = name_similarity(norm(p["name"]), norm((c.get("displayName") or {}).get("text")))
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


def format_minutes(m):
    """810 → '13:30', 1440 → '24:00'"""
    if m == DAY_MINUTES:
        return "24:00"
    return f"{(m % DAY_MINUTES) // 60:02d}:{m % 60:02d}"


def convert_hours(roh):
    """구글 영업시간 → 앱 형식 {"0": "HH:MM-HH:MM", ...} (0=월). 하루에 여러 구간이면 가장 이른 시작~가장 늦은 끝."""
    if not roh or not roh.get("periods"):
        return None
    periods = roh["periods"]
    if len(periods) == 1 and "close" not in periods[0]:  # 24시간 영업
        out = {}
        for d in range(7):
            out[str(d)] = "00:00-24:00"
        return out

    spans = {}  # 요일 → [(시작 분, 끝 분)]. 끝이 다음 날이면 1440분을 더해 둔다
    for per in periods:
        o, c = per.get("open"), per.get("close")
        if not o or not c:
            continue
        day = (o["day"] + 6) % 7  # 구글 0=일요일 → 앱 0=월요일
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
    """명령줄에서 '--limit 5' 같은 값을 읽는다 (없으면 default)"""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


def save_cache(cache):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def main():
    limit = option_value("--limit", 5)  # 이번 실행에서 새로 요청할 최대 개수
    targets = pick_targets(load_places())
    cache = {}
    for k, v in apiutil.read_json(CACHE, {}).items():
        if isinstance(v, dict) and "places" in v:  # 옛 형식(매칭 결과만 저장한 v0.1)은 다시 받는다
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
        cache[place_key(p)] = {"places": raw.get("places", [])}  # 원본 저장 (못 찾은 곳도 저장해서 다시 요청하지 않음)
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
