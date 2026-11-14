"""Reading Speech Accent Archive transcriptions into R/L labels.
No audio or data/ needed: transcription snippets are typed in (korean1's comes from its page)."""
from eval.saa import EV, group_of, label_slots, segments


def words(*spec):
    """("red", "ɹ ɛ d"), ... -> G2P-shaped words."""
    return [{"word": w, "phonemes": [{"ipa": s} for s in ph.split()]} for w, ph in spec]


# ---------- cutting an IPA string into sounds ----------
def test_segments_keep_diacritics_on_their_sound():
    assert segments("bɹĩŋ") == ["b", "ɹ", "ĩ", "ŋ"]
    assert segments("bik˺ tɔi") == ["b", "i", "k˺", "t", "ɔ", "i"]
    assert segments("pʰiːz̥") == ["pʰ", "iː", "z̥"]


def test_segments_join_affricates_and_split_r_colouring():
    assert segments("ʧiːz") == ["tʃ", "iː", "z"]
    assert segments("tʃiz") == ["tʃ", "i", "z"]
    assert segments("stɔ˞") == ["s", "t", "ɔ", "˞"]  # r-coloured vowel = vowel + an R-like piece


# ---------- labels for each expected R and L ----------
def test_r_said_as_l_is_an_error_and_correct_ones_are_correct():
    lab = label_slots(words(("bring", "b ɹ ɪ ŋ"), ("red", "ɹ ɛ d"), ("blue", "b l uː")), "bɹĩŋ lɛd̥ blu")
    assert lab[(0, 1)] == ("correct", "ɹ")
    assert lab[(1, 0)] == ("error", "l")  # korean1 said 'red' as lɛd̥
    assert lab[(2, 1)] == ("correct", "l")
    rl = {k for k in lab if len(k) == 2 and lab[k][1] in ("ɹ", "l")}
    assert rl == {(0, 1), (1, 0), (2, 1)}  # other pairs are labelled too, R/L slots unchanged


def test_l_said_as_r_and_taps_are_kept_apart():
    lab = label_slots(words(("plastic", "p l æ s t ɪ k"), ("blue", "b l uː")), "pɹæstik bɾu")
    assert lab[(0, 1)] == ("error", "ɹ")
    assert lab[(1, 1)] == ("tap", "ɾ")  # a tap is NOT lumped with English R


def test_trill_symbol_and_r_coloured_vowel_count_as_r():
    lab = label_slots(words(("three", "θ ɹ iː"), ("store", "s t ɔː ɹ")), "ðri stɔ˞")
    assert lab[(0, 1)] == ("correct", "r")
    assert lab[(1, 3)] == ("correct", "˞")


def test_dropped_sound_and_restarts():
    # 'for' with no R; 'frog' said twice (restart), the first copy lines up and the R is fine
    lab = label_slots(words(("for", "f ɔː ɹ"), ("frog", "f ɹ ɑː ɡ"), ("for", "f ɔː ɹ")), "fɔː pɹɔɡ̥ pɹak˺ fɔː")
    assert lab[(0, 2)] == ("deleted", "")
    assert lab[(1, 1)] == ("correct", "ɹ")
    assert lab[(2, 2)] == ("deleted", "")


def test_korean1_real_transcription_start():
    # first words of korean1 (accent.gmu.edu/samples/korean1): please call Stella ... bring ... her from
    lab = label_slots(words(("Please", "p l iː z"), ("call", "k ɔː l"), ("Stella", "s t ɛ l ə"), ("Ask", "æ s k"),
                            ("her", "h ɚ"), ("to", "t uː"), ("bring", "b ɹ ɪ ŋ")),
                      "plĭs kol stɛlɑ ɛsk ɜ tu bɹĩŋ")
    assert [lab[k][0] for k in [(0, 1), (1, 2), (2, 3), (6, 1)]] == ["correct"] * 4


# ---------- V labels ----------
def test_v_said_as_b_and_devoiced_v():
    lab = label_slots(words(("of", "ʌ v"), ("five", "f aɪ v"), ("of", "ʌ v")), "ɔb̥ faɪf ʌv")
    assert lab[(0, 1)] == ("error", "b")   # korean48 wrote 'of' as ɔb̥
    assert lab[(1, 2)] == ("other", "f")   # V said as F (devoiced): not this pair's error
    assert lab[(2, 1)] == ("correct", "v")


# ---------- every MVP English pair ----------
def test_th_said_as_s_or_t_and_dh_said_as_d():
    lab = label_slots(words(("things", "θ ɪ ŋ z"), ("the", "ð ə"), ("three", "θ ɹ iː")), "sɪŋz də t̪ɹi")
    assert lab[(0, 0)] == ("error", "s")
    assert lab[(1, 0)] == ("error", "d")
    assert lab[(2, 0)] == ("error", "t")  # dental t̪ is still a T


def test_th_said_as_f_or_voiced_is_other_and_weak_dh_is_correct():
    lab = label_slots(words(("thick", "θ ɪ k"), ("with", "w ɪ ð"), ("these", "ð iː z")), "fɪk wɪθ ð̞iz")
    assert lab[(0, 0)] == ("other", "f")
    assert lab[(1, 2)] == ("other", "θ")
    assert lab[(2, 0)] == ("correct", "ð")


def test_f_said_as_p_and_bilabial_f_is_other():
    lab = label_slots(words(("five", "f aɪ v"), ("fresh", "f ɹ ɛ ʃ")), "pʰaɪb ɸɹɛʃ")
    assert lab[(0, 0)] == ("error", "p")
    assert lab[(0, 2)] == ("error", "b")
    assert lab[(1, 0)] == ("other", "ɸ")  # neither English F nor P


def test_ship_said_as_sheep_and_back():
    lab = label_slots(words(("big", "b ɪ ɡ"), ("cheese", "tʃ iː z"), ("kids", "k ɪ d z")), "biɡ ʧɪz kədz")
    assert lab[(0, 1)] == ("error", "i")
    assert lab[(1, 1)] == ("error", "ɪ")
    assert lab[(2, 1)] == ("other", "ə")


def test_extra_vowel_after_a_final_consonant():
    lab = label_slots(words(("Six", "s ɪ k s"), ("bags", "b æ ɡ z"), ("Bob", "b ɑː b"), ("and", "ə n d")),
                      "siksə bæɡz̥ bɑp æn")
    assert lab[(0, 3, EV)] == ("error", "ə")      # 'siksə'
    assert lab[(1, 3, EV)] == ("correct", "z")    # devoiced z is still z, nothing after it
    assert lab[(2, 2, EV)] == ("other", "p")      # final consonant changed: not this check's question
    assert lab[(3, 2, EV)] == ("deleted", "")


def test_extra_vowel_and_words_run_together():
    # 'need a' -> 'nidə': the ə is the word 'a', not an extra vowel; 'snack for' -> 'snækə fɔ': a real one
    lab = label_slots(words(("need", "n iː d"), ("a", "ə"), ("snack", "s n æ k"), ("for", "f ɔː ɹ")),
                      "nidə snækə fɔ")
    assert lab[(0, 2, EV)] == ("correct", "d")
    assert lab[(2, 3, EV)] == ("error", "ə")


def test_a_perfect_transcription_labels_every_slot_correct():
    from backend.g2p import expected_phonemes
    from eval.saa import PARAGRAPH
    exp = expected_phonemes(PARAGRAPH, "en")
    ipa = lambda p: p["ipa"] if isinstance(p, dict) else p
    lab = label_slots(exp, " ".join("".join(ipa(p) for p in w["phonemes"]) for w in exp))
    assert {v[0] for v in lab.values()} == {"correct"}
    targets = {"ɹ", "l", "v", "f", "θ", "ð", "ɪ", "iː"}
    assert len([k for k in lab if len(k) == 2]) == sum(ipa(p) in targets for w in exp for p in w["phonemes"])


def test_group_is_korean_or_others():
    assert group_of("korean") == "korean"
    assert group_of("mandarin") == "others"
    assert group_of("english") == "others"


def test_extra_vowel_r_coloured_ending_is_the_same_final_sound():
    lab = label_slots(words(("store", "s t ɔː ɹ"), ("call", "k ɔː l")), "stɔ˞ kɔɫ")
    assert lab[(0, 3, EV)] == ("correct", "˞")
    assert lab[(1, 2, EV)] == ("correct", "ɫ")
