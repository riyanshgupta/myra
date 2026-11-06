"""Declarative Base class"""
import uuid
from datetime import datetime, timezone

import fastuuid
from sqlalchemy import DateTime, func, text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> uuid.UUID:
    # fastuuid generates the UUIDv7; convert to a stdlib UUID so
    # pydantic, SQLAlchemy and asyncpg all accept it
    return uuid.UUID(str(fastuuid.uuid7()))


class TimestampModel(SQLModel):
    """Shared columns for every table. Not a table itself.

    Python-side defaults only run when you go through SQLModel. Raw SQL (the LLM's
    database tool) skips them, so each column also has a server-side default.
    """
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": utcnow},
        nullable=False,
    )

class IntBaseModel(TimestampModel):
    """Autoincrement integer id. For tables the LLM reads and writes."""
    id: int | None = Field(default=None, primary_key=True)

class BaseModel(TimestampModel):
    """Shared columns for every table. Not a table itself.

    Python-side defaults only run when you go through SQLModel. Raw SQL (the LLM's
    database tool) skips them, so each column also has a server-side default.
    """
    id: uuid.UUID = Field(
        default_factory=new_id,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        description="Unique identifier for the record",
    )