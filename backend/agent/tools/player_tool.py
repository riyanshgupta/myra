"""Frontend tool: the app performs the action, the backend only relays it."""
from __future__ import annotations

import uuid
from typing import Any

from agent.tools.base import ClientEvent, Tool, ToolArgumentError, ToolResult

_SIMPLE_ACTIONS = {"pause", "resume", "next", "previous"}
_SEEK_BY_ACTIONS = {"seek_forward", "seek_backward"}
_MAX_SECONDS = 24 * 60 * 60


def _seconds(args: dict[str, Any], default: int | None) -> int:
    raw = args.get("seconds", default)
    if raw is None:
        raise ToolArgumentError("'seconds' is required for this action")
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        raise ToolArgumentError("'seconds' must be an integer") from None
    if not 0 <= seconds <= _MAX_SECONDS:
        raise ToolArgumentError("'seconds' is out of range")
    return seconds


class PlayerControlTool(Tool):
    name = "player"
    tool_type = "frontend"
    description = """Control the music player in the app. Set `action` to one of:
- pause, resume, next, previous
- seek_forward / seek_backward: skip by `seconds` (optional, default 10)
- seek_to: jump to `seconds` from the start of the song (required)
The app performs the action; you only trigger it."""

    async def execute(self, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        action = args.get("action")
        try:
            if action in _SIMPLE_ACTIONS:
                params: dict[str, Any] = {}
            elif action in _SEEK_BY_ACTIONS:
                params = {"seconds": _seconds(args, default=10)}
            elif action == "seek_to":
                params = {"seconds": _seconds(args, default=None)}
            else:
                valid = sorted(_SIMPLE_ACTIONS | _SEEK_BY_ACTIONS | {"seek_to"})
                return ToolResult.failure(f"Unknown action. Use one of: {', '.join(valid)}")
        except ToolArgumentError as exc:
            return ToolResult.failure(str(exc))

        return ToolResult.success(
            {"status": "sent to the app"},
            client_event=ClientEvent("function_call", {"function_name": action, "arguments": params}),
        )