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
python -m uvicorn app.main:app --reload   # NOT bare `uvicorn` — see note below
```

### Run the server with `python -m uvicorn` (not bare `uvicorn`)

Start the backend as `python -m uvicorn app.main:app`. The bare `uvicorn` launcher on
some machines binds to a different Python interpreter than the one where the AI deps
(`chromadb`, `sentence-transformers`) are installed, so importing the legal router fails
with `ModuleNotFoundError: No module named 'chromadb'`. Running via `python -m` guarantees
the same interpreter (and therefore the same installed packages) is used.

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

### Fonts — install Noto Sans Gujarati on the demo machine (required for Gujarati docs)

The generated `.docx` documents pin **Noto Sans Gujarati** for all Gujarati/Devanagari
text (see `templates/_build_templates.py`). If that font is **not installed** on the
machine that opens the document, Word/LibreOffice substitutes the next face in the
documented fallback chain (`Nirmala UI` → `Shruti` → `Arial Unicode MS`); on a machine
that has none of these the Gujarati shows as box glyphs (□□□) even though the underlying
text is correct Unicode. Install the bundled font so every machine renders it identically.

The font (SIL Open Font License, see `fonts/OFL.txt`) is committed at
`fonts/NotoSansGujarati-Regular.ttf` so it can be installed anywhere:

```bash
# Windows (PowerShell, per-user — no admin needed)
Copy-Item fonts\NotoSansGujarati-Regular.ttf "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\"
# or double-click the .ttf and press "Install"

# Linux
mkdir -p ~/.local/share/fonts && cp fonts/NotoSansGujarati-Regular.ttf ~/.local/share/fonts/ && fc-cache -f

# macOS
cp fonts/NotoSansGujarati-Regular.ttf ~/Library/Fonts/
```

Regenerate the templates after any font/layout change with
`python templates/_build_templates.py`.
