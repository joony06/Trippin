# 소상공인시장진흥공단 상가(상권)정보 API로 대전 중구 점포 목록 수집
#
# 버전 기록
# v0.1 (2026-11-18) 대전 중구 점포 목록 수집 초안 작성 (인증키 발급 후 실제 호출로 확인 필요)
# v0.2 (2026-11-18) 인증키를 .env에서 읽도록 변경, 공통 도구(apiutil) 사용, --probe(응답 구조 확인) 추가
# v0.3 (2026-11-18) --daejeon: 대전 전체 점포 수집 (대형 프랜차이즈 판정용 브랜드 매장 수 계산에 사용)
#
# 실행 (프로젝트 루트에서):
#   python data/collect_sbiz.py --probe   # 3건만 받아 data/raw/sbiz_probe.json 에 원본 저장 → 구조 확인
#   python data/collect_sbiz.py           # 전체 수집 → data/raw/sbiz_daejeon_junggu.json
#   python data/collect_sbiz.py --daejeon # 대전 전체 수집 → data/raw/sbiz_daejeon_all.json (몇 분 걸림)
#
# 문서: https://apis.data.go.kr/B553077/api/open/sdsc2 (storeListInDong: 행정구역 단위 상가업소 조회)

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apiutil import data_go_kr_key, get_json, save_json  # noqa: E402

ENDPOINT = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
SIGNGU_CD_DAEJEON_JUNGGU = "30140"  # 대전광역시 중구 시군구 코드
CTPRVN_CD_DAEJEON = "30"            # 대전광역시 시도 코드


def fetch_page(key, page, rows, div_id="signguCd", area=SIGNGU_CD_DAEJEON_JUNGGU):
    return get_json(ENDPOINT, {
        "serviceKey": key,
        "divId": div_id,
        "key": area,
        "numOfRows": rows,
        "pageNo": page,
        "type": "json",
    })


def simplify(item):
    """앱에서 쓰는 필드만 남긴다."""
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


def main():
    key = data_go_kr_key()

    if "--probe" in sys.argv:
        save_json("sbiz_probe.json", fetch_page(key, 1, 3))
        return

    whole = "--daejeon" in sys.argv
    div_id, area = ("ctprvnCd", CTPRVN_CD_DAEJEON) if whole else ("signguCd", SIGNGU_CD_DAEJEON_JUNGGU)
    items, page = [], 1
    while True:
        data = fetch_page(key, page, 1000, div_id, area)
        body = data.get("body") or {}
        batch = body.get("items") or []
        if whole:  # 매장 수 계산에 필요한 값만 남겨 파일 크기를 줄인다
            items.extend({"name": i.get("bizesNm"), "branch": i.get("brchNm"),
                          "category_large": i.get("indsLclsNm")} for i in batch)
        else:
            items.extend(simplify(i) for i in batch)
        total = int(body.get("totalCount") or 0)
        print(f"{page}쪽: {len(batch)}건 (누적 {len(items)} / 전체 {total})")
        if not batch or len(items) >= total:
            break
        page += 1
    save_json("sbiz_daejeon_all.json" if whole else "sbiz_daejeon_junggu.json", items)


if __name__ == "__main__":
    main()
