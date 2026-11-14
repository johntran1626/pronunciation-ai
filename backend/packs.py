"""Sentence packs: read content/packs/*.json and hand them to the API.

Files are read on every request. They're tiny (a few KB), so it's fast, and an edited pack shows up
without restarting the server.
"""
import json
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent.parent / "content" / "packs"


def _all_packs():
    """id -> pack, from every JSON file in content/packs/."""
    packs = {}
    for f in sorted(PACKS_DIR.glob("*.json")):
        pack = json.loads(f.read_text(encoding="utf-8"))
        packs[pack["id"]] = pack
    return packs


def list_packs(lang=None):
    """Short summaries for the picker: everything except the sentences themselves."""
    out = []
    for pack in _all_packs().values():
        if lang and pack["lang"] != lang:
            continue
        summary = {k: v for k, v in pack.items() if k != "items"}
        summary["count"] = len(pack["items"])
        out.append(summary)
    return out


def get_pack(pack_id):
    """The full pack, or None. The id is only used as a dictionary key, never as a file path."""
    return _all_packs().get(pack_id)
