# 한글 → 로마자 (국어의 로마자 표기법 기본 규칙). 영어·중국어·일본어 화면에서 영문 이름이 없는 가게·동네 이름에 쓴다.
#
# 버전 기록
# v0.1 (2026-11-21) 음절 분해로 로마자 변환: 받침 연음(ㄱ+ㅇ → g), ㄹㄹ → ll, 겹받침, 단어 첫 글자 대문자, 동 이름(대흥동 → Daeheung-dong)
#                   흔한 메뉴·업종 단어(칼국수, 카페 등) 앞은 띄어서 읽기 쉽게 (미소본가스마일 칼국수 → Misobongaseumail Kalguksu)
#
# 발음 변화(비음화·경음화 등)는 반영하지 않는다. 사람이 읽고 따라 말할 수 있는 정도가 목표.

import re

_CHO = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_JUNG = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu",
         "eu", "ui", "i"]
# 받침이 음절 끝에 올 때 (대표음)
_JONG = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
         "ng", "t", "t", "k", "t", "p", "t"]
# 다음 음절이 ㅇ으로 시작하면 받침이 넘어가 첫소리처럼 읽힌다: (남는 받침, 넘어가는 소리)
_LIAISON = {1: ("", "g"), 2: ("", "kk"), 3: ("k", "s"), 4: ("", "n"), 5: ("n", "j"), 6: ("n", ""), 7: ("", "d"),
            8: ("", "r"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"), 13: ("l", "t"),
            14: ("l", "p"), 15: ("l", ""), 16: ("", "m"), 17: ("", "b"), 18: ("p", "s"), 19: ("", "s"),
            20: ("", "ss"), 22: ("", "j"), 23: ("", "ch"), 24: ("", "k"), 25: ("", "t"), 26: ("", "p"), 27: ("", "")}
_IEUNG, _RIEUL_CHO, _RIEUL_JONG = 11, 5, 8


def _split(ch):
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return None


# 이름 끝에 붙는 흔한 단어: 앞에 띄어쓰기를 넣어 로마자가 한 덩어리로 길어지지 않게 한다
_WORDS = ["칼국수", "국밥", "카페", "커피", "식당", "분식", "치킨", "베이커리", "제과", "갈비", "냉면", "순대", "국수",
          "돈까스", "떡볶이", "김밥", "만두", "해장국", "전시관", "기념관", "공원", "시장", "본점", "점"]
_WORD_RE = re.compile("(?<=[가-힣]{2})(" + "|".join(sorted(_WORDS, key=len, reverse=True)) + ")")


def romanize(text):
    """'미소본가 칼국수' → 'Misobonga Kalguksu'. 한글이 아닌 글자는 그대로 둔다."""
    if not text:
        return text
    text = _WORD_RE.sub(r" \1", text).replace("  ", " ")
    parts = [_split(c) for c in text]
    out = []
    for i, ch in enumerate(text):
        sp = parts[i]
        if sp is None:
            out.append(ch)
            continue
        cho, jung, jong = sp
        nxt = parts[i + 1] if i + 1 < len(parts) else None
        # 앞 음절 받침이 넘어왔으면 첫소리는 이미 붙어 있다
        prev = parts[i - 1] if i > 0 else None
        moved = prev is not None and prev[2] and prev[2] != 21 and cho == _IEUNG and prev[2] in _LIAISON
        if not moved:
            if cho == _RIEUL_CHO and prev is not None and prev[2] == _RIEUL_JONG:
                out.append("l")          # ㄹㄹ → ll
            else:
                out.append(_CHO[cho])
        out.append(_JUNG[jung])
        if jong:
            if nxt is not None and nxt[0] == _IEUNG and jong in _LIAISON:
                stay, go = _LIAISON[jong]
                out.append(stay + go)
            else:
                out.append(_JONG[jong])
    s = "".join(out)
    return re.sub(r"(^|[\s(\[/·-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)


def romanize_dong(dong):
    """'대흥동' → 'Daeheung-dong', '대사동' → 'Daesa-dong'"""
    if not dong:
        return dong
    if dong.endswith("동") and len(dong) > 1:
        return romanize(dong[:-1]) + "-dong"
    return romanize(dong)
