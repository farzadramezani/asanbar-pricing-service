from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.models import Base

metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The local role and business schema are both named pricing. Pin search_path
    # so PostgreSQL's "$user" default does not move Alembic's version table there.
    engine = create_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        connect_args={"options": "-csearch_path=public"},
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=metadata,
            include_schemas=True,
            include_name=lambda name, type_, _: type_ != "schema" or name == "pricing",
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
