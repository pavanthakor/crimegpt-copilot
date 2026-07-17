"""SQLAlchemy engine, session factory, declarative Base, and get_db dependency."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, future=True
)

Base = declarative_base()


def get_db() -> Session:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
