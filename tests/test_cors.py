"""The browser app (localhost:3000) may read replies from the backend; other sites may not.


"""
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)

FRONTEND = "http://localhost:3000"


def test_frontend_origin_may_read_health():
    r = client.get("/health", headers={"Origin": FRONTEND})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == FRONTEND


def test_preflight_for_analyze_is_allowed():
    # Before a POST with a file, the browser first asks "may I?" with an OPTIONS request (a "preflight").
    r = client.options("/analyze", headers={
        "Origin": FRONTEND,
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == FRONTEND
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_unknown_site_gets_no_permission():
    r = client.get("/health", headers={"Origin": "https://some-other-site.example"})
    assert r.status_code == 200                       # the server still answers...
    assert "access-control-allow-origin" not in r.headers  # ...but the browser will hide the reply


# The deployed frontend's address comes from the FRONTEND_ORIGINS setting (comma-separated), so a new Vercel URL
# needs a setting change on the host, not a code change.

def test_allowed_origins_adds_the_setting_to_the_local_ones():
    from backend.app import LOCAL_ORIGINS, allowed_origins
    got = allowed_origins(" https://coach.vercel.app/ , https://www.example.org")
    assert got == LOCAL_ORIGINS + ["https://coach.vercel.app", "https://www.example.org"]


def test_allowed_origins_without_the_setting_is_local_only():
    from backend.app import LOCAL_ORIGINS, allowed_origins
    assert allowed_origins(None) == LOCAL_ORIGINS
    assert allowed_origins("") == LOCAL_ORIGINS
    assert allowed_origins(" , ") == LOCAL_ORIGINS


def test_allowed_origins_refuses_a_wildcard():
    # "*" would let any website read our replies; refuse it loudly instead of quietly opening up.
    import pytest
    from backend.app import allowed_origins
    with pytest.raises(ValueError):
        allowed_origins("*")


def test_setting_reaches_the_running_app(monkeypatch):
    import importlib
    import backend.app as app_module
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://coach.vercel.app")
    try:
        fresh = TestClient(importlib.reload(app_module).app)
        r = fresh.get("/health", headers={"Origin": "https://coach.vercel.app"})
        assert r.headers.get("access-control-allow-origin") == "https://coach.vercel.app"
    finally:
        monkeypatch.delenv("FRONTEND_ORIGINS")
        importlib.reload(app_module)
