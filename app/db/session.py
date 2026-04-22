import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

DATABASE_URL: str = os.getenv(
    "DB_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/rag"
)

# Create engine
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database by creating tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_document_metadata_columns()


def _ensure_document_metadata_columns() -> None:
    """Backfill document metadata columns for existing databases."""
    inspector = inspect(engine)
    if not inspector.has_table("documents"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("documents")}
    statements = []

    if "title" not in existing_columns:
        statements.append(
            "ALTER TABLE documents ADD COLUMN title VARCHAR NOT NULL DEFAULT 'Untitled Document'"
        )
    if "document_type" not in existing_columns:
        statements.append(
            "ALTER TABLE documents ADD COLUMN document_type VARCHAR NOT NULL DEFAULT 'general'"
        )
    if "year" not in existing_columns:
        statements.append("ALTER TABLE documents ADD COLUMN year INTEGER")
    if "program_name" not in existing_columns:
        statements.append("ALTER TABLE documents ADD COLUMN program_name VARCHAR")
    if "donor_name" not in existing_columns:
        statements.append("ALTER TABLE documents ADD COLUMN donor_name VARCHAR")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Session:
    """Dependency for getting a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
