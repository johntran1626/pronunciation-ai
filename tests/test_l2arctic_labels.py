"""Reading L2-ARCTIC's human labels and pinning them onto OUR expected phonemes."""
from eval.l2arctic import label_phonemes, parse_label


def test_parse_correct_phone():
    assert parse_label("AH0") == ("AH", "correct", None)
    assert parse_label("l") == ("L", "correct", None)          # lowercase spelling in some files


def test_parse_substitution_deletion_insertion():
    assert parse_label("L,R,s") == ("L", "sub", "R")
    assert parse_label("IH, IY1, s") == ("IH", "sub", "IY")    # spaces and stress digits
    assert parse_label("R,sil,d") == ("R", "del", None)
    assert parse_label("sil, AX, a") == (None, "ins", "AH")    # AX (schwa) spelled as AH
    assert parse_label("DH,D,S") == ("DH", "sub", "D")         # capital S in some files


def words(*prons):
    return [{"word": f"w{i}", "pron": p} for i, p in enumerate(prons)]


def test_labels_land_on_our_phonemes():
    labels, ins_after = label_phonemes(words("B AO1 L Z"), ["B", "AO1", "L,sil,d", "Z"])
    assert labels == [("correct", None), ("correct", None), ("del", None), ("correct", None)]
    assert ins_after == set()


def test_extra_vowel_is_attached_after_the_final_consonant():
    labels, ins_after = label_phonemes(words("B AH1 S", "N AW1"), ["B", "AH1", "S", "sil,AH0,a", "N", "AW1"])
    assert ins_after == {2}                                      # after our phoneme #2 (the S of "bus")
    assert labels[2] == ("correct", None)


def test_different_dictionary_pronunciation_is_left_unlabelled():
    # g2p_en says "the" = DH AH0; the annotators' dictionary used DH IY. Don't guess: no label.
    labels, _ = label_phonemes(words("DH AH0"), ["DH", "IY0"])
    assert labels == [("correct", None), None]
