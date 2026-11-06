from functools import lru_cache
from sqlalchemy import Integer
from sqlmodel import SQLModel

from models.tracks import (
    FavoriteTrack, PlaybackState, Playlist, PlaylistTrack, QueueTrack, Track,
)
from models.user import UserMetadata  # User is left out on purpose: it holds pin_hash

# Only these tables are shown to the LLM and accepted by SQLTool.
ALLOWED_MODELS = [
    UserMetadata, Playlist, PlaylistTrack, Track,
    FavoriteTrack, QueueTrack, PlaybackState,
]
ALLOWED_TABLES = frozenset(m.__tablename__ for m in ALLOWED_MODELS)


def _owner_parents(table) -> set[str]:
    """Tables this one points to that have a user_id column."""
    return {
        fk.column.table.name
        for col in table.columns
        for fk in col.foreign_keys
        if "user_id" in fk.column.table.columns
    }


@lru_cache
def get_shared_tables() -> frozenset[str]:
    """Allowed tables with no owner at all (e.g. a song catalog)."""
    return frozenset(
        name
        for name in ALLOWED_TABLES
        if "user_id" not in SQLModel.metadata.tables[name].columns
        and not _owner_parents(SQLModel.metadata.tables[name])
    )


def _access_note(table) -> str:
    if "user_id" in table.columns:
        return "Owned by the user. Always filter with user_id = :user_id."
    parents = sorted(_owner_parents(table))
    if parents:
        return (
            f"Has no user_id column. Reach it through {', '.join(parents)} "
            "and filter that table with user_id = :user_id."
        )
    return "Shared data, not owned by any user. Do not use :user_id for it."


def _relationship_tables() -> list[str]:
    """Describe association tables from their foreign keys, without table-name rules."""
    descriptions = []
    for name in sorted(ALLOWED_TABLES):
        table = SQLModel.metadata.tables[name]
        references = sorted({fk.column.table.name for col in table.columns for fk in col.foreign_keys})
        if len(references) >= 2:
            descriptions.append(
                f"- {name} links rows from {', '.join(references)}. "
                "When a request asks to associate, add, assign, or include one of these rows "
                "in another, insert the relationship row here after both referenced rows exist. "
                "Creating the referenced rows alone does not create the relationship."
            )
    return descriptions


def _ordered_relationship_tables() -> list[str]:
    """Tell the agent how to assign order values within each parent relationship."""
    descriptions = []
    for name in sorted(ALLOWED_TABLES):
        table = SQLModel.metadata.tables[name]
        if "position" not in table.columns:
            continue
        parents = sorted({fk.column.table.name for col in table.columns for fk in col.foreign_keys})
        if parents:
            descriptions.append(
                f"- {name}.position orders rows within each {', '.join(parents)} parent. "
                "When adding rows, explicitly assign distinct consecutive values after the "
                "current maximum for that parent; do not rely on its column default. For a "
                "batch, use ROW_NUMBER() plus the current maximum so each new row gets a "
                "different position."
            )
    return descriptions


def _unique_columns(table) -> set[str]:
    """Return columns protected by a single-column unique constraint or index."""
    unique = {
        constraint.columns.keys()[0]
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint" and len(constraint.columns) == 1
    }
    unique.update(
        next(iter(index.columns)).name
        for index in table.indexes
        if index.unique and len(index.columns) == 1
    )
    return unique


@lru_cache
def generate_llm_schema_context() -> str:
    model_map = {m.__tablename__: m for m in ALLOWED_MODELS}
    schema_output = []

    for table_name in sorted(ALLOWED_TABLES):
        table_obj = SQLModel.metadata.tables[table_name]
        model_class = model_map[table_name]

        table_context = [f"Table: {table_name}"]
        if model_class.__doc__:
            table_context.append(f"Description: {model_class.__doc__.strip()}")
        table_context.append(f"Access: {_access_note(table_obj)}")
        unique_columns = _unique_columns(table_obj)
        table_context.append("Columns:")

        for col in table_obj.columns:
            attributes = []
            if col.primary_key:
                attributes.append("PRIMARY KEY")
            if col.name in unique_columns:
                attributes.append("UNIQUE")
            attributes.append("NULL" if col.nullable else "NOT NULL")

            if col.server_default is not None:
                default = getattr(col.server_default, "arg", "set by the database")
                attributes.append(f"DEFAULT {default} - leave out of INSERT")
            
            elif col.primary_key and isinstance(col.type, Integer):
                attributes.append("AUTO-INCREMENT - leave out of INSERT")
    
            elif not col.nullable:
                attributes.append("REQUIRED in INSERT")

            for fk in col.foreign_keys:
                attributes.append(f"FOREIGN KEY -> {fk.target_fullname}")

            field = model_class.model_fields.get(col.name)
            col_desc = col.comment or (field.description if field else None) or ""

            table_context.append(
                f"  - {col.name} ({col.type}) [{', '.join(attributes)}] : {col_desc}"
            )

        schema_output.append("\n".join(table_context))

    relationships = _relationship_tables()
    ordered_relationships = _ordered_relationship_tables()
    if relationships:
        schema_output.insert(
            0,
            "Relationship handling:\n"
            "Use the schema foreign keys to identify relationship tables. For each requested "
            "association between existing or newly created rows, insert the corresponding "
            "foreign-key values into the relationship table; inserting entity rows does not "
            "associate them. For foreign keys, use the referenced table's primary-key value, "
            "not an external service ID or another column's value.\n"
            "For a UNIQUE conflict, do not retry the same plain INSERT. Use PostgreSQL "
            "INSERT ... ON CONFLICT (unique_column) DO NOTHING, then SELECT the existing "
            "row's primary key by its unique value before inserting dependent relationship rows.\n"
            + "\n".join(relationships),
        )
    if ordered_relationships:
        schema_output.insert(
            1 if relationships else 0,
            "Ordering rows in relationships:\n" + "\n".join(ordered_relationships),
        )
    schema_output.append(
        "User music state guidance:\n"
        "- Use :user_id for every user-owned write and filter reads/updates to that user. "
        "Never accept a user_id value from the user or invent one.\n"
        "- favorite_tracks saves a track for the user; identify the track through tracks.id, "
        "not its JioSaavn ID.\n"
        "- queue_tracks stores upcoming tracks. Set user_id, tracks.id, and a distinct position "
        "after that user's current maximum.\n"
        "- playback_states stores the user's current track and player controls. Update the "
        "existing user's row when present; otherwise insert one.\n"
        "- user_metadata stores per-user play counts and last-played timestamps. Do not change "
        "tracks.play_count to represent one user's play; that is the aggregate catalog count."
    )
    return "\n\n-------------------------\n\n".join(schema_output)
