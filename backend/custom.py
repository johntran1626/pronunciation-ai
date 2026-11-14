"""A typed Custom-mode sentence -> the same sentence with every number and abbreviation written
out as the words a native speaker would SAY. The app then uses this one text everywhere (shown to the learner,
sent to the native TTS voice, turned into expected sounds), so the three can't disagree.

Why: our G2P guessed wrong on typed digits (g2pk read 커피 2잔 as 이잔; a native says 두 잔) and abbreviations
(g2p_en read "Dr." as "drive"). A wrong guess = a correct speaker marked red = the worst error this app can make.

Korean rule (standard textbook grammar): native numbers (한, 두, 세, 네, 다섯... 스무) before NATIVE counters
(개, 명, 잔, 병, 시, 시간, 살, 번...), Sino numbers (일, 이, 삼...) before every other unit (분, 원, 년, 월, 일, 층...)
and for bare numbers. Native numbers only go to 99; 100 and up are read in Sino. Limits: a few counters read
both ways by meaning (3번 = 세 번 "three times" OR 삼 번 "number three"); we pick the more common one and the
learner SEES the reading before recording.
"""
import re

from backend.tts import normalize_text

MAX_CHARS = 80                     # about what fits in the 15 s recording limit at learner speed

# ---------- Korean numbers ----------

SINO_DIGITS = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]
NATIVE_UNITS = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]   # the forms used before a counter

# Counters that take NATIVE numbers (두 잔, 세 시, 다섯 명). Everything else takes Sino numbers.
NATIVE_COUNTERS = {
    "개", "명", "사람", "분들", "잔", "병", "캔", "컵", "그릇", "접시", "마리", "살", "시", "시간", "권", "대", "장",
    "번", "번째", "달", "켤레", "벌", "송이", "자루", "채", "통", "판", "가지", "군데", "곳", "쌍", "줄", "알",
    "조각", "봉지", "상자", "박스", "팩", "바퀴", "모금", "그루", "포기", "다발", "끼", "숟가락",
}
# Sino counters listed only so the LONGER name wins (개월 is not 개 + 월; 인분 is Sino).
SINO_COUNTERS = {
    "개월", "분", "초", "년", "월", "일", "주", "주일", "원", "층", "호", "호선", "학년", "인분", "회", "등", "도",
    "세", "박", "교시", "퍼센트", "킬로", "미터", "센티", "그램", "페이지", "달러", "번지",
}
COUNTERS = sorted(NATIVE_COUNTERS | SINO_COUNTERS, key=len, reverse=True)   # longest first
# 번 = "times" (세 번, native) unless it NAMES something: 삼 번 출구 (exit 3), 이 번 버스 (bus 2) are Sino.
NUMBERED_BY_BEON = re.compile(r"\s?(출구|버스|선|방|문제|자리|좌석|게이트|칸|트랙|홈)")


def _sino4(n):
    """1..9999 in Sino words. A leading 1 is silent before 십/백/천 (십, 백, 천, not 일십)."""
    out = []
    for value, name in ((1000, "천"), (100, "백"), (10, "십"), (1, "")):
        d, n = divmod(n, value)
        if d:
            out.append(("" if d == 1 and name else SINO_DIGITS[d]) + name)
    return "".join(out)


def sino_number(n):
    """0 -> 영; 15000 -> '만 오천'. Spaces every 만 (10^4) group, as Korean spelling rules write numbers."""
    if n == 0:
        return "영"
    groups, k = [], 0
    while n:
        n, g = divmod(n, 10000)
        if g:
            word = "만" if (k == 1 and g == 1) else _sino4(g) + ["", "만", "억", "조"][k]
            groups.append(word)
        k += 1
    return " ".join(reversed(groups))


def native_number(n):
    """1..99 as said BEFORE a counter: 1 한, 2 두, 3 세, 4 네, 20 스무, 21 스물한."""
    if not 1 <= n <= 99:
        raise ValueError(f"native numbers go from 1 to 99, not {n}")
    tens, units = divmod(n, 10)
    if units == 0:
        return "스무" if tens == 2 else NATIVE_TENS[tens]
    return NATIVE_TENS[tens] + NATIVE_UNITS[units]


def _digits(s, zero):
    return "".join(zero if c == "0" else SINO_DIGITS[int(c)] for c in s)


def _with_counter(n, counter):
    if counter == "월":                         # months: 유월 and 시월 drop a sound
        return {6: "유월", 10: "시월"}.get(n, sino_number(n) + "월")
    if counter == "번째" and n == 1:
        return "첫 번째"
    if counter in NATIVE_COUNTERS and 1 <= n <= 99:
        return f"{native_number(n)} {counter}"
    return f"{sino_number(n)} {counter}"


NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?( ?)")


def _korean(text):
    # Phone numbers (010-1234-5678): digit by digit, 0 = 공.
    text = re.sub(r"\d+(?:-\d+)+", lambda m: " ".join(_digits(g, "공") for g in m.group().split("-")), text)
    # Clock times (3:30): native hour + Sino minutes.
    text = re.sub(r"(\d{1,2}):(\d{2})",
                  lambda m: _with_counter(int(m.group(1)), "시")
                  + (f" {sino_number(int(m.group(2)))} 분" if int(m.group(2)) else ""), text)
    out, pos = [], 0
    for m in NUMBER.finditer(text):
        out.append(text[pos:m.start()])
        whole, decimal, space = int(m.group(1).replace(",", "")), m.group(2), m.group(3)
        rest = text[m.end():]
        counter = next((c for c in COUNTERS if rest.startswith(c)), None)
        if decimal:                                 # 1.5 -> 일 점 오
            word = f"{sino_number(whole)} 점 {_digits(decimal, '영')}"
            out.append(word + (f" {counter}" if counter else space))
        elif counter == "번" and NUMBERED_BY_BEON.match(rest[len(counter):]):
            out.append(f"{sino_number(whole)} 번")
        elif counter:
            out.append(_with_counter(whole, counter))
        else:
            out.append(sino_number(whole) + space)
        pos = m.end() + (len(counter) if counter else 0)
    out.append(text[pos:])
    return "".join(out)

# ---------- English ----------

ABBREVIATIONS = [
    (re.compile(r"\bMrs\.?(?=\s)"), "Missus"), (re.compile(r"\bMr\.?(?=\s)"), "Mister"),
    (re.compile(r"\bMs\.?(?=\s)"), "Miz"), (re.compile(r"\bDr\.?(?=\s)"), "Doctor"),
    (re.compile(r"\bJr\."), "Junior"), (re.compile(r"\bSr\."), "Senior"),
    (re.compile(r"\bSt\.(?=\s+[A-Z])"), "Saint"), (re.compile(r"\bSt\."), "Street"),
    (re.compile(r"\bvs\.?(?=\s)"), "versus"), (re.compile(r"\betc\."), "et cetera"),
    (re.compile(r"\bNo\.\s?(?=\d)"), "number "),
]


def _english(text):
    from g2p_en.expand import normalize_numbers   # g2p_en is already a dependency (it does $, 1st, years, 5,000)

    if re.search(r"[ᄀ-ᇿ㄰-㆏가-힣]", text):
        raise ValueError("This looks like Korean. Switch to \"I'm learning Korean\" to practice it.")
    for rx, word in ABBREVIATIONS:
        text = rx.sub(word, text)

    def clock(m):
        h, mm = normalize_numbers(str(int(m.group(1)))), int(m.group(2))
        if mm == 0:
            return f"{h} o'clock"
        return f"{h} oh {normalize_numbers(str(mm))}" if mm < 10 else f"{h} {normalize_numbers(str(mm))}"
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", clock, text)

    def am_pm(m):        # 3 pm / 9 a.m. -> "3 P M" (the voice says the letters); keep a sentence-final period
        end = "." if m.group().endswith(".") and m.end() == len(text) else ""
        return f"{m.group(1)} {m.group(2).upper()} M{end}"
    text = re.sub(r"(\d)\s?([AaPp])\.?[Mm]\b\.?", am_pm, text)
    text = re.sub(r"(\d)\s?%", r"\1 percent", text).replace("&", " and ")
    return normalize_numbers(text)

# ---------- entry point ----------


def custom_text(text, lang):
    """Typed sentence -> spoken-words sentence. Raises ValueError with a message the learner can read."""
    if lang not in ("ko", "en"):
        raise ValueError(f"unsupported language: {lang!r} (use 'ko' or 'en')")
    text = normalize_text(text)
    if len(text) > MAX_CHARS:
        raise ValueError(f"That's {len(text)} characters. Keep it to {MAX_CHARS} or fewer (one short sentence).")
    if not re.search(r"\w", text):
        raise ValueError("Type a sentence with at least one word.")
    said = _korean(text) if lang == "ko" else _english(text)
    return normalize_text(said)
