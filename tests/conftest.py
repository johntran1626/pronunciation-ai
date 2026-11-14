"""Shared test setup.

The whole suite sends far more than 20 recordings a minute from one test client, so every test starts with a
roomy /analyze limit. tests/test_analyze_limit.py swaps in a tight one to test the limit itself.
"""
import pytest

from backend import app as app_module
from backend.limits import TTSLimiter


@pytest.fixture(autouse=True)
def roomy_analyze_limit(monkeypatch):
    if hasattr(app_module, "analyze_limiter"):
        monkeypatch.setattr(app_module, "analyze_limiter",
                            TTSLimiter(per_client=10_000, window_s=60, daily_chars=0))
