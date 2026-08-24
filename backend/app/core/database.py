from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Возвращает сессию SQLAlchemy и закрывает её после запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_schema():
    """Только для SQLite. На PostgreSQL не вызываем PRAGMA."""
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(subjects)")).fetchall()
        }
        if "attestation_type" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE subjects ADD COLUMN attestation_type VARCHAR(20) "
                    "DEFAULT 'none' NOT NULL"
                )
            )
            conn.commit()
