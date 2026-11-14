"""Fine-tune the listener (wav2vec2 phoneme recognizer) with CTC on what learners ACTUALLY said.

    python -m eval.ft_data --build           # once: audio + labels -> data/ft/
    python -m eval.finetune --smoke          # a few minutes: 30 steps + a tiny dev check, to see it runs
    python -m eval.finetune --run            # the real thing (hours; resumable: run the same command again)

Output (git-ignored): data/models/listener_v1/
    last.pt     everything needed to carry on (weights, optimizer, schedule, where in which epoch)
    best/       the fine-tuned weights with the lowest dev phone error rate (loadable with from_pretrained)
    train.log   one line per 20 steps; one line per dev check

How it learns (CTC, the same loss the model was first trained with):
  the model writes one symbol (or "blank") per 20 ms frame; CTC adds up every way of placing the target symbols
  on the frames ('ɹ aɪ t' -> ɹɹ__aɪ_t, ɹ_aɪaɪ_t, ...) and pushes the model to make those paths more likely.
  So we never need per-frame labels, only the list of sounds said in the recording.

What is frozen / what moves:
  - the feature encoder (the convolution layers that turn raw samples into 20 ms frames) stays frozen: it is generic
    sound processing, and freezing it saves memory and time;
  - the 24 transformer layers and the output layer are trained, gently (small learning rate), so the model keeps
    what it knew and only shifts towards learner pronunciations.
"""
import argparse
import os
import random
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "models" / "listener_v1"
SPECIAL = {"<pad>", "<s>", "</s>", "<unk>"}
# The old listener writes some r-vowels as ONE token; our targets spell them as two. Split them before counting
# errors, so the "before" dev score isn't punished for spelling alone.
SPLIT_TOKENS = {"ɑːɹ": ["ɑː", "ɹ"], "ɔːɹ": ["ɔː", "ɹ"], "oːɹ": ["oː", "ɹ"], "ɪɹ": ["ɪ", "ɹ"], "ɛɹ": ["ɛ", "ɹ"],
                "ʊɹ": ["ʊ", "ɹ"], "aɪɚ": ["aɪ", "ɚ"], "aɪə": ["aɪ", "ə"], "əl": ["ə", "l"]}
DEV_CHECK_MAX = 800   # recordings per dev check (a fixed sample), so a check takes minutes, not an hour


# ---------- 1. safety ----------
def check_no_test(rows):
    """The Korean test speakers must never reach training or checkpoint choice."""
    bad = [r["id"] for r in rows if r.get("split") == "test"]
    if bad:
        raise ValueError(f"{len(bad)} test (Korean) recordings in the training data, e.g. {bad[:3]}")


# ---------- 2. batches ----------
def batches(seconds, max_seconds, seed, epoch):
    """Group recording indices so (longest recording x count) <= max_seconds, the padded size the GPU sees.
    Shuffle, sort neighbours by length (less padding), then shuffle the batches. Same seed+epoch = same batches."""
    rng = random.Random(seed * 100003 + epoch)
    order = list(range(len(seconds)))
    rng.shuffle(order)
    chunk = 64
    order = [i for k in range(0, len(order), chunk) for i in sorted(order[k:k + chunk], key=lambda i: seconds[i])]
    out, cur, longest = [], [], 0.0
    for i in order:
        new_longest = max(longest, seconds[i])
        if cur and new_longest * (len(cur) + 1) > max_seconds:
            out.append(cur)
            cur, new_longest = [], seconds[i]
        cur.append(i)
        longest = new_longest
    if cur:
        out.append(cur)
    rng.shuffle(out)
    return out


def load_audio(item):
    if "audio" in item:
        return item["audio"]
    return np.load(item["path"]).astype(np.float32) / 32767.0


def collate(items, vocab):
    """-> input_values (padded with 0 after per-recording volume normalization, as the model's feature extractor
    does), attention_mask (1 = real audio), labels (symbol ids, padded with -100 = ignored by the loss)."""
    n = max(len(it["audio"]) for it in items)
    m = max(len(it["targets"]) for it in items)
    x = torch.zeros(len(items), n)
    mask = torch.zeros(len(items), n, dtype=torch.long)
    labels = torch.full((len(items), m), -100, dtype=torch.long)
    for k, it in enumerate(items):
        a = torch.as_tensor(it["audio"], dtype=torch.float32)
        x[k, :len(a)] = (a - a.mean()) / torch.sqrt(a.var(unbiased=False) + 1e-7)
        mask[k, :len(a)] = 1
        labels[k, :len(it["targets"])] = torch.tensor([vocab[s] for s in it["targets"]])
    return {"input_values": x, "attention_mask": mask, "labels": labels}


# ---------- 3. scoring on dev ----------
def greedy(ids, symbol_of, blank):
    """Per-frame best ids -> symbols: merge repeats, drop blanks and special tokens (same as backend/recognize.py)."""
    out, prev = [], None
    for i in ids:
        if i != prev and i != blank and symbol_of[i] not in SPECIAL:
            out.extend(SPLIT_TOKENS.get(symbol_of[i], [symbol_of[i]]))
        prev = i
    return out


def edit_distance(a, b):
    """Fewest swaps + drops + adds to turn a into b."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j - 1] + (x != y), prev[j] + 1, cur[j - 1] + 1))
        prev = cur
    return prev[-1]


def dev_per(model, items, vocab, device, load=load_audio):
    """Phone error rate on dev: (swaps + drops + adds) / number of target sounds. One recording at a time,
    no padding, exactly as the app runs the model."""
    model.eval()
    symbol_of = {i: s for s, i in vocab.items()}
    blank = model.config.pad_token_id
    errs = total = 0
    with torch.inference_mode():
        for it in items:
            x = collate([{"audio": load(it), "targets": it["targets"]}], vocab)["input_values"].to(device)
            ids = model(x).logits.argmax(-1)[0].tolist()
            errs += edit_distance(greedy(ids, symbol_of, blank), it["targets"])
            total += len(it["targets"])
    return errs / max(total, 1)


# ---------- 4. training ----------
def _schedule(warmup, total):
    """Learning-rate multiplier: rises linearly for `warmup` steps, then falls linearly to 0 at the last step."""
    def f(step):
        if step < warmup:
            return (step + 1) / warmup
        return max(0.0, (total - step) / max(1, total - warmup))
    return f


def _save_atomic(obj, path):
    tmp = path.with_suffix(".tmp")
    torch.save(obj, tmp)
    os.replace(tmp, path)   # a crash mid-save leaves the old last.pt intact


def train(train_items, dev_items, out_dir, *, model, vocab, epochs, max_seconds, lr, warmup, device, save_every,
          log=print, max_steps=None, eval_every_epoch=True, seed=0, load=load_audio, grad_clip=1.0, log_every=20):
    check_no_test(train_items)
    check_no_test(dev_items)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.config.ctc_loss_reduction = "mean"   # loss per target sound, so long and short recordings weigh alike
    model.config.ctc_zero_infinity = True      # a recording too short for its targets gives 0, not infinity
    model.freeze_feature_encoder()
    model.to(device)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
    plan = [batches([it["seconds"] for it in train_items], max_seconds, seed, e) for e in range(epochs)]
    total = sum(len(b) for b in plan)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, _schedule(warmup, total))
    st = {"step": 0, "epoch": 0, "batch": 0, "dev_per": [], "best_per": None, "first_loss": None, "last_loss": None}

    last = out_dir / "last.pt"
    if last.exists():
        ck = torch.load(last, map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        st = ck["state"]
        log(f"resumed at step {st['step']} (epoch {st['epoch']}, batch {st['batch']})")

    def save():
        _save_atomic({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                      "state": st}, last)

    def check_dev(label):
        per = dev_per(model, dev_items, vocab, device, load)
        st["dev_per"].append(per)
        log(f"dev PER {label}: {per:.4f} ({len(dev_items)} recordings)")
        if label != "before" and (st["best_per"] is None or per < st["best_per"]):
            st["best_per"] = per
            model.save_pretrained(out_dir / "best")
            log(f"  new best -> {out_dir / 'best'}")

    if eval_every_epoch and st["step"] == 0 and not st["dev_per"]:
        check_dev("before")   # the old listener's score: the number to beat
    log(f"{len(train_items)} train recordings, {sum(it['seconds'] for it in train_items) / 3600:.2f} h, "
        f"{total} steps over {epochs} epochs")

    t0, recent = time.time(), []
    for epoch in range(st["epoch"], epochs):
        for bi in range(st["batch"], len(plan[epoch])):
            if max_steps is not None and st["step"] >= max_steps:
                save()
                return st
            model.train()
            b = collate([{"audio": load(train_items[i]), "targets": train_items[i]["targets"]}
                         for i in plan[epoch][bi]], vocab)
            loss = model(**{k: v.to(device) for k, v in b.items()}).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            st["step"] += 1
            st["batch"] = bi + 1
            value = loss.item()
            st["first_loss"] = value if st["first_loss"] is None else st["first_loss"]
            st["last_loss"] = value
            recent.append(value)
            if st["step"] % log_every == 0:
                per_step = (time.time() - t0) / len(recent)
                left = (total - st["step"]) * per_step / 3600
                log(f"step {st['step']}/{total} epoch {epoch + 1} loss {np.mean(recent[-log_every:]):.3f} "
                    f"lr {sched.get_last_lr()[0]:.2e} {per_step:.2f} s/step ~{left:.1f} h left")
            if st["step"] % save_every == 0:
                save()
        st["epoch"], st["batch"] = epoch + 1, 0
        if eval_every_epoch:
            check_dev(f"after epoch {epoch + 1}")
        save()
    log(f"done: {st['step']} steps; dev PER {['%.4f' % p for p in st['dev_per']]}")
    return st


# ---------- 5. the real run ----------
def main():
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    from backend.align import MODEL, vocab
    from eval.ft_data import load_manifest

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="30 steps + 20 dev recordings, in data/models/listener_smoke")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--max-seconds", type=float, default=32.0)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--save-every", type=int, default=300)
    a = ap.parse_args()
    if not (a.smoke or a.run):
        ap.error("pass --smoke or --run")

    rows = load_manifest()
    tr = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    random.Random(0).shuffle(dev)
    dev = dev[:20 if a.smoke else DEV_CHECK_MAX]
    out = ROOT / "data" / "models" / ("listener_smoke" if a.smoke else "listener_v1")
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "train.log", "a", encoding="utf-8")

    def log(s):
        line = f"{time.strftime('%H:%M:%S')} {s}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = Wav2Vec2ForCTC.from_pretrained(MODEL)
    model.gradient_checkpointing_enable()   # recompute layer outputs in the backward pass: ~half the memory
    Wav2Vec2FeatureExtractor.from_pretrained(MODEL).save_pretrained(out / "best")
    log(f"device {device}; {len(tr)} train / {len(dev)} dev recordings; args {vars(a)}")
    st = train(tr, dev, out, model=model, vocab=vocab(), epochs=1 if a.smoke else a.epochs,
               max_seconds=a.max_seconds, lr=a.lr, warmup=10 if a.smoke else a.warmup, device=device,
               save_every=10 if a.smoke else a.save_every, log=log, max_steps=30 if a.smoke else None,
               eval_every_epoch=True)
    if a.smoke:  # the smoke run stops mid-epoch, so score dev once more by hand
        log(f"smoke: loss {st['first_loss']:.3f} -> {st['last_loss']:.3f}; dev PER before {st['dev_per'][0]:.4f}, "
            f"after 30 steps {dev_per(model, dev, vocab(), device):.4f}")


if __name__ == "__main__":
    main()
