import os

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from app.db.session import Base, SessionLocal, engine

router = APIRouter()


@router.post("/clear-database")
def clear_database(x_cleanup_token: str = Header(default="")):
    enabled = os.getenv("ENABLE_DATABASE_CLEANUP", "").lower() == "true"
    cleanup_token = os.getenv("DATABASE_CLEANUP_TOKEN", "")

    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    if not cleanup_token or x_cleanup_token != cleanup_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid cleanup token",
        )

    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]

    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=OFF"))
        for table_name in table_names:
            db.execute(text(f'DELETE FROM "{table_name}"'))
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()

    return {
        "message": "Database cleared successfully",
        "tables": table_names,
    }
