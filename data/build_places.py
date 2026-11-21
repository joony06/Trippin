# 수집한 원본(상가정보·TourAPI)을 앱의 장소 데이터(data/places.json)로 바꾼다
#
# 버전 기록
# v0.1 (2026-11-18) 관광 업종 선별, 카테고리 변환, TourAPI·상가정보 중복 제거, 영문 이름 짝짓기, 대기업 계열 표시
# v0.2 (2026-11-18) 대형 프랜차이즈 표시: 대전 전체에서 지점명이 붙은 같은 상호가 FRANCHISE_MIN_STORES곳 이상이면 is_franchise
# v0.3 (2026-11-18) 관광객이 갈 수 없는 곳 제외: 구내식당 업종, 상호에 기관·단체 단어(상조회·협의회 등)가 든 곳
# v0.4 (2026-11-18) 빵/도넛·떡/한과·아이스크림/빙수는 카테고리를 [카페, 음식]으로 (카페로 찾아도 S1 점수를 받도록)
# v0.5 (2026-11-19) Gemini 설명문(data/descriptions.json)과 구글 평점·리뷰 수·영업시간(data/raw/google_raw.json) 합치기
# v0.6 (2026-11-19) 구글 캐시가 검색 결과 원본이 되어, 매칭은 collect_google.best_match로 여기서 판정
# v0.7 (2026-11-21) 검수표 반영: 가게별 판정(store_verdicts.json: 대기업·대형체인·기관)을 덮어씀, 대형체인 브랜드 목록(chain_brands.txt),
#                   철자 다른 브랜드 표기(바게트/바게뜨, 베스킨/배스킨) 맞춤, 관광지 이름으로 역사·자연·야경 카테고리 보강,
#                   요금은 모르는 값이라 0 대신 None(화면에 '정보 없음'). 이미 만든 places.json에만 적용: --apply-only
#
# 실행 (프로젝트 루트에서, collect_sbiz.py·collect_tour.py를 먼저 실행):
#   python data/build_places.py
# 결과: data/places.json  → 앱은 이 파일이 있으면 샘플 대신 이 파일을 쓴다 (flask --app app init-db 로 다시 적재)
#
# 아직 없는 값: 영업시간·요금·구글 평점은 비워 둔다.
#   영업시간이 없으면 영업 필터에서 빼지 않고, 구글 값이 없으면 S4·S5에 중립값 0.5가 들어간다.

import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "places.json")
BRANDS = os.path.join(HERE, "conglomerate_brands.txt")
CHAINS = os.path.join(HERE, "chain_brands.txt")          # 대형 체인 브랜드 (대기업 집단은 아님)
VERDICTS = os.path.join(HERE, "store_verdicts.json")    # 검수표 가게별 판정
DESCRIPTIONS = os.path.join(HERE, "descriptions.json")   # gen_descriptions.py 결과 (저장소에 올림)
GOOGLE = os.path.join(RAW, "google_raw.json")             # collect_google.py 결과 (저장소에 안 올림)

# 대형 프랜차이즈 기준: 대전 전체에서 '지점명이 있는 같은 상호'가 이 수 이상이면 대형 프랜차이즈로 본다
# (전국 가맹점 수 API는 가명정보 승인 절차가 필요해서, 대전 상가정보로 대신 센다)
FRANCHISE_MIN_STORES = 10

# ---------------------------------------------------------------- 상가정보: 관광객 대상 업종만

# (대분류, 중분류) → 앱 카테고리. 목록에 없는 업종(미용실·부동산·학원 등)은 뺀다.
SBIZ_CATEGORY = {
    ("음식", "한식"): ["음식"],
    ("음식", "중식"): ["음식"],
    ("음식", "일식"): ["음식"],
    ("음식", "서양식"): ["음식"],
    ("음식", "동남아시아"): ["음식"],
    ("음식", "기타 외국식"): ["음식"],
    ("음식", "기타 간이"): ["음식"],
    ("음식", "비알코올 "): ["카페"],   # API 값 끝에 공백이 붙어 있다
    ("음식", "비알코올"): ["카페"],
}
# 소분류에 따라 카테고리를 바꾼다 (첫 번째가 대표 카테고리)
SMALL_CATEGORY_OVERRIDE = {
    "빵/도넛": ["카페", "음식"],
    "떡/한과": ["카페", "음식"],
    "아이스크림/빙수": ["카페", "음식"],
}

# 음식 업종이지만 관광객이 갈 수 없는 곳 (소분류 이름 기준)
EXCLUDE_SMALL_CATEGORIES = {"구내식당", "기타 구내식당", "출장 음식 서비스", "단체 급식"}

# 상호에 이런 단어가 들어 있으면 가게가 아니라 기관·단체로 보고 뺀다 (예: 중구청직원상조회)
EXCLUDE_NAME_WORDS = ["상조회", "협의회", "협회", "위원회", "조합", "재단", "공단", "구청", "시청",
                      "주민센터", "복지관", "어린이집", "유치원", "학교", "교회", "성당", "경로당",
                      "노인회", "부녀회", "직원", "급식", "기숙사"]

# 주점은 MVP에서 제외 (필요하면 위에 ("음식", "주점"): ["음식", "야경"] 추가)

# ---------------------------------------------------------------- TourAPI: 콘텐츠 타입·분류 → 앱 카테고리

TOUR_TYPE_CATEGORY = {
    "12": ["사진명소"],   # 관광지 (아래 lclsSystm1로 앞에 더 구체적인 카테고리를 붙인다)
    "14": ["문화"],       # 문화시설
    "28": ["액티비티"],   # 레포츠
    "38": ["쇼핑"],       # 쇼핑
    "39": ["음식"],       # 음식점
}
TOUR_LCLS_CATEGORY = {   # 신분류체계 대분류
    "HS": "역사",        # 역사관광
    "NA": "자연",        # 자연관광
    "VE": "가족",        # 문화·레저 시설(테마파크·공원 등)
    "EX": "액티비티",    # 체험관광
    "LS": "액티비티",    # 레저스포츠
    "SH": "쇼핑",
    "FD": "음식",
    "EV": "문화",        # 축제·공연
}


# 같은 브랜드를 다르게 적은 상호 (상가정보 원본 철자) → 브랜드 목록 철자
BRAND_SPELLING = {"바게트": "바게뜨", "베스킨": "배스킨"}

# 관광지 이름에 이 단어가 있으면 카테고리를 앞에 붙인다 (TourAPI 분류만으로는 역사 8곳·자연 3곳·야경 0곳이라)
TOUR_NAME_CATEGORY = [
    ("역사", ["기념관", "전시관", "사당", "생가", "서원", "향교", "종가", "마애", "숭절사", "유적", "고택"]),
    ("자연", ["공원", "숲", "산", "둘레길", "수목원", "계곡"]),
    ("야경", ["전망대", "스카이로드", "으능정이", "볼파크"]),
]


def norm_name(s):
    """비교용 이름: 괄호 내용·공백·지점 표기 제거, 브랜드 철자 맞춤"""
    s = re.sub(r"\(.*?\)", "", s or "")
    s = re.sub(r"\s+", "", s)
    for wrong, right in BRAND_SPELLING.items():
        s = s.replace(wrong, right)
    return s.replace("본점", "").lower()


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def dong_from_address(addr):
    m = re.search(r"\(([가-힣0-9]+동)\)", addr or "") or re.search(r"([가-힣0-9]+동)\s", addr or "")
    return m.group(1) if m else None


def load_brands(path=BRANDS):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def tour_categories(name, cats):
    """관광지(음식·쇼핑 제외) 이름으로 역사·자연·야경을 앞에 붙인다. 순서: 역사 → 자연 → 기존 → 야경"""
    if "음식" in cats or "쇼핑" in cats:
        return cats
    hit = {cat for cat, words in TOUR_NAME_CATEGORY if any(w in name for w in words)} | set(cats)
    front = [c for c in ("역사", "자연") if c in hit]
    back = ["야경"] if "야경" in hit and "야경" not in cats else []
    return front + [c for c in cats if c not in front] + back


def apply_overrides(places):
    """브랜드 목록·검수표 판정·카테고리 보강·요금을 적용한다. 기관으로 판정된 곳은 뺀다. (남은 곳, 판정 반영 수, 기관 제외 수)"""
    brands, chains = load_brands(BRANDS), load_brands(CHAINS)
    verdicts = {}
    if os.path.exists(VERDICTS):
        with open(VERDICTS, encoding="utf-8") as f:
            verdicts = json.load(f).get("verdicts", {})
    out, n_verdict, n_org = [], 0, 0
    for p in places:
        p["is_conglomerate"] = is_conglomerate(p["name"], brands)
        p["is_franchise"] = bool(p.get("is_franchise")) or any(norm_name(p["name"]).startswith(norm_name(c)) for c in chains)
        p["fee"] = None  # 요금 정보는 수집하지 않았다 (0원으로 두면 '무료'로 잘못 보임)
        if p["source"] == "tour":
            p["categories"] = tour_categories(p["name"], p["categories"])
        v = verdicts.get(f"{p['source']}:{p.get('source_id')}", {}).get("verdict")
        if v == "기관":
            n_org += 1
            continue
        if v == "대기업":
            p["is_conglomerate"], p["is_franchise"] = True, False
        elif v == "대형체인":
            p["is_conglomerate"], p["is_franchise"] = False, True
        n_verdict += bool(v)
        out.append(p)
    return out, n_verdict, n_org


def is_conglomerate(name, brands):
    n = norm_name(name)
    return any(norm_name(b) in n for b in brands)


def franchise_brands():
    """대전 전체 상가정보에서 지점명이 붙은 상호의 매장 수를 센다. {정규화된 상호: 매장 수}"""
    path = os.path.join(RAW, "sbiz_daejeon_all.json")
    if not os.path.exists(path):
        print("※ data/raw/sbiz_daejeon_all.json 이 없어 대형 프랜차이즈 판정을 건너뜁니다. "
              "(python data/collect_sbiz.py --daejeon 먼저 실행)")
        return {}
    with open(path, encoding="utf-8") as f:
        stores = json.load(f)
    counts = {}
    for st in stores:
        if st.get("branch") and st.get("name"):
            n = norm_name(st["name"])
            if len(n) >= 2:
                counts[n] = counts.get(n, 0) + 1
    return {n: c for n, c in counts.items() if c >= FRANCHISE_MIN_STORES}


def is_franchise(name, big):
    """상호가 대형 프랜차이즈 브랜드와 같거나, 브랜드 이름으로 시작하면 (예: '올리브영 대전대흥점')"""
    n = norm_name(name)
    return n in big or any(n.startswith(b) for b in big if len(b) >= 3)


def merge_extras(places):
    from collect_google import best_match  # 같은 폴더의 스크립트 (매칭 기준을 한 곳에서 관리)
    """설명문과 구글 데이터를 합친다. 파일이 없으면 건너뛴다. (설명문 수, 구글 매칭 수)"""
    descs, google = {}, {}
    if os.path.exists(DESCRIPTIONS):
        with open(DESCRIPTIONS, encoding="utf-8") as f:
            descs = json.load(f)
    if os.path.exists(GOOGLE):
        with open(GOOGLE, encoding="utf-8") as f:
            google = json.load(f)
    n_desc = n_google = 0
    for p in places:
        d = descs.get(p.get("source_id")) if p["source"] == "tour" else None
        if d:
            p["description"], p["description_en"] = d.get("ko"), d.get("en")
            n_desc += 1
        raw = google.get(f"{p['source']}:{p.get('source_id')}")
        g = best_match(p, raw) if isinstance(raw, dict) and "places" in raw else None
        if g:
            p["google_rating"], p["google_reviews"] = g.get("rating"), g.get("reviews")
            if g.get("hours"):
                p["hours"] = g["hours"]
            n_google += 1
    return n_desc, n_google


def load(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)


def build():
    brands = load_brands()
    big = franchise_brands()
    tour_kor = load("tour_kor.json")
    tour_eng = load("tour_eng.json")
    sbiz = load("sbiz_daejeon_junggu.json")

    # 영문 제목 "Ppuri Park (뿌리공원)" → 괄호 안 한국어 이름으로 짝짓기, 안 되면 50m 안의 가장 가까운 곳
    eng_by_name = {}
    for e in tour_eng:
        m = re.search(r"\(([^)]*[가-힣][^)]*)\)", e.get("title") or "")
        if m:
            eng_by_name[norm_name(m.group(1))] = re.sub(r"\s*\(.*?\)\s*$", "", e["title"]).strip()

    def english_name(k):
        if norm_name(k["title"]) in eng_by_name:
            return eng_by_name[norm_name(k["title"])]
        best = None
        for e in tour_eng:
            if e.get("lat") and k.get("lat"):
                d = km((k["lat"], k["lng"]), (e["lat"], e["lng"]))
                if d < 0.05 and (best is None or d < best[0]):
                    best = (d, re.sub(r"\s*\(.*?\)\s*$", "", e["title"]).strip())
        return best[1] if best else None

    places = []

    # 1) TourAPI 국문: 관광공사에 등록된 곳은 모두 넣는다
    for k in tour_kor:
        if not k.get("lat"):
            continue
        cats = list(TOUR_TYPE_CATEGORY.get(k["content_type"], ["문화"]))
        lcls = (k.get("category_code") or "")[:2]
        front = TOUR_LCLS_CATEGORY.get(lcls)
        if front and front not in cats:
            cats.insert(0, front)
        places.append({
            "name": k["title"],
            "name_en": english_name(k),
            "categories": cats,
            "description": None,
            "dong": dong_from_address(k.get("address")),
            "address": k.get("address"),
            "lat": k["lat"], "lng": k["lng"],
            "fee": 0, "hours": None,
            "is_conglomerate": is_conglomerate(k["title"], brands),
            "is_franchise": is_franchise(k["title"], big),
            "google_rating": None, "google_reviews": None,
            "image": k.get("image"),
            "source": "tour",
            "source_id": k.get("content_id"),
        })

    tour_points = [(norm_name(p["name"]), (p["lat"], p["lng"])) for p in places]

    # 2) 상가정보: 관광객 대상 업종만, TourAPI와 겹치는 곳(이름 같고 100m 안)은 뺀다
    skipped_dup = 0
    skipped_org = 0  # 구내식당·기관·단체
    for s in sbiz:
        cats = SBIZ_CATEGORY.get((s.get("category_large"), s.get("category_mid")))
        if not cats or not s.get("lat"):
            continue
        small = (s.get("category_small") or "").strip()
        cats = SMALL_CATEGORY_OVERRIDE.get(small, cats)
        if small in EXCLUDE_SMALL_CATEGORIES:
            skipped_org += 1
            continue
        if any(w in (s.get("name") or "") for w in EXCLUDE_NAME_WORDS):
            skipped_org += 1
            continue
        n = norm_name(s["name"])
        if any((n in tn or tn in n) and km((s["lat"], s["lng"]), tp) < 0.1 for tn, tp in tour_points):
            skipped_dup += 1
            continue
        name = s["name"] + (f" {s['branch']}" if s.get("branch") else "")
        places.append({
            "name": name,
            "name_en": None,
            "categories": list(cats),
            "description": f"{s.get('dong') or '대전 중구'}의 {s.get('category_small') or s.get('category_mid')}",
            "dong": s.get("dong"),
            "address": s.get("address"),
            "lat": s["lat"], "lng": s["lng"],
            "fee": 0, "hours": None,
            "is_conglomerate": is_conglomerate(s["name"], brands),
            "is_franchise": is_franchise(s["name"], big),
            "google_rating": None, "google_reviews": None,
            "image": None,
            "source": "sbiz",
            "source_id": s.get("source_id"),
        })

    places, n_verdict, n_org = apply_overrides(places)
    for i, p in enumerate(places, start=1):
        p["id"] = i
    n_desc, n_google = merge_extras(places)

    out = {
        "_note": "data/build_places.py로 만든 파일. 출처: 소상공인시장진흥공단 상가(상권)정보, 한국관광공사 TourAPI. "
                 "요금은 수집하지 않음(None). 구글 평점·영업시간은 일부 장소만.",
        "places": places,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    tour_n = sum(1 for p in places if p["source"] == "tour")
    print(f"TourAPI {tour_n}곳 + 상가정보 {len(places) - tour_n}곳 = {len(places)}곳 "
          f"(겹쳐서 뺀 상가 {skipped_dup}곳, 기관·구내식당 제외 {skipped_org}곳, 대기업 계열 {sum(p['is_conglomerate'] for p in places)}곳, "
          f"대형 프랜차이즈 {sum(p['is_franchise'] and not p['is_conglomerate'] for p in places)}곳(브랜드 {len(big)}개 기준), "
          f"영문 이름 {sum(1 for p in places if p['name_en'])}곳)")
    print(f"설명문 {n_desc}곳, 구글 평점·영업시간 {n_google}곳 합침, 검수표 판정 {n_verdict}곳 반영(기관 {n_org}곳 뺌)")
    print(f"저장: {OUT}")


def apply_only():
    """원본(raw) 없이, 이미 있는 places.json에 브랜드·판정·카테고리·요금만 다시 적용한다."""
    with open(OUT, encoding="utf-8") as f:
        data = json.load(f)
    places, n_verdict, n_org = apply_overrides(data["places"])
    for i, p in enumerate(places, start=1):
        p["id"] = i
    data["places"] = places
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(places)}곳 (검수표 판정 {n_verdict}곳 반영, 기관 {n_org}곳 뺌, 대기업 {sum(p['is_conglomerate'] for p in places)}곳, "
          f"대형체인 {sum(p['is_franchise'] and not p['is_conglomerate'] for p in places)}곳)")


if __name__ == "__main__":
    apply_only() if "--apply-only" in sys.argv else build()
