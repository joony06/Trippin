# Gemini로 관광공사 장소 소개문(한국어·영어) 만들기
#
# 버전 기록
# v0.1 (2026-11-19) 관광공사 개요(overview)를 바탕으로 한·영 2문장 소개문 생성, data/descriptions.json에 저장
# v0.2 (2026-11-19) 기본 모델을 gemini-3.8-flash로 변경 (2.5-flash는 새 사용자에게 막힘)
# v0.3 (2026-11-19) 응답 대기 180초, 시간 초과·연결 오류는 최대 3번 다시 시도하고 그래도 안 되면 그 묶음만 건너뜀
# v0.4 (2026-11-19) 503(모델 혼잡)·500·429는 20·40·60·90초 쉬며 재시도, --list-models로 쓸 수 있는 모델 이름 확인
# v0.5 (2026-11-20) 무료 티어 하루 요청 수(20회) 때문에 여러 곳(기본 12곳)씩 묶어 요청, 하루 한도 초과면 바로 멈춤
# v0.6 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, argparse 대신 sys.argv, 정규식 대신 글자 단위 반복으로 HTML 태그 제거.
#                   하루 한도 초과는 직접 만든 예외(DailyQuotaExceeded, 9주차)로 알림. 요청·저장 내용은 v0.5와 같다
#
# 실행 (프로젝트 폴더에서, .env에 GEMINI_API_KEY 필요):
#   python data/tools/collect_tour.py --detail       # 먼저: 장소별 개요 수집 (data/raw/tour_overview.json)
#   python data/tools/gen_descriptions.py --limit 3  # 시험: 3곳만 만들고 화면에 보여 줌 (요청 1회)
#   python data/tools/gen_descriptions.py            # 전체 (이미 만든 곳은 건너뜀)
#   python data/tools/gen_descriptions.py --batch 6  # 한 번에 묶을 장소 수 (기본 12)
#   python data/tools/gen_descriptions.py --list-models  # 이 키로 쓸 수 있는 Flash 모델 이름 보기
# 결과: data/descriptions.json (저장소에 올림) → build_places.py가 읽어서 places.json에 합침
#
# 원칙: 관광공사 개요에 있는 내용만 요약한다. 개요가 없는 곳은 만들지 않는다 (지어낸 설명 방지).
# 모델은 환경 변수 GEMINI_MODEL로 바꿀 수 있다 (기본 gemini-3.8-flash).

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

import apiutil

PLACES = os.path.join(apiutil.DATA_DIR, "places.json")
OVERVIEW = os.path.join(apiutil.RAW_DIR, "tour_overview.json")
OUT = os.path.join(apiutil.DATA_DIR, "descriptions.json")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_API = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
DEFAULT_MODEL = "gemini-3.8-flash"

PROMPT = """너는 대전 중구 관광 안내 웹사이트의 편집자다.
아래 [장소 목록]의 각 장소에 대해, 한국관광공사가 쓴 [개요]에 있는 사실만 써서 관광객용 짧은 설명을 만들어라.
- 장소마다 한국어 1~2문장(80자 안팎), 영어 1~2문장(25단어 안팎)
- 개요에 없는 사실(연도, 숫자, 메뉴, 가격, 영업시간 등)은 절대 덧붙이지 말 것
- 광고 문구처럼 과장하지 말 것
- 모든 장소를 빠짐없이, 주어진 id 그대로 답할 것
- JSON으로만 답할 것: {{"items": [{{"id": "...", "ko": "...", "en": "..."}}, ...]}}

[장소 목록]
{places}"""

BATCH = 12                    # 한 번 요청에 묶을 장소 수 (무료 티어 하루 요청 한도가 작아서)
RETRY_WAITS = [20, 40, 60, 90]  # 모델 혼잡(503 등)일 때 다시 시도하기 전 쉬는 시간(초)
MAX_OVERVIEW = 1200           # 개요는 앞 1200자만 보낸다
MIN_OVERVIEW = 20             # 개요가 이보다 짧으면 만들지 않는다


class DailyQuotaExceeded(Exception):
    """무료 티어 하루 요청 한도를 다 썼을 때"""


def replace_br(text):
    """줄바꿈 태그 <br>, <br/>, <BR /> 를 띄어쓰기 한 칸으로 바꾼다."""
    out = ""
    i = 0
    while i < len(text):
        if text[i] == "<" and text[i + 1:i + 3].lower() == "br":
            j = i + 3
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] == "/":
                j += 1
            if j < len(text) and text[j] == ">":
                out += " "
                i = j + 1
                continue
        out += text[i]
        i += 1
    return out


def remove_tags(text):
    """나머지 태그(<b>, </p> 등 '<' 와 '>' 사이에 한 글자 이상)를 없앤다."""
    out = ""
    i = 0
    while i < len(text):
        if text[i] == "<":
            close = text.find(">", i + 1)
            if close > i + 1:
                i = close + 1
                continue
        out += text[i]
        i += 1
    return out


def clean(text):
    """개요 정리: 태그 지우기 → 여러 칸 띄어쓰기를 한 칸으로 → 앞 1200자"""
    text = remove_tags(replace_br(text or ""))
    return " ".join(text.split())[:MAX_OVERVIEW]


def call(key, model, prompt):
    """Gemini에 한 번 요청해 JSON 답을 돌려준다. 실패하면 None"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    req = urllib.request.Request(
        API.format(model=model), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=240) as res:
                data = json.loads(res.read().decode("utf-8"))
            text = ""
            for part in data["candidates"][0]["content"]["parts"]:
                if not part.get("thought"):  # 모델의 생각 과정은 빼고 답만
                    text += part.get("text", "")
            return json.loads(text)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code == 429 and ("per day" in msg or "PerDay" in msg):
                raise DailyQuotaExceeded(msg[:300])
            if e.code in (429, 500, 503) and attempt < len(RETRY_WAITS):
                print(f"  (HTTP {e.code}, {RETRY_WAITS[attempt]}초 뒤 다시 시도)", flush=True)
                time.sleep(RETRY_WAITS[attempt])
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
    """batch: [(장소, 개요)] → {id: {"ko": ..., "en": ...}}"""
    lines = []
    ids = set()
    for p, overview in batch:
        lines.append(json.dumps({"id": p["source_id"], "name": p["name"], "name_en": p.get("name_en") or "",
                                 "categories": p["categories"], "overview": overview}, ensure_ascii=False))
        ids.add(p["source_id"])
    data = call(key, model, PROMPT.format(places="\n".join(lines)))
    out = {}
    for it in (data or {}).get("items", []):
        if it.get("id") in ids and it.get("ko") and it.get("en"):
            out[it["id"]] = {"ko": it["ko"].strip(), "en": it["en"].strip()}
    return out


def list_models(key):
    """이 키로 쓸 수 있는 Flash 모델 이름을 보여 준다."""
    req = urllib.request.Request(MODELS_API, headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=60) as res:
        models = json.loads(res.read().decode("utf-8")).get("models", [])
    for m in models:
        if "flash" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", []):
            print(m["name"].replace("models/", ""))


def option_value(name, default):
    """명령줄에서 '--limit 3' 같은 값을 읽는다 (없으면 default)"""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


def make_todo(places, overviews, done, limit):
    """아직 안 만들었고 개요가 충분한 장소 목록 [(장소, 정리된 개요)]"""
    todo = []
    for p in places:
        cid = p.get("source_id")
        overview = clean(overviews.get(cid))
        if cid in done or len(overview) < MIN_OVERVIEW:  # 지어낸 설명 방지
            continue
        todo.append((p, overview))
    return todo[:limit]


def save(out):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def main():
    limit = option_value("--limit", 1000)
    batch_size = option_value("--batch", BATCH)

    apiutil.load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit(".env 파일에 GEMINI_API_KEY=... 를 넣어 주세요.")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    if "--list-models" in sys.argv:
        list_models(key)
        return
    print(f"모델: {model}")
    if not os.path.exists(OVERVIEW):
        sys.exit("먼저 python data/tools/collect_tour.py --detail 로 개요를 받아 주세요.")

    places = []
    for p in apiutil.read_json(PLACES)["places"]:
        if p.get("source") == "tour":
            places.append(p)
    overviews = apiutil.read_json(OVERVIEW)
    out = apiutil.read_json(OUT, {})

    todo = make_todo(places, overviews, out, limit)
    size = max(1, min(batch_size, limit))
    batches = []
    for i in range(0, len(todo), size):
        batches.append(todo[i:i + size])
    print(f"남은 장소 {len(todo)}곳 → 요청 {len(batches)}회 ({size}곳씩)")

    made = 0
    for n, batch in enumerate(batches, start=1):
        names = []
        for p, _ in batch:
            names.append(p["name"])
        print(f"- {n}/{len(batches)}: {', '.join(names)[:80]}…", flush=True)
        try:
            got = generate_batch(key, model, batch)
        except DailyQuotaExceeded:
            print("\n오늘 무료 요청 한도를 다 썼어요. 지금까지 만든 것은 저장됐고, "
                  "내일(한국 시각 오후 5시 이후) 다시 실행하면 이어서 만듭니다.")
            break
        out.update(got)
        made += len(got)
        if limit <= 5:  # 시험 실행이면 만든 결과를 보여 준다
            for p, _ in batch:
                d = got.get(p["source_id"])
                if d:
                    print(f"\n[{p['name']}]\n  ko: {d['ko']}\n  en: {d['en']}")
        save(out)
        time.sleep(5)
    print(f"\n이번에 {made}곳 생성, 전체 {len(out)}곳 → {OUT}")


if __name__ == "__main__":
    main()
