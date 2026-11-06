"""Lets the LLM run SQL on allowed tables, with user-owned rows scoped to the current user."""
from __future__ import annotations

import re
import uuid
from collections.abc import Collection
from typing import TYPE_CHECKING, Any
from config import settings
from agent.tools.base import Tool, ToolArgumentError, ToolResult, require_str

logger = settings.get_logger("agent.tools.sql_tool")
if TYPE_CHECKING:
    from agent.tools.sql_executor import SQLExecutor

MAX_ROWS = 50
_USER_ID_FILTER = re.compile(r"\b(?:[A-Za-z_]\w*\.)?user_id\s*=\s*:user_id\b", re.IGNORECASE)
_INSERT_USER_ID = re.compile(
    r"\binsert\s+into\s+[\w\.]+\s*\([^)]*\buser_id\b[^)]*\)\s*values\s*\([^)]*:user_id\b",
    re.IGNORECASE | re.DOTALL,
)
_BLOCKED = re.compile(r"\b(users|pg_\w+|information_schema)\b", re.IGNORECASE)
_TABLE_REF = re.compile(
    r'\b(?:from|join|into|update)\s+("?[A-Za-z_][\w$]*"?(?:\."?[A-Za-z_][\w$]*"?)?)', re.IGNORECASE
)
_CTE = re.compile(r'(?:\bwith\s+(?:recursive\s+)?|,\s*)("?[A-Za-z_]\w*"?)\s+as\s*\(', re.IGNORECASE)


def _tables_in(query: str) -> set[str]:
    """Rough table extraction (misses nothing common; `IS DISTINCT FROM x` may be misread as a table)."""
    ctes = {name.strip('"').lower() for name in _CTE.findall(query)}
    tables = {ref.replace('"', "").lower().split(".")[-1] for ref in _TABLE_REF.findall(query)}
    return tables - ctes


def _short(error: str) -> str:
    """Drop the echoed SQL and parameters SQLAlchemy appends to errors."""
    return error.split("\n[SQL:")[0].strip()[:400]


class SQLTool(Tool):
    name = "database"
    tool_type = "backend"
    description = """Run ONE SQL statement (SELECT, INSERT, UPDATE, or scoped DELETE) on the app database.
Arguments: query (SQL text), params (object with values for your named parameters).
Rules:
- Use named parameters like :title in the query and put their values in `params`.
- :user_id is filled in by the server. Never pass it yourself. Queries on user-owned tables must use it.
- A table without a user_id column must be reached through its parent table (see the notes in "Database tables").
- Columns with a DEFAULT are filled in by the database: leave them out of INSERT. Never invent ids or timestamps.
- Foreign-key values must be primary keys from the referenced table, not external service IDs. On a UNIQUE conflict, use PostgreSQL ON CONFLICT (unique_column) DO NOTHING, then SELECT the existing row's id before inserting dependent rows.
- To get the id of a row you just inserted, end the INSERT with RETURNING id.
- You can insert many rows in one statement: INSERT ... VALUES (:a1, :b1), (:a2, :b2).
- DELETE must target only the current user's rows using :user_id. No DROP or schema changes. No comments. One statement only.
Returns rows (max 50) and rowcount."""

    def __init__(
        self,
        executor: SQLExecutor,
        allowed_tables: Collection[str],
        shared_tables: Collection[str] = (),
    ) -> None:
        """`allowed_tables`: everything the LLM may touch. `shared_tables`: allowed tables with
        no owner (like a song catalog) that may be used without :user_id."""
        self._executor = executor
        self._allowed = {t.lower() for t in allowed_tables}
        self._shared = {t.lower() for t in shared_tables}

    def _check_query(self, query: str) -> str:
        query = query.strip().rstrip(";").strip()
        if ";" in query:
            raise ToolArgumentError("Only one SQL statement is allowed")
        if "--" in query or "/*" in query:
            raise ToolArgumentError("SQL comments are not allowed")
        if _BLOCKED.search(query):
            raise ToolArgumentError("That table is not available")

        tables = _tables_in(query)
        if not tables:
            raise ToolArgumentError("Query must read or write one of the available tables")
        unknown = tables - self._allowed
        if unknown:
            raise ToolArgumentError(
                f"Table(s) not available: {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(sorted(self._allowed))}"
            )

        if query.upper().startswith("DELETE") and tables & self._shared:
            raise ToolArgumentError("Shared catalog tables cannot be deleted")

        scoped = tables - self._shared
        if scoped:
            where_clause = re.split(r"\bwhere\b", query, maxsplit=1, flags=re.IGNORECASE)
            has_scoped_filter = len(where_clause) > 1 and bool(_USER_ID_FILTER.search(where_clause[1]))
            has_scoped_insert = bool(_INSERT_USER_ID.search(query)) or bool(_USER_ID_FILTER.search(query))
            is_insert = query[:6].upper() == "INSERT"
            if not (has_scoped_insert if is_insert else has_scoped_filter):
                raise ToolArgumentError(
                    f"Query touches user-owned table(s) {', '.join(sorted(scoped))}, so it must scope rows to :user_id. "
                    "For reads and updates, filter with user_id = :user_id. For inserts, include "
                    "user_id = :user_id or select through an ownership-checked parent."
                )
        return query

    async def execute(self, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        try:
            logger.debug("SQLTool.execute called with args: %s, user_id: %s", args, user_id)
            query = self._check_query(require_str(args, "query"))
            params = args.get("params") or {}
            if not isinstance(params, dict):
                raise ToolArgumentError("'params' must be an object")
        except ToolArgumentError as exc:
            return ToolResult.failure(str(exc))

        params = {**params, "user_id": user_id}  # always overrides anything the LLM sent
        try:
            outcome = await self._executor.execute_query(query, params)
        except Exception as exc:  # the validator raises on forbidden queries
            return ToolResult.failure(f"Query rejected: {_short(str(exc))}")

        if "error" in outcome:
            return ToolResult.failure(_short(outcome["error"]))

        rows = [dict(row) for row in outcome["data"]]
        data: dict[str, Any] = {"rows": rows[:MAX_ROWS], "rowcount": outcome["rowcount"]}
        if len(rows) > MAX_ROWS:
            data["truncated"] = True
        return ToolResult.success(data)
