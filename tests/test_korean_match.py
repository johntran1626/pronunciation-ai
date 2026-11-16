"""Korean "did you say it?" checks: the Korean-trained listener's evidence, the made-up edits, and the bars."""
import random
from pathlib import Path

import pytest

from backend.g2p import expected_phonemes
from backend.korean_listener import pool_evidence, sentence_evidence
from eval.korean_match import BARS, decide, plan_edits

FIXTURE = Path("tests/fixtures/zeroth_126_003_2058.wav")
TEXT = "강아지가 용변을 보도록 유도하는 말을 가르칠 수도 있다"


# ---------- evidence, pooled per word (same shape as backend/match.py's features) ----------
def test_pool_evidence_counts_each_model_symbol_once_and_averages_per_word():
    # word 0: two symbols (one of them a glide+vowel symbol covering 2 phonemes); word 1: one symbol, not heard
    pairs = [("G", [(0, 0)]), ("iA", [(0, 1), (0, 2)]), ("N", [(1, 0)])]
    per = pool_evidence(pairs, scores=[0.8, 0.4, 0.1], in_place=["G", "A", None], n_words=3)
    assert per[0] == {"n": 2, "heard": 0.5, "missing": 0.0, "conf": pytest.approx(0.6)}
    assert per[1] == {"n": 1, "heard": 0.0, "missing": 1.0, "conf": pytest.approx(0.1)}
    assert per[2] == {"n": 0, "heard": 0.0, "missing": 0.0, "conf": 0.0}       # a word with no sounds (digits)


def test_sentence_evidence_weights_words_by_their_symbols():
    s = sentence_evidence([{"n": 3, "heard": 1.0, "missing": 0.0, "conf": 0.9},
                           {"n": 1, "heard": 0.0, "missing": 1.0, "conf": 0.1}])
    assert s == {"n": 4, "heard": 0.75, "missing": 0.25, "conf": pytest.approx(0.7)}
    assert sentence_evidence([])["n"] == 0


# ---------- the made-up mistakes ----------
def test_plan_edits_is_repeatable_and_really_changes_the_text():
    pool = ["사과", "바나나", "포도", "가르칠"]
    a = plan_edits(random.Random("x"), TEXT, pool)
    b = plan_edits(random.Random("x"), TEXT, pool)
    assert a == b                                            # same seed, same edits (resumable runs agree)
    words = TEXT.split()
    assert 0 <= a["swap_index"] < len(words) and 0 <= a["cut_index"] < len(words)
    assert a["swap_word"] != words[a["swap_index"]]
    assert a["swapped"].split()[a["swap_index"]] == a["swap_word"]


# ---------- the bars, fixed before the run ----------
def _m(nat_sent=0.005, noise_all=True, other=0.9, nat_word=0.002, catch=0.4, lrn_sent=0.01, lrn_word=0.005):
    return {"sentence": {"natives_rejected": nat_sent, "noise_all_rejected": noise_all, "other_caught": other,
                         "learners_rejected": lrn_sent},
            "word": {"natives_false": nat_word, "caught": catch, "learners_false": lrn_word}}


def test_bars_are_the_ones_agreed_before_the_run():
    assert BARS == {"natives_rejected": 0.01, "other_caught": 0.5, "learners_rejected": 0.02,
                    "natives_false_word": 0.005, "caught_word": 0.25, "learners_false_word": 0.01}


def test_decide_grades_hints_or_turns_off():
    assert decide(_m()) == {"sentence": "grade", "word": "grade"}
    assert decide(_m(lrn_sent=0.05, lrn_word=0.03)) == {"sentence": "hint", "word": "hint"}   # natives fine, learners not
    assert decide(_m(nat_sent=0.02))["sentence"] == "off"
    assert decide(_m(noise_all=False))["sentence"] == "off"
    assert decide(_m(other=0.3))["sentence"] == "off"
    assert decide(_m(nat_word=0.01))["word"] == "off"
    assert decide(_m(catch=0.1))["word"] == "off"


# ---------- the real Korean-trained listener on a committed native recording ----------
@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_live_korean_listener_hears_the_native_reading_and_not_a_swapped_word():
    import soundfile as sf
    from backend.korean_listener import emissions, word_evidence
    audio, sr = sf.read(FIXTURE, dtype="float32")
    lp = emissions(audio, sr)
    per, n_heard = word_evidence(lp, expected_phonemes(TEXT, "ko"))
    assert n_heard > 20
    assert sentence_evidence(per)["heard"] > 0.6
    swapped = TEXT.replace("가르칠", "바나나")
    per2, _ = word_evidence(lp, expected_phonemes(swapped, "ko"))
    k = TEXT.split().index("가르칠")
    assert per2[k]["heard"] < per[k]["heard"]


def test_learner_groups_by_rating_keep_the_top_rated_name():
    from eval.korean_match import learner_group
    assert learner_group(3) == "learners"          # 상: the group the bars are judged on (unchanged)
    assert learner_group(2) == "learners_2"        # 중
    assert learner_group(1) == "learners_1"        # 하
