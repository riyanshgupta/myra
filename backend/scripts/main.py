"""One-off: give EXISTING tables the server-side defaults the models now declare.

    python -m scripts.apply_server_defaults

create_all() never alters tables that already exist, so run this once (safe to re-run).
Needs PostgreSQL 13+ for gen_random_uuid().
"""
import asyncio

from sqlalchemy import text
from sqlmodel import SQLModel

from db.session import engine

DEFAULTS = {"id": "gen_random_uuid()", "created_at": "now()", "updated_at": "now()"}


async def main() -> None:
    from models import tracks, user  # noqa: F401  (registers tables on the metadata)

    async with engine.begin() as conn:
        for table in SQLModel.metadata.tables.values():
            for column, default in DEFAULTS.items():
                col = table.columns.get(column)
                if col is None:
                    continue
                if column == "id" and "UUID" not in str(col.type).upper():
                    continue  # only touch uuid ids
                await conn.execute(
                    text(f'ALTER TABLE "{table.name}" ALTER COLUMN "{column}" SET DEFAULT {default}')
                )
                print(f"{table.name}.{column} -> DEFAULT {default}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())