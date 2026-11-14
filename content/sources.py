"""Candidate pools of natural, SPOKEN, licensed Korean lines for the 5 sentence packs.

Run from the project root:  .venv/bin/python -m content.sources
Writes data/pack_candidates/<pack>.json + summary.json (git-ignored). Nothing here is machine-written: every
line is copied word for word from one of three native-written sources, with its source, id, link and license:

  krdict      한국어기초사전 (National Institute of Korean Language), CC BY-SA 2.0 KR. Only the example lines the
              dictionary itself labels 대화 (dialogue), from words tagged with a pack's topic (e.g. 음식 주문하기),
              plus a few seed words for bar talk (the dictionary has no bar topic).
  chatbot     songys/Chatbot_data, MIT. Questions (Q, casual) AND answers (A, polite) labelled 0 = daily life.
  klue_wos    KLUE WoS (task dialogues), CC BY-SA 4.0. Turns from restaurant-only dialogues, split into sentences.
  tatoeba     Tatoeba, CC BY 2.0 FR. Only authors who mark Korean as their native language (level 5); no 톰 lines
              (those are translations of English "Tom" sentences). Read from data/tatoeba_raw/ (downloaded export).

Bar + restaurant = one pack; Tatoeba fills gaps.
`--no-krdict` builds from the other three only (while the site doesn't answer from here).

Packs: krdict lines go to the pack of their dictionary topic (or seed word). Other lines go to a pack when it contains one of that pack's topic words (topic_packs; the project chose the WORDS,
never the sentences). casual = every chatbot / Tatoeba line; every WoS line goes to bar_restaurant.
Then pool() keeps a line only if its speech style is spoken (every pack keeps BOTH 반말 and 존댓말,
because the switch filters each pack by level), 4-15 syllables, no digits / Latin / quotes / emoji jamo, no repeats, and labels it 반말 / 존댓말.
The final ~10 per pack are picked from these pools by content/ko_packs.py.
"""
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from functools import cache
from pathlib import Path

from backend.tts import load_env

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pack_candidates"
RAW = OUT / "raw"                    # downloaded files (data only; read with csv / pyarrow, never executed)
TATOEBA_DIR = ROOT / "data" / "tatoeba_raw"
CACHE = RAW / "krdict"               # one XML file per API answer, key removed, so reruns cost no calls

# ---------- packs ----------

# Topic names exactly as the dictionary writes them (주제 및 상황 범주) -> API codes (openApiInfo page, 2026-11-13).
# Some names have two codes (one per level band).
TOPIC_CODES = {
    "인사하기": [1], "소개하기(자기소개)": [2], "소개하기(가족소개)": [3], "개인 정보 교환하기": [4, 40],
    "시간 표현하기": [11], "날짜 표현하기": [12], "요일 표현하기": [13], "날씨와 계절": [14, 46], "하루 생활": [15],
    "감사하기": [20], "사과하기": [21],
    "학교생활": [16, 47], "교육": [81],
    "직업과 진로": [49, 82], "직장 생활": [50, 83], "전화하기": [19],
    "약속하기": [18], "주말 및 휴가": [23, 52], "취미": [24, 53], "감정, 기분 표현하기": [35, 61],
    "영화 보기": [39], "여가 생활": [84], "초대와 방문": [32, 58],
    "음식 주문하기": [9], "음식 설명하기": [44], "식문화": [79],
}

ANY = {"formal", "polite", "casual"}
PACKS = {
    "basics": {"styles": ANY, "seeds": [],
               "topics": ["인사하기", "소개하기(자기소개)", "소개하기(가족소개)", "개인 정보 교환하기", "시간 표현하기",
                          "날짜 표현하기", "요일 표현하기", "날씨와 계절", "하루 생활", "감사하기", "사과하기"]},
    "school": {"styles": ANY, "seeds": [], "topics": ["학교생활", "교육"]},
    "office": {"styles": ANY, "seeds": [], "topics": ["직업과 진로", "직장 생활", "전화하기"]},
    "casual": {"styles": ANY, "seeds": [],
               "topics": ["약속하기", "주말 및 휴가", "취미", "감정, 기분 표현하기", "영화 보기", "여가 생활", "초대와 방문"]},
    # bar + restaurant are one pack.
    "bar_restaurant": {"styles": ANY, "topics": ["음식 주문하기", "음식 설명하기", "식문화"],
                       # Seed headwords (our choice of WORDS to look up; the sentences come from the dictionary).
                       "seeds": ["술", "맥주", "소주", "막걸리", "건배", "안주", "취하다", "술집", "회식", "술자리",
                                 "마시다", "숙취", "잔", "따르다", "한잔하다"]},
}

KRDICT = {"license": "CC BY-SA 2.0 KR", "credit": "국립국어원 한국어기초사전 (krdict.korean.go.kr)"}

CHATBOT = {"license": "MIT", "credit": "Youngsook Song (2018), Chatbot_data_for_Korean v1.0",
           "url": "https://github.com/songys/Chatbot_data",
           "download": "https://raw.githubusercontent.com/songys/Chatbot_data/master/ChatbotData.csv"}
WOS = {"license": "CC BY-SA 4.0", "credit": "KLUE benchmark (Park et al., 2021), WoS dialogue state tracking",
       "url": "https://github.com/KLUE-benchmark/KLUE",
       "download": "https://huggingface.co/datasets/klue/klue/resolve/refs%2Fconvert%2Fparquet/wos/{split}/0000.parquet"}
TATOEBA = {"license": "CC BY 2.0 FR", "url": "https://tatoeba.org/en/sentences/show/{id}"}

# Topic words per pack. Drinking words must start a word (so 기술 / 수술 / 미술 don't count as 술).
BAR_RE = re.compile(r"(^|\s)(술|맥주|소주|막걸리|와인|안주|건배|회식|한잔|한 잔)|취했|취해|취한|숙취")
TOPICS = {
    "basics": re.compile(r"안녕|감사|고마|고맙|미안|죄송|반가|처음 뵙|잘 지내|이름이|날씨|생일|축하"),
    "school": re.compile(r"학교|수업|시험|숙제|과제|교수|선생|학생|공부|강의|학기|전공|도서관|방학|성적|졸업|교실|기숙사|입학"),
    "office": re.compile(r"회사|회의|회식|출근|퇴근|사장님|부장|과장|팀장|업무|야근|월급|면접|보고서|동료|직장|상사|이직|취업|연봉|출장"),
    "bar_restaurant": re.compile(BAR_RE.pattern + r"|주문|메뉴|식당|예약|계산|맛있|맛집|음식|배달|(^|\s)밥"),
}


def topic_packs(text):
    """The packs whose topic words appear in this line (may be none, may be several)."""
    return {pack for pack, rx in TOPICS.items() if rx.search(text)}

# ---------- text checks ----------

TRAIL = " \t.!?~…,\"'“”‘’"
FORMAL_ENDS = ("니다", "니까", "십시오", "시오")
WRITTEN_ENDS = ("다", "는가", "인가")
ALLOWED_CHARS = re.compile(r"^[가-힣\s.,?!~…]+$")   # Hangul syllables, spaces, plain punctuation


def syllables(text):
    """Number of Hangul syllable blocks (the unit a learner says)."""
    return sum("가" <= ch <= "힣" for ch in text)


def _final_consonant(ch):
    """Index of the final consonant (0 = none) of one Hangul syllable."""
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else 0


def split_sentences(text):
    return [p for p in re.split(r"(?<=[.?!])\s+", text.strip()) if p]


@cache
def _tagger():
    import mecab  # comes with g2pk (already installed); loads a dictionary, so only once
    return mecab.MeCab()


def _piece_style(piece):
    s = piece.strip().rstrip(TRAIL)
    if not s:
        return "fragment"
    if s.endswith(FORMAL_ENDS) or (s.endswith("시다") and len(s) >= 3 and _final_consonant(s[-3]) == 17):
        return "formal"      # 17 = final ㅂ: 합시다 (let's, formal); 마시다 (dictionary form) stays written
    if s.endswith(("요", "죠")):
        return "polite"
    if s.endswith(WRITTEN_ENDS):
        return "written"     # 한다 style: narration and books, not how people talk
    if s.endswith("오"):
        return "hao"         # 하오체 (계획이오): old-fashioned; -시오 is caught as formal above
    pos = _tagger().pos(s)
    if pos and any(tag.startswith("E") for tag in pos[-1][1].split("+")):
        return "casual"      # ends in a verb ending (EC/EF): 무서워, 할까, 가니, 보자
    return "fragment"        # ends in a noun, adverb, number...: 아이스 커피, 12시 땡


def spoken_style(text):
    """formal (합니다) / polite (해요) / casual (해) / written (한다) / hao (하오, old-fashioned) / fragment. The LAST sentence decides; any
    written-style sentence anywhere makes the whole line written. Short non-final pieces like '네.' are fine."""
    styles = [_piece_style(p) for p in split_sentences(text)]
    if not styles:
        return "fragment"
    if "written" in styles:
        return "written"
    return styles[-1]


def clean_reason(text):
    """Why a line can't be a pack sentence, or None if it can."""
    if re.search(r"\d", text):
        return "digits"
    if re.search(r"[A-Za-z]", text):
        return "latin"
    if re.search(r"[\"'‘’“”()\[\]<>「」『』]", text):
        return "quotes"
    if not ALLOWED_CHARS.match(text):
        return "symbols"     # ㅋㅋ / ㅠㅠ, emoji, slashes...
    n = syllables(text)
    if n < 4:
        return "short"
    if n > 15:
        return "long"
    return None


def _norm(text):
    return re.sub(r"[\s.,?!~…]", "", text)


def pool(rows, pack):
    """Clean, pack-style, de-duplicated candidates (first copy wins), each tagged with style + syllables."""
    allowed = PACKS[pack]["styles"]
    seen, out = set(), []
    for r in rows:
        text = r["text"].strip()
        if clean_reason(text):
            continue
        style = spoken_style(text)
        if style not in allowed or _norm(text) in seen:
            continue
        seen.add(_norm(text))
        out.append({**r, "text": text, "style": style, "speech": "반말" if style == "casual" else "존댓말",
                    "syllables": syllables(text), "pack": pack})
    return out

# ---------- krdict API ----------


class KrdictError(RuntimeError):
    pass


def _urlopen(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


class Krdict:
    """Tiny client for the dictionary's Open API. The key lives in .env; it is removed from every error message
    and from every cached answer. `fetch` is swappable so tests never touch the network."""
    BASE = "https://krdict.korean.go.kr/api/"

    TRIES = 4

    def __init__(self, key=None, cache_dir=CACHE, fetch=None, pause=1.5, retry_wait=20.0):
        if key is None:
            load_env()
            key = os.environ.get("KRDICT_API_KEY", "").strip()
        if not key:
            raise KrdictError("KRDICT_API_KEY is not set (put it in .env)")
        self._key, self.cache_dir, self.fetch, self.pause = key, Path(cache_dir), fetch or _urlopen, pause
        self.retry_wait = retry_wait
        self.calls = 0

    def _fetch(self, path, url):
        """Network errors (timeouts, resets) are retried with a growing wait; API errors (bad key...) are not."""
        for attempt in range(1, self.TRIES + 1):
            try:
                return self.fetch(url)
            except Exception as e:  # noqa: BLE001 - re-raised without the URL (it holds the key)
                if attempt == self.TRIES:
                    raise KrdictError(f"krdict {path} request failed after {attempt} tries: "
                                      f"{type(e).__name__}: {self._redact(str(e))}") from None
                time.sleep(self.retry_wait * attempt)

    def _redact(self, s):
        return s.replace(self._key, "<KEY>")

    def get(self, path, **params):
        tag = hashlib.sha256(json.dumps([path, sorted(params.items())], ensure_ascii=False).encode()).hexdigest()[:24]
        f = self.cache_dir / path / f"{tag}.xml"
        if f.exists():
            return f.read_text(encoding="utf-8")
        url = self.BASE + path + "?" + urllib.parse.urlencode({**params, "key": self._key})
        body = self._fetch(path, url)
        self.calls += 1
        if self.pause:
            time.sleep(self.pause)
        body = self._redact(body)
        err = re.search(r"<error_code>(.*?)</error_code>\s*<message>(.*?)</message>", body, re.S)
        if err:
            raise KrdictError(f"krdict error {err.group(1).strip()}: {err.group(2).strip()}")
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(f)
        return body


def _xml(text):
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        raise KrdictError(f"krdict answer is not valid XML: {e}") from None


def parse_search(xml_text):
    """-> (total, [(target_code, headword), ...])"""
    root = _xml(xml_text)
    total = int(root.findtext("total") or 0)
    return total, [(it.findtext("target_code", "").strip(), it.findtext("word", "").strip())
                   for it in root.iter("item")]


def parse_view(xml_text):
    """One word entry -> headword, grade, topic names and ONLY its 대화 (dialogue) example lines, in order."""
    root = _xml(xml_text)
    item = root.find("item")
    info = item.find("word_info")
    topics = []
    for c in info.iter("category_info"):
        if c.findtext("type", "").strip() == "주제 및 상황 범주":
            name = c.findtext("written_form", "").strip()
            if name and name not in topics:
                topics.append(name)
    dialogue = [e.findtext("example", "").strip() for e in info.iter("example_info")
                if e.findtext("type", "").strip() == "대화"]
    return {"target_code": item.findtext("target_code", "").strip(), "word": info.findtext("word", "").strip(),
            "grade": info.findtext("word_grade", "").strip(), "topics": topics, "dialogue": [d for d in dialogue if d]}


def krdict_rows(view):
    code = view["target_code"]
    return [{"text": line, "source": "krdict", "source_id": f"{code}#{i}",
             "source_url": f"https://krdict.korean.go.kr/dicSearch/SearchView?ParaWordNo={code}",
             "license": KRDICT["license"], "credit": KRDICT["credit"], "context": view["word"],
             "topics": view["topics"], "grade": view["grade"]}
            for i, line in enumerate(view["dialogue"])]


def _search_all(client, **params):
    """All target codes for one search, following pages (the API stops at start=1000)."""
    codes, start = [], 1
    while start <= 1000:
        total, items = parse_search(client.get("search", num=100, start=start, **params))
        codes += [c for c, _ in items if c]
        start += 100
        if start > total or not items:
            break
    return codes


def collect_krdict(client, probe_syllables):
    """Every word tagged with any pack topic (the API has no wildcard, so search each common syllable with all
    topic codes OR-ed together), plus the seed words. -> {pack: [rows]}"""
    codes_all = ",".join(str(c) for name in sorted(TOPIC_CODES) for c in TOPIC_CODES[name])
    topic_codes = set()
    for syl in probe_syllables:
        topic_codes.update(_search_all(client, q=syl, advanced="y", method="include", subject_cat=codes_all))
    seed_codes = {}
    for pack, p in PACKS.items():
        for seed in p["seeds"]:
            for c in _search_all(client, q=seed, advanced="y", method="exact"):
                seed_codes.setdefault(c, set()).add(pack)
    topic_pack = {name: pack for pack, p in PACKS.items() for name in p["topics"]}
    out = {pack: [] for pack in PACKS}
    for code in sorted(topic_codes | set(seed_codes), key=int):
        view = parse_view(client.get("view", method="target_code", q=code))
        packs = {topic_pack[t] for t in view["topics"] if t in topic_pack} | seed_codes.get(code, set())
        for pack in sorted(packs):
            out[pack] += krdict_rows(view)
    return out


# ---------- Chatbot_data, KLUE WoS, Tatoeba ----------


def chatbot_rows(fileobj):
    """Questions (casual) and answers (polite) of the pairs labelled 0 (daily life). Labels 1/2 are breakup / love."""
    rows = []
    for n, r in enumerate(csv.DictReader(fileobj), start=1):
        if r.get("label", "").strip() != "0":
            continue
        for side in ("Q", "A"):
            if r.get(side, "").strip():
                rows.append({"text": r[side].strip(), "source": "chatbot", "source_id": f"row{n}.{side}",
                             "source_url": CHATBOT["url"], "license": CHATBOT["license"],
                             "credit": CHATBOT["credit"], "context": side})
    return rows


def wos_rows(dialogues):
    """Turns (customer AND staff) of dialogues whose only domain is 식당, one row per sentence."""
    rows = []
    for d in dialogues:
        if list(d["domains"]) != ["식당"]:
            continue
        for t, turn in enumerate(d["dialogue"]):
            for k, sent in enumerate(split_sentences(turn["text"])):
                rows.append({"text": sent, "source": "klue_wos", "source_id": f"{d['guid']}#{t}.{k}",
                             "source_url": WOS["url"], "license": WOS["license"], "credit": WOS["credit"],
                             "context": turn["role"]})
    return rows


def tatoeba_rows(sentences, users):
    """Korean sentences (id, lang, text, author, ...) whose author lists Korean at level 5 (native); no 톰 lines."""
    native = {r[2] for r in csv.reader(users, delimiter="\t") if len(r) > 2 and r[0] == "kor" and r[1] == "5"}
    rows = []
    for r in csv.reader(sentences, delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(r) < 4 or r[1] != "kor" or r[3] not in native or "톰" in r[2]:
            continue
        rows.append({"text": r[2].strip(), "source": "tatoeba", "source_id": r[0],
                     "source_url": TATOEBA["url"].format(id=r[0]), "license": TATOEBA["license"],
                     "credit": f"Tatoeba user {r[3]} (tatoeba.org)", "context": "sentence"})
    return rows


def route(chat, wos, tatoeba, kr=None):
    """-> {pack: raw rows}. krdict rows first (already sorted by dictionary topic), so the dictionary copy wins a
    repeat. Chatbot + Tatoeba lines go to casual and to every pack whose topic words they contain; every WoS line
    goes to bar_restaurant (they are all restaurant talk)."""
    raw = {pack: list((kr or {}).get(pack, [])) for pack in PACKS}
    for r in chat + tatoeba:
        raw["casual"].append(r)
        for pack in sorted(topic_packs(r["text"])):
            raw[pack].append(r)
    raw["bar_restaurant"] += wos
    return raw

# ---------- run ----------


def _download(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    return dest


def probe_syllables(texts, n=300):
    """The n most common syllables in a big pile of Korean text: each topic word almost surely contains one."""
    c = Counter(ch for t in texts for ch in t if "가" <= ch <= "힣")
    return [s for s, _ in c.most_common(n)]


def main(argv=None):
    import pyarrow.parquet as pq

    use_krdict = "--no-krdict" not in (sys.argv[1:] if argv is None else argv)

    chat_csv = _download(CHATBOT["download"], RAW / "ChatbotData.csv")
    dialogues = []
    for split in ("train", "validation"):
        f = _download(WOS["download"].format(split=split), RAW / f"wos_{split}.parquet")
        dialogues += pq.read_table(f).to_pylist()
    with open(chat_csv, encoding="utf-8") as fh:
        chat = chatbot_rows(fh)
    with open(TATOEBA_DIR / "kor_sentences_detailed.tsv", encoding="utf-8") as s, \
         open(TATOEBA_DIR / "user_languages.csv", encoding="utf-8") as u:
        tat = tatoeba_rows(s, u)
    kr = None
    if use_krdict:
        client = Krdict()
        t0 = time.time()
        kr = collect_krdict(client, probe_syllables([r["text"] for r in chat]))
        print(f"krdict: {client.calls} new API calls in {time.time() - t0:.0f} s", flush=True)
    raw = route(chat, wos_rows(dialogues), tat, kr)

    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for pack in PACKS:
        cands = pool(raw[pack], pack)
        (OUT / f"{pack}.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
        summary[pack] = {"raw": len(raw[pack]), "kept": len(cands),
                         "by_source": dict(Counter(c["source"] for c in cands)),
                         "by_speech": dict(Counter(c["speech"] for c in cands))}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'pack':<15}{'raw':>6}{'kept':>6}  by source / by speech")
    for pack, s in summary.items():
        print(f"{pack:<15}{s['raw']:>6}{s['kept']:>6}  {s['by_source']}  {s['by_speech']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
