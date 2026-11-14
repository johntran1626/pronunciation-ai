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


# A host's proxy can answer CORS itself and echo ANY Origin back (Hugging Face Spaces does), which would undo the
# list above. So the app also refuses a request whose Origin is not on the list: 403 and nothing useful in it.

def test_unknown_site_is_refused():
    r = client.get("/health", headers={"Origin": "https://some-other-site.example"})
    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers
    assert "ok" not in r.text


def test_unknown_site_cannot_post_a_recording():
    r = client.post("/analyze", headers={"Origin": "https://some-other-site.example"},
                    data={"text": "Hi.", "lang": "en"}, files={"audio": ("a.wav", b"x", "audio/wav")})
    assert r.status_code == 403


def test_unknown_site_preflight_is_refused():
    r = client.options("/analyze", headers={"Origin": "https://some-other-site.example",
                                            "Access-Control-Request-Method": "POST"})
    assert r.status_code == 403


def test_null_origin_is_refused():
    # Sandboxed frames and local files send the literal word "null".
    assert client.get("/health", headers={"Origin": "null"}).status_code == 403


def test_no_origin_is_allowed():
    # curl, health checks and server-to-server calls send no Origin; browsers always do across sites.
    assert client.get("/health").status_code == 200


def test_page_on_the_backend_itself_is_allowed():
    # The /docs page is served by the backend, so its "Try it out" requests come from the backend's own address.
    r = client.get("/health", headers={"Origin": "http://testserver"})   # TestClient's host is "testserver"
    assert r.status_code == 200


def test_origin_check_ignores_a_trailing_slash_and_case():
    assert client.get("/health", headers={"Origin": "HTTP://LOCALHOST:3000/"}).status_code == 200


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
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "https://coach.vercel.app"
    finally:
        monkeypatch.delenv("FRONTEND_ORIGINS")
        importlib.reload(app_module)
