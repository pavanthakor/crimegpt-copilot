"""Setup helper: print and validate demo seed counts (used by setup.ps1 / setup.sh)."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/verify_seed_counts.py` from anywhere — put backend/ on sys.path
# so `app.*` imports resolve the same way as `cd backend && python -m ...`.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))

from app.core.db import SessionLocal  # noqa: E402
from app.models import Case, User  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        users = db.query(User).count()
        cases = db.query(Case).count()
        names = sorted(u.username for u in db.query(User).all())
        print(f"users={users}")
        print(f"cases={cases}")
        print("usernames=" + ",".join(names))
        if users < 4 or cases < 2:
            print("VERIFY_FAIL: need users>=4 and cases>=2", file=sys.stderr)
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
