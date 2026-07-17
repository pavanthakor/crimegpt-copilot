from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.core.db import get_db

app = FastAPI(title="CrimeGPT Copilot")

app.include_router(auth_router)
app.include_router(cases_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    """Open a DB session and confirm connectivity with a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as exc:  # surface the failure instead of 500-ing
        return {"db": "error", "detail": str(exc)}
