# 수집 스크립트 공통 도구: .env 읽기, API 호출, 원본 저장
#
# 버전 기록
# v0.1 .env 읽기, 공공데이터포털 호출
# v0.2 data/tools로 이동, read_json 추가

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TOOLS_DIR))
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")  # 원본 (저장소·제출 파일 제외)


def load_env():
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    f = open(path, encoding="utf-8")
    try:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    finally:
        f.close()


def data_go_kr_key():
    load_env()
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        sys.exit(".env 파일에 DATA_GO_KR_KEY=공공데이터포털_일반인증키 를 넣어 주세요.")
    return key


def get_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        res = urllib.request.urlopen(full, timeout=30)
        try:
            text = res.read().decode("utf-8")
        finally:
            res.close()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} 오류: {e.read().decode('utf-8', 'ignore')[:500]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 인증키 오류 시 XML 응답
        sys.exit("JSON이 아닌 응답이 왔어요 (인증키 확인):\n" + text[:800])


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    f = open(path, encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


def save_json(name, data):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    f = open(path, "w", encoding="utf-8")
    try:
        json.dump(data, f, ensure_ascii=False, indent=1)
    finally:
        f.close()
    print(f"저장: {path}")
    return path
