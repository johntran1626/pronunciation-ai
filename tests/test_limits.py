"""The TTS rate limiter (backend/limits.py).

A fake clock (a list we move forward by hand) makes time-based rules testable without waiting.
"""
from backend.limits import TTSLimiter


def make(per_client=3, window_s=60, daily_chars=1000):
    now = [1_000_000.0]                       # seconds since 1970 (a fixed fake "now")
    lim = TTSLimiter(per_client=per_client, window_s=window_s, daily_chars=daily_chars, clock=lambda: now[0])
    return lim, now


def test_allows_up_to_the_per_client_limit_then_refuses():
    lim, _ = make(per_client=3)
    assert [lim.allow("a", 5)[0] for _ in range(4)] == [True, True, True, False]


def test_clients_are_counted_separately():
    lim, _ = make(per_client=1)
    assert lim.allow("a", 5)[0]
    assert not lim.allow("a", 5)[0]
    assert lim.allow("b", 5)[0]


def test_window_slides_old_requests_stop_counting():
    lim, now = make(per_client=1, window_s=60)
    assert lim.allow("a", 5)[0]
    now[0] += 59
    ok, retry = lim.allow("a", 5)
    assert not ok and retry == 1              # 1 s until the first request is 60 s old
    now[0] += 1
    assert lim.allow("a", 5)[0]


def test_refused_requests_do_not_use_up_the_budget():
    lim, now = make(per_client=1, window_s=60, daily_chars=100)
    lim.allow("a", 10)
    for _ in range(5):
        lim.allow("a", 10)                    # refused: per-client limit
    now[0] += 60
    assert lim.used_today() == 10


def test_daily_budget_is_shared_by_everyone():
    lim, _ = make(per_client=100, daily_chars=20)
    assert lim.allow("a", 15)[0]
    ok, retry = lim.allow("b", 6)
    assert not ok and retry > 0
    assert lim.allow("b", 5)[0]               # exactly fills the budget


def test_daily_budget_resets_at_utc_midnight():
    lim, now = make(per_client=100, daily_chars=10)
    now[0] = 86_400 * 20_000 + 86_399         # one second before a UTC midnight
    assert lim.allow("a", 10)[0]
    ok, retry = lim.allow("a", 1)
    assert not ok and retry == 1
    now[0] += 1
    assert lim.allow("a", 10)[0]
