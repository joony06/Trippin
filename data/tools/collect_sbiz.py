# 소상공인시장진흥공단 상가(상권)정보 API로 대전 중구 점포 목록 수집
#
# 버전 기록
# v0.1 (2026-11-18) 대전 중구 점포 목록 수집 초안 작성
# v0.2 (2026-11-18) 인증키를 .env에서 읽도록 변경, 공통 도구(apiutil) 사용, --probe(응답 구조 확인) 추가
# v0.3 (2026-11-18) --daejeon: 대전 전체 점포 수집 (대형 프랜차이즈 판정용 브랜드 매장 수 계산에 사용)
# v0.4 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, 대전 전체용 축약 함수 분리. 받는 값은 같다
#
# 실행 (프로젝트 폴더에서, .env에 DATA_GO_KR_KEY 필요):
#   python data/tools/collect_sbiz.py --probe   # 3건만 받아 data/raw/sbiz_probe.json 에 원본 저장 → 구조 확인
#   python data/tools/collect_sbiz.py           # 대전 중구 → data/raw/sbiz_daejeon_junggu.json
#   python data/tools/collect_sbiz.py --daejeon # 대전 전체 → data/raw/sbiz_daejeon_all.json (몇 분 걸림)
#
# 문서: https://apis.data.go.kr/B553077/api/open/sdsc2 (storeListInDong: 행정구역 단위 상가업소 조회)

import sys

import apiutil

ENDPOINT = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
SIGNGU_CD_DAEJEON_JUNGGU = "30140"  # 대전광역시 중구 시군구 코드
CTPRVN_CD_DAEJEON = "30"            # 대전광역시 시도 코드
ROWS_PER_PAGE = 1000


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
    """대전 중구 점포: 앱에서 쓰는 값만 남긴다."""
    return {
        "source_id": item.get("bizesId"),
        "name": item.get("bizesNm"),
        "branch": item.get("brchNm"),
        "category_large": item.get("indsLclsNm"),
        "category_mid": item.get("indsMclsNm"),
        "category_small": item.get("indsSclsNm"),
        "dong": item.get("ldongNm") or item.get("adongNm"),
        "address": item.get("rdnmAdr") or item.get("lnoAdr"),
        "lat": float(item["lat"]) if item.get("lat") else None,
        "lng": float(item["lon"]) if item.get("lon") else None,
    }


def simplify_for_count(item):
    """대전 전체 점포: 브랜드 매장 수 계산에 필요한 값만 (파일 크기를 줄인다)"""
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
            items.append(simplify_for_count(i) if whole else simplify(i))
        total = int(body.get("totalCount") or 0)
        print(f"{page}쪽: {len(batch)}건 (누적 {len(items)} / 전체 {total})")
        if not batch or len(items) >= total:
            break
        page += 1
    apiutil.save_json("sbiz_daejeon_all.json" if whole else "sbiz_daejeon_junggu.json", items)


if __name__ == "__main__":
    main()
