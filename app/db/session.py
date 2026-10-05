from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine

from app.core.config import get_settings

metadata = MetaData(schema="pricing")


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
