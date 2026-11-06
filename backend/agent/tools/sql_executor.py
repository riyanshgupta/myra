"""
Contains method to execute raw SQL queries against the database. 
This will be called by the agent to execute SQL queries and return the results.
"""


import re

from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SQLQueryValidator:
    ALLOWED_STATEMENTS = {"SELECT", "INSERT", "UPDATE", "DELETE"}

    FORBIDDEN_KEYWORDS = {
        "DROP", "ALTER", "TRUNCATE", "CREATE",
        "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
        "MERGE", "REPLACE"
    }

    @classmethod
    def validate(cls, query: str) -> None:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        query = query.strip()

        # Reject SQL comments and multiple statements.
        if re.search(r"--|/\*|\*/|#", query):
            raise ValueError("SQL comments are not allowed")

        normalized_query = query.rstrip(";").strip()

        if ";" in normalized_query:
            raise ValueError("Multiple SQL statements are not allowed")

        match = re.match(
            r"^(SELECT|INSERT|UPDATE|DELETE)\b",
            normalized_query,
            re.IGNORECASE,
        )

        if not match:
            raise ValueError(
                "Only SELECT, INSERT, UPDATE, and scoped DELETE queries are allowed"
            )

        # Block forbidden keywords anywhere in the query.
        # This is a basic safeguard, not a full SQL parser.
        keywords = re.findall(
            r"\b[A-Za-z_]+\b",
            normalized_query.upper(),
        )

        forbidden = cls.FORBIDDEN_KEYWORDS.intersection(keywords)

        if forbidden:
            raise ValueError(
                f"Forbidden SQL operation(s): {', '.join(sorted(forbidden))}"
            )


class SQLExecutor:
    def __init__(
        self,
        db_session: AsyncSession,
        validator: type[SQLQueryValidator] = SQLQueryValidator,
    ):
        self._db_session = db_session
        self._validator = validator

    async def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validator.validate(query)

        try:
            result = await self._db_session.execute(
                text(query),
                params or {},
            )
            await self._db_session.commit()
            if result.returns_rows:
                return {
                    "data": result.mappings().all(),
                    "rowcount": result.rowcount,
                }

            return {
                "data": [],
                "rowcount": result.rowcount,
            }

        except Exception as exc:
            await self._db_session.rollback()
            return {"error": f"Error executing query: {exc}"}
