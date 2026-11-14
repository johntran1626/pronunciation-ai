#!/bin/sh
# Upload the backend to its Hugging Face Space, which then builds the Dockerfile and starts the server.
#   sh deploy/space/upload.sh
# Sends only COMMITTED files the server needs (git archive of HEAD): Dockerfile, .dockerignore, requirements.txt,
# backend/, content/, plus deploy/space/README.md as the Space's README (it holds the Space's settings header).
# Uncommitted edits are never uploaded, so the code on the Space always matches a commit you can point to.
# The one exception is generated audio: the pack reference clips (below), which the bake script rebuilds exactly.
set -eu

SPACE=johntran1626/pronunciation-ai
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain -- Dockerfile .dockerignore requirements.txt backend content deploy/space)" ]; then
  echo "Note: some server files have uncommitted changes; uploading the last commit without them." >&2
fi

DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT
git archive HEAD Dockerfile .dockerignore requirements.txt backend content | tar -x -C "$DIR"
git show HEAD:deploy/space/README.md > "$DIR/README.md"

# Native reference clips for every pack sentence: generated audio, git-ignored, made by `python -m backend.bake_refs`.
# --list stops the upload if any clip is missing, so the Space never ships a half set.
REFS=$(python -m backend.bake_refs --list)
mkdir -p "$DIR/data/tts_cache"
echo "$REFS" | while read -r f; do cp "data/tts_cache/$f" "$DIR/data/tts_cache/"; done
echo "Pack reference files: $(ls "$DIR/data/tts_cache" | wc -l | tr -d ' ')"

hf upload "$SPACE" "$DIR" . --repo-type space --commit-message "Deploy $(git rev-parse --short HEAD)"
echo "Uploaded. Build progress: https://huggingface.co/spaces/$SPACE (or: hf spaces logs $SPACE --build)"
