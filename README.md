# CrimeGPT — Copilot

On-premise crime-documentation and legal-intelligence assistant for Indian police.
See `CLAUDE.md` for the full technical foundation and `CLAUDE.md §12` for complete
environment setup.

## Setup notes

Quick start (see `CLAUDE.md §12` for details):

```bash
docker compose up -d                 # Postgres
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed                   # demo users + demo case
python -m app.ai.rag                 # build the legal RAG index (idempotent)
uvicorn app.main:app --reload
```

### `USE_TF=0` (required for the AI/embeddings layer)

The RAG layer uses `sentence-transformers`, which pulls in `transformers`. On machines
that have **Keras 3** installed, `transformers` fails to import with a TensorFlow/Keras
error. Set `USE_TF=0` to force the PyTorch backend and skip the TF import path:

```bash
# bash / Windows Git Bash
export USE_TF=0
# PowerShell
$env:USE_TF = "0"
```

`backend/app/ai/rag.py` sets this automatically at import time, so `python -m app.ai.rag`
works out of the box. Export it yourself only if you import `sentence-transformers` /
`transformers` directly in your own scripts.
