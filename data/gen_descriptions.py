# Gemini로 관광공사 장소 설명문(한국어·영어) 생성
#
# 버전 기록
# v0.1 (2026-11-19) 관광공사 개요(overview)를 바탕으로 한·영 2문장 설명문 생성, data/descriptions.json에 캐시
# v0.2 (2026-11-19) 기본 모델을 gemini-3.8-flash로 변경 (2.5-flash는 새 사용자에게 막힘)
# v0.3 (2026-11-19) 응답 대기 60초 → 180초, 시간 초과·연결 오류는 최대 3번 다시 시도하고 그래도 안 되면 그 장소만 건너뜀
# v0.4 (2026-11-19) 503(모델 혼잡)·500·429는 20·40·60·90초 쉬며 재시도, --list-models로 쓸 수 있는 모델 이름 확인
# v0.5 (2026-11-20) 무료 티어 하루 요청 수(20회) 때문에 한 번에 여러 곳(기본 12곳)씩 묶어 요청 → 107곳을 약 9회로, 하루 한도 초과면 바로 멈춤
#
# 실행 (프로젝트 루트에서, .env에 GEMINI_API_KEY 필요):
#   python data/collect_tour.py --detail       # 먼저: 장소별 개요 수집 (data/raw/tour_overview.json)
#   python data/gen_descriptions.py --limit 3  # 시험: 3곳만 만들고 화면에 보여 줌 (요청 1회)
#   python data/gen_descriptions.py            # 전체 (이미 만든 곳은 건너뜀, 무료 한도 때문에 천천히 진행)
#   python data/gen_descriptions.py --list-models  # 이 키로 쓸 수 있는 Flash 모델 이름 보기
# 결과: data/descriptions.json (저장소에 올림) → build_places.py가 읽어서 places.json에 합침
#
# 원칙: 관광공사 개요에 있는 내용만 요약한다. 개요가 없는 곳은 만들지 않는다 (지어낸 설명 방지).
# 모델은 환경 변수 GEMINI_MODEL로 바꿀 수 있다 (기본 gemini-3.8-flash). 404가 나면 AI Studio에서 쓸 수 있는 Flash 모델 이름을 넣는다.

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apiutil import RAW_DIR, ROOT, load_env  # noqa: E402

PLACES = os.path.join(ROOT, "data", "places.json")
OVERVIEW = os.path.join(RAW_DIR, "tour_overview.json")
OUT = os.path.join(ROOT, "data", "descriptions.json")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """너는 대전 중구 관광 안내 웹사이트의 편집자다.
아래 [장소 목록]의 각 장소에 대해, 한국관광공사가 쓴 [개요]에 있는 사실만 써서 관광객용 짧은 설명을 만들어라.
- 장소마다 한국어 1~2문장(80자 안팎), 영어 1~2문장(25단어 안팎)
- 개요에 없는 사실(연도, 숫자, 메뉴, 가격, 영업시간 등)은 절대 덧붙이지 말 것
- 광고 문구처럼 과장하지 말 것
- 모든 장소를 빠짐없이, 주어진 id 그대로 답할 것
- JSON으로만 답할 것: {{"items": [{{"id": "...", "ko": "...", "en": "..."}}, ...]}}

[장소 목록]
{places}"""

BATCH = 12  # 한 번 요청에 묶을 장소 수 (무료 티어 하루 요청 한도가 작아서)


class DailyQuotaExceeded(Exception):
    pass


def clean(text):
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()[:1200]


def call(key, model, prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    req = urllib.request.Request(
        API.format(model=model), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    waits = [20, 40, 60, 90]
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(req, timeout=240) as res:
                data = json.loads(res.read().decode("utf-8"))
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(pt.get("text", "") for pt in parts if not pt.get("thought"))
            return json.loads(text)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code == 429 and ("per day" in msg or "PerDay" in msg):
                raise DailyQuotaExceeded(msg[:300])
            if e.code in (429, 500, 503) and attempt < len(waits):
                print(f"  (HTTP {e.code}, {waits[attempt]}초 뒤 다시 시도)", flush=True)
                time.sleep(waits[attempt])
                continue
            sys.exit(f"HTTP {e.code} 오류: {msg[:500]}")
        except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
            if attempt >= 2:
                break
            print(f"  ({type(e).__name__}, {attempt + 1}번째 실패 → 다시 시도)", flush=True)
            time.sleep(10)
        except (KeyError, IndexError, json.JSONDecodeError):
            return None
    return None


def generate_batch(key, model, batch):
    """batch: [(place, overview)] → {id: {ko, en}}"""
    lines = []
    for p, overview in batch:
        lines.append(json.dumps({"id": p["source_id"], "name": p["name"], "name_en": p.get("name_en") or "",
                                 "categories": p["categories"], "overview": overview}, ensure_ascii=False))
    data = call(key, model, PROMPT.format(places="\n".join(lines)))
    ids = {p["source_id"] for p, _ in batch}
    out = {}
    for it in (data or {}).get("items", []):
        if it.get("id") in ids and it.get("ko") and it.get("en"):
            out[it["id"]] = {"ko": it["ko"].strip(), "en": it["en"].strip()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000, help="이번에 만들 최대 장소 수")
    ap.add_argument("--batch", type=int, default=BATCH, help="한 번 요청에 묶을 장소 수")
    ap.add_argument("--list-models", action="store_true", help="쓸 수 있는 Flash 모델 이름 보기")
    args = ap.parse_args()

    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit(".env 파일에 GEMINI_API_KEY=... 를 넣어 주세요.")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    if args.list_models:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                     headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=60) as res:
            models = json.loads(res.read().decode("utf-8")).get("models", [])
        for m in models:
            if "flash" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", []):
                print(m["name"].replace("models/", ""))
        return
    print(f"모델: {model}")
    if not os.path.exists(OVERVIEW):
        sys.exit("먼저 python data/collect_tour.py --detail 로 개요를 받아 주세요.")

    with open(PLACES, encoding="utf-8") as f:
        places = [p for p in json.load(f)["places"] if p.get("source") == "tour"]
    with open(OVERVIEW, encoding="utf-8") as f:
        overviews = json.load(f)
    out = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            out = json.load(f)

    todo = []
    for p in places:
        cid = p.get("source_id")
        overview = clean(overviews.get(cid))
        if cid in out or len(overview) < 20:  # 이미 만들었거나 개요가 없으면 건너뜀 (지어낸 설명 방지)
            continue
        todo.append((p, overview))
    todo = todo[:args.limit]
    size = max(1, min(args.batch, args.limit))
    batches = [todo[i:i + size] for i in range(0, len(todo), size)]
    print(f"남은 장소 {len(todo)}곳 → 요청 {len(batches)}회 ({size}곳씩)")

    made = 0
    for n, batch in enumerate(batches, start=1):
        print(f"- {n}/{len(batches)}: {', '.join(p['name'] for p, _ in batch)[:80]}…", flush=True)
        try:
            got = generate_batch(key, model, batch)
        except DailyQuotaExceeded:
            print("\n오늘 무료 요청 한도를 다 썼어요. 지금까지 만든 것은 저장됐고, 내일(한국 시각 오후 5시 이후) 다시 실행하면 이어서 만듭니다.")
            break
        out.update(got)
        made += len(got)
        if args.limit <= 5:
            for p, _ in batch:
                d = got.get(p["source_id"])
                if d:
                    print(f"\n[{p['name']}]\n  ko: {d['ko']}\n  en: {d['en']}")
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        time.sleep(5)
    print(f"\n이번에 {made}곳 생성, 전체 {len(out)}곳 → {OUT}")


if __name__ == "__main__":
    main()
