"""Readers for speechocean762 and the L2-ARCTIC suitcase corpus.
No audio or data/ needed: the label formats are typed in (copied from the real files)."""
from eval.extra_corpora import so_human, so_word_labels, suitcase_segments, textgrid_tiers


# ---------- speechocean762: 5 experts per sound -> one L2-ARCTIC-style label ----------
def test_majority_of_experts_decides():
    # from utterance 000010011 'CALL': 2 of 5 experts heard an accent, 3 heard it fine -> correct
    w = {"ref-phones": "K AO0 L", "phones": ["K AO0 L", "K {AO0} L", "K AO0 L", "K AO0 L", "K AO0 {L}"]}
    assert so_word_labels(w) == ["K", "AO0", "L"]


def test_wrong_and_accented_sounds():
    w = {"ref-phones": "B EH0 R", "phones": ["B (EH0) (R)", "B (EH0) (R)", "B (EH0) {R}", "B EH0 R", "B {EH0} R"]}
    assert so_word_labels(w) == ["B", "EH0,err,s", "R,acc,s"]  # R: 2 wrong + 1 accent + 2 fine = no majority


def test_extra_vowel_needs_three_experts():
    w = {"ref-phones": "N AA0 T", "phones": ["N AA0 T [AH0]"] * 3 + ["N AA0 T"] * 2}
    assert so_word_labels(w) == ["N", "AA0", "T", "sil,AH0,a"]
    w2 = {"ref-phones": "N AA0 T", "phones": ["N AA0 T [AH0]"] * 2 + ["N AA0 T"] * 3}
    assert so_word_labels(w2) == ["N", "AA0", "T"]


def test_unreadable_annotation_is_skipped():
    assert so_word_labels({"ref-phones": "N AA0 T", "phones": ["N AA0"] * 5}) is None  # 2 sounds for 3


def test_so_human_names_the_unspecified_errors():
    assert so_human("other", "sub:ERR") == "wrong_any"  # experts: wrong, but not WHAT was said
    assert so_human("other", "sub:ACC") == "accented"
    assert so_human("correct", "") == "correct"


# ---------- suitcase: long stories cut at pauses ----------
TG = '''File type = "ooTextFile"
Object class = "TextGrid"
item [1]:
    class = "IntervalTier"
    name = "words"
    intervals [1]:
        xmin = 0
        xmax = 0.5
        text = "the"
    intervals [2]:
        xmin = 0.5
        xmax = 1.0
        text = "man"
    intervals [3]:
        xmin = 1.0
        xmax = 1.4
        text = ""
    intervals [4]:
        xmin = 1.4
        xmax = 2.0
        text = "ran"
item [2]:
    class = "IntervalTier"
    name = "phones"
    intervals [1]:
        xmin = 0
        xmax = 0.2
        text = "DH,D,s"
    intervals [2]:
        xmin = 0.2
        xmax = 0.5
        text = "AH0"
    intervals [3]:
        xmin = 0.5
        xmax = 1.0
        text = "M"
    intervals [4]:
        xmin = 1.0
        xmax = 1.4
        text = "sil"
    intervals [5]:
        xmin = 1.4
        xmax = 2.0
        text = "R,L,s"
'''


def test_textgrid_tiers():
    t = textgrid_tiers(TG)
    assert t["words"][1] == (0.5, 1.0, "man") and t["phones"][0] == (0.0, 0.2, "DH,D,s")


def test_segments_cut_at_a_pause_and_carry_their_labels():
    segs = suitcase_segments(TG, min_len=0.8, max_len=5.0)
    assert [s["text"] for s in segs] == ["the man", "ran"]
    assert segs[0]["labels"] == ["DH,D,s", "AH0", "M"] and segs[1]["labels"] == ["R,L,s"]
    assert segs[0]["start"] == 0.0 and segs[1]["end"] == 2.0
