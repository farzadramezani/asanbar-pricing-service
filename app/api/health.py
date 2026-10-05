from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.db.session import get_engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(engine: Annotated[Engine, Depends(get_engine)]) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL unavailable") from exc
    return {"status": "ready"}
