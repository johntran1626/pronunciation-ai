# syntax=docker/dockerfile:1
# Backend image for Hugging Face Spaces (Docker SDK): the FastAPI app on port 7860, CPU only.
#   docker build --platform linux/amd64 -t pronunciation-backend .
#   docker run --platform linux/amd64 -p 7860:7860 -e HF_TOKEN pronunciation-backend
# linux/amd64 is what Spaces runs (and praat-parselmouth 0.4.7 has no Linux ARM wheel); on an Apple-silicon Mac,
# Docker emulates it, which is slower but runs the same code.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Spaces run the container as user 1000, so that user owns everything the app writes (data/ caches).
RUN useradd -m -u 1000 user && mkdir -p /app/data && chown -R user /app
WORKDIR /app

# CPU-only PyTorch first: the default Linux wheels bundle CUDA libraries (several GB) that a CPU host never uses.
# The second install then finds torch/torchaudio already at the pinned versions.
# g2pk goes in with --no-deps: it lists konlpy (a Java bridge) as a dependency but never imports it.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 torchaudio==2.11.1 \
 && pip install -r requirements.txt \
 && pip install --no-deps g2pk==0.9.4

USER user
# Set only now, so the root-run install above can't create these folders owned by root.
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    NLTK_DATA=/home/user/nltk_data

# Public model files, fetched once at build so the app never downloads them at request time:
# NLTK data for English G2P, and the original wav2vec2 listener (Korean, and English without the fine-tune).
RUN python -c "import nltk; [nltk.download(p, download_dir='/home/user/nltk_data', quiet=True) for p in ('cmudict', 'averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng')]"
RUN python -c "from huggingface_hub import hf_hub_download; from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC; m = 'facebook/wav2vec2-xlsr-53-espeak-cv-ft'; Wav2Vec2ForCTC.from_pretrained(m); Wav2Vec2FeatureExtractor.from_pretrained(m); hf_hub_download(m, 'vocab.json')"

COPY --chown=user backend/ backend/
COPY --chown=user content/ content/

EXPOSE 7860

# Hugging Face Spaces puts one proxy in front of the app; it appends the visitor's address to X-Forwarded-For,
# so the rate limits key on that entry instead of the proxy's address (backend/app.py, client_ip).
ENV TRUSTED_PROXY_HOPS=1

# Start-up: download the private fine-tuned listener (kept out of the image, see backend/fetch_listener.py),
# then serve. HF_HUB_OFFLINE=1 makes the app use only the files already on disk.
CMD ["sh", "-c", "python -m backend.fetch_listener && exec env HF_HUB_OFFLINE=1 uvicorn backend.app:app --host 0.0.0.0 --port 7860"]
