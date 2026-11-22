# TourAPI(국문·영문)로 대전 중구 관광 정보 수집
#
# 버전 기록
# v0.1 국문·영문 목록 수집, --probe
#
# 실행: python data/tools/collect_tour.py [--probe]  (.env에 DATA_GO_KR_KEY)

import os
import sys
import time

import apiutil

SERVICES = {
    "kor": "https://apis.data.go.kr/B551011/KorService2/areaBasedList2",
    "eng": "https://apis.data.go.kr/B551011/EngService2/areaBasedList2",
}
REGION = {"lDongRegnCd": "30", "lDongSignguCd": "140"}  # 대전 중구

# 국문 12 관광지·14 문화·28 레포츠·38 쇼핑·39 음식 (영문은 코드가 다름)
CONTENT_TYPES = {"kor": ["12", "14", "28", "38", "39"], "eng": ["76", "78", "75", "79", "82"]}
ROWS_PER_PAGE = 100


def number_or_none(value):
    if value:
        return float(value)
    return None


def fetch(key, lang, content_type, page, rows):
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
        "lat": number_or_none(item.get("mapy")),
        "lng": number_or_none(item.get("mapx")),
        "image": item.get("firstimage") or None,
        "category_code": item.get("lclsSystm3") or item.get("cat3"),
    }


def collect_type(key, lang, content_type):
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


def main():
    key = apiutil.data_go_kr_key()

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
