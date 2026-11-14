"""Spike (c) part 2: pick R/L margins by a FALSE-ALARM CAP on one group of speakers, test on another.

TUNE on the 20 non-Korean speakers: for each cap (e.g. at most 1% of correct sounds flagged),
find the smallest margin that keeps false alarms under the cap (smallest = catches the most errors).
TEST on the 4 Korean speakers, which were never looked at while tuning.

Reads the CSVs that spikes/c_rl.py saves (no model needed; runs in a second):
  python spikes/c_margins.py
Throwaway feasibility code. Not part of the app.
"""
import csv
from math import sqrt
from pathlib import Path

CACHE = Path("data/cache")
CAPS = [0.005, 0.01, 0.02, 0.03]


def load(group):
    with open(CACHE / f"spike_c_{group}.csv") as f:
        return [dict(r, gap=float(r["score_other"]) - float(r["score_target"])) for r in csv.DictReader(f)]


def wilson(k, n, z=1.96):
    """95% interval for a rate k/n (works for small n, unlike +-2 standard errors)."""
    if n == 0:
        return float("nan"), float("nan")
    p, d = k / n, 1 + z * z / n
    c, h = p + z * z / (2 * n), z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def margin_for_cap(correct_gaps, cap):
    """Smallest margin m with share(gap > m) <= cap, i.e. the (1 - cap) quantile of correct sounds' gaps."""
    gaps = sorted(correct_gaps)
    allowed = int(cap * len(gaps))  # how many correct sounds we may flag
    return gaps[len(gaps) - allowed - 1] if allowed < len(gaps) else gaps[0]


def rate(rows, m):
    k = sum(r["gap"] > m for r in rows)
    lo, hi = wilson(k, len(rows))
    return f"{k:>3}/{len(rows):<4} {k / max(1, len(rows)):>5.1%} ({lo:.0%}-{hi:.0%})"


def main():
    tune, test = load("others"), load("korean")
    print("Margin chosen on the 20 NON-Korean speakers, measured on the 4 Korean speakers (never tuned on).")
    print("Rates show a 95% interval in brackets.\n")
    for target in ("R", "L"):
        t_ok = [r["gap"] for r in tune if r["target"] == target and r["kind"] == "correct"]
        k_ok = [r for r in test if r["target"] == target and r["kind"] == "correct"]
        k_err = [r for r in test if r["target"] == target and r["kind"] == "swap"]
        print(f"{target}: tuned on {len(t_ok)} correct {target}s; tested on {len(k_ok)} correct + {len(k_err)} swapped")
        print(f"  {'cap':>5} {'margin':>7}   {'Korean false alarms':<26} {'Korean errors caught':<26}")
        for cap in CAPS:
            m = margin_for_cap(t_ok, cap)
            print(f"  {cap:>5.1%} {m:>7.3f}   {rate(k_ok, m):<26} {rate(k_err, m):<26}")
        print()


if __name__ == "__main__":
    main()
