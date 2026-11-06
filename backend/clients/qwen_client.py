"""Async client for Qwen's guest chat web API.

The web API is undocumented and may change independently of this client. Keep
its wire format in this module; callers should work with ``QwenChatSession``
and ``QwenChatResult`` instead of constructing request payloads themselves.
"""

from __future__ import annotations

import re
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from time import time
from typing import Any, TypedDict

import msgspec
from curl_cffi.requests import AsyncSession, Response

from clients.base_client import BaseClient
from core.session import base_session

_BASE_URL = "https://chat.qwen.ai"
_BOOTSTRAP_URL = "https://sg-wum.alibaba.com/w/wu.json"
_DEFAULT_MODEL = "qwen3.7-plus"
_DEFAULT_TIMEOUT = 90.0
_DEFAULT_HEADERS = {
    "Connection": "keep-alive",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "bx-v": "2.5.36",
}
_TOKEN_RE = re.compile(r"['\"]([A-Za-z0-9_+/=-]{32,})['\"]")
logger = logging.getLogger(__name__)


class QwenFeatureConfig(TypedDict, total=False):
    """Overrides for Qwen web-chat generation options.

    Unspecified keys retain the client defaults. The values below reflect the
    observed Qwen web API payload; this undocumented API may add or change
    accepted values.
    """

    thinking_enabled: bool
    output_schema: str
    research_mode: str
    auto_thinking: bool
    thinking_mode: str
    thinking_format: str
    auto_search: bool


class QwenClientError(RuntimeError):
    """Base error for Qwen API and response failures."""


class QwenAPIError(QwenClientError):
    """The Qwen API returned an unsuccessful HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Qwen API returned HTTP {status_code}: {detail[:500]}")


class QwenProtocolError(QwenClientError):
    """Qwen returned a response that did not match the expected protocol."""


@dataclass(frozen=True, slots=True)
class QwenChatSession:
    """State required to continue one guest chat in a later request.

    Store the returned session between turns and pass it to
    :meth:`QwenClient.continue_chat`. It includes Qwen's guest token, so treat
    it as sensitive server-side data; do not send it to an untrusted client.
    """

    chat_id: str
    bx_umidtoken: str
    model: str = _DEFAULT_MODEL
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class QwenChatResult:
    """Assistant text plus the continuation state for the next turn.

    ``session`` contains an updated ``parent_id`` when Qwen provides an
    assistant message ID in its response. Use that updated session for the
    next ``continue_chat`` call.
    """

    session: QwenChatSession
    reply: str
    assistant_message_id: str | None = None


class QwenClient(BaseClient):
    """HTTP client for Qwen's undocumented guest chat API.

    The HTTP session is injected and owned by the application. The client
    itself does not retain conversation state: each chat is represented by an
    immutable :class:`QwenChatSession`, so conversations can be interleaved
    without sharing their turn history.

    Args:
        model: Default Qwen model used by :meth:`new_chat` unless overridden.
        session: Shared curl_cffi AsyncSession managed by the application.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Create a Qwen API client using an externally managed HTTP session.

        The caller owns the session lifecycle. Do not close the injected session
        from this client because other API clients may share it.
        """
        super().__init__(session)
        self._model = model
        self._timeout = timeout
        self._closed = False

    def close(self) -> None:
        """Mark this client as unavailable without closing the shared session."""
        self._closed = True

    async def new_chat(
        self,
        message: str,
        *,
        model: str | None = None,
        feature_config: QwenFeatureConfig | None = None,
    ) -> QwenChatResult:
        """Create a guest conversation and send its first user message.

        Args:
            message: Non-empty text to send as the first turn.
            model: Optional model override; defaults to the constructor's
                ``model`` setting (``qwen3.7-plus`` by default).
            feature_config: Optional generation settings. Omitted keys keep
                these defaults: ``thinking_enabled=False``,
                ``output_schema="json"``, ``research_mode="normal"``,
                ``auto_thinking=False``, ``thinking_mode="Fast"``,
                ``thinking_format="summary"``, and ``auto_search=False``.
                Boolean keys accept ``bool``; the other keys accept strings.
                The settings mirror the observed Qwen web request; Qwen does
                not publish a stable schema for this guest endpoint.

        Returns:
            A :class:`QwenChatResult` with the assistant reply and the session
            to use for the next turn.

        Raises:
            ValueError: ``message`` is empty or contains only whitespace.
            QwenAPIError: Qwen returns a non-success HTTP status.
            QwenProtocolError: Qwen's bootstrap, chat creation, or completion
                response is missing required data.
            curl_cffi request exceptions: The network request fails or times
                out.
        """
        prompt = self._validate_message(message)
        selected_model = model or self._model
        umidtoken = await self._get_umidtoken()
        chat_id = await self._create_chat(umidtoken, selected_model)
        
        session = QwenChatSession(
            chat_id=chat_id,
            bx_umidtoken=umidtoken,
            model=selected_model,
        )
        return await self._send(session, prompt, feature_config=feature_config)

    async def continue_chat(
        self,
        session: QwenChatSession,
        message: str,
        *,
        feature_config: QwenFeatureConfig | None = None,
    ) -> QwenChatResult:
        """Append a user turn to an existing Qwen guest conversation.

        Pass the ``session`` from the most recent :class:`QwenChatResult`, not
        the original session from ``new_chat``. The updated session contains
        the Qwen assistant message ID needed to link this turn to the previous
        reply.

        Args:
            session: Continuation state returned by ``new_chat`` or the latest
                ``continue_chat`` call. Keep it server-side because it contains
                Qwen's guest token.
            message: Non-empty text for the next user turn.
            feature_config: Optional generation settings, with the same keys,
                types, and defaults as in :meth:`new_chat`. For example,
                ``{"thinking_enabled": True, "auto_search": True}`` overrides
                only those two settings and retains all other defaults.

        Returns:
            A :class:`QwenChatResult` containing the assistant reply and the
            updated session required for the following turn.

        Raises:
            TypeError: ``session`` is not a :class:`QwenChatSession`.
            ValueError: ``message`` is empty or the session is incomplete.
            QwenProtocolError: The previous response had no assistant message
                ID, so Qwen cannot safely link another turn.
            QwenAPIError: Qwen returns a non-success HTTP status.
            curl_cffi request exceptions: The network request fails or times
                out.
        """
        if not isinstance(session, QwenChatSession):
            raise TypeError("session must be a QwenChatSession")
        if not session.chat_id or not session.bx_umidtoken:
            raise ValueError("session must include chat_id and bx_umidtoken")
        if session.parent_id is None:
            raise QwenProtocolError(
                "This chat has no assistant message ID to continue from; "
                "the previous Qwen completion response did not include one."
            )
        prompt = self._validate_message(message)
        return await self._send(session, prompt, feature_config=feature_config)

    async def _get_umidtoken(self) -> str:
        response = await self._request(
            "GET",
            _BOOTSTRAP_URL,
            headers={
                "Accept": "*/*",
                "Referer": f"{_BASE_URL}/c/new-chat",
                "sec-fetch-dest": "script",
                "sec-fetch-mode": "no-cors",
                "sec-fetch-site": "cross-site",
                "sec-fetch-storage-access": "none",
                "source": "web",
                **_DEFAULT_HEADERS,
            },
        )
        self._ensure_success(response.status_code, response.text)

        # The bootstrap payload has varied between JSON and a small JS
        # response. Prefer an explicitly named token when it is JSON.
        try:
            payload = msgspec.json.decode(response.content)
        except msgspec.DecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in ("bx_umidtoken", "bx-umidtoken", "token"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value

        match = _TOKEN_RE.search(response.text)
        if not match:
            raise QwenProtocolError("Qwen bootstrap response did not contain a token")
        return match.group(1)

    async def _create_chat(self, umidtoken: str, model: str) -> str:
        headers = self._headers(
            umidtoken,
            referer=f"{_BASE_URL}/c/new-chat",
            accept="application/json, text/plain, */*",
        )
        headers["source"] = "web"
        headers.update(_SAME_ORIGIN_FETCH_HEADERS)
        response = await self._request(
            "POST",
            f"{_BASE_URL}/api/v2/chats/new",
            headers=headers,
            json={
                "title": "New Chat",
                "models": [model],
                "chat_mode": "guest",
                "chat_type": "t2t",
                "timestamp": _timestamp_ms(),
                "project_id": "",
            },
        )
        self._ensure_success(response.status_code, response.text)
        try:
            payload = msgspec.json.decode(response.content)
            chat_id = payload.get("data", {}).get("id")
        except (msgspec.DecodeError, AttributeError):
            chat_id = None
        if not isinstance(chat_id, str) or not chat_id:
            raise QwenProtocolError("Qwen create-chat response did not contain data.id")
        return chat_id

    async def _send(
        self,
        session: QwenChatSession,
        message: str,
        *,
        feature_config: QwenFeatureConfig | None,
        retry_guest_limit: bool = True,
    ) -> QwenChatResult:
        user_message_id = str(uuid.uuid4())
        message_node_id = str(uuid.uuid4())
        message_timestamp = _timestamp_s()
        payload = {
            "stream": True,
            "version": "2.1",
            "size": "16:9",
            "incremental_output": True,
            "chat_id": session.chat_id,
            "chat_mode": "guest",
            "model": session.model,
            "parent_id": session.parent_id,
            "messages": [
                {
                    "fid": user_message_id,
                    "parentId": session.parent_id,
                    "childrenIds": [message_node_id],
                    "role": "user",
                    "content": message,
                    "user_action": "chat",
                    "files": [],
                    "timestamp": message_timestamp,
                    "models": [session.model],
                    "chat_type": "t2t",
                    "feature_config": {
                        **_default_feature_config(),
                        **(feature_config or {}),
                    },
                    "extra": {"meta": {"subChatType": "t2t"}},
                    "sub_chat_type": "t2t",
                    "parent_id": session.parent_id,
                }
            ],
            "timestamp": message_timestamp + 1,
        }
        headers = self._headers(
            session.bx_umidtoken,
            referer=f"{_BASE_URL}/c/guest",
            accept="application/json",
        )
        headers.update(_SAME_ORIGIN_FETCH_HEADERS)
        headers["X-Accel-Buffering"] = "no"
        headers["Cookie"] = "x-ap=ap-southeast-1"
        response = await self._request(
            "POST",
            f"{_BASE_URL}/api/v2/chat/completions",
            params={"chat_id": session.chat_id},
            headers=headers,
            json=payload,
        )
        self._ensure_success(response.status_code, response.text)
        # Keep response handling in memory; do not write API responses to disk.
        reply, assistant_id = _decode_completion(response.content)
        if not reply:
            if retry_guest_limit and _is_guest_chat_limit(response.content):
                logger.warning(
                    "Qwen guest chat limit reached for chat %s; retrying in a new chat",
                    session.chat_id,
                )
                umidtoken = await self._get_umidtoken()
                chat_id = await self._create_chat(umidtoken, session.model)
                fresh_session = QwenChatSession(
                    chat_id=chat_id,
                    bx_umidtoken=umidtoken,
                    model=session.model,
                )
                return await self._send(
                    fresh_session,
                    message,
                    feature_config=feature_config,
                    retry_guest_limit=False,
                )
            if "_____tmd_____" in response.text or '"action":"captcha"' in response.text:
                raise QwenProtocolError(
                    "Qwen returned an anti-bot challenge instead of a completion."
                )
            logger.warning(
                "[QwenClient._send] status_code: %d Qwen completion response contained no assistant text: %s",
                response.status_code,
                response.text[:500],
            )
            raise QwenProtocolError("Qwen completion response contained no assistant text")

        # Qwen usually includes the assistant message's ID in its final stream
        # event. Without that ID, another turn cannot be linked safely.
        new_session = QwenChatSession(
            chat_id=session.chat_id,
            bx_umidtoken=session.bx_umidtoken,
            model=session.model,
            parent_id=assistant_id or session.parent_id,
        )
        updated = new_session
        return QwenChatResult(updated, reply, assistant_id)

    @staticmethod
    def _headers(umidtoken: str, *, referer: str, accept: str) -> dict[str, str]:
        return {
            **_DEFAULT_HEADERS,
            "source": "h5",
            "Accept": accept,
            "Content-Type": "application/json",
            "Origin": _BASE_URL,
            "Referer": referer,
            "bx-umidtoken": umidtoken,
            "X-Request-Id": str(uuid.uuid4()),
            "Timezone": datetime.now().astimezone().strftime(
                "%a %b %d %Y %H:%M:%S GMT%z"
            ),
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        """Send a request through the injected shared AsyncSession.

        Session lifecycle is managed by the application, not this client.
        Request-specific headers and cookies should be passed through kwargs.
        """
        if self._closed:
            raise RuntimeError("QwenClient is closed")

        return await self.session.request(
            method,
            url,
            timeout=self._timeout,
            **kwargs,
        )

    @staticmethod
    def _ensure_success(status_code: int, body: str) -> None:
        if status_code != 200:
            logger.warning(
                "Qwen API returned HTTP %s: %s",
                status_code,
                body[:500],
            )
        if not 200 <= status_code < 300:
            raise QwenAPIError(status_code, body)

    @staticmethod
    def _validate_message(message: str) -> str:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        return message


def _is_guest_chat_limit(content: bytes) -> bool:
    """Return whether Qwen's completion payload reports an exhausted guest limit."""
    try:
        payload = msgspec.json.decode(content)
    except msgspec.DecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    return isinstance(data, dict) and data.get("code") == "RateLimited"


def _timestamp_ms() -> int:
    return int(time() * 1000)


def _timestamp_s() -> int:
    return int(time())


def _default_feature_config() -> dict[str, Any]:
    return {
        "thinking_enabled": False,
        "output_schema": "json",
        "research_mode": "normal",
        "auto_thinking": False,
        "thinking_mode": "Fast",
        "thinking_format": "summary",
        "auto_search": False,
    }


_SAME_ORIGIN_FETCH_HEADERS = {
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _decode_completion(content: bytes) -> tuple[str, str | None]:
    """Read text and assistant message ID from Qwen's SSE response."""
    decoded = content.decode("utf-8", errors="replace")
    fragments: list[str] = []
    assistant_id: str | None = None

    # Handle standard SSE (including multiline data fields) and tolerate a
    # JSON response body if the upstream changes its transport format.
    data_lines = [line[5:].lstrip() for line in decoded.splitlines() if line.startswith("data:")]
    if not data_lines and decoded.strip():
        data_lines = [decoded.strip()]

    for line in data_lines:
        if not line or line == "[DONE]":
            continue
        try:
            event = msgspec.json.decode(line)
        except msgspec.DecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_fragments = _completion_text(event)
        fragments.extend(event_fragments)
        
        assistant_id = assistant_id or _assistant_id(event)

    return "".join(fragments), assistant_id


def _completion_text(value: Any, *, assistant_context: bool = False) -> list[str]:
    """Extract generated text from OpenAI chunks and nested Qwen events.

    Qwen's web endpoint has returned both OpenAI-compatible ``choices`` and
    nested ``data.message``/``output`` objects. Only read generic text fields
    when the object is identified as an assistant message, so user echoes and
    event metadata are not accidentally returned as the answer.
    """
    if isinstance(value, list):
        return [part for item in value for part in _completion_text(
            item, assistant_context=assistant_context
        )]
    if not isinstance(value, dict):
        return []

    role = value.get("role")
    is_assistant = assistant_context or role == "assistant"
    found: list[str] = []

    choices = value.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or choice.get("message")
            if isinstance(delta, dict):
                found.extend(_completion_text(delta, assistant_context=True))

    # Standard chunk fields, and Qwen's message objects.
    for key in ("content", "text", "output_text"):
        field_value = value.get(key)
        if is_assistant and isinstance(field_value, str):
            found.append(field_value)
        elif is_assistant and isinstance(field_value, list):
            # Some APIs encode content as [{"type":"text", "text":"..."}].
            for block in field_value:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    found.append(block["text"])

    for key in ("data", "message", "delta", "output", "result"):
        child = value.get(key)
        if isinstance(child, (dict, list)):
            found.extend(_completion_text(child, assistant_context=is_assistant))

    return found


def _assistant_id(value: Any) -> str | None:
    """Find a likely assistant message ID without mistaking chat IDs for it."""
    if not isinstance(value, dict):
        return None
    # Use DFS to find parent_id key and the value, once found return
    for key in value:
        if key == "parent_id" and isinstance(value[key], str):
            return value[key]
        elif isinstance(value[key], dict):
            result = _assistant_id(value[key])
            if result is not None:
                return result
        elif isinstance(value[key], list):
            for item in value[key]:
                result = _assistant_id(item)
                if result is not None:
                    return result
    return None

qwen_client = QwenClient(session=base_session.get_session())
