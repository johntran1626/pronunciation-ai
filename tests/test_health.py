"""The backend is alive."""
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)  # calls the app directly, no real server needed


def test_health_says_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
