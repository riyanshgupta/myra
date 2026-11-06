"""The tool-calling loop: ask Qwen, run the tool it asks for, feed the result back."""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from agent.parser import ToolCallParseError, ToolCallParser
from agent.registry import ToolRegistry
from agent.tools.base import ClientEvent, Tool, ToolResult

logger = logging.getLogger(__name__)

MAX_STEPS = 8  # LLM follow-ups per request; multi-step tasks (playlists) need several
MAX_TOOL_RESPONSE_CHARS = 6000
_FALLBACK_REPLY = "Sorry, I could not finish that. Please try again."
_LIMIT_NOTICE = (
    "Tool limit reached. Stop calling tools. Tell the user in plain text what you completed and "
    "what you could not. Do not say anything was done unless a tool result confirmed it."
)
_NUDGE = (
    "You described an action but did not call a tool. If you still need a tool, reply with "
    "ONLY the tool call. If you are finished, give the final answer without mentioning future steps."
)
_AFTER_RESULT = (
    "If more steps are needed, reply with ONLY the next tool call. "
    "If the task is complete, give the final answer."
)

# "Let me create the playlist:" / "I'll search for ..." with no tool call attached
_INTENT = re.compile(
    r"\b(let me (?!know\b)|i'll|i will|now i (?:need|will|should)|next,? i|first,? i)", re.IGNORECASE
)
_INTENT_OPENING = re.compile(
    r"^\W*(?:(?:sure|okay|ok|alright|great)\W+)?(?:let me (?!know\b)|i'll|i will)", re.IGNORECASE
)
_TRAILING_PROMISE = (":", "...", "…")


def _looks_unfinished(reply: str, steps: int) -> bool:
    """True if a tool-free reply reads like a promise of an action rather than an answer."""
    text = reply.strip()
    if text.endswith(_TRAILING_PROMISE):
        return True
    if steps > 0:  # mid-task, so intent anywhere near the end means it stopped early
        return bool(_INTENT.search(text[-200:]))
    return len(text) < 250 and bool(_INTENT_OPENING.match(text))


class ChatBackend(Protocol):
    """What the runner needs from your llm_orchestrator."""

    async def new_chat(self, message: str) -> Any: ...

    async def continue_chat(self, session: Any, message: str) -> Any: ...


@dataclass
class AgentResult:
    reply: str
    session: Any
    event: ClientEvent | None = None  # None means a plain text answer


class AgentRunner:
    def __init__(
        self,
        llm: ChatBackend,
        registry: ToolRegistry,
        parser: ToolCallParser | None = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._parser = parser or ToolCallParser()
        self._max_steps = max_steps

    async def run(self, message: str, session: Any | None, user_id: uuid.UUID) -> AgentResult:
        if session is None:
            result = await self._llm.new_chat(message)
        else:
            result = await self._llm.continue_chat(session, message)

        event: ClientEvent | None = None
        steps = 0
        nudged = False
        gave_up = False
        last_error: str | None = None  # error of the most recent failed step, if it failed
        while True:
            parse_error = None
            call = None
            try:
                call = self._parser.parse(result.reply)
            except ToolCallParseError as exc:
                parse_error = str(exc)
                logger.warning("Step %d: bad tool call (%s). Raw reply: %r", steps, parse_error, result.reply[:500])

            if call is None and parse_error is None:
                # Plain text. Normally the final answer, unless it only promises an action.
                if not nudged and steps < self._max_steps and _looks_unfinished(result.reply, steps):
                    nudged = True
                    steps += 1
                    logger.info("Step %d: reply looks unfinished, nudging. Reply: %r", steps, result.reply[:200])
                    result = await self._llm.continue_chat(result.session, _NUDGE)
                    continue
                # Still promising a future action after the nudge: do not expose internal narration.
                gave_up = nudged and _looks_unfinished(result.reply, steps)
                logger.info("Step %d: final answer (%d chars)", steps, len(result.reply))
                break

            if steps >= self._max_steps:
                notice = _LIMIT_NOTICE
                if last_error:
                    notice += f" The last tool call failed: {last_error[:200]}"
                result = await self._llm.continue_chat(result.session, notice)
                logger.info("Step %d: tool limit reached. Reply: %r", steps, result.reply[:200])
                break
            steps += 1

            if parse_error is not None:
                last_error = parse_error
                feedback: dict[str, Any] = {"ok": False, "error": parse_error}
            else:
                logger.info("Step %d: tool call %s", steps, call.name)
                tool = self._registry.get(call.name)
                if tool is None:
                    outcome = ToolResult.failure(f"Unknown tool '{call.name}'")
                    logger.warning("Unknown tool requested: %s", call.name)
                else:
                    outcome = await self._execute(tool, call.arguments, user_id)
                    
                    if not outcome.ok:
                        logger.warning(f"Tool {call.name} failed: {outcome.error} \n\n Arguments: {call.arguments}, user_id: {user_id}")

                last_error = None if outcome.ok else outcome.error
                if outcome.ok and outcome.client_event is not None:
                    event = outcome.client_event  # the last one wins
                feedback = outcome.for_llm()

            logger.info("Step %d: tool feedback %s...", steps, json.dumps(feedback, default=str)[:200])
            result = await self._llm.continue_chat(result.session, self._tool_response(feedback))

        reply = _FALLBACK_REPLY if gave_up else (self._parser.strip(result.reply) or _FALLBACK_REPLY)
        return AgentResult(reply=reply, session=result.session, event=event)

    @staticmethod
    async def _execute(tool: Tool, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        try:
            return await tool.execute(args, user_id)
        except Exception:
            logger.exception("Tool %s crashed", tool.name)
            return ToolResult.failure("The tool failed unexpectedly")

    @staticmethod
    def _tool_response(payload: dict[str, Any]) -> str:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > MAX_TOOL_RESPONSE_CHARS:
            text = text[:MAX_TOOL_RESPONSE_CHARS] + "...[truncated]"
        # The reminder keeps Qwen from narrating the next step instead of doing it
        return f"<tool_response>\n{text}\n</tool_response>\n{_AFTER_RESULT}"
    
