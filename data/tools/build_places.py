# 수집한 원본(상가정보·TourAPI·구글·Gemini 소개문)을 앱의 장소 데이터(data/places.json)로 합친다
#
# 버전 기록
# v0.1 (2026-11-18) 관광 업종 선별, 카테고리 변환, TourAPI·상가정보 중복 제거, 영문 이름 짝짓기, 대기업 계열 표시
# v0.2 (2026-11-18) 대형 프랜차이즈 표시: 대전 전체에서 지점명이 붙은 같은 상호가 FRANCHISE_MIN_STORES곳 이상이면 is_franchise
# v0.3 (2026-11-18) 관광객이 갈 수 없는 곳 제외: 구내식당 업종, 상호에 기관·단체 단어(상조회·협의회 등)가 든 곳
# v0.4 (2026-11-18) 빵/도넛·떡/한과·아이스크림/빙수는 카테고리를 [카페, 음식]으로
# v0.5 (2026-11-19) Gemini 소개문(data/descriptions.json)과 구글 평점·리뷰 수·영업시간(data/raw/google_raw.json) 합치기
# v0.6 (2026-11-19) 구글 매칭은 collect_google.best_match로 여기서 판정
# v0.7 (2026-11-21) 검수표 반영: 가게별 판정(store_verdicts.json)을 덮어씀, 대형체인 브랜드 목록(chain_brands.txt), 브랜드 철자 맞춤,
#                   관광지 이름으로 역사·자연·야경 카테고리 보강, 요금은 모르는 값이라 None. 이미 만든 places.json에만 적용: --apply-only
# v0.8 (2026-11-21) 영문 이름 위치 짝짓기 수정: 이름으로 이미 짝지어진 영문 이름은 근처 다른 장소에 붙이지 않음
# v0.9 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, 정규식 대신 글자 단위 반복 함수(괄호 지우기·동 이름 찾기 등),
#                   장소 하나 만들기를 함수로 분리. 같은 원본으로 만든 places.json이 v0.8과 한 글자도 다르지 않음을 확인
#
# 실행 (프로젝트 폴더에서, collect_sbiz.py·collect_tour.py를 먼저 실행):
#   python data/tools/build_places.py               # 원본(data/raw)으로 전부 다시 만들기
#   python data/tools/build_places.py --apply-only  # 원본 없이, 이미 있는 places.json에 브랜드·검수표 판정만 다시 적용
# 결과: data/places.json  (앱은 처음 실행할 때 이 파일을 DB에 넣는다. 다시 넣으려면 trippin.db를 지우고 실행)

import json
import math
import os
import sys

import apiutil
from collect_google import best_match  # 구글 매칭 기준은 collect_google.py 한 곳에서 관리

RAW = apiutil.RAW_DIR
OUT = os.path.join(apiutil.DATA_DIR, "places.json")
BRANDS = os.path.join(apiutil.DATA_DIR, "conglomerate_brands.txt")  # 대기업 집단 브랜드
CHAINS = os.path.join(apiutil.DATA_DIR, "chain_brands.txt")          # 대형 체인 브랜드 (대기업 집단은 아님)
VERDICTS = os.path.join(apiutil.DATA_DIR, "store_verdicts.json")    # 검수표 가게별 판정
DESCRIPTIONS = os.path.join(apiutil.DATA_DIR, "descriptions.json")   # gen_descriptions.py 결과
GOOGLE = os.path.join(RAW, "google_raw.json")                       # collect_google.py 결과

# 대형 프랜차이즈 기준: 대전 전체에서 '지점명이 있는 같은 상호'가 이 수 이상이면 대형 프랜차이즈
# (전국 가맹점 수 API는 가명정보 승인 절차가 필요해서, 대전 상가정보로 대신 센다)
FRANCHISE_MIN_STORES = 10

# ---------------------------------------------------------------- 상가정보: 관광객 대상 업종만

# (대분류, 중분류) → 앱 카테고리. 목록에 없는 업종(미용실·부동산·학원·주점 등)은 뺀다.
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
# 음식 업종이지만 관광객이 갈 수 없는 곳 (소분류 이름)
EXCLUDE_SMALL_CATEGORIES = {"구내식당", "기타 구내식당", "출장 음식 서비스", "단체 급식"}
# 상호에 이런 단어가 있으면 가게가 아니라 기관·단체로 보고 뺀다 (예: 중구청직원상조회)
EXCLUDE_NAME_WORDS = ["상조회", "협의회", "협회", "위원회", "조합", "재단", "공단", "구청", "시청",
                      "주민센터", "복지관", "어린이집", "유치원", "학교", "교회", "성당", "경로당",
                      "노인회", "부녀회", "직원", "급식", "기숙사"]

# ---------------------------------------------------------------- TourAPI: 콘텐츠 타입·분류 → 앱 카테고리

TOUR_TYPE_CATEGORY = {
    "12": ["사진명소"],   # 관광지 (아래 분류로 앞에 더 구체적인 카테고리를 붙인다)
    "14": ["문화"],       # 문화시설
    "28": ["액티비티"],   # 레포츠
    "38": ["쇼핑"],       # 쇼핑
    "39": ["음식"],       # 음식점
}
TOUR_LCLS_CATEGORY = {   # 신분류체계 대분류 앞 두 글자
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
# 관광지 이름에 이 단어가 있으면 카테고리를 붙인다 (TourAPI 분류만으로는 역사 8곳·자연 3곳·야경 0곳이라)
TOUR_NAME_CATEGORY = [
    ("역사", ["기념관", "전시관", "사당", "생가", "서원", "향교", "종가", "마애", "숭절사", "유적", "고택"]),
    ("자연", ["공원", "숲", "산", "둘레길", "수목원", "계곡"]),
    ("야경", ["전망대", "스카이로드", "으능정이", "볼파크"]),
]
DUPLICATE_KM = 0.1      # 상가정보와 관광공사 장소가 이름이 겹치고 이 거리 안이면 같은 곳
ENGLISH_NEAR_KM = 0.05  # 영문 이름을 위치로 짝지을 때 거리 한도


# ---------------------------------------------------------------- 글자 다루기 (정규식 대신 반복문)

def is_hangul(ch):
    return "가" <= ch <= "힣"


def remove_parens(s):
    """'(…)' 부분을 모두 지운다. 닫는 괄호가 없으면 그대로 둔다. '빵집(대흥점)' → '빵집'"""
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
    """영문 제목 끝의 '(…)'를 지운다. 'Ppuri Park (뿌리공원)' → 'Ppuri Park'"""
    body = title.rstrip()
    first = body.find("(")
    if body.endswith(")") and first != -1 and first < len(body) - 1:
        return body[:first].strip()
    return title.strip()


def hangul_in_parens(title):
    """'(…)' 안에 한글이 있으면 그 내용. 'Ppuri Park (뿌리공원)' → '뿌리공원'. 없으면 None"""
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
    """주소에서 동 이름(두 글자 이상) 찾기. 먼저 '(대흥동)'처럼 괄호 안, 없으면 '대흥동 ' 처럼 띄어쓰기 앞. 없으면 None"""
    addr = addr or ""
    # 1) 괄호 안 전체가 한글·숫자이고 '동'으로 끝나는 것
    i = addr.find("(")
    while i != -1:
        j = i + 1
        while j < len(addr) and is_dong_char(addr[j]):
            j += 1
        word = addr[i + 1:j]
        if len(word) >= 2 and word.endswith("동") and j < len(addr) and addr[j] == ")":
            return word
        i = addr.find("(", i + 1)
    # 2) 한글·숫자 덩어리가 '동'으로 끝나고 바로 뒤가 띄어쓰기인 것 (앞에서부터 첫 번째)
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
    """비교용 이름: 괄호 내용·띄어쓰기·'본점' 제거, 브랜드 철자 맞춤, 소문자"""
    s = "".join(remove_parens(s or "").split())
    for wrong in BRAND_SPELLING:
        s = s.replace(wrong, BRAND_SPELLING[wrong])
    return s.replace("본점", "").lower()


def km(a, b):
    """두 (위도, 경도) 사이 거리(km)"""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------- 대기업·대형 프랜차이즈 판정

def load_brands(path):
    """브랜드 목록 파일(한 줄에 하나, #은 주석)을 읽는다."""
    if not os.path.exists(path):
        return []
    brands = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                brands.append(line.strip())
    return brands


def is_conglomerate(name, brands):
    n = norm_name(name)
    for b in brands:
        if norm_name(b) in n:
            return True
    return False


def franchise_brands():
    """대전 전체 상가정보에서 지점명이 붙은 상호의 매장 수를 세어, 기준 이상인 것만 {정규화된 상호: 매장 수}"""
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
    """상호가 대형 프랜차이즈 브랜드와 같거나, 브랜드 이름으로 시작하면 (예: '올리브영 대전대흥점')"""
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


# ---------------------------------------------------------------- 카테고리·검수표

def tour_categories(name, cats):
    """관광지(음식·쇼핑 제외) 이름으로 역사·자연·야경을 붙인다. 순서: 역사 → 자연 → 기존 → 야경"""
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
    back = ["야경"] if "야경" in hit and "야경" not in cats else []
    return front + middle + back


def apply_overrides(places):
    """브랜드 목록·검수표 판정·카테고리 보강·요금을 적용한다. 기관으로 판정된 곳은 뺀다.
    돌려주는 값: (남은 곳, 판정 반영 수, 기관 제외 수)"""
    brands = load_brands(BRANDS)
    chains = load_brands(CHAINS)
    verdicts = apiutil.read_json(VERDICTS, {}).get("verdicts", {})
    out = []
    n_verdict = 0
    n_org = 0
    for p in places:
        p["is_conglomerate"] = is_conglomerate(p["name"], brands)
        p["is_franchise"] = bool(p.get("is_franchise")) or is_chain(p["name"], chains)
        p["fee"] = None  # 요금은 수집하지 않았다 (0원으로 두면 '무료'로 잘못 보임)
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
    """Gemini 소개문과 구글 평점·리뷰 수·영업시간을 합친다. 파일이 없으면 건너뛴다. (소개문 수, 구글 매칭 수)"""
    descs = apiutil.read_json(DESCRIPTIONS, {})
    google = apiutil.read_json(GOOGLE, {})
    n_desc = 0
    n_google = 0
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


# ---------------------------------------------------------------- 영문 이름 짝짓기

def english_titles(tour_eng):
    """영문 제목 'Ppuri Park (뿌리공원)' → {정규화한 한국어 이름: 'Ppuri Park'}"""
    by_name = {}
    for e in tour_eng:
        korean = hangul_in_parens(e.get("title") or "")
        if korean is not None:
            by_name[norm_name(korean)] = remove_trailing_parens(e["title"])
    return by_name


def english_name(k, tour_eng, by_name, claimed):
    """국문 장소 k의 영문 이름: 괄호 안 한국어 이름으로 찾고, 없으면 50m 안 가장 가까운 영문 장소.
    다른 장소가 이름으로 이미 가져간 영문 이름은 위치로 붙이지 않는다 (같은 건물의 다른 가게에 붙던 문제)."""
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
    return best[1] if best else None


# ---------------------------------------------------------------- 장소 만들기

def tour_place(k, name_en, brands, big):
    """관광공사 국문 항목 → 장소"""
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
    """상가정보 항목 → 장소"""
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
    """구내식당 업종이거나 상호에 기관·단체 단어가 있으면 True"""
    if small in EXCLUDE_SMALL_CATEGORIES:
        return True
    for w in EXCLUDE_NAME_WORDS:
        if w in (s.get("name") or ""):
            return True
    return False


def overlaps_tour(s, tour_points):
    """관광공사 장소와 이름이 겹치고 100m 안이면 같은 곳으로 본다"""
    n = norm_name(s["name"])
    for tn, tp in tour_points:
        if (n in tn or tn in n) and km((s["lat"], s["lng"]), tp) < DUPLICATE_KM:
            return True
    return False


def save_places(data):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def number_places(places):
    """장소 번호를 1부터 차례로 붙인다"""
    for i, p in enumerate(places, start=1):
        p["id"] = i


def build():
    brands = load_brands(BRANDS)
    big = franchise_brands()
    tour_kor = apiutil.read_json(os.path.join(RAW, "tour_kor.json"))
    tour_eng = apiutil.read_json(os.path.join(RAW, "tour_eng.json"))
    sbiz = apiutil.read_json(os.path.join(RAW, "sbiz_daejeon_junggu.json"))

    by_name = english_titles(tour_eng)
    claimed = set()  # 이름으로 짝지어진 영문 이름
    for k in tour_kor:
        if norm_name(k["title"]) in by_name:
            claimed.add(by_name[norm_name(k["title"])])

    # 1) TourAPI 국문: 관광공사에 등록된 곳은 모두 넣는다
    places = []
    for k in tour_kor:
        if k.get("lat"):
            places.append(tour_place(k, english_name(k, tour_eng, by_name, claimed), brands, big))

    tour_points = []
    for p in places:
        tour_points.append((norm_name(p["name"]), (p["lat"], p["lng"])))

    # 2) 상가정보: 관광객 대상 업종만, 기관·구내식당과 관광공사 장소와 겹치는 곳은 뺀다
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

    # 3) 검수표·브랜드 판정 → 번호 → 소개문·구글 데이터
    places, n_verdict, n_org = apply_overrides(places)
    number_places(places)
    n_desc, n_google = merge_extras(places)

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
    print(f"설명문 {n_desc}곳, 구글 평점·영업시간 {n_google}곳 합침, 검수표 판정 {n_verdict}곳 반영(기관 {n_org}곳 뺌)")
    print(f"저장: {OUT}")


def apply_only():
    """원본(raw) 없이, 이미 있는 places.json에 브랜드·판정·카테고리·요금만 다시 적용한다."""
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
