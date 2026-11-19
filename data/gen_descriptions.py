# Gemini로 관광공사 장소 설명문(한국어·영어) 생성
#
# 버전 기록
# v0.1 (2026-11-19) 관광공사 개요(overview)를 바탕으로 한·영 2문장 설명문 생성, data/descriptions.json에 캐시
# v0.2 (2026-11-19) 기본 모델을 gemini-3.8-flash로 변경 (2.5-flash는 새 사용자에게 막힘)
# v0.3 (2026-11-19) 응답 대기 60초 → 180초, 시간 초과·연결 오류는 최대 3번 다시 시도하고 그래도 안 되면 그 장소만 건너뜀
#
# 실행 (프로젝트 루트에서, .env에 GEMINI_API_KEY 필요):
#   python data/collect_tour.py --detail       # 먼저: 장소별 개요 수집 (data/raw/tour_overview.json)
#   python data/gen_descriptions.py --limit 3  # 시험: 3곳만 만들고 화면에 보여 줌
#   python data/gen_descriptions.py            # 전체 (이미 만든 곳은 건너뜀, 무료 한도 때문에 천천히 진행)
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
아래 [개요]는 한국관광공사가 쓴 장소 소개다. 이 개요에 있는 사실만 써서 관광객용 짧은 설명을 만들어라.
- 한국어 1~2문장(80자 안팎), 영어 1~2문장(25단어 안팎)
- 개요에 없는 사실(연도, 숫자, 메뉴, 가격, 영업시간 등)은 절대 덧붙이지 말 것
- 광고 문구처럼 과장하지 말 것
- JSON으로만 답할 것: {{"ko": "...", "en": "..."}}

[장소 이름] {name}
[영문 이름] {name_en}
[카테고리] {cats}
[개요] {overview}"""


def clean(text):
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()[:1500]


def generate(key, model, p, overview):
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(
            name=p["name"], name_en=p.get("name_en") or "-", cats=", ".join(p["categories"]),
            overview=overview)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    req = urllib.request.Request(
        API.format(model=model), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                data = json.loads(res.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            out = json.loads(text)
            if out.get("ko") and out.get("en"):
                return {"ko": out["ko"].strip(), "en": out["en"].strip()}
            return None
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code == 429 and attempt < 2:  # 분당 한도 → 잠시 쉬고 다시
                time.sleep(30)
                continue
            sys.exit(f"HTTP {e.code} 오류: {msg[:500]}")
        except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
            # 응답이 늦거나 연결이 끊기면 잠시 쉬고 다시 시도
            print(f"  ({p['name']}: {type(e).__name__}, {attempt + 1}번째 실패 → 다시 시도)")
            time.sleep(10)
            continue
        except (KeyError, IndexError, json.JSONDecodeError):
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit(".env 파일에 GEMINI_API_KEY=... 를 넣어 주세요.")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
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

    done = 0
    for p in places:
        cid = p.get("source_id")
        if cid in out or done >= args.limit:
            continue
        overview = clean(overviews.get(cid))
        if len(overview) < 20:
            continue  # 개요가 없으면 만들지 않는다
        print(f"- {p['name']} 생성 중…", flush=True)
        d = generate(key, model, p, overview)
        if d:
            out[cid] = d
            done += 1
            if args.limit <= 5:
                print(f"\n[{p['name']}]\n  ko: {d['ko']}\n  en: {d['en']}")
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        time.sleep(4.5)  # 무료 티어 분당 요청 한도 안에서
    print(f"\n이번에 {done}곳 생성, 전체 {len(out)}곳 → {OUT}")


if __name__ == "__main__":
    main()
