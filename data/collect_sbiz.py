# 소상공인시장진흥공단 상가(상권)정보 API로 대전 중구 점포 목록 수집 (초안)
#
# 버전 기록
# v0.1 (2026-11-18) 대전 중구 점포 목록 수집 초안 작성 (인증키 발급 후 실제 호출로 확인 필요)
#
# 실행: DATA_GO_KR_KEY=발급받은_일반인증키 python data/collect_sbiz.py
# 결과: data/raw/sbiz_daejeon_junggu.json (원본 데이터는 .gitignore로 저장소에 올리지 않음)
#
# 주의: 엔드포인트·파라미터·응답 구조는 공공데이터포털 문서 기준으로 작성했고 아직 실제로 호출해 보지 않았다.
#      키를 받으면 먼저 numOfRows=10으로 한 번 돌려서 응답 모양을 확인할 것.

import json
import os
import sys
import urllib.parse
import urllib.request

ENDPOINT = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
SIGNGU_CD_DAEJEON_JUNGGU = "30140"  # 대전광역시 중구 시군구 코드
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "sbiz_daejeon_junggu.json")


def fetch_page(key, page, rows=1000):
    params = {
        "serviceKey": key,
        "divId": "signguCd",
        "key": SIGNGU_CD_DAEJEON_JUNGGU,
        "numOfRows": rows,
        "pageNo": page,
        "type": "json",
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def simplify(item):
    """앱에서 쓰는 필드만 남긴다."""
    return {
        "source_id": item.get("bizesId"),
        "name": item.get("bizesNm"),
        "branch": item.get("brchNm"),
        "category_large": item.get("indsLclsNm"),
        "category_mid": item.get("indsMclsNm"),
        "category_small": item.get("indsSclsNm"),
        "address": item.get("rdnmAdr"),
        "lat": float(item["lat"]) if item.get("lat") else None,
        "lng": float(item["lon"]) if item.get("lon") else None,
    }


def main():
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        sys.exit("환경 변수 DATA_GO_KR_KEY에 공공데이터포털 일반 인증키를 넣어 주세요.")

    items, page = [], 1
    while True:
        data = fetch_page(key, page)
        body = data.get("body") or {}
        batch = body.get("items") or []
        items.extend(simplify(i) for i in batch)
        total = int(body.get("totalCount") or 0)
        print(f"{page}쪽: {len(batch)}건 (누적 {len(items)} / 전체 {total})")
        if not batch or len(items) >= total:
            break
        page += 1

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
