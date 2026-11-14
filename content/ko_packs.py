"""Pick ~10 native 존댓말 lines and ~10 native 반말 lines per Korean pack, and list the gaps.

Run from the project root (after `python -m content.sources`):  .venv/bin/python -m content.ko_packs
Reads data/pack_candidates/<pack>.json, writes data/pack_candidates/picks.json (git-ignored), prints a table, and
writes the app's packs: content/packs/ko_<pack>.json (10 존댓말 + 10 반말 lines each).
Every Korean line is a native line, copied with its source and license; only the English translations
(content/ko_translations.py) are LLM-written.

How a line is chosen, per pack and per level (존댓말 / 반말), one at a time:
  1. source order: krdict, then Chatbot_data, then KLUE WoS, then Tatoeba
  2. krdict only: the line that actually says the dictionary word (the topic belongs to the WORD, and a dictionary
     dialogue has two lines, often only one of them on topic)
  3. krdict only: easier words first (초급, then 중급, then the rest)
  4. lines that stand alone (not an answer starting 응, / 네, / 아니, ... that needs the question before it)
  5. Casual pack only: 해요 before 합니다 (합니다 is speech-and-meeting talk, not a chat)
  6. the line that adds target sounds we don't have yet (eo_vs_o, eu, ae_vs_e, tap_r, p_stops)
  7. length close to 9 syllables (easy to say, long enough to score), then the source id (so reruns agree)
A line is skipped if our G2P can't read it or it has no target sound, and only one line per dictionary entry is
kept (a krdict dialogue is a question + its answer; two of them would feel like the same sentence twice).
"""
import json
import re
from collections import Counter
from pathlib import Path

from content.ko_translations import TRANSLATIONS
from content.sources import OUT, PACKS

PACK_FILES = Path(__file__).resolve().parent / "packs"
NAMES = {"basics": "Basics", "school": "School", "office": "Office", "casual": "Casual",
         "bar_restaurant": "Bar & restaurant"}
ITEM_KEYS = ["text", "translation", "speech", "tags", "source", "source_id", "source_url", "license", "credit"]

SOURCE_ORDER = ["krdict", "chatbot", "klue_wos", "tatoeba"]
GRADE_ORDER = {"초급": 0, "중급": 1}
LEVELS = ["존댓말", "반말"]
TARGET_LEN = 9
LOOK = 200          # lines per level that get G2P-tagged (see _pick_level)

# Lines the rules picked that don't fit the pack (checked by hand). The rules match the
# dictionary WORD as a substring, so look-alikes, homonyms and idioms slip through. Excluded by source id; the
# next-best native line takes the slot (nothing is rewritten).
EXCLUDE = {
    "school": {
        "58167#8": "가게가 왜 이렇게 조용해요? = a quiet shop, not school",
        "27260#23": "말도 마십시오. = idiom 'don't even ask', not school",
        "89445#22": "저 사람은 돈만 알아. = 'only cares about money', not school",
        "34734#6": "오늘 회사 끝나고 뭐 해? = after work, not school",
        "57301#6": "몇 통 몇 반 = neighborhood units (통/반), not a school class",
        "57301#7": "십사 통 육 반 반장 = same 통/반 dialogue",
    },
    "office": {
        "48995#0": "범행 동기 = a crime motive (동기 homonym: coworker / motive)",
        "62839#11": "네가 잘 안 먹어서 끊었어. = stopped buying food (끊다 homonym), not office",
        "38269#0": "기사님, 이 버스가 시청에 가나요? = a bus driver (기사 homonym: article / driver)",
        "62839#18": "영화 표 미리 끊을까? = movie tickets, not office",
        "62839#17": "천천히 끊어 읽어 줄게 = reading in chunks (끊다), not office",
        "61058#0": "아름다워진 비결 = a beauty secret, not office",
        "72882#1": "사람 목숨이 어디 인력으로 되나요? = life and death (인력 homonym)",
        "48995#4": "춤을 배우기 시작한 동기 = a dance motive (동기 homonym)",
        "55825#1": "생사를 건 모험 = a life-or-death adventure",
        "64685#4": "맡기신 가방 = a cloakroom bag, not office",
        "56351#5": "마당에서 바깥일 = yard work",
        "75463#0": "제대까지 = military discharge",
        "61303#1": "사적 권리 침해 = a legal-rights line, not office talk",
        "15676#0": "일차 산업 = a school-style economics question",
        "27765#0": "인공 지능을 가진 로봇 = robots, not office",
        "58299#0": "교재 구했어? 도서관에 = school, not office",
        "62839#28": "요가 학원을 끊었어 = signed up for yoga (끊다), not office",
        "14013#0": "선생님께 급히 오라는 연락 = school, not office",
        "64540#1": "어른들이 부르시면 대답을 = parenting, not office",
        "70089#0": "장래 희망 = a school question, not office",
        "62839#0": "이 끈 좀 끊어라 = cutting a string (끊다)",
    },
    "casual": {
        "57323#48": "점을 치고 = fortune-telling idiom (치다), odd as a first practice line",
        "62819#1": "숨을 크게 한번 쉬어 보세요. = a doctor's instruction, not casual talk",
    },
    "bar_restaurant": {
        "56181#0": "물고기 키우고 싶어요 = a pet fish (물 substring)",
        "31685#2": "고기 좀 잡으셨어요? = fishing (고기 = fish here)",
        "66228#11": "맛이 간 거 = slang for 'gone crazy' (맛 idiom)",
        "16488#5": "쓰다 달다 말이 없어 = idiom 'says nothing at all'",
        "57275#4": "저 갈비는 누구야? = 갈비 as a nickname for a skinny person",
        "57306#0": "무슨 사탕을 그렇게 많이 샀어? = candy shopping, not a bar or restaurant",
        "17371#2": "내 잔을 받게 = 하게체 (an older style, not 반말; 하오체 is dropped the same way)",
        "27372#4": "회의 전에 커피 준비해 놓을까요? = office prep, not a bar or restaurant",
        "57275#3": "갈비에 금만 조금 갔대요 = a cracked rib (갈비 homonym)",
        "70811#0": "소리가 아주 맛있게 들리는데요? = a sound, not food",
        "15631#5": "자리 비우셨어요 = away from the desk (비우다)",
        "30204#5": "땀이 식지 않아 = sweat, not food (식다)",
        "64682#3": "시원한 공기를 좀 마시고 = fresh air, not a drink",
        "65343#1": "신선한데? 이 디자인으로 = a fresh design (신선하다)",
        "57411#1": "퇴근하는 길에 밀가루를 좀 사 와 = grocery shopping",
        "77501#0": "집들이 선물로 젓가락 = a housewarming gift, not eating out",
    },
}


def count(cands):
    """{speech level: {source: number of lines}}"""
    out = {}
    for c in cands:
        out.setdefault(c["speech"], Counter())[c["source"]] += 1
    return {level: dict(n) for level, n in out.items()}


def korean_tags(text):
    """Target sounds in a line from OUR G2P, or None if G2P can't read it (then /analyze couldn't score it)."""
    from content.build_dev_pack import flat_phonemes, korean_tags as tags_of
    try:
        phonemes = flat_phonemes(text, "ko")
    except Exception:  # noqa: BLE001 - any G2P failure means "not usable", never a crash of the whole build
        return None
    return tags_of(phonemes) if phonemes else None


def _entry(c):
    """krdict 'code#i' -> 'krdict:code' (one dialogue); other sources: every row is its own entry."""
    sid = c["source_id"]
    return f"krdict:{sid.split('#')[0]}" if c["source"] == "krdict" else f"{c['source']}:{sid}"


ANSWER_RE = re.compile(r"^(응|네|예|아니요|아니|아뇨|그래|맞아|그럼)\s*[.,!?~]")


def is_answer(text):
    """Starts like a reply (응. / 네, / 아니, ...): it needs the question before it to make sense."""
    return bool(ANSWER_RE.match(text.strip()))


def uses_headword(c):
    """krdict: does the line contain the dictionary word (verbs: the stem, 끝나다 -> 끝나; 신선하다 -> 신선)?
    Plain substring, so irregular forms (바꾸다 -> 바꿔) are missed: those just rank lower, they're not dropped."""
    if c["source"] != "krdict":
        return True
    word = c.get("context", "")
    stem = word[:-2] if word.endswith("하다") and len(word) > 2 else word[:-1] if word.endswith("다") and len(word) > 1 else word
    return bool(stem) and stem in c["text"].replace(" ", "")


def _static_key(c, pack=None):
    return (SOURCE_ORDER.index(c["source"]) if c["source"] in SOURCE_ORDER else len(SOURCE_ORDER),
            not uses_headword(c),
            GRADE_ORDER.get(c.get("grade"), 2) if c["source"] == "krdict" else 0,
            is_answer(c["text"]),
            pack == "casual" and c.get("style") == "formal")


def _pick_level(cands, n, tag_fn, look=LOOK, pack=None, exclude=()):
    cands = [c for c in cands if c["source_id"] not in exclude]
    # G2P is slow (~thousands of casual lines), so only the best `look` lines by source, grade and length get tagged.
    cands = sorted(cands, key=lambda c: (*_static_key(c, pack), abs(c.get("syllables", TARGET_LEN) - TARGET_LEN),
                                         c["source_id"]))[:look]
    pool = []
    for c in cands:
        tags = tag_fn(c["text"])
        if tags:
            pool.append({**c, "tags": tags})
    picked, have, used = [], set(), set()
    while len(picked) < n:
        pool = [c for c in pool if _entry(c) not in used]
        if not pool:
            break
        best = min(pool, key=lambda c: (
            *_static_key(c, pack),
            -len(set(c["tags"]) - have),
            abs(c.get("syllables", TARGET_LEN) - TARGET_LEN),
            c["source_id"]))
        picked.append(best)
        have |= set(best["tags"])
        used.add(_entry(best))
    return picked


def pick(cands, n=10, tag_fn=korean_tags, pack=None, exclude=None):
    """{level: [up to n picked lines, each with its tags]} for both levels. `exclude` = source ids to skip
    (default: this pack's EXCLUDE list)."""
    exclude = set(EXCLUDE.get(pack, {}) if exclude is None else exclude)
    return {level: _pick_level([c for c in cands if c["speech"] == level], n, tag_fn, pack=pack, exclude=exclude)
            for level in LEVELS}


def gaps(picks, n=10):
    """How many lines each level is short of n (0 = no gap)."""
    return {level: max(0, n - len(picks.get(level, []))) for level in LEVELS}


def build_files(report, translations=TRANSLATIONS):
    """{pack: the app's pack dict} from the picks report. Writes nothing. KeyError if a line has no translation."""
    packs = {}
    for name, entry in report.items():
        lines = [line for level in LEVELS for line in entry["picks"].get(level, [])]   # 존댓말 first, then 반말
        missing = [line["source_id"] for line in lines if line["source_id"] not in translations]
        if missing:
            raise KeyError(f"{name}: no English translation for {', '.join(missing)} (content/ko_translations.py)")
        items = [{"id": f"ko_{name}_{i:02d}",
                  **{k: translations[line["source_id"]] if k == "translation" else line[k] for k in ITEM_KEYS}}
                 for i, line in enumerate(lines, 1)]
        sources = sorted({it["credit"] for it in items})
        licenses = sorted({it["license"] for it in items})
        packs[name] = {"id": "ko-" + name.replace("_", "-"), "lang": "ko", "name": NAMES[name],
                       "dev_only": False, "reviewed": False,
                       "source": (f"Native example lines from {'; '.join(sources)}, unmodified (source per line). "
                                  "English translations LLM-written (Claude, Anthropic), not checked by a native "
                                  "Korean speaker."),
                       "license": f"{', '.join(licenses)} (per line)",
                       "items": items}
    return packs


def main():
    report = {}
    print(f"{'pack':<15}{'level':<6}{'native lines by source':<52}{'picked':>7}{'gap':>5}")
    for pack in PACKS:
        cands = json.loads((OUT / f"{pack}.json").read_text(encoding="utf-8"))
        counts, picks = count(cands), pick(cands, pack=pack)
        report[pack] = {"counts": counts, "gaps": gaps(picks), "picks": picks}
        for level in LEVELS:
            by_src = ", ".join(f"{s} {counts.get(level, {}).get(s, 0)}" for s in SOURCE_ORDER)
            print(f"{pack:<15}{level:<6}{by_src:<52}{len(picks[level]):>7}{report[pack]['gaps'][level]:>5}")
    (OUT / "picks.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, pack in build_files(report).items():
        path = PACK_FILES / f"ko_{name}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: {len(pack['items'])} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
