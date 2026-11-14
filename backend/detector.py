"""One small logistic-regression detector per mistake, in plain numpy (no new dependency).

In brief: each checked sound has 15 numbers (the recognizer's margin, did it hear the wrong sound, and the 13
waveform measurements in backend/features.py). Logistic regression gives each number a weight, adds them up, and
squashes the sum into a probability between 0 and 1: "how much does this look like the mistake?". Training picks
the weights that best separate correct sounds from mistakes on the tuning speakers. Like a judge with a scoring
sheet: each clue is worth some points (plus or minus), and the total decides.

Details that matter:
  - Scaling: every number is turned into "spreads from the tuning average" first, so a dB number and a 0/1 flag
    can share one penalty. A missing number (None, e.g. no formant in a hiss) becomes 0 = "average", i.e. no
    evidence either way. The no_formants / no_reference flags tell the model when that happened.
  - Balanced classes: mistakes are rare (20 errors per 2,000 sounds). Without weighting, "always correct" already
    fits 99% of the data. So each class gets the same total weight (= the number of the rarer class): the model
    must learn what an error looks like.
  - L2 penalty (1.0): pulls weights toward 0 so a clue that only fits a few tuning errors by luck can't get a big
    weight. The intercept is not penalised.
  - Newton's method: each step uses the slope AND the curvature of the loss, so ~10-30 steps converge exactly.
    The loss is convex (one bowl, one bottom), so the answer doesn't depend on where we start.
"""
import warnings

import numpy as np

from backend.features import MEASURED

FEATURE_NAMES = ("margin", "heard_agrees") + MEASURED
L2 = 1.0


def vectorize(rows, names=FEATURE_NAMES):
    """rows = dicts with these keys (missing key or None -> nan; True/False -> 1/0) -> (n, len(names)) array."""
    X = np.full((len(rows), len(names)), np.nan)
    for i, r in enumerate(rows):
        for j, k in enumerate(names):
            v = r.get(k)
            if v is not None and v != "":
                X[i, j] = float(v)
    return X


def _scaled(model, X):
    Z = (np.asarray(X, dtype=float) - np.array(model["mean"])) / np.array(model["std"])
    return np.nan_to_num(Z, nan=0.0)


def fit(X, y, l2=L2, steps=50, names=FEATURE_NAMES):
    """-> model dict (json-safe): names, mean, std, w (one weight per feature), b (intercept).
    `names` = the column names of X (the slplab experiment adds columns; the app's live models keep FEATURE_NAMES)."""
    X, y = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    with warnings.catch_warnings():                                   # an all-missing column -> nan, fixed below
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0)
    mean = np.where(np.isnan(mean), 0.0, mean)
    std = np.where(np.isnan(std) | (std < 1e-9), 1.0, std)        # a constant column: leave it unscaled
    model = {"names": list(names[:X.shape[1]]), "mean": mean.tolist(), "std": std.tolist()}
    Z = np.c_[_scaled(model, X), np.ones(len(X))]                    # last column = intercept
    n_pos, n_neg = y.sum(), (1 - y).sum()
    per_class = min(n_pos, n_neg)
    s = np.where(y == 1, per_class / max(n_pos, 1), per_class / max(n_neg, 1))   # sample weights
    pen = np.r_[np.full(Z.shape[1] - 1, l2), 0.0]
    w = np.zeros(Z.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -35, 35)))
        grad = Z.T @ (s * (p - y)) + pen * w
        H = (Z * (s * p * (1 - p))[:, None]).T @ Z + np.diag(pen + 1e-9)
        step = np.linalg.solve(H, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    model.update(w=w[:-1].tolist(), b=float(w[-1]))
    return model


def predict(model, X):
    """-> probability of 'this is the mistake' per row."""
    z = _scaled(model, X) @ np.array(model["w"]) + model["b"]
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def auc(neg, pos):
    """Chance that a random error scores higher than a random correct sound (ties = half). 0.5 = coin flip,
    1.0 = perfect. For each error: how many correct sounds score below it (+ half the ties), via a sorted search,
    so 50,000 x 2,000 rows take milliseconds (Mann-Whitney U / (n_pos x n_neg))."""
    neg, pos = np.sort(np.asarray(neg, dtype=float)), np.asarray(pos, dtype=float)
    if not neg.size or not pos.size:
        return None
    below = np.searchsorted(neg, pos, side="left")
    ties = np.searchsorted(neg, pos, side="right") - below
    return float((below + 0.5 * ties).sum() / (len(pos) * len(neg)))
