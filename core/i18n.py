# 다국어: 언어별 번역 파일(i18n/*.json)에서 화면 문구를 찾는다
#
# 버전 기록
# v0.1 (2026-11-18) 한국어·영어·중국어·일본어 번역 파일 로드와 문구 찾기 함수 작성

import json
import os

LANGS = {"ko": "한국어", "en": "English", "zh": "中文", "ja": "日本語"}
DEFAULT_LANG = "ko"

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n")
_CACHE = {}


def _load(lang):
    if lang not in _CACHE:
        with open(os.path.join(_DIR, f"{lang}.json"), encoding="utf-8") as f:
            _CACHE[lang] = json.load(f)
    return _CACHE[lang]


def translate(lang, key, **kwargs):
    """번역 문구를 찾는다. 없으면 한국어 → 키 순서로 대신 보여 준다."""
    lang = lang if lang in LANGS else DEFAULT_LANG
    text = _load(lang).get(key) or _load(DEFAULT_LANG).get(key) or key
    return text.format(**kwargs) if kwargs else text
