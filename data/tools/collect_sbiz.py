# 상가(상권)정보 API로 대전 중구 점포 수집
#
# 버전 기록
# v0.1 초안
# v0.2 .env 인증키, --probe
# v0.3 --daejeon (대전 전체)
#
# 실행: python data/tools/collect_sbiz.py [--probe | --daejeon]  (.env에 DATA_GO_KR_KEY)

import sys

import apiutil

ENDPOINT = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
SIGNGU_CD_DAEJEON_JUNGGU = "30140"  # 대전광역시 중구 시군구 코드
CTPRVN_CD_DAEJEON = "30"            # 대전광역시 시도 코드
ROWS_PER_PAGE = 1000


def number_or_none(value):
    if value:
        return float(value)
    return None


def fetch_page(key, page, rows, div_id="signguCd", area=SIGNGU_CD_DAEJEON_JUNGGU):
    return apiutil.get_json(ENDPOINT, {
        "serviceKey": key,
        "divId": div_id,
        "key": area,
        "numOfRows": rows,
        "pageNo": page,
        "type": "json",
    })


def simplify(item):
    return {
        "source_id": item.get("bizesId"),
        "name": item.get("bizesNm"),
        "branch": item.get("brchNm"),
        "category_large": item.get("indsLclsNm"),
        "category_mid": item.get("indsMclsNm"),
        "category_small": item.get("indsSclsNm"),
        "dong": item.get("ldongNm") or item.get("adongNm"),
        "address": item.get("rdnmAdr") or item.get("lnoAdr"),
        "lat": number_or_none(item.get("lat")),
        "lng": number_or_none(item.get("lon")),
    }


def simplify_for_count(item):
    return {"name": item.get("bizesNm"), "branch": item.get("brchNm"), "category_large": item.get("indsLclsNm")}


def main():
    key = apiutil.data_go_kr_key()

    if "--probe" in sys.argv:
        apiutil.save_json("sbiz_probe.json", fetch_page(key, 1, 3))
        return

    whole = "--daejeon" in sys.argv
    if whole:
        div_id, area = "ctprvnCd", CTPRVN_CD_DAEJEON
    else:
        div_id, area = "signguCd", SIGNGU_CD_DAEJEON_JUNGGU

    items = []
    page = 1
    while True:
        body = fetch_page(key, page, ROWS_PER_PAGE, div_id, area).get("body") or {}
        batch = body.get("items") or []
        for i in batch:
            if whole:
                items.append(simplify_for_count(i))
            else:
                items.append(simplify(i))
        total = int(body.get("totalCount") or 0)
        print(f"{page}쪽: {len(batch)}건 (누적 {len(items)} / 전체 {total})")
        if not batch or len(items) >= total:
            break
        page += 1
    if whole:
        apiutil.save_json("sbiz_daejeon_all.json", items)
    else:
        apiutil.save_json("sbiz_daejeon_junggu.json", items)


if __name__ == "__main__":
    main()
