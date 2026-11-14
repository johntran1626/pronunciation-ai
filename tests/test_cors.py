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
