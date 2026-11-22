# 한국관광공사 TourAPI(국문·영문)로 대전 중구 관광 정보 수집
#
# 버전 기록
# v0.1 (2026-11-18) 국문 KorService2·영문 EngService2 지역기반 목록 수집, --probe(응답 구조 확인) 작성
# v0.2 (2026-11-19) --detail: 국문 장소별 공통정보(detailCommon2)의 개요(overview) 수집 → 설명문 생성 재료
# v0.3 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, 쪽(page) 반복을 while 문 함수로 분리. 받는 값은 같다
#
# 실행 (프로젝트 폴더에서, .env에 DATA_GO_KR_KEY 필요):
#   python data/tools/collect_tour.py --probe   # 국문·영문 2건씩 원본 저장 → data/raw/tour_probe_kor.json, tour_probe_eng.json
#   python data/tools/collect_tour.py           # 전체 수집 → data/raw/tour_kor.json, tour_eng.json
#   python data/tools/collect_tour.py --detail  # 국문 장소별 개요 → data/raw/tour_overview.json (tour_kor.json 먼저 필요)
#
# 매뉴얼(v4.4) 기준: 지역은 법정동 코드 lDongRegnCd(시도) + lDongSignguCd(시군구)로 거른다. 대전광역시 = 30, 중구 = 140

import os
import sys
import time

import apiutil

SERVICES = {
    "kor": "https://apis.data.go.kr/B551011/KorService2/areaBasedList2",
    "eng": "https://apis.data.go.kr/B551011/EngService2/areaBasedList2",
}
DETAIL_ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
REGION = {"lDongRegnCd": "30", "lDongSignguCd": "140"}  # 대전 중구

# 국문 콘텐츠 타입: 12 관광지, 14 문화시설, 28 레포츠, 38 쇼핑, 39 음식점
# 영문은 코드가 다르다: 76 관광지, 78 문화시설, 75 레포츠, 79 쇼핑, 82 음식점
CONTENT_TYPES = {"kor": ["12", "14", "28", "38", "39"], "eng": ["76", "78", "75", "79", "82"]}
ROWS_PER_PAGE = 100


def fetch(key, lang, content_type, page, rows):
    """목록 한 쪽을 받는다."""
    params = {
        "serviceKey": key,
        "numOfRows": rows,
        "pageNo": page,
        "MobileOS": "ETC",
        "MobileApp": "Trippin",
        "_type": "json",
        "arrange": "C",
        "contentTypeId": content_type,
    }
    params.update(REGION)
    return apiutil.get_json(SERVICES[lang], params)


def items_of(data):
    """응답에서 (항목 목록, 전체 개수)를 꺼낸다. 항목이 하나면 목록이 아니라 딕셔너리로 오므로 목록으로 맞춘다."""
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items") or {}
    if isinstance(items, dict):
        items = items.get("item", [])
    else:
        items = []
    if not isinstance(items, list):
        items = [items]
    return items, int(body.get("totalCount") or 0)


def simplify(item, lang):
    """앱에서 쓰는 값만 남긴다."""
    address_parts = []
    for x in [item.get("addr1"), item.get("addr2")]:
        if x:
            address_parts.append(x)
    return {
        "content_id": item.get("contentid"),
        "content_type": item.get("contenttypeid"),
        "lang": lang,
        "title": item.get("title"),
        "address": " ".join(address_parts),
        "lat": float(item["mapy"]) if item.get("mapy") else None,
        "lng": float(item["mapx"]) if item.get("mapx") else None,
        "image": item.get("firstimage") or None,
        "category_code": item.get("lclsSystm3") or item.get("cat3"),
    }


def collect_type(key, lang, content_type):
    """한 콘텐츠 타입의 모든 쪽을 차례로 받는다."""
    out = []
    page = 1
    while True:
        items, total = items_of(fetch(key, lang, content_type, page, ROWS_PER_PAGE))
        for i in items:
            out.append(simplify(i, lang))
        print(f"[{lang}] 타입 {content_type} {page}쪽: {len(items)}건 (전체 {total})")
        if not items or page * ROWS_PER_PAGE >= total:
            break
        page += 1
    return out


def collect_overviews(key):
    """장소별 개요(관광공사가 쓴 소개글)를 받는다. 이미 받은 곳은 건너뛴다."""
    places = apiutil.read_json(os.path.join(apiutil.RAW_DIR, "tour_kor.json"))
    out = apiutil.read_json(os.path.join(apiutil.RAW_DIR, "tour_overview.json"), {})
    for i, p in enumerate(places, start=1):
        cid = p.get("content_id")
        if not cid or cid in out:
            continue
        data = apiutil.get_json(DETAIL_ENDPOINT, {
            "serviceKey": key, "MobileOS": "ETC", "MobileApp": "Trippin", "_type": "json",
            "contentId": cid, "numOfRows": 1, "pageNo": 1,
        })
        items, _ = items_of(data)
        out[cid] = (items[0].get("overview") or "") if items else ""
        if i % 20 == 0:
            print(f"  {i}/{len(places)}")
        time.sleep(0.1)  # 너무 빨리 연달아 요청하지 않게
    apiutil.save_json("tour_overview.json", out)
    filled = 0
    for v in out.values():
        if v:
            filled += 1
    print(f"개요 {filled}곳 / {len(out)}곳")


def main():
    key = apiutil.data_go_kr_key()

    if "--detail" in sys.argv:
        collect_overviews(key)
        return

    if "--probe" in sys.argv:
        for lang in SERVICES:
            apiutil.save_json(f"tour_probe_{lang}.json", fetch(key, lang, CONTENT_TYPES[lang][0], 1, 2))
        return

    for lang in SERVICES:
        out = []
        for ct in CONTENT_TYPES[lang]:
            out.extend(collect_type(key, lang, ct))
        apiutil.save_json(f"tour_{lang}.json", out)


if __name__ == "__main__":
    main()
