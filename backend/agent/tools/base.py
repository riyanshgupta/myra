"""The interface every LLM tool implements, plus small argument helpers."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

ToolType = Literal["backend", "frontend"]


class ToolArgumentError(ValueError):
    """The LLM sent missing or invalid arguments. The message goes back to it."""


def require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolArgumentError(f"'{key}' is required and must be a non-empty string")
    return value.strip()


def get_limit(args: dict[str, Any], default: int, maximum: int) -> int:
    try:
        limit = int(args.get("limit", default))
    except (TypeError, ValueError):
        raise ToolArgumentError("'limit' must be an integer") from None
    return max(1, min(limit, maximum))


@dataclass
class ClientEvent:
    """Something the app must act on: play a song, or run a player function.
    Never shown to the LLM (it can contain long signed URLs)."""

    type: Literal["song", "function_call"]
    payload: dict[str, Any]


@dataclass
class ToolResult:
    ok: bool = True
    data: dict[str, Any] = field(default_factory=dict)  # what the LLM sees
    error: str | None = None
    client_event: ClientEvent | None = None  # what the app gets

    @classmethod
    def success(
        cls,
        data: dict[str, Any] | None = None,
        *,
        client_event: ClientEvent | None = None,
    ) -> "ToolResult":
        return cls(ok=True, data=data or {}, client_event=client_event)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, error=error)

    def for_llm(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, **self.data}
        return {"ok": False, "error": self.error}


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]  # goes into the prompt: explain actions and arguments
    tool_type: ClassVar[ToolType] = "backend"  # "frontend" = the app performs the action

    @abstractmethod
    async def execute(self, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        """Run the tool. `user_id` comes from the auth token, never from the LLM."""