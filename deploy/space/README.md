---
title: Pronunciation Coach API
emoji: 🗣️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Backend API for a Korean ↔ English pronunciation coach
---

# Pronunciation Coach API

The backend of a web app that helps English speakers pronounce Korean and Korean speakers pronounce English.
It takes a recording and the sentence you meant to say, and returns which sounds passed or need work, with timings
for replaying each word or syllable. Everything it reports about your pronunciation is estimated from your audio.

Source code, method and evaluation results: https://github.com/johntran1626/pronunciation-ai

- `GET /health`: is the server up
- `GET /packs`: sentence packs
- `POST /analyze`: audio + target text → per-sound results (interactive docs at `/docs`)

Native reference audio for every pack sentence (Azure neural TTS, normal and slower speed) is generated ahead of time
and shipped in the image; only Custom-mode sentences are synthesized on demand.

The fine-tuned English listener is kept in a private model repo and downloaded when the container starts, because
part of its training data is licensed for non-commercial use only and is not redistributed.
