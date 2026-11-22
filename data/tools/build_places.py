# 수집 원본을 합쳐 data/places.json 만들기
#
# 버전 기록
# v0.1 업종 선별·카테고리 변환·중복 제거·영문 이름·대기업 표시
# v0.2 대형 프랜차이즈 표시
# v0.3 구내식당·기관·단체 제외
# v0.4 빵·떡·아이스크림은 [카페, 음식]
# v0.5 구글 데이터 합치기
# v0.6 구글 매칭은 collect_google.best_match로
# v0.7 검수표 판정·체인 목록 반영, --apply-only
# v0.8 영문 이름 위치 짝짓기 수정
#
# 실행: python data/tools/build_places.py [--apply-only]

import json
import math
import os
import sys

import apiutil
from collect_google import best_match

RAW = apiutil.RAW_DIR
OUT = os.path.join(apiutil.DATA_DIR, "places.json")
BRANDS = os.path.join(apiutil.DATA_DIR, "conglomerate_brands.txt")
CHAINS = os.path.join(apiutil.DATA_DIR, "chain_brands.txt")
VERDICTS = os.path.join(apiutil.DATA_DIR, "store_verdicts.json")
GOOGLE = os.path.join(RAW, "google_raw.json")

# 대전에서 지점명이 붙은 같은 상호가 이 수 이상이면 대형 프랜차이즈
FRANCHISE_MIN_STORES = 10


# (대분류, 중분류) → 카테고리. 없는 업종은 제외
SBIZ_CATEGORY = {
    ("음식", "한식"): ["음식"],
    ("음식", "중식"): ["음식"],
    ("음식", "일식"): ["음식"],
    ("음식", "서양식"): ["음식"],
    ("음식", "동남아시아"): ["음식"],
    ("음식", "기타 외국식"): ["음식"],
    ("음식", "기타 간이"): ["음식"],
    ("음식", "비알코올 "): ["카페"],  # API 값 끝에 공백
    ("음식", "비알코올"): ["카페"],
}
SMALL_CATEGORY_OVERRIDE = {
    "빵/도넛": ["카페", "음식"],
    "떡/한과": ["카페", "음식"],
    "아이스크림/빙수": ["카페", "음식"],
}
EXCLUDE_SMALL_CATEGORIES = {"구내식당", "기타 구내식당", "출장 음식 서비스", "단체 급식"}
# 기관·단체로 보는 상호 단어
EXCLUDE_NAME_WORDS = ["상조회", "협의회", "협회", "위원회", "조합", "재단", "공단", "구청", "시청",
                      "주민센터", "복지관", "어린이집", "유치원", "학교", "교회", "성당", "경로당",
                      "노인회", "부녀회", "직원", "급식", "기숙사"]


TOUR_TYPE_CATEGORY = {
    "12": ["사진명소"],  # 관광지
    "14": ["문화"],       # 문화시설
    "28": ["액티비티"],   # 레포츠
    "38": ["쇼핑"],       # 쇼핑
    "39": ["음식"],       # 음식점
}
TOUR_LCLS_CATEGORY = {
    "HS": "역사",        # 역사관광
    "NA": "자연",        # 자연관광
    "VE": "가족",  # 테마파크·공원 등
    "EX": "액티비티",    # 체험관광
    "LS": "액티비티",    # 레저스포츠
    "SH": "쇼핑",
    "FD": "음식",
    "EV": "문화",        # 축제·공연
}
BRAND_SPELLING = {"바게트": "바게뜨", "베스킨": "배스킨"}
# 이름에 이 단어가 있으면 카테고리 추가
TOUR_NAME_CATEGORY = [
    ("역사", ["기념관", "전시관", "사당", "생가", "서원", "향교", "종가", "마애", "숭절사", "유적", "고택"]),
    ("자연", ["공원", "숲", "산", "둘레길", "수목원", "계곡"]),
    ("야경", ["전망대", "스카이로드", "으능정이", "볼파크"]),
]
DUPLICATE_KM = 0.1
ENGLISH_NEAR_KM = 0.05


def is_hangul(ch):
    return "가" <= ch <= "힣"


def remove_parens(s):
    """'빵집(대흥점)' → '빵집'"""
    out = ""
    i = 0
    while i < len(s):
        if s[i] == "(":
            close = s.find(")", i + 1)
            if close != -1:
                i = close + 1
                continue
        out += s[i]
        i += 1
    return out


def remove_trailing_parens(title):
    body = title.rstrip()
    first = body.find("(")
    if body.endswith(")") and first != -1 and first < len(body) - 1:
        return body[:first].strip()
    return title.strip()


def hangul_in_parens(title):
    i = title.find("(")
    while i != -1:
        close = title.find(")", i + 1)
        if close == -1:
            return None
        inside = title[i + 1:close]
        for ch in inside:
            if is_hangul(ch):
                return inside
        i = title.find("(", i + 1)
    return None


def is_dong_char(ch):
    return is_hangul(ch) or "0" <= ch <= "9"


def dong_from_address(addr):
    addr = addr or ""
    # 1) 괄호 안 '…동'
    i = addr.find("(")
    while i != -1:
        j = i + 1
        while j < len(addr) and is_dong_char(addr[j]):
            j += 1
        word = addr[i + 1:j]
        if len(word) >= 2 and word.endswith("동") and j < len(addr) and addr[j] == ")":
            return word
        i = addr.find("(", i + 1)
    # 2) 띄어쓰기 앞 '…동'
    i = 0
    while i < len(addr):
        if not is_dong_char(addr[i]):
            i += 1
            continue
        j = i
        while j < len(addr) and is_dong_char(addr[j]):
            j += 1
        word = addr[i:j]
        if len(word) >= 2 and word.endswith("동") and j < len(addr) and addr[j].isspace():
            return word
        i = j
    return None


def norm_name(s):
    s = "".join(remove_parens(s or "").split())
    for wrong in BRAND_SPELLING:
        s = s.replace(wrong, BRAND_SPELLING[wrong])
    return s.replace("본점", "").lower()


def km(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def load_brands(path):
    if not os.path.exists(path):
        return []
    brands = []
    f = open(path, encoding="utf-8")
    try:
        for line in f:
            if line.strip() and not line.startswith("#"):
                brands.append(line.strip())
    finally:
        f.close()
    return brands


def is_conglomerate(name, brands):
    n = norm_name(name)
    for b in brands:
        if norm_name(b) in n:
            return True
    return False


def franchise_brands():
    """대전 전체에서 지점명이 붙은 상호별 매장 수 (기준 이상만)"""
    stores = apiutil.read_json(os.path.join(RAW, "sbiz_daejeon_all.json"))
    if stores is None:
        print("※ data/raw/sbiz_daejeon_all.json 이 없어 대형 프랜차이즈 판정을 건너뜁니다. "
              "(python data/tools/collect_sbiz.py --daejeon 먼저 실행)")
        return {}
    counts = {}
    for st in stores:
        if st.get("branch") and st.get("name"):
            n = norm_name(st["name"])
            if len(n) >= 2:
                counts[n] = counts.get(n, 0) + 1
    big = {}
    for n in counts:
        if counts[n] >= FRANCHISE_MIN_STORES:
            big[n] = counts[n]
    return big


def is_franchise(name, big):
    """브랜드와 같거나 브랜드 이름으로 시작하는 상호"""
    n = norm_name(name)
    if n in big:
        return True
    for b in big:
        if len(b) >= 3 and n.startswith(b):
            return True
    return False


def is_chain(name, chains):
    n = norm_name(name)
    for c in chains:
        if n.startswith(norm_name(c)):
            return True
    return False


def tour_categories(name, cats):
    if "음식" in cats or "쇼핑" in cats:
        return cats
    hit = set(cats)
    for cat, words in TOUR_NAME_CATEGORY:
        for w in words:
            if w in name:
                hit.add(cat)
    front = []
    for c in ("역사", "자연"):
        if c in hit:
            front.append(c)
    middle = []
    for c in cats:
        if c not in front:
            middle.append(c)
    if "야경" in hit and "야경" not in cats:
        back = ["야경"]
    else:
        back = []
    return front + middle + back


def apply_overrides(places):
    brands = load_brands(BRANDS)
    chains = load_brands(CHAINS)
    verdicts = apiutil.read_json(VERDICTS, {}).get("verdicts", {})
    out = []
    n_verdict = 0
    n_org = 0
    for p in places:
        p["is_conglomerate"] = is_conglomerate(p["name"], brands)
        p["is_franchise"] = bool(p.get("is_franchise")) or is_chain(p["name"], chains)
        p["fee"] = None  # 요금 미수집
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
        if v:
            n_verdict += 1
        out.append(p)
    return out, n_verdict, n_org


def merge_extras(places):
    google = apiutil.read_json(GOOGLE, {})
    n_google = 0
    for p in places:
        raw = google.get(f"{p['source']}:{p.get('source_id')}")
        if isinstance(raw, dict) and "places" in raw:
            g = best_match(p, raw)
        else:
            g = None
        if g:
            p["google_rating"], p["google_reviews"] = g.get("rating"), g.get("reviews")
            if g.get("hours"):
                p["hours"] = g["hours"]
            n_google += 1
    return n_google


def english_titles(tour_eng):
    by_name = {}
    for e in tour_eng:
        korean = hangul_in_parens(e.get("title") or "")
        if korean is not None:
            by_name[norm_name(korean)] = remove_trailing_parens(e["title"])
    return by_name


def english_name(k, tour_eng, by_name, claimed):
    """영문 이름: 괄호 속 한국어 이름 우선, 없으면 50m 안 가장 가까운 곳"""
    if norm_name(k["title"]) in by_name:
        return by_name[norm_name(k["title"])]
    best = None
    for e in tour_eng:
        title = remove_trailing_parens(e.get("title") or "")
        if title in claimed:
            continue
        if e.get("lat") and k.get("lat"):
            d = km((k["lat"], k["lng"]), (e["lat"], e["lng"]))
            if d < ENGLISH_NEAR_KM and (best is None or d < best[0]):
                best = (d, remove_trailing_parens(e["title"]))
    if best:
        return best[1]
    else:
        return None


def tour_place(k, name_en, brands, big):
    cats = list(TOUR_TYPE_CATEGORY.get(k["content_type"], ["문화"]))
    front = TOUR_LCLS_CATEGORY.get((k.get("category_code") or "")[:2])
    if front and front not in cats:
        cats.insert(0, front)
    return {
        "name": k["title"],
        "name_en": name_en,
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
    }


def sbiz_place(s, cats, brands, big):
    name = s["name"]
    if s.get("branch"):
        name += " " + s["branch"]
    return {
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
    }


def is_organization(s, small):
    """구내식당 업종 또는 기관·단체 단어 포함 시 True"""
    if small in EXCLUDE_SMALL_CATEGORIES:
        return True
    for w in EXCLUDE_NAME_WORDS:
        if w in (s.get("name") or ""):
            return True
    return False


def overlaps_tour(s, tour_points):
    """관광공사 장소와 이름이 겹치고 100m 안이면 같은 곳"""
    n = norm_name(s["name"])
    for tn, tp in tour_points:
        if (n in tn or tn in n) and km((s["lat"], s["lng"]), tp) < DUPLICATE_KM:
            return True
    return False


def save_places(data):
    f = open(OUT, "w", encoding="utf-8")
    try:
        json.dump(data, f, ensure_ascii=False, indent=1)
    finally:
        f.close()


def number_places(places):
    for i, p in enumerate(places, start=1):
        p["id"] = i


def build():
    brands = load_brands(BRANDS)
    big = franchise_brands()
    tour_kor = apiutil.read_json(os.path.join(RAW, "tour_kor.json"))
    tour_eng = apiutil.read_json(os.path.join(RAW, "tour_eng.json"))
    sbiz = apiutil.read_json(os.path.join(RAW, "sbiz_daejeon_junggu.json"))

    by_name = english_titles(tour_eng)
    claimed = set()
    for k in tour_kor:
        if norm_name(k["title"]) in by_name:
            claimed.add(by_name[norm_name(k["title"])])

    # 1) 관광공사 장소
    places = []
    for k in tour_kor:
        if k.get("lat"):
            places.append(tour_place(k, english_name(k, tour_eng, by_name, claimed), brands, big))

    tour_points = []
    for p in places:
        tour_points.append((norm_name(p["name"]), (p["lat"], p["lng"])))

    # 2) 상가정보 (관광 업종만, 기관·중복 제외)
    skipped_dup = 0
    skipped_org = 0
    for s in sbiz:
        cats = SBIZ_CATEGORY.get((s.get("category_large"), s.get("category_mid")))
        if not cats or not s.get("lat"):
            continue
        small = (s.get("category_small") or "").strip()
        cats = SMALL_CATEGORY_OVERRIDE.get(small, cats)
        if is_organization(s, small):
            skipped_org += 1
            continue
        if overlaps_tour(s, tour_points):
            skipped_dup += 1
            continue
        places.append(sbiz_place(s, cats, brands, big))

    # 3) 판정 → 번호 → 구글
    places, n_verdict, n_org = apply_overrides(places)
    number_places(places)
    n_google = merge_extras(places)

    save_places({
        "_note": "data/build_places.py로 만든 파일. 출처: 소상공인시장진흥공단 상가(상권)정보, 한국관광공사 TourAPI. "
                 "요금은 수집하지 않음(None). 구글 평점·영업시간은 일부 장소만.",
        "places": places,
    })

    tour_n = 0
    n_cong = 0
    n_fran = 0
    n_en = 0
    for p in places:
        if p["source"] == "tour":
            tour_n += 1
        if p["is_conglomerate"]:
            n_cong += 1
        elif p["is_franchise"]:
            n_fran += 1
        if p["name_en"]:
            n_en += 1
    print(f"TourAPI {tour_n}곳 + 상가정보 {len(places) - tour_n}곳 = {len(places)}곳 "
          f"(겹쳐서 뺀 상가 {skipped_dup}곳, 기관·구내식당 제외 {skipped_org}곳, 대기업 계열 {n_cong}곳, "
          f"대형 프랜차이즈 {n_fran}곳(브랜드 {len(big)}개 기준), 영문 이름 {n_en}곳)")
    print(f"구글 평점·영업시간 {n_google}곳 합침, 검수표 판정 {n_verdict}곳 반영(기관 {n_org}곳 뺌)")
    print(f"저장: {OUT}")


def apply_only():
    data = apiutil.read_json(OUT)
    places, n_verdict, n_org = apply_overrides(data["places"])
    number_places(places)
    data["places"] = places
    save_places(data)
    n_cong = 0
    n_fran = 0
    for p in places:
        if p["is_conglomerate"]:
            n_cong += 1
        elif p["is_franchise"]:
            n_fran += 1
    print(f"{len(places)}곳 (검수표 판정 {n_verdict}곳 반영, 기관 {n_org}곳 뺌, 대기업 {n_cong}곳, 대형체인 {n_fran}곳)")


if __name__ == "__main__":
    if "--apply-only" in sys.argv:
        apply_only()
    else:
        build()
