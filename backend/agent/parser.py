from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_OPEN_TAG = "<tool_call>"


class ToolCallParseError(ValueError):
    """The reply tried to call a tool but the call is malformed."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


class ToolCallParser:
    # strict=False allows raw newlines inside JSON strings, which multi-line SQL needs
    _decoder = json.JSONDecoder(strict=False)
    _BLOCK = re.compile(r"<tool_call>.*?(?:</tool_call>|\Z)", re.DOTALL)

    def parse(self, reply: str) -> ToolCall | None:
        """Return the tool call in `reply`, or None if it is a plain answer.

        Lenient on purpose: text before or after the call, ```json fences, a
        missing closing tag and raw newlines in strings are all accepted.
        """
        start = reply.find(_OPEN_TAG)
        if start == -1:
            return None

        body = reply[start + len(_OPEN_TAG):]
        brace = body.find("{")
        if brace == -1:
            raise ToolCallParseError(
                'Tool call has no JSON. Reply with: <tool_call>{"name": ..., "arguments": {...}}</tool_call>'
            )
        candidate = body[brace:]
        try:
            payload, _ = self._decoder.raw_decode(candidate)
        except json.JSONDecodeError as exc:
            try:  # Qwen sometimes drops the last "}" or trails off into </parameter></function>
                payload, _ = self._decoder.raw_decode(self._balance(candidate))
            except json.JSONDecodeError:
                raise ToolCallParseError(f"Tool call is not valid JSON: {exc.msg}") from None

        if not isinstance(payload, dict):
            raise ToolCallParseError("Tool call must be a JSON object")
        name, arguments = payload.get("name"), payload.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ToolCallParseError("Tool call needs a string 'name' and an object 'arguments'")
        return ToolCall(name=name, arguments=arguments)

    @staticmethod
    def _balance(text: str) -> str:
        """Cut trailing junk (a tag after the JSON) and close unclosed braces/brackets."""
        closers: list[str] = []
        in_string = escaped = False
        for i, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                closers.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if not closers:
                    return text[:i]
                closers.pop()
                if not closers:
                    return text[: i + 1]
            elif ch == "<":  # JSON has no "<" outside strings, so this is a trailing tag
                return text[:i] + "".join(reversed(closers))
        return text + ('"' if in_string else "") + "".join(reversed(closers))

    def strip(self, reply: str) -> str:
        """Remove any leftover tool-call text so it never reaches the user."""
        return self._BLOCK.sub("", reply).strip()