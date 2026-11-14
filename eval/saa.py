"""The Speech Accent Archive's Korean speakers as a SECOND, independent R/L test set.

In brief: 26 Korean speakers read the same paragraph, and a phonetician wrote down (in IPA) exactly what each
one said. We line that transcription up with the sounds the paragraph SHOULD have, which tells us, for every R
and L, whether the speaker got it right ("correct"), swapped it ("error"), tapped it like Korean ㄹ ("tap", kept
apart: a tap is neither English R nor L), or dropped it ("deleted"). Then we run our own pipeline on the same recording and see
whether the app's red/green agrees with the phonetician. The thresholds are NOT tuned here: they come from the
same 20 non-Korean L2-ARCTIC speakers as before, so this set is a clean test.

Lining up two sound lists = edit distance (like backend/sequence_align.py), but with PHONETIC costs: swapping two
liquids (l, ɹ, ɾ) is cheap, so an L said as R lines up as a swap instead of "L dropped + R added".

The same idea for ALL 1,244 transcribed speakers (every first language, data/saa_all/ from OSF) and
EVERY English MVP pair: F/P, V/B, TH (θ said as s/t, ð said as d/t), ship/sheep (ɪ/iː), and an extra vowel after a
final consonant ('siksə'). Korean speakers = test group, everyone else (native English speakers too) = tuning group.

Run:
  python -m eval.saa_fetch --audio-from DIR     (once: pages + audio -> data/saa/)
  python -m eval.saa --run                      (pipeline on the 26 labelled recordings -> data/cache/eval_saa.csv)
  python -m eval.saa                            (report from the cache -> results/saa.json)
  python -m eval.saa --set all --run            (all languages -> data/cache/eval_saa_all.csv; resumable)
  python -m eval.saa --set all                  (label counts per pair and group, from that cache)
  python -m eval.saa --set all --features       (detector features -> data/cache/saa_all_features.csv)
"""
import argparse
import csv
import json
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from eval.listener import keep_speaker, tagged

ROOT = Path(__file__).resolve().parents[1]
SPEAKERS = ROOT / "data" / "saa" / "speakers.csv"
AUDIO = ROOT / "data" / "saa" / "audio"
CACHE = ROOT / "data" / "cache" / "eval_saa.csv"
RESULTS = ROOT / "results" / "saa.json"
# The all-languages download (eval/saa_osf.py). align/ keeps every sound's start/end per speaker, so later
# waveform features (formants for ship/sheep, ...) can be measured without re-running the neural network.
SETS = {"korean": dict(speakers=SPEAKERS, audio=AUDIO, cache=tagged(CACHE), align=None),   # tagged(): own folder per listener
        "all": dict(speakers=ROOT / "data" / "saa_all" / "speakers.csv", audio=ROOT / "data" / "saa_all" / "audio",
                    cache=tagged(ROOT / "data" / "cache" / "eval_saa_all.csv"),
                    align=tagged(ROOT / "data" / "cache" / "saa_all_align"),
                    summary=ROOT / "results" / "saa_all_labels.json")}
EV = "extra_vowel"  # == backend.scoring.EXTRA_VOWEL (not imported here: that pulls in the neural network)
HISS = ("v", "ð", "θ", "f")  # sounds that get the hiss + closure-dip numbers (l2arctic.vb_features)
PARAGRAPH = ("Please call Stella. Ask her to bring these things with her from the store: Six spoons of fresh snow "
             "peas, five thick slabs of blue cheese, and maybe a snack for her brother Bob. We also need a small "
             "plastic snake and a big toy frog for the kids. She can scoop these things into three red bags, and we "
             "will go meet her Wednesday at the train station.")
RL = ("r_as_l", "l_as_r")
PAIRS_SAA = RL + ("v_as_b",)  # plus V said as B

# ---------- 1. cutting an IPA string into sounds ----------
MODIFIERS = set("ːˑ˺ʰʷʲˀʼⁿˡ̚")   # written after a sound, belong to it
SKIP = set(" .,|‖()[]/-‿")
AFFRICATE = {"ʧ": "tʃ", "ʤ": "dʒ", "ʦ": "ts", "ʣ": "dz"}
R_COLOUR = "˞"


def segments(ipa):
    """'bɹĩŋ' -> ['b', 'ɹ', 'ĩ', 'ŋ']. Diacritics stay on their sound; t+ʃ -> tʃ; a ˞ becomes its own piece."""
    out, joinable = [], False  # joinable: the previous piece may still take a ʃ/ʒ (no space in between)
    for ch in unicodedata.normalize("NFD", ipa):
        if ch in SKIP:
            joinable = False
            continue
        if (unicodedata.combining(ch) or ch in MODIFIERS) and out and out[-1] != R_COLOUR:
            out[-1] += ch
            continue
        if ch in "ʃʒ" and joinable and _strip(out[-1]) in ("t", "d"):
            out[-1] = _strip(out[-1]) + ch
            continue
        out.append(AFFRICATE.get(ch, "ɡ" if ch == "g" else ch))
        joinable = True
    return [unicodedata.normalize("NFC", s) for s in out]


def _strip(seg):
    """The bare sound: diacritics and length marks dropped ('iː' -> 'i', 'd̥' -> 'd', 'tʃ' stays)."""
    return "".join(c for c in unicodedata.normalize("NFD", seg) if not unicodedata.combining(c) and c not in MODIFIERS)


# ---------- 2. phonetic costs ----------
R_LIKE = {"ɹ", "r", "ɻ", "ʁ", R_COLOUR}
L_LIKE = {"l", "ɫ", "ɭ", "ʎ"}
TAP = {"ɾ", "ɽ"}
GROUPS = [R_LIKE | L_LIKE | TAP, set("pbtdkɡʔqcɟ"), set("fvθðszʃʒhɸβxçɣɦ"), {"tʃ", "dʒ", "ts", "dz"},
          set("mnŋɲ"), set("wjɥ")]
VOWELS = set("aeiouæɑɒɔəɚɝɛɜɪʊʌɯɤøœyʏɐɘɵɨʉ")


def _kind(base):
    return "V" if base[:1] in VOWELS else "C"


def _swap(a, b):
    if a == b:
        return 0.0
    if _kind(a) != _kind(b):
        return 1.6  # dearer than drop + add, so a consonant never lines up with a vowel
    if _kind(a) == "V":
        return 0.4  # vowel quality varies a lot between speakers and transcribers
    if any(a in g and b in g for g in GROUPS):
        return 0.3 if a in GROUPS[0] else 0.5
    return 1.0


def _indel(base):
    return 0.5 if _kind(base) == "V" else 1.0  # extra/dropped vowels (epenthesis, 'siksə') are common


def _align(expected, heard):
    """Edit distance on bare sounds -> for each expected index, the heard index it lines up with (or None)."""
    return _dp(expected, heard)[1]


def _dp(expected, heard):
    """-> (total cost, {expected index: heard index or None})."""
    n, m = len(expected), len(heard)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = cost[i - 1][0] + _indel(expected[i - 1])
    for j in range(1, m + 1):
        cost[0][j] = cost[0][j - 1] + _indel(heard[j - 1])
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i - 1][j - 1] + _swap(expected[i - 1], heard[j - 1]),
                             cost[i - 1][j] + _indel(expected[i - 1]), cost[i][j - 1] + _indel(heard[j - 1]))
    pairs, i, j = {}, n, m
    while i > 0 or j > 0:  # walk back from the corner
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + _swap(expected[i - 1], heard[j - 1]):
            pairs[i - 1], i, j = j - 1, i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + _indel(expected[i - 1]):
            pairs[i - 1], i = None, i - 1
        else:
            j -= 1
    return cost[n][m], pairs


MERGE = 0.2  # 2 expected words in 1 written word ('wiɔlsə' = we also): common in transcriptions, cheap
SPLIT = 1.0  # 1 expected word written as 2 ('wɛnz deɪ'): rare, so dearer (else it swallows restarts)
EXTRA_WORD = 0.5  # an extra written word (a restart like 'pɹɔɡ̥ pɹak˺', a filler) costs half per sound


def _word_groups(exp_words, heard_words):
    """Line up WORDS first (so a restart like 'pɹɔɡ̥ pɹak˺' = an extra word, never a source of sounds for its
    neighbours). Moves: 1:1, 2:1 merge, 1:2 split, expected word dropped, extra written word.
    -> list of (expected word indexes, heard word indexes) that belong together."""
    n, m = len(exp_words), len(heard_words)
    memo = {}

    def d(ei, hj):  # cost of saying expected words ei as written words hj
        key = (ei, hj)
        if key not in memo:
            memo[key] = _dp([s for i in ei for s in exp_words[i]], [s for j in hj for s in heard_words[j]])[0]
        return memo[key]

    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] == INF:
                continue
            moves = [(1, 1, 0.0), (2, 1, MERGE), (1, 2, SPLIT), (1, 0, None), (0, 1, None)]
            for di, dj, extra in moves:
                if i + di > n or j + dj > m:
                    continue
                ei, hj = tuple(range(i, i + di)), tuple(range(j, j + dj))
                if extra is None:  # a dropped expected word, or an extra written word
                    c = sum(_indel(s) for k in ei for s in exp_words[k]) + EXTRA_WORD * sum(_indel(s) for k in hj for s in heard_words[k])
                else:
                    c = d(ei, hj) + extra
                if cost[i][j] + c < cost[i + di][j + dj]:
                    cost[i + di][j + dj], back[i + di][j + dj] = cost[i][j] + c, (i, j, ei, hj)
    groups, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj, ei, hj = back[i][j]
        groups.append((ei, hj))
        i, j = pi, pj
    return groups[::-1]


# ---------- 3. labels for every checked sound ----------
# target sound -> (what counts as RIGHT, what counts as THIS pair's mistake). Anything else = "other" (a different
# mistake, e.g. TH said as F, or ɸ for F: neither English F nor P), kept out of both counts like in L2-ARCTIC.
RULES = {
    "ɹ": (R_LIKE, L_LIKE),
    "l": (L_LIKE, R_LIKE),          # a tap [ɾ] for either is its own label, "tap"
    "v": ({"v"}, {"b"}),            # f (devoiced), β, ʋ, p -> other
    "f": ({"f"}, {"p"}),            # all-languages set from here on
    "θ": ({"θ"}, {"s", "t"}),       # dental t̪ strips to t = a T
    "ð": ({"ð"}, {"d", "t"}),       # a weak ð̞ strips to ð = right
    "ɪ": ({"ɪ", "ᵻ", "ɨ"}, {"i"}),  # ship said as sheep
    "iː": ({"i"}, {"ɪ"}),           # sheep said as ship (length marks are stripped: iː = i)
}
V_LIKE, B_LIKE = RULES["v"]  # (old names, kept for anyone importing them)


def _label(target, heard):
    if heard is None:
        return "deleted", ""
    b = _strip(heard)
    good, bad = RULES[target]
    if b in good:
        return "correct", b
    if b in bad:
        return "error", b
    if target in ("ɹ", "l") and b in TAP:
        return "tap", b
    return "other", b


def _label_extra(k, match, heard, expected):
    """Extra-vowel check for the word-final consonant at expected index k: did the transcriber write a vowel after
    it that lines up with NO expected sound? ('siksə' -> error; 'nidə' for 'need a' -> no, that ə is the word 'a')."""
    h = match.get(k)
    if h is None:
        return "deleted", ""
    nxt = next((match[j] for j in range(k + 1, len(expected)) if match.get(j) is not None), len(heard))
    extra = [heard[j] for j in range(h + 1, nxt) if _kind(_strip(heard[j])) == "V"]
    if extra:
        return "error", "".join(extra)
    b = _strip(heard[h])
    same = b == expected[k] or any(b in g and expected[k] in g for g in (R_LIKE, L_LIKE))  # stɔ˞ = store's R
    return ("correct", b) if same else ("other", b)  # a changed final sound: a different question


def group_of(language):
    """Korean speakers are the test group; every other first language (English too) is for tuning."""
    return "korean" if language == "korean" else "others"


def label_slots(words, transcription):
    """-> {(word_index, phoneme_index): (label, transcribed sound)} for every expected sound in RULES, and
    {(word_index, phoneme_index, EV): (label, detail)} for every word-final consonant (the extra-vowel check)."""
    from backend.sequence_align import is_vowel  # the same vowel test the app's extra-vowel candidates use

    def bare(ipa):
        return ipa if ipa in ("tʃ", "dʒ") else _strip(segments(ipa)[0])

    def ipa_of(p):  # G2P output has plain strings; aligned words have dicts
        return p["ipa"] if isinstance(p, dict) else p

    exp_words = [[bare(ipa_of(p)) for p in w["phonemes"]] for w in words]
    heard_raw = [segments(tok) for tok in transcription.split()]
    heard_raw = [h for h in heard_raw if h]
    heard_words = [[_strip(s) for s in h] for h in heard_raw]
    out = {}
    for ei, hj in _word_groups(exp_words, heard_words):
        slots = [(wi, pi, ipa_of(p)) for wi in ei for pi, p in enumerate(words[wi]["phonemes"])]
        expected = [s for wi in ei for s in exp_words[wi]]
        heard = [s for j in hj for s in heard_raw[j]]
        match = _align(expected, [_strip(s) for s in heard]) if heard else {}
        for k, (wi, pi, ipa) in enumerate(slots):
            if ipa in RULES:
                out[(wi, pi)] = _label(ipa, heard[match[k]] if match.get(k) is not None else None)
            if pi == len(words[wi]["phonemes"]) - 1 and not is_vowel(ipa):
                out[(wi, pi, EV)] = _label_extra(k, match, heard, expected)
    return out


# ---------- 4. the pipeline on one recording ----------
FIELDS = ["group", "language", "speaker", "utt", "word", "word_index", "phoneme_index", "pair", "target", "human",
          "human_detail", "margin", "heard_agrees", "op", "heard", "baseline_flag", "start", "end", "f3", "f3_dip",
          "fric", "closure", "seconds", "duration"]


def _blank(x, nd=None):
    return "" if x is None else (round(x, nd) if nd is not None else x)


def run_speaker(sid, transcription, audio_dir=AUDIO, group="saa", language="korean", align_dir=None):
    import soundfile as sf
    from backend.align import align, emissions
    from backend.compare import attach_heard
    from backend.g2p import expected_phonemes
    from backend.recognize import recognize
    from backend.scoring import candidates
    from backend.acoustics import f3_dip, rl_f3, vb_features  # the same features the app and L2-ARCTIC eval use

    audio, sr = sf.read(Path(audio_dir) / f"{sid}.mp3", dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    t0 = time.perf_counter()
    expected = expected_phonemes(PARAGRAPH, "en")
    em = emissions(audio, sr)
    words, _ = attach_heard(align(em, expected, "en"), recognize(em), "en")
    cands = candidates(em, words, "en")
    seconds = time.perf_counter() - t0
    f3_of, ref = rl_f3(audio, sr, words)
    hiss = vb_features(audio, sr, words, targets=HISS)
    labels = label_slots(expected, transcription)
    if align_dir:  # every sound's times, for features measured later without the network
        Path(align_dir).mkdir(parents=True, exist_ok=True)
        keep = ("ipa", "start", "end", "op", "heard")
        (Path(align_dir) / f"{sid}.json").write_text(json.dumps(
            [{"word": w["word"], "phonemes": [{k: p.get(k) for k in keep} for p in w["phonemes"]]} for w in words],
            ensure_ascii=False))
    rows = []
    for c in cands:
        key = (c["word_index"], c["phoneme_index"])
        p = words[key[0]]["phonemes"][key[1]]
        ev = c["pair"] == EV
        human, detail = labels.get(key + (EV,) if ev else key, ("unlabelled", ""))
        f3 = f3_of.get(key) if c["pair"] in RL else None
        fc = hiss.get(key, {}) if not ev and p["ipa"] in HISS else {}
        rows.append(dict(group=group, language=language, speaker=sid, utt="paragraph", word=words[key[0]]["word"],
                         word_index=key[0], phoneme_index=key[1], pair=c["pair"], target=p["ipa"], human=human,
                         human_detail=detail, margin=c["margin"], heard_agrees=int(c["heard_agrees"]), op=p["op"],
                         heard=p["heard"] or "",
                         baseline_flag=int(bool(p.get("extra_after")) if ev else p["op"] != "match"),
                         start=round(p["start"], 3), end=round(p["end"], 3), f3=_blank(f3, 1),
                         f3_dip=_blank(f3_dip(f3, ref)), fric=_blank(fc.get("fric")),
                         closure=_blank(fc.get("closure"))))
    return rows, seconds, len(audio) / sr


def run_all(which="korean"):
    """Resumable: speakers already in the cache are skipped, so a stopped run just carries on."""
    cfg = SETS[which]
    speakers = [r for r in csv.DictReader(open(cfg["speakers"], encoding="utf-8")) if r["transcription"]
                and keep_speaker("saa", r["speaker"], r.get("language", "korean") == "korean")]
    cache = cfg["cache"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = {r["speaker"] for r in csv.DictReader(open(cache, encoding="utf-8"))} if cache.exists() else set()
    todo = [s for s in speakers if s["speaker"] not in done]
    print(f"{len(speakers)} speakers, {len(done)} already cached, {len(todo)} to run", flush=True)
    start, failed = time.time(), []
    with open(cache, "a", newline="", encoding="utf-8") as f:
        out = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if not done:
            out.writeheader()
        for i, s in enumerate(todo, 1):
            lang = s.get("language", "korean")
            try:
                rows, sec, dur = run_speaker(s["speaker"], s["transcription"], cfg["audio"],
                                             "saa" if which == "korean" else group_of(lang), lang, cfg["align"])
            except Exception as e:  # one bad file must not stop a 40-minute run; it is listed at the end
                failed.append(s["speaker"])
                print(f"FAILED {s['speaker']}: {type(e).__name__}: {e}", flush=True)
                continue
            out.writerows({**r, "seconds": round(sec, 3), "duration": round(dur, 1)} for r in rows)
            f.flush()
            print(f"[{i}/{len(todo)}] {s['speaker']}: {dur:.0f} s audio, {sec:.1f} s pipeline", flush=True)
    print(f"done: {len(todo) - len(failed)} speakers in {time.time() - start:.0f} s -> {cache}; failed: {failed}")


# ---------- 5. the report ----------
def _load_saa(path=CACHE):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        r["margin"] = float(r["margin"])
        r["heard_agrees"] = r["heard_agrees"] == "1"
        r["baseline_flag"] = r["baseline_flag"] == "1"
        for f in ("f3_dip", "fric", "closure"):
            r[f] = float(r[f]) if r.get(f) not in ("", None) else None
    return rows


def report():
    from eval import run as ev

    saa, l2 = _load_saa(), ev.load()
    out = {"data": "Speech Accent Archive (accent.gmu.edu, CC BY-NC-SA 4.0): Korean speakers with a narrow IPA "
                   "transcription; thresholds tuned on the 20 non-Korean L2-ARCTIC speakers (eval/run.py)",
           "speakers": len({r["speaker"] for r in saa}), "pairs": {}}
    for pair in PAIRS_SAA:
        s_rows = [r for r in saa if r["pair"] == pair]
        tune = [r for r in l2 if r["pair"] == pair and r["group"] == "others"]
        l2_ko = [r for r in l2 if r["pair"] == pair and r["group"] == "korean"]
        as_test = [{**r, "group": "korean"} for r in s_rows]
        cap = ev.cap_for(pair)
        res = {"labels (saa)": dict(Counter(r["human"] for r in s_rows)),
               "saa": ev.evaluate_pair(tune + as_test, cap),
               "pooled (saa + l2arctic korean)": ev.evaluate_pair(tune + as_test + l2_ko, cap)}
        t = {k: res["saa"][k] for k in ("variant", "feature", "margin", "m_lo", "dip") if k in res["saa"]}
        taps = [r for r in s_rows if r["human"] == "tap"]
        res["taps flagged (saa)"] = ev.rate(sum(ev.flag_t(r, t) for r in taps), len(taps))
        for v in ("A", "B"):  # for information only: NOT what decides the pass bar
            m = ev.pick_margin([r for r in tune if r["human"] == "correct"], v, cap)
            c = [r for r in as_test if r["human"] == "correct"]
            e = [r for r in as_test if r["human"] == "error"]
            res[f"info: variant {v} (saa)"] = {"margin": m, "caught": ev.rate(*ev.count(e, v, m)),
                                               "false_alarms": ev.rate(*ev.count(c, v, m))}
        out["pairs"][pair] = res
    labelled = Counter(r["human"] for r in saa)
    n = sum(labelled.values())
    out["labelling sanity"] = {"slots": n, "share labelled (not deleted/other)":
                               round(1 - (labelled["deleted"] + labelled["other"]) / n, 4) if n else None}
    secs = sorted({(r["speaker"], float(r["seconds"]), float(r["duration"])) for r in saa})
    out["pipeline seconds per recording"] = {"median": sorted(s for _, s, _ in secs)[len(secs) // 2],
                                             "audio seconds median": sorted(d for _, _, d in secs)[len(secs) // 2]}
    RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))


def summary():
    """How many right / wrong / other slots each pair has in each group (no tuning, no scores yet)."""
    cfg = SETS["all"]
    rows = _load_saa(cfg["cache"])
    out = {"data": "Speech Accent Archive, all first languages (OSF osf.io/yh23d, CC BY-NC-SA 4.0), labels read "
                   "from the narrow IPA transcriptions by eval/saa.py",
           "speakers": dict(Counter(g for g, _ in {(r["group"], r["speaker"]) for r in rows})),
           "languages": len({r["language"] for r in rows}), "labels": {}}
    for pair in sorted({r["pair"] for r in rows}):
        out["labels"][pair] = {g: dict(Counter(r["human"] for r in rows if r["pair"] == pair and r["group"] == g))
                               for g in ("korean", "others")}
    lab = Counter(r["human"] for r in rows)
    out["labelling sanity"] = {"slots": sum(lab.values()), **dict(lab)}
    secs = sorted({(r["speaker"], float(r["seconds"])) for r in rows})
    out["pipeline seconds per recording (median)"] = sorted(s for _, s in secs)[len(secs) // 2] if secs else None
    cfg["summary"].write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))


def show(sid, which="korean"):
    """Hand check: every R/L slot of one speaker with its label."""
    by = defaultdict(list)
    for r in csv.DictReader(open(SETS[which]["cache"], encoding="utf-8")):
        if r["speaker"] == sid:
            by[r["pair"]].append(f"{r['word']}:{r['human']}({r['human_detail']})")
    for pair, items in by.items():
        print(f"{sid} {pair}: " + "  ".join(items))


# ---------- the shared detector features, from the SAVED times (no neural network) ----------
SAA_FEATURES = tagged(ROOT / "data" / "cache" / "saa_all_features.csv")


def saa_feature_rows(sid, words, audio, sr):
    """One speaker's saved alignment (align/<sid>.json) + audio -> one row per sound with the x_ columns."""
    from backend.features import sound_features
    from eval.detectors import x_columns
    feats = sound_features(audio, sr, words)
    return [{"speaker": sid, "word_index": wi, "phoneme_index": pi, **x_columns(f)}
            for (wi, pi), f in sorted(feats.items())]


def feature_pass(which="all"):
    """Resumable: speakers already in the features file are skipped."""
    import soundfile as sf
    from eval.detectors import X_COLS
    cfg = SETS[which]
    sids = sorted(f.stem for f in Path(cfg["align"]).glob("*.json"))
    done = ({r["speaker"] for r in csv.DictReader(open(SAA_FEATURES, encoding="utf-8"))}
            if SAA_FEATURES.exists() else set())
    todo = [s for s in sids if s not in done]
    print(f"{len(sids)} aligned speakers, {len(done)} done, {len(todo)} to measure", flush=True)
    start, failed = time.time(), []
    with open(SAA_FEATURES, "a", newline="", encoding="utf-8") as f:
        out = csv.DictWriter(f, fieldnames=["speaker", "word_index", "phoneme_index", *X_COLS])
        if not done:
            out.writeheader()
        for i, sid in enumerate(todo, 1):
            try:
                words = json.loads((Path(cfg["align"]) / f"{sid}.json").read_text())
                audio, sr = sf.read(Path(cfg["audio"]) / f"{sid}.mp3", dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                out.writerows(saa_feature_rows(sid, words, audio, sr))
            except Exception as e:  # one bad file must not stop the run; listed at the end
                failed.append(sid)
                print(f"FAILED {sid}: {type(e).__name__}: {e}", flush=True)
                continue
            f.flush()
            if i % 50 == 0:
                print(f"[{i}/{len(todo)}] {time.time() - start:.0f} s", flush=True)
    print(f"done: {len(todo) - len(failed)} speakers in {time.time() - start:.0f} s -> {SAA_FEATURES}; "
          f"failed: {failed}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="run the pipeline first (slow)")
    ap.add_argument("--set", choices=list(SETS), default="korean", help="korean = the 26 Korean speakers; all = every language")
    ap.add_argument("--show", nargs="*", help="print the labels of these speakers")
    ap.add_argument("--features", action="store_true", help="detector features from the saved times")
    args = ap.parse_args()
    if args.features:
        feature_pass(args.set)
        raise SystemExit
    if args.run:
        run_all(args.set)
    if args.show:
        for sid in args.show:
            show(sid, args.set)
    elif args.set == "all":
        summary()
    else:
        report()
