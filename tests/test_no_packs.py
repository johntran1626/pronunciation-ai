"""Sentence packs are gone: the page is type-first, so nothing builds, serves or ships packs any more."""
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def test_no_pack_endpoints():
    assert client.get("/packs").status_code == 404
    assert client.get("/packs/en-basics").status_code == 404


def test_no_pack_code_or_files():
    gone = ["backend/packs.py", "backend/bake_refs.py", "content/packs", "content/en_packs.py", "content/ko_packs.py",
            "content/ko_translations.py", "content/sources.py", "content/build_dev_pack.py"]
    assert [p for p in gone if (ROOT / p).exists()] == []


def test_deploy_ships_no_pack_audio():
    # the Space image no longer copies pre-made pack clips; typed sentences make (and cache) their own
    for f in ["Dockerfile", "deploy/space/upload.sh"]:
        text = (ROOT / f).read_text(encoding="utf-8")
        assert "bake_refs" not in text and "tts_cache" not in text, f
