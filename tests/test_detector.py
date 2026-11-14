"""backend/detector.py, numpy logistic regression + AUC."""
import json

import numpy as np

from backend.detector import FEATURE_NAMES, auc, fit, predict, vectorize


def test_feature_names_are_margin_evidence_then_measured():
    from backend.features import MEASURED
    assert FEATURE_NAMES == ("margin", "heard_agrees") + MEASURED


def test_auc_basics():
    assert auc([0, 1], [2, 3]) == 1.0
    assert auc([2, 3], [0, 1]) == 0.0
    assert auc([1, 1], [1, 1]) == 0.5          # ties count half
    assert auc([0, 2], [1, 3]) == 0.75


def test_vectorize_missing_is_nan_and_booleans_are_numbers():
    X = vectorize([{"margin": 0.5, "heard_agrees": True, "dur": None}])
    assert X.shape == (1, len(FEATURE_NAMES))
    assert X[0, 0] == 0.5 and X[0, 1] == 1.0 and np.isnan(X[0, FEATURE_NAMES.index("dur")])


def _data(n_neg=2000, n_pos=20, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_neg + n_pos, len(FEATURE_NAMES)))
    y = np.r_[np.zeros(n_neg), np.ones(n_pos)]
    X[y == 1, 0] += 3.0                         # only 'margin' carries signal
    X[:, FEATURE_NAMES.index("burst")] = 7.0    # a constant column must not crash the scaling
    X[::7, FEATURE_NAMES.index("dur")] = np.nan  # missing values -> 0 after scaling
    return X, y


def test_fit_finds_the_signal_despite_a_rare_class():
    X, y = _data()
    m = fit(X, y)
    s = predict(m, X)
    assert np.all((s > 0) & (s < 1)) and not np.isnan(s).any()
    assert auc(s[y == 0], s[y == 1]) > 0.95
    w = dict(zip(m["names"], m["w"]))
    # with only 20 errors, pure-noise columns still pick up small weights (~0.5 here); margin must clearly lead
    assert w["margin"] > 3 * max(abs(v) for k, v in w.items() if k != "margin")


def test_both_classes_weigh_the_same():
    """20 errors vs 2,000 correct: unweighted, every probability would sit near 1%. Balanced, an average error
    scores above 0.5 and an average correct sound below it."""
    X, y = _data()
    s = predict(fit(X, y), X)
    assert np.median(s[y == 1]) > 0.5 > np.median(s[y == 0])


def test_model_survives_json():
    X, y = _data()
    m = fit(X, y)
    m2 = json.loads(json.dumps(m))
    assert np.allclose(predict(m, X), predict(m2, X))
