# 트립핀 화면 글자: 4개 언어 번역 + 한글 이름을 로마자로 바꾸기
#
# 버전 기록
# v0.1 (2026-11-18) 한국어·영어·중국어·일본어 번역 파일 로드와 문구 찾기 함수 작성 (core/i18n.py)
# v0.2 (2026-11-21) 한글 → 로마자 변환 추가 (core/romanize.py): 받침 연음, ㄹㄹ → ll, 겹받침, 단어 첫 글자 대문자, 동 이름
# v0.3 (2026-11-22) 수업 수준으로 다시 정리: core/i18n.py + core/romanize.py를 이 파일 하나로 합침,
#                   정규식 대신 for 반복문과 문자열 비교로 같은 결과를 냄 (4주차 유니코드, 5주차 리스트·딕셔너리, 7주차 반복문)
#
# 번역 문구는 i18n/ko.json, en.json, zh.json, ja.json 에 있다 (키 → 문구 딕셔너리).

import json
import os

LANGS = {"ko": "한국어", "en": "English", "zh": "中文", "ja": "日本語"}
DEFAULT_LANG = "ko"

I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
loaded = {}  # 언어 코드 → 번역 딕셔너리 (한 번 읽은 파일은 다시 읽지 않는다)


# ---------------------------------------------------------------- 번역

def load_language(lang):
    """i18n/<lang>.json 을 읽어 딕셔너리로 돌려준다."""
    if lang not in loaded:
        with open(os.path.join(I18N_DIR, lang + ".json"), encoding="utf-8") as f:
            loaded[lang] = json.load(f)
    return loaded[lang]


def translate(lang, key, **values):
    """번역 문구를 찾는다. 그 언어에 없으면 한국어, 한국어에도 없으면 키를 그대로 보여 준다.
    values가 있으면 문구 안의 {n} 같은 자리에 채운다."""
    if lang not in LANGS:
        lang = DEFAULT_LANG
    text = load_language(lang).get(key) or load_language(DEFAULT_LANG).get(key) or key
    if values:
        return text.format(**values)
    return text


# ---------------------------------------------------------------- 로마자 (국어의 로마자 표기법 기본 규칙)
# 한글 한 글자(음절)는 유니코드 번호로 첫소리·가운뎃소리·끝소리(받침) 번호를 계산할 수 있다 (4주차 데이터의 표현).
#   번호 = 0xAC00 + (첫소리 × 21 + 가운뎃소리) × 28 + 받침
# 발음 변화(비음화·경음화 등)는 반영하지 않는다. 사람이 읽고 따라 말할 수 있는 정도가 목표.

FIRST = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
MIDDLE = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu",
          "eu", "ui", "i"]
# 받침이 음절 끝에 올 때 나는 소리 (대표음)
LAST = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
        "ng", "t", "t", "k", "t", "p", "t"]
# 다음 음절이 ㅇ으로 시작하면 받침이 넘어가 첫소리처럼 읽힌다 (연음): 받침 번호 → (남는 소리, 넘어가는 소리)
LIAISON = {1: ("", "g"), 2: ("", "kk"), 3: ("k", "s"), 4: ("", "n"), 5: ("n", "j"), 6: ("n", ""), 7: ("", "d"),
           8: ("", "r"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"), 13: ("l", "t"),
           14: ("l", "p"), 15: ("l", ""), 16: ("", "m"), 17: ("", "b"), 18: ("p", "s"), 19: ("", "s"),
           20: ("", "ss"), 22: ("", "j"), 23: ("", "ch"), 24: ("", "k"), 25: ("", "t"), 26: ("", "p"), 27: ("", "")}
IEUNG = 11        # 첫소리 ㅇ
RIEUL_FIRST = 5   # 첫소리 ㄹ
RIEUL_LAST = 8    # 받침 ㄹ
NG_LAST = 21      # 받침 ㅇ (넘어가지 않는다)

# 이름 끝에 붙는 흔한 단어: 앞에 띄어쓰기를 넣어 로마자가 한 덩어리로 길어지지 않게 한다 (긴 단어부터 비교)
WORDS = ["칼국수", "국밥", "카페", "커피", "식당", "분식", "치킨", "베이커리", "제과", "갈비", "냉면", "순대", "국수",
         "돈까스", "떡볶이", "김밥", "만두", "해장국", "전시관", "기념관", "공원", "시장", "본점", "점"]
WORDS_LONG_FIRST = sorted(WORDS, key=len, reverse=True)

# 이 글자 바로 뒤에 오는 영어 소문자는 대문자로 바꾼다 (단어의 첫 글자)
WORD_START_MARKS = "([/·-"


def is_hangul(ch):
    return "가" <= ch <= "힣"


def split_syllable(ch):
    """한글 음절 → (첫소리, 가운뎃소리, 받침) 번호. 한글 음절이 아니면 None"""
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return None


def space_before_words(text):
    """'미소본가스마일칼국수' → '미소본가스마일 칼국수'. 앞에 한글이 두 글자 이상 있을 때만 띄운다."""
    out = ""
    i = 0
    while i < len(text):
        found = None
        if i >= 2 and is_hangul(text[i - 2]) and is_hangul(text[i - 1]):
            for word in WORDS_LONG_FIRST:
                if text.startswith(word, i):
                    found = word
                    break
        if found:
            out += " " + found
            i += len(found)
        else:
            out += text[i]
            i += 1
    return out.replace("  ", " ")


def capitalize_words(s):
    """문장 맨 앞이나 띄어쓰기·괄호·- 뒤에 오는 영어 소문자를 대문자로"""
    out = ""
    for i in range(len(s)):
        ch = s[i]
        starts_word = i == 0 or s[i - 1].isspace() or s[i - 1] in WORD_START_MARKS
        if starts_word and "a" <= ch <= "z":
            ch = ch.upper()
        out += ch
    return out


def romanize(text):
    """'미소본가 칼국수' → 'Misobonga Kalguksu'. 한글이 아닌 글자는 그대로 둔다."""
    if not text:
        return text
    text = space_before_words(text)
    parts = []
    for ch in text:
        parts.append(split_syllable(ch))

    out = ""
    for i in range(len(text)):
        part = parts[i]
        if part is None:
            out += text[i]
            continue
        first, middle, last = part
        prev = parts[i - 1] if i > 0 else None
        nxt = parts[i + 1] if i + 1 < len(parts) else None

        # 앞 음절 받침이 넘어왔으면(연음) 첫소리는 이미 붙어 있다
        moved = (prev is not None and prev[2] and prev[2] != NG_LAST
                 and first == IEUNG and prev[2] in LIAISON)
        if not moved:
            if first == RIEUL_FIRST and prev is not None and prev[2] == RIEUL_LAST:
                out += "l"  # ㄹㄹ → ll
            else:
                out += FIRST[first]
        out += MIDDLE[middle]
        if last:
            if nxt is not None and nxt[0] == IEUNG and last in LIAISON:
                stay, go = LIAISON[last]
                out += stay + go
            else:
                out += LAST[last]
    return capitalize_words(out)


def romanize_dong(dong):
    """'대흥동' → 'Daeheung-dong'"""
    if not dong:
        return dong
    if dong.endswith("동") and len(dong) > 1:
        return romanize(dong[:-1]) + "-dong"
    return romanize(dong)
