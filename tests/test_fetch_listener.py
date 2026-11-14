"""backend/fetch_listener.py: the server's start-up download of the fine-tuned listener (no network here:
the download function is a fake that writes the files the real one would)."""
import pytest

from backend import fetch_listener
from backend.fetch_listener import FILES, REPO, REVISION, fetch
from backend.listener import ready

TOKEN = "hf_test_not_a_real_token"


def fake_download(written=FILES):
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        for name in written:
            (kwargs["local_dir"] / name).write_text("{}")

    return download, calls


@pytest.fixture
def dest(tmp_path):
    return tmp_path / "listener_v1" / "best"   # same tag as the real folder, so its threshold files apply


def test_no_token_skips_the_download_and_warns(dest, capsys, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    download, calls = fake_download()
    assert fetch(dest, download=download) is False
    assert calls == []
    assert "HF_TOKEN" in capsys.readouterr().err


def test_token_downloads_the_pinned_revision_into_the_listener_folder(dest, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    download, calls = fake_download()
    assert fetch(dest, download=download) is True
    assert len(calls) == 1
    call = calls[0]
    assert (call["repo_id"], call["revision"], call["token"]) == (REPO, REVISION, TOKEN)
    assert call["local_dir"] == dest and sorted(call["allow_patterns"]) == sorted(FILES)
    assert ready(dest)   # the live app will now pick the fine-tuned listener for English


def test_incomplete_download_stops_the_server_start(dest, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    download, _ = fake_download(written=["preprocessor_config.json"])   # no config.json, no weights
    with pytest.raises(RuntimeError, match="incomplete"):
        fetch(dest, download=download)


def test_the_token_is_never_printed(dest, capsys, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    download, _ = fake_download()
    fetch(dest, download=download)
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_pinned_revision_is_a_full_commit_hash():
    assert len(REVISION) == 40 and all(c in "0123456789abcdef" for c in REVISION)
    assert fetch_listener.FINE_TUNED.parts[-3:] == ("models", "listener_v1", "best")
