# 트립핀 화면 글자: 4개 언어 번역, 한글 → 로마자
#
# 버전 기록
# v0.1 번역 파일 읽기·문구 찾기
# v0.2 한글 → 로마자 변환

import json
import os

LANGS = {"ko": "한국어", "en": "English", "zh": "中文", "ja": "日本語"}
DEFAULT_LANG = "ko"

I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
loaded = {}


def load_language(lang):
    if lang not in loaded:
        f = open(os.path.join(I18N_DIR, lang + ".json"), encoding="utf-8")
        try:
            loaded[lang] = json.load(f)
        finally:
            f.close()
    return loaded[lang]


def translate(lang, key, **values):
    """번역 문구 (없으면 한국어 → 키)"""
    if lang not in LANGS:
        lang = DEFAULT_LANG
    text = load_language(lang).get(key) or load_language(DEFAULT_LANG).get(key) or key
    if values:
        return text.format(**values)
    return text


# 음절 번호 = 0xAC00 + (첫소리 × 21 + 가운뎃소리) × 28 + 받침

FIRST = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
MIDDLE = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu",
          "eu", "ui", "i"]
# 받침 대표음
LAST = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
        "ng", "t", "t", "k", "t", "p", "t"]
# 연음: 받침 번호 → (남는 소리, 넘어가는 소리)
LIAISON = {1: ("", "g"), 2: ("", "kk"), 3: ("k", "s"), 4: ("", "n"), 5: ("n", "j"), 6: ("n", ""), 7: ("", "d"),
           8: ("", "r"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"), 13: ("l", "t"),
           14: ("l", "p"), 15: ("l", ""), 16: ("", "m"), 17: ("", "b"), 18: ("p", "s"), 19: ("", "s"),
           20: ("", "ss"), 22: ("", "j"), 23: ("", "ch"), 24: ("", "k"), 25: ("", "t"), 26: ("", "p"), 27: ("", "")}
IEUNG = 11        # 첫소리 ㅇ
RIEUL_FIRST = 5   # 첫소리 ㄹ
RIEUL_LAST = 8    # 받침 ㄹ
NG_LAST = 21      # 받침 ㅇ (연음 없음)

# 이 단어 앞 띄어쓰기
WORDS = ["칼국수", "국밥", "카페", "커피", "식당", "분식", "치킨", "베이커리", "제과", "갈비", "냉면", "순대", "국수",
         "돈까스", "떡볶이", "김밥", "만두", "해장국", "전시관", "기념관", "공원", "시장", "본점", "점"]
WORDS_LONG_FIRST = sorted(WORDS, key=len, reverse=True)

WORD_START_MARKS = "([/·-"


def is_hangul(ch):
    return "가" <= ch <= "힣"


def split_syllable(ch):
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return None


def space_before_words(text):
    """'미소본가스마일칼국수' → '미소본가스마일 칼국수'"""
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
    out = ""
    for i in range(len(s)):
        ch = s[i]
        starts_word = i == 0 or s[i - 1].isspace() or s[i - 1] in WORD_START_MARKS
        if starts_word and "a" <= ch <= "z":
            ch = ch.upper()
        out += ch
    return out


def romanize(text):
    """'미소본가 칼국수' → 'Misobonga Kalguksu'"""
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
        if i > 0:
            prev = parts[i - 1]
        else:
            prev = None
        if i + 1 < len(parts):
            nxt = parts[i + 1]
        else:
            nxt = None

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
