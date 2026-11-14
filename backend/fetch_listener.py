"""Download the fine-tuned English listener into data/models/listener_v1/best when the server starts.

    python -m backend.fetch_listener      # needs HF_TOKEN (read access to the private model repo)

Why at start-up and not when the Docker image is built: the weights live in a PRIVATE Hugging Face model repo
because their training data includes non-commercial corpora, and anyone can pull the image of a public Space.
Downloading them into the running container keeps them out of the image.

Without HF_TOKEN nothing is downloaded and English falls back to the original listener (backend/listener.py),
with a warning. With a token, a failed or incomplete download is an error, so the server never starts on a
half-written model.
"""
import os
import sys
from pathlib import Path

from backend.listener import FINE_TUNED, ready

REPO = "johntran1626/pronunciation-listener-v1"
REVISION = "be3e3f5b1d8b4a27e46b02236a1ef5db28ae485d"   # the upload whose SHA-256 matched the local weights
FILES = ["config.json", "preprocessor_config.json", "model.safetensors"]


def fetch(dest=FINE_TUNED, download=None):
    """Download the pinned revision into dest. Returns True if downloaded, False if skipped (no token)."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("warning: HF_TOKEN is not set, so English uses the original listener", file=sys.stderr)
        return False
    if download is None:
        from huggingface_hub import snapshot_download as download
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    download(repo_id=REPO, revision=REVISION, local_dir=dest, allow_patterns=FILES, token=token)
    if not ready(dest) or not all((dest / name).exists() for name in FILES):
        raise RuntimeError(f"fine-tuned listener download is incomplete in {dest}")
    print(f"fine-tuned listener ready ({REPO}@{REVISION[:7]})")
    return True


if __name__ == "__main__":
    fetch()
