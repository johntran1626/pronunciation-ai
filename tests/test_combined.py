"""The combined tune-on-others / test-on-Korean report (eval/combined.py), on tiny hand-made rows."""
from eval.combined import evaluate_all, normalize, role


def test_who_tunes_and_who_tests():
    assert role("l2arctic", "others") == "tune" and role("l2arctic", "korean") == "test"
    assert role("suitcase", "suitcase_others") == "tune" and role("suitcase", "suitcase_korean") == "test"
    assert role("saa", "others") == "tune" and role("saa", "korean") == "test"
    assert role("speechocean", "so_adult") == "tune"     # Mandarin adults: tuning only
    assert role("speechocean", "so_child") is None        # children: left out (different voices, not our users)


def raw(group="others", human="correct", margin="-0.5", agrees="0", pair="r_as_l", speaker="S1", utt="u1", **kw):
    r = dict(group=group, speaker=speaker, utt=utt, pair=pair, human=human, margin=margin, heard_agrees=agrees,
             baseline_flag="0", f3_dip="", fric="", closure="")
    r.update(kw)
    return r


def test_normalize_maps_groups_and_parses_numbers():
    r = normalize(raw(group="suitcase_korean", margin="0.25", agrees="1", f3_dip="-0.3"), "suitcase")
    assert r["group"] == "korean" and r["source"] == "suitcase"
    assert r["speaker"] == "suitcase:S1"                  # sources can't merge each other's speakers
    assert r["margin"] == 0.25 and r["heard_agrees"] is True and r["f3_dip"] == -0.3 and r["fric"] is None
    assert normalize(raw(group="so_child"), "speechocean") is None


def rows_for(pair="r_as_l"):
    """Tuning: 4 correct (one high margin) + 2 errors + 1 speechocean 'wrong_any'. Test: 2 sources."""
    rs = [normalize(raw(margin=m, speaker=f"T{i}", pair=pair), "l2arctic") for i, m in enumerate([-0.9, -0.8, -0.7, 0.6])]
    rs += [normalize(raw(human="error", margin=m, agrees="1", speaker="E", pair=pair), "l2arctic") for m in (0.9, 0.95)]
    rs += [normalize(raw(group="so_adult", human="wrong_any", margin="0.99", agrees="1", pair=pair), "speechocean")]
    rs += [normalize(raw(group="korean", margin="-0.9", speaker="K1", pair=pair), "l2arctic"),
           normalize(raw(group="korean", human="error", margin="0.8", agrees="1", speaker="K1", pair=pair), "l2arctic"),
           normalize(raw(group="korean", margin="-0.9", speaker="k2", utt="paragraph", pair=pair), "saa"),
           normalize(raw(group="korean", human="error", margin="0.7", agrees="1", speaker="k2", utt="paragraph",
                         pair=pair), "saa")]
    return rs


def test_wrong_any_is_never_counted_as_a_pair_error():
    res = evaluate_all(rows_for(), pairs=["r_as_l"])["pairs"]["r_as_l"]
    assert res["tuning (others)"]["caught"]["n"] == 2     # the 2 real errors, not the wrong_any


def test_thresholds_come_from_tuning_rows_only():
    rs = rows_for()
    before = evaluate_all(rs, pairs=["r_as_l"])["pairs"]["r_as_l"]["margin"]
    rs.append(normalize(raw(group="korean", margin="0.99", agrees="1", speaker="K9"), "l2arctic"))  # a Korean outlier
    after = evaluate_all(rs, pairs=["r_as_l"])["pairs"]["r_as_l"]
    assert after["margin"] == before                      # test speakers can't move the threshold
    assert after["test (korean)"]["false_alarms"]["k"] == 1   # ...but they are counted


def test_per_source_numbers_add_up_to_the_pooled_test():
    res = evaluate_all(rows_for(), pairs=["r_as_l"])["pairs"]["r_as_l"]
    by = res["test by source"]
    assert set(by) == {"l2arctic", "saa"}
    for side in ("caught", "false_alarms"):
        assert sum(by[s][side]["k"] for s in by) == res["test (korean)"][side]["k"]
        assert sum(by[s][side]["n"] for s in by) == res["test (korean)"][side]["n"]


def test_current_app_thresholds_are_also_scored_on_the_new_test_set():
    app = {"r_as_l": {"variant": "A", "margin": 0.75, "enabled": True}}
    res = evaluate_all(rows_for(), pairs=["r_as_l"], app_thresholds=app)["pairs"]["r_as_l"]["current app (korean)"]
    assert res["caught"]["k"] == 1 and res["caught"]["n"] == 2        # 0.8 > 0.75 caught, 0.7 missed
    assert res["false_alarms"]["k"] == 0 and res["was_enabled"] is True
