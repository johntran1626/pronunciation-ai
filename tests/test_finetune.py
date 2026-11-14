"""Fine-tune the listener on what was ACTUALLY said.py + eval/finetune.py."""
import numpy as np
import pytest
import torch

from backend.align import vocab
from eval import ft_data as fd
from eval import finetune as ft


# ---------- 1. labels -> the sounds actually said ----------
def test_arpabet_labels_give_what_was_said():
    # correct DH, unstressed AH (schwa), L said as R, R dropped, an extra AH added (a schwa)
    assert fd.arpa_actual(["DH", "AH0", "L,R,s", "R,sil,d", "sil,AH,a"]) == ["ð", "ə", "ɹ", "ə"]


def test_distortion_star_and_stray_marks_keep_the_sound():
    # 'AA*' = a distorted AA (closest sound AA); 'V8' and 'D_' are typos in the corpus; 'ER)' too
    assert fd.arpa_actual(["AA*", "V8", "D_", "ER)", "T,D*,s"]) == ["ɑː", "v", "d", "ɚ", "d"]


def test_unknown_sound_drops_the_whole_recording():
    # 'ERR' = annotator could not say what was said; 'SPN' = noise; speechocean 'err'/'acc' = wrong but unknown
    for bad in (["K", "AE,ERR,s"], ["SPN"], ["W", "IY0,err,s"], ["W", "IY0,acc,s"], []):
        assert fd.arpa_actual(bad) is None


def test_saa_transcription_to_model_symbols():
    # 'bɹɪ̃ŋ' (nasalized vowel), 'ðiz' (i -> iː like ARPAbet IY), 'sneɪk' (e+ɪ is one diphthong)
    assert fd.saa_actual("bɹɪ̃ŋ ðiz sneɪk") == ["b", "ɹ", "ɪ", "ŋ", "ð", "iː", "z", "s", "n", "eɪ", "k"]


def test_saa_r_colour_dark_l_and_lookalike_letters():
    # 'stɔ˞' = store (r-colour -> its own ɹ), 'hɝ' -> ɚ, 'ɔlˠ' = velarized l (the mark is dropped, ɫ-like l -> l),
    # 'әv' uses a CYRILLIC schwa (U+04D9) that some transcribers typed
    assert fd.saa_actual("stɔ˞ hɝ ɔlˠ ɫ әv") == ["s", "t", "ɔː", "ɹ", "h", "ɚ", "ɔː", "l", "l", "ə", "v"]


def test_saa_keeps_non_english_sounds_that_the_model_knows():
    # a trill, a tap and a glottal stop are what was said: keep them (they are in the model's vocabulary)
    assert fd.saa_actual("ræ ɾ ʔ") == ["r", "æ", "ɾ", "ʔ"]


def test_saa_unknown_sound_drops_the_recording():
    assert fd.saa_actual("ðə ɮ") is None   # ɮ is not in the model's vocabulary


def test_every_mapped_symbol_is_a_real_model_token():
    v = vocab()
    syms = fd.arpa_actual(["AA", "AE", "AH", "AH0", "AO", "AW", "AY", "B", "CH", "D", "DH", "EH", "ER", "EY", "F",
                           "G", "HH", "IH", "IY", "JH", "K", "L", "M", "N", "NG", "OW", "OY", "P", "R", "S", "SH",
                           "T", "TH", "UH", "UW", "V", "W", "Y", "Z", "ZH"])
    syms += fd.saa_actual("pʰlis kʰɔl stɛlə ɑsk˺ ɜ tə bɹɪ̃ŋ mɑɪbi faɪf tʊi bɑp ʧiz")
    assert all(s in v and s not in fd.SPECIAL for s in syms)


# ---------- 2. who trains, who tunes, who is never seen ----------
def test_korean_speakers_are_test_and_never_trained_on():
    assert fd.split_of("l2arctic", "HKK", korean=True) == "test"
    assert fd.split_of("saa", "korean7", korean=True) == "test"
    assert fd.split_of("l2arctic", "ABA", korean=False) in ("train", "dev")


def test_split_is_by_speaker_and_shared_across_l2arctic_and_suitcase():
    # suitcase speakers ARE L2-ARCTIC speakers: one person must land in the same split in both corpora
    for spk in ("ABA", "ASI", "BWC", "EBVS", "ERMS", "HQTV", "LXC", "MBMPS", "NCC", "NJS"):
        assert fd.split_of("l2arctic", spk, korean=False) == fd.split_of("suitcase", spk, korean=False)
    # deterministic: same answer every time
    assert fd.split_of("saa", "dutch3", korean=False) == fd.split_of("saa", "dutch3", korean=False)


def test_l2arctic_dev_has_one_speaker_per_first_language():
    # only 20 non-Korean speakers: a hash gave 2 dev speakers by chance; dev is where the detectors are retuned
    l1 = {"Arabic": ["ABA", "SKA", "YBAA", "ZHAA"], "Mandarin": ["BWC", "LXC", "NCC", "TXHC"],
          "Hindi": ["ASI", "RRBI", "SVBI", "TNI"], "Spanish": ["EBVS", "ERMS", "MBMPS", "NJS"],
          "Vietnamese": ["HQTV", "PNV", "THV", "TLV"]}
    for lang, spks in l1.items():
        assert [fd.split_of("l2arctic", s, korean=False) for s in spks].count("dev") == 1, lang


def test_dev_is_about_the_chosen_share_of_speakers():
    splits = [fd.split_of("saa", f"spk{i}", korean=False) for i in range(2000)]
    share = splits.count("dev") / len(splits)
    assert abs(share - fd.DEV_FRAC) < 0.03


def test_guard_refuses_test_rows_in_training():
    rows = [{"id": "a", "split": "train"}, {"id": "b", "split": "test"}]
    with pytest.raises(ValueError, match="test"):
        ft.check_no_test(rows)
    ft.check_no_test([{"id": "a", "split": "train"}, {"id": "c", "split": "dev"}])


# ---------- 3. batches ----------
def test_batches_cover_every_item_once_and_stay_under_the_audio_cap():
    secs = [3.0, 8.0, 5.5, 12.0, 2.0, 7.0, 30.0, 4.0, 9.5, 1.0]
    b = ft.batches(secs, max_seconds=16.0, seed=0, epoch=0)
    flat = sorted(i for batch in b for i in batch)
    assert flat == list(range(len(secs)))
    for batch in b:  # padded size = longest x count (that is what memory sees)
        assert len(batch) == 1 or max(secs[i] for i in batch) * len(batch) <= 16.0


def test_batches_are_reproducible_and_reshuffled_each_epoch():
    secs = [float(i % 7 + 1) for i in range(60)]
    assert ft.batches(secs, 16.0, seed=0, epoch=3) == ft.batches(secs, 16.0, seed=0, epoch=3)
    assert ft.batches(secs, 16.0, seed=0, epoch=3) != ft.batches(secs, 16.0, seed=0, epoch=4)


def test_collate_pads_audio_and_labels():
    v = {"<pad>": 0, "a": 1, "b": 2}
    items = [{"audio": np.ones(1600, np.float32), "targets": ["a", "b", "a"]},
             {"audio": np.ones(800, np.float32), "targets": ["b"]}]
    out = ft.collate(items, v)
    assert out["input_values"].shape == (2, 1600)
    assert out["attention_mask"].tolist()[1][:800] == [1] * 800 and out["attention_mask"][1, 800:].sum() == 0
    assert out["labels"].tolist() == [[1, 2, 1], [2, -100, -100]]   # -100 = ignored by the CTC loss


def test_greedy_decode_and_phone_error_rate():
    v = {"<pad>": 0, "a": 1, "b": 2}
    ids = [0, 1, 1, 0, 1, 2, 2, 0]          # a _ a b  -> a a b
    assert ft.greedy(ids, {i: s for s, i in v.items()}, blank=0) == ["a", "a", "b"]
    assert ft.edit_distance(["a", "a", "b"], ["a", "b"]) == 1
    assert ft.edit_distance([], ["a", "b"]) == 2


# ---------- 4. the training loop (a tiny random model, CPU, seconds) ----------
VOC = {"<pad>": 0, "<s>": 1, "</s>": 2, "<unk>": 3, "a": 4, "b": 5, "c": 6}


def tiny_model():
    from transformers import Wav2Vec2Config, Wav2Vec2ForCTC
    torch.manual_seed(0)
    cfg = Wav2Vec2Config(vocab_size=len(VOC), hidden_size=32, num_hidden_layers=2, num_attention_heads=2,
                         intermediate_size=64, conv_dim=(16, 16), conv_stride=(5, 4), conv_kernel=(10, 8),
                         num_conv_pos_embeddings=16, num_conv_pos_embedding_groups=4, pad_token_id=0,
                         feat_extract_norm="layer", do_stable_layer_norm=True, mask_time_prob=0.0,
                         layerdrop=0.0, ctc_loss_reduction="mean", ctc_zero_infinity=True)
    return Wav2Vec2ForCTC(cfg)


def tiny_items():
    rng = np.random.default_rng(0)
    return [{"id": f"u{i}", "split": "train", "seconds": 0.25, "audio": rng.standard_normal(4000).astype(np.float32),
             "targets": t} for i, t in enumerate([["a", "b"], ["c"], ["b", "a", "c"], ["a"]])]


def test_training_lowers_the_loss(tmp_path):
    items = tiny_items()
    log = []
    res = ft.train(items, items[:2], tmp_path, model=tiny_model(), vocab=VOC, epochs=40, max_seconds=1.0, lr=3e-3,
                   warmup=5, device="cpu", save_every=1000, log=log.append, eval_every_epoch=False)
    assert res["step"] == 40   # 4 items x 0.25 s fit in ONE 1 s batch -> 1 step per epoch
    assert res["first_loss"] > 1.5 * res["last_loss"]


def test_training_resumes_where_it_stopped(tmp_path):
    items = tiny_items()
    kw = dict(vocab=VOC, epochs=10, max_seconds=0.5, lr=1e-3, warmup=2, device="cpu", save_every=1,
              eval_every_epoch=False)
    a = ft.train(items, items[:1], tmp_path, model=tiny_model(), max_steps=3, log=lambda s: None, **kw)
    assert a["step"] == 3 and (tmp_path / "last.pt").exists()
    log = []
    b = ft.train(items, items[:1], tmp_path, model=tiny_model(), max_steps=5, log=log.append, **kw)
    assert b["step"] == 5
    assert any("resumed at step 3" in line for line in log)


def test_dev_score_is_written_and_best_is_kept(tmp_path):
    items = tiny_items()
    res = ft.train(items, items[:2], tmp_path, model=tiny_model(), vocab=VOC, epochs=2, max_seconds=1.0, lr=1e-3,
                   warmup=1, device="cpu", save_every=1000, log=lambda s: None, eval_every_epoch=True)
    assert len(res["dev_per"]) == 3   # before training (the old listener) + after each epoch
    assert (tmp_path / "best" / "config.json").exists()
