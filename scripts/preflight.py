"""Cold-start preflight for the CrimeGPT demo (CLAUDE.md §12, §16).

Brings the stack up from cold and prints PASS/FAIL for every dependency the §15 demo
needs. Run this before the demo — if every line is PASS, the demo flow will work.

    python scripts/preflight.py              # bring the stack up, then check
    python scripts/preflight.py --no-start   # check only, don't start anything
    python scripts/preflight.py --fix        # also run migrations + seed if needed

Checks, in dependency order:
    1. Postgres reachable          docker compose up -d, then a real SELECT 1
    2. Alembic at head             DB revision == latest migration script
    3. Seed data present           the exact rows app/seed.py declares
    4. Chroma collection = 1059    the BNS/BNSS/BSA corpus is ingested
    5. Ollama + qwen2.5:7b         the model the LLM layer will actually request
    6. Noto Sans Gujarati          the bundled font for Gujarati rendering
    6b. Whisper voice model        faster-whisper importable + `small` weights on disk (CPU)
    7. Demo cache populated        every doc type x EN/GU, reviewed strings intact

Exit code 0 if all required checks pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

# Make `app.*` importable and ensure Gujarati/Hindi output does not blow up on cp1252.
sys.path.insert(0, str(BACKEND))
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover — non-reconfigurable stream
        pass

EXPECTED_CHROMA_DOCS = 1059
EXPECTED_JUDGMENT_DOCS = 41
FONT_FILE = REPO_ROOT / "fonts" / "NotoSansGujarati-Regular.ttf"
DEMO_CASE_ID = 1
REQUIRED_LANGS = ["en", "gu"]

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"

_results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> str:
    _results.append((name, status, detail))
    return status


def _run(cmd: list[str], timeout: int = 120,
         cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


# ---------------------------------------------------------------------------
# 1. Postgres
# ---------------------------------------------------------------------------
def check_postgres(start: bool) -> bool:
    if start:
        try:
            proc = _run(["docker", "compose", "up", "-d"], timeout=180)
            if proc.returncode != 0:
                record("Postgres reachable", FAIL,
                       f"docker compose up failed: {proc.stderr.strip().splitlines()[-1:]}")
                return False
        except (OSError, subprocess.TimeoutExpired) as exc:
            record("Postgres reachable", FAIL, f"docker unavailable: {exc}")
            return False

    from sqlalchemy import text

    from app.core.db import SessionLocal

    # Postgres accepts TCP before it accepts queries — poll rather than fail fast.
    deadline = time.time() + (60 if start else 5)
    last = ""
    while time.time() < deadline:
        try:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                ver = db.execute(text("SHOW server_version")).scalar()
                record("Postgres reachable", PASS, f"server_version={ver}")
                return True
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 — any connect error means "not ready yet"
            last = str(exc).splitlines()[0][:120]
            time.sleep(2)
    record("Postgres reachable", FAIL, last or "timed out")
    return False


# ---------------------------------------------------------------------------
# 2. Alembic
# ---------------------------------------------------------------------------
def check_alembic(fix: bool) -> bool:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from app.core.db import SessionLocal

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    def current() -> str | None:
        db = SessionLocal()
        try:
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # noqa: BLE001 — table absent on a virgin database
            return None
        finally:
            db.close()

    if current() != head and fix:
        # alembic.ini lives in backend/, so this must run from there.
        _run([sys.executable, "-m", "alembic", "upgrade", "head"],
             timeout=300, cwd=BACKEND)

    cur = current()
    if cur == head:
        return bool(record("Alembic at head", PASS, f"revision={head}"))
    record("Alembic at head", FAIL,
           f"db={cur or 'no alembic_version table'} head={head}"
           + ("" if fix else " — rerun with --fix"))
    return False


# ---------------------------------------------------------------------------
# 3. Seed data
# ---------------------------------------------------------------------------
def check_seed(fix: bool) -> bool:
    from app.core.db import SessionLocal
    from app.models import Case, CaseDiaryEntry, Person, SeizedItem, Statement, User
    from app.seed import DEMO_CASES, DEMO_USERS, seed

    # Expected counts come from seed.py itself, so this never drifts from the seed.
    want = {
        "users": len(DEMO_USERS),
        "cases": len(DEMO_CASES),
        "persons": sum(len(c["persons"]) for c in DEMO_CASES),
        "seized_items": sum(len(c["seized_items"]) for c in DEMO_CASES),
        "statements": sum(len(c["statements"]) for c in DEMO_CASES),
        "diary": sum(len(c.get("diary", [])) for c in DEMO_CASES),
    }

    def counts() -> dict[str, int]:
        db = SessionLocal()
        try:
            return {
                "users": db.query(User).count(),
                "cases": db.query(Case).count(),
                "persons": db.query(Person).count(),
                "seized_items": db.query(SeizedItem).count(),
                "statements": db.query(Statement).count(),
                "diary": db.query(CaseDiaryEntry).count(),
            }
        finally:
            db.close()

    try:
        got = counts()
    except Exception as exc:  # noqa: BLE001 — tables may not exist yet
        record("Seed data present", FAIL, str(exc).splitlines()[0][:120])
        return False

    if got != want and fix:
        seed()
        got = counts()

    if got == want:
        cases = ", ".join(c["case"]["case_number"] for c in DEMO_CASES)
        return bool(record("Seed data present", PASS,
                           f"{want['users']} users, {want['cases']} cases ({cases})"))
    diff = ", ".join(f"{k}={got[k]}/want {want[k]}" for k in want if got[k] != want[k])
    record("Seed data present", FAIL, diff + ("" if fix else " — rerun with --fix"))
    return False


# ---------------------------------------------------------------------------
# 4. Chroma
# ---------------------------------------------------------------------------
def check_chroma() -> bool:
    try:
        from app.ai.rag import COLLECTION_NAME, _collection

        n = _collection().count()
    except Exception as exc:  # noqa: BLE001 — missing store / import failure
        record(f"Chroma collection = {EXPECTED_CHROMA_DOCS}", FAIL,
               str(exc).splitlines()[0][:120])
        return False

    if n == EXPECTED_CHROMA_DOCS:
        record(f"Chroma collection = {EXPECTED_CHROMA_DOCS}", PASS,
               f"{COLLECTION_NAME}={n} docs")
    else:
        record(f"Chroma collection = {EXPECTED_CHROMA_DOCS}", FAIL,
               f"{COLLECTION_NAME}={n} docs — run: python -m app.ai.ingest_corpus")
        return False
    return check_judgments_collection()


def check_judgments_collection() -> bool:
    """The judgments corpus is a separate collection — /judgments 503s without it."""
    try:
        from app.ai.judgments import COLLECTION_NAME as JCOLL
        from app.ai.judgments import _collection as jcoll

        n = jcoll().count()
    except Exception as exc:  # noqa: BLE001 — missing store / import failure
        record(f"Judgments collection = {EXPECTED_JUDGMENT_DOCS}", FAIL,
               str(exc).splitlines()[0][:120])
        return False

    if n == EXPECTED_JUDGMENT_DOCS:
        return bool(record(f"Judgments collection = {EXPECTED_JUDGMENT_DOCS}", PASS,
                           f"{JCOLL}={n} docs"))
    record(f"Judgments collection = {EXPECTED_JUDGMENT_DOCS}", FAIL,
           f"{JCOLL}={n} docs — run: python -m app.ai.judgments")
    return False


# ---------------------------------------------------------------------------
# 5. Ollama
# ---------------------------------------------------------------------------
def check_ollama() -> bool:
    import json

    from app.core.config import settings

    host = settings.OLLAMA_HOST.rstrip("/")
    model = settings.LLM_MODEL
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=10) as resp:
            tags = json.load(resp)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        record(f"Ollama + {model}", FAIL, f"{host} unreachable: {exc}")
        return False

    names = [m.get("name", "") for m in tags.get("models", [])]
    # Ollama reports "qwen2.5:7b" but a config may omit the tag — match either way.
    if model in names or f"{model}:latest" in names:
        return bool(record(f"Ollama + {model}", PASS, f"{host}, {len(names)} model(s)"))
    record(f"Ollama + {model}", FAIL,
           f"{host} up but {model!r} absent — run: ollama pull {model}. Have: {names}")
    return False


# ---------------------------------------------------------------------------
# 6. Font
# ---------------------------------------------------------------------------
def check_font() -> bool:
    if not FONT_FILE.exists():
        record("Noto Sans Gujarati", FAIL, f"missing {FONT_FILE}")
        return False
    size_kb = FONT_FILE.stat().st_size // 1024
    record("Noto Sans Gujarati", PASS, f"{FONT_FILE.name} ({size_kb} KB)")

    # Informational: .docx opened in Word uses an INSTALLED font, not the repo file.
    installed = []
    for d in (Path(r"C:\Windows\Fonts"),
              Path.home() / "AppData/Local/Microsoft/Windows/Fonts"):
        if d.is_dir():
            installed += [p.name for p in d.glob("*.tt*")
                          if any(k in p.name.lower() for k in ("gujarati", "shruti"))]
    if not installed:
        record("Gujarati font installed system-wide", WARN,
               "none found — generated .docx may show boxes in Word on this machine; "
               f"install {FONT_FILE.name} to fix")
    else:
        record("Gujarati font installed system-wide", PASS, ", ".join(installed))
    return True


# ---------------------------------------------------------------------------
# 6b. Whisper (voice input)
# ---------------------------------------------------------------------------
def check_whisper() -> bool:
    """faster-whisper importable AND the configured model's weights present (CPU only)."""
    try:
        from app.ai.transcribe import _model_spec, model_present
    except Exception as exc:  # noqa: BLE001 — import failure
        record("Whisper voice model", FAIL, str(exc).splitlines()[0][:120])
        return False

    present, detail = model_present()
    record(f"Whisper voice model ({_model_spec()}, CPU)", PASS if present else FAIL, detail)
    return present


# ---------------------------------------------------------------------------
# 7. Demo cache
# ---------------------------------------------------------------------------
def check_demo_cache() -> bool:
    from app import demo_cache, demo_cache_reviewed
    from app.demo_cache_build import DOC_TYPES

    missing = []
    for doc_type in DOC_TYPES:
        for lang in REQUIRED_LANGS:
            if demo_cache.load_document(DEMO_CASE_ID, doc_type, lang) is None:
                missing.append(f"{doc_type}/{lang}")
    for lang in REQUIRED_LANGS:
        if demo_cache.load_analysis(DEMO_CASE_ID, lang) is None:
            missing.append(f"analysis/{lang}")

    n = len(DOC_TYPES) * len(REQUIRED_LANGS) + len(REQUIRED_LANGS)
    if missing:
        record("Demo cache populated", FAIL,
               f"{len(missing)}/{n} missing: {', '.join(missing[:6])}"
               " — run: python -m app.demo_cache_build")
        return False
    record("Demo cache populated", PASS,
           f"{n}/{n} entries ({len(DOC_TYPES)} doc types x {'/'.join(REQUIRED_LANGS)} + analysis)")

    ok, problems = demo_cache_reviewed.verify(DEMO_CASE_ID)
    if ok:
        record("Reviewed Gujarati intact", PASS,
               f"{demo_cache_reviewed.locked_string_count()} protected string(s) match "
               "reviewed_gu.json")
        return True
    record("Reviewed Gujarati intact", FAIL, "; ".join(problems[:4]))
    return False


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Cold-start preflight for the demo.")
    ap.add_argument("--no-start", action="store_true",
                    help="do not run docker compose up; check only")
    ap.add_argument("--fix", action="store_true",
                    help="run alembic upgrade / seed if those checks fail")
    args = ap.parse_args()

    print("CrimeGPT preflight")
    print(f"repo: {REPO_ROOT}\n")

    t0 = time.perf_counter()
    if check_postgres(start=not args.no_start):
        check_alembic(args.fix)
        check_seed(args.fix)
    else:
        record("Alembic at head", FAIL, "skipped — no database")
        record("Seed data present", FAIL, "skipped — no database")
    check_chroma()
    check_ollama()
    check_font()
    check_whisper()
    check_demo_cache()
    elapsed = time.perf_counter() - t0

    width = max(len(name) for name, _, _ in _results)
    print()
    for name, status, detail in _results:
        print(f"  [{status}] {name.ljust(width)}  {detail}")

    failed = [n for n, s, _ in _results if s == FAIL]
    warned = [n for n, s, _ in _results if s == WARN]
    print()
    if failed:
        print(f"FAIL — {len(failed)} check(s) failed: {', '.join(failed)}  ({elapsed:.1f}s)")
        return 1
    suffix = f", {len(warned)} warning(s)" if warned else ""
    print(f"ALL PASS — {len(_results) - len(warned)} check(s) green{suffix}  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
