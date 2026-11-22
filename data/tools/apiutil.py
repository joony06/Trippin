# 수집 스크립트 공통 도구: 폴더 위치, .env(API 키) 읽기, 공공데이터포털 호출, 원본 저장
#
# 버전 기록
# v0.1 (2026-11-18) .env 로더(외부 패키지 없이)와 공공데이터포털 GET 호출 함수 작성
# v0.2 (2026-11-22) 수업 수준으로 다시 정리: data/tools/ 로 옮김, JSON 파일 읽기 함수(read_json) 추가 (10주차 사용자 정의 모듈)
#
# data/tools/ 의 다른 스크립트가 import apiutil 로 불러 쓴다.

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TOOLS_DIR))  # 프로젝트 폴더 (app.py가 있는 곳)
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")             # 수집한 원본 (API 키로 받은 것이라 저장소·제출 파일에 넣지 않는다)


def load_env():
    """프로젝트 폴더의 .env 파일을 읽어 환경 변수로 넣는다 (이미 있는 값은 그대로 둔다)."""
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
    """공공데이터포털 인증키. 없으면 안내하고 멈춘다."""
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


def read_json(path, default=None):
    """JSON 파일을 읽는다. 파일이 없으면 default"""
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(name, data):
    """data/raw/<name> 에 저장하고 경로를 돌려준다."""
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"저장: {path}")
    return path
