# 수집 스크립트 공통 도구: .env 읽기, 공공데이터포털 호출
#
# 버전 기록
# v0.1 (2026-11-18) .env 로더(외부 패키지 없이)와 공공데이터포털 GET 호출 함수 작성

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")


def load_env():
    """프로젝트 루트의 .env 파일을 읽어 환경 변수로 넣는다 (이미 있는 값은 그대로 둔다)."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def data_go_kr_key():
    load_env()
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        sys.exit(".env 파일에 DATA_GO_KR_KEY=공공데이터포털_일반인증키 를 넣어 주세요.")
    return key


def get_json(url, params):
    """GET 요청 후 JSON으로 읽는다. 인증키 오류 등으로 XML이 오면 내용을 보여 주고 멈춘다."""
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full, timeout=30) as res:
            text = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} 오류: {e.read().decode('utf-8', 'ignore')[:500]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 인증키가 틀리거나 등록 직후(1~2시간)면 XML 오류 메시지가 온다
        sys.exit("JSON이 아닌 응답이 왔어요 (인증키 확인):\n" + text[:800])


def save_json(name, data):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"저장: {path}")
    return path
