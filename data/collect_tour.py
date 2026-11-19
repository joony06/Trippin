# 한국관광공사 TourAPI(국문·영문)로 대전 중구 관광 정보 수집
#
# 버전 기록
# v0.1 (2026-11-18) 국문 KorService2·영문 EngService2 지역기반 목록 수집, --probe(응답 구조 확인) 작성
# v0.2 (2026-11-19) --detail: 국문 장소별 공통정보(detailCommon2)의 개요(overview) 수집 → 설명문 생성 재료
#
# 실행 (프로젝트 루트에서):
#   python data/collect_tour.py --probe   # 국문·영문 2건씩 원본 저장 → data/raw/tour_probe_kor.json, tour_probe_eng.json
#   python data/collect_tour.py           # 전체 수집 → data/raw/tour_kor.json, tour_eng.json
#   python data/collect_tour.py --detail  # 국문 장소별 개요 → data/raw/tour_overview.json (tour_kor.json 먼저 필요)
#
# 매뉴얼(v4.4) 기준: 지역은 법정동 코드 lDongRegnCd(시도) + lDongSignguCd(시군구)로 거른다.
#   대전광역시 = 30, 중구 = 140
# 영문 서비스는 아직 실제로 호출해 보지 않았다. --probe 결과로 파라미터가 맞는지 먼저 확인할 것.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apiutil import data_go_kr_key, get_json, save_json  # noqa: E402

SERVICES = {
    "kor": "https://apis.data.go.kr/B551011/KorService2/areaBasedList2",
    "eng": "https://apis.data.go.kr/B551011/EngService2/areaBasedList2",
}
REGION = {"lDongRegnCd": "30", "lDongSignguCd": "140"}  # 대전 중구

# 국문 콘텐츠 타입: 12 관광지, 14 문화시설, 15 축제·공연·행사, 28 레포츠, 38 쇼핑, 39 음식점
# (영문은 코드가 다르다: 76 관광지, 78 문화시설, 85 축제, 75 레포츠, 79 쇼핑, 82 음식점)
CONTENT_TYPES = {"kor": ["12", "14", "28", "38", "39"], "eng": ["76", "78", "75", "79", "82"]}


def fetch(key, lang, content_type, page, rows):
    return get_json(SERVICES[lang], {
        "serviceKey": key,
        "numOfRows": rows,
        "pageNo": page,
        "MobileOS": "ETC",
        "MobileApp": "Trippin",
        "_type": "json",
        "arrange": "C",
        "contentTypeId": content_type,
        **REGION,
    })


def items_of(data):
    body = (data.get("response") or {}).get("body") or {}
    items = (body.get("items") or {})
    items = items.get("item", []) if isinstance(items, dict) else []
    return items if isinstance(items, list) else [items], int(body.get("totalCount") or 0)


def simplify(item, lang):
    return {
        "content_id": item.get("contentid"),
        "content_type": item.get("contenttypeid"),
        "lang": lang,
        "title": item.get("title"),
        "address": " ".join(x for x in [item.get("addr1"), item.get("addr2")] if x),
        "lat": float(item["mapy"]) if item.get("mapy") else None,
        "lng": float(item["mapx"]) if item.get("mapx") else None,
        "image": item.get("firstimage") or None,
        "category_code": item.get("lclsSystm3") or item.get("cat3"),
    }


DETAIL_ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"


def collect_overviews(key):
    """장소별 개요(관광공사가 쓴 소개글)를 받는다. 이미 받은 곳은 건너뛴다."""
    import json
    import time
    from apiutil import RAW_DIR
    with open(os.path.join(RAW_DIR, "tour_kor.json"), encoding="utf-8") as f:
        places = json.load(f)
    path = os.path.join(RAW_DIR, "tour_overview.json")
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            out = json.load(f)
    for i, p in enumerate(places, start=1):
        cid = p.get("content_id")
        if not cid or cid in out:
            continue
        data = get_json(DETAIL_ENDPOINT, {
            "serviceKey": key, "MobileOS": "ETC", "MobileApp": "Trippin", "_type": "json",
            "contentId": cid, "numOfRows": 1, "pageNo": 1,
        })
        items, _ = items_of(data)
        out[cid] = (items[0].get("overview") or "") if items else ""
        if i % 20 == 0:
            print(f"  {i}/{len(places)}")
        time.sleep(0.1)
    save_json("tour_overview.json", out)
    print(f"개요 {sum(1 for v in out.values() if v)}곳 / {len(out)}곳")


def main():
    key = data_go_kr_key()

    if "--detail" in sys.argv:
        collect_overviews(key)
        return

    if "--probe" in sys.argv:
        for lang in SERVICES:
            save_json(f"tour_probe_{lang}.json", fetch(key, lang, CONTENT_TYPES[lang][0], 1, 2))
        return

    for lang in SERVICES:
        out = []
        for ct in CONTENT_TYPES[lang]:
            page = 1
            while True:
                items, total = items_of(fetch(key, lang, ct, page, 100))
                out.extend(simplify(i, lang) for i in items)
                print(f"[{lang}] 타입 {ct} {page}쪽: {len(items)}건 (전체 {total})")
                if not items or page * 100 >= total:
                    break
                page += 1
        save_json(f"tour_{lang}.json", out)


if __name__ == "__main__":
    main()
