"""Application service for Qwen chat operations."""

from __future__ import annotations


from clients.qwen_client import (
    QwenChatResult,
    QwenChatSession,
    QwenClient,
    QwenFeatureConfig,
    qwen_client
)


class QwenService:
    """Application-facing interface for starting and continuing Qwen chats.

    This layer delegates Qwen's HTTP protocol to :class:`QwenClient`, while
    giving routes and other application services a stable chat API. Reuse a
    service instance for the application lifetime so the client can reuse its
    connection pool. Inject a client when managing its lifecycle elsewhere or
    substituting a test double.

    ``feature_config`` is a partial override of these defaults:

    | Key | Type | Default |
    | --- | --- | --- |
    | ``thinking_enabled`` | ``bool`` | ``False`` |
    | ``output_schema`` | ``str`` | ``"json"`` |
    | ``research_mode`` | ``str`` | ``"normal"`` |
    | ``auto_thinking`` | ``bool`` | ``False`` |
    | ``thinking_mode`` | ``str`` | ``"Fast"`` |
    | ``thinking_format`` | ``str`` | ``"summary"`` |
    | ``auto_search`` | ``bool`` | ``False`` |

    The defaults reflect the captured Qwen web request. Qwen does not publish
    a stable schema for this guest endpoint, so string option values are passed
    through to Qwen and may be subject to upstream changes.
    """

    def __init__(self, client: QwenClient) -> None:
        """Create the service, optionally using an externally managed client.
        """
        self._client = client

    async def new_chat(
        self,
        message: str,
        *,
        model: str | None = None,
        feature_config: QwenFeatureConfig | None = None,
    ) -> QwenChatResult:
        """Start a new guest chat, send its first message, and return its reply.

        Args:
            message: Non-empty first user message.
            model: Optional model override; defaults to the client configuration.
            feature_config: Optional partial override of the settings in the
                class documentation. For example,
                ``{"thinking_enabled": True, "auto_search": True}`` enables
                those options and leaves the other defaults unchanged.

        Returns:
            The assistant reply and a ``session`` value required to continue
            this conversation.

        Raises:
            ValueError: ``message`` is blank.
            QwenClientError: Qwen returns an error or an unexpected response.
            QwenClientError: Qwen returns an invalid response or a request
                fails or times out.
        """
        return await self._client.new_chat(
            message,
            model=model,
            feature_config=feature_config,
        )

    async def continue_chat(
        self,
        session: QwenChatSession,
        message: str,
        *,
        feature_config: QwenFeatureConfig | None = None,
    ) -> QwenChatResult:
        """Send another user message in a conversation started by ``new_chat``.

        Args:
            session: The ``result.session`` from the immediately preceding
                ``new_chat`` or ``continue_chat`` call. Use the latest value so
                each reply is linked to the correct parent message. Keep this
                state server-side; it contains Qwen's guest access token.
            message: Non-empty text for the next user turn.
            feature_config: Optional partial override of the documented
                defaults. Omitted keys retain their defaults; e.g.
                ``{"output_schema": "json", "auto_search": True}``.

        Returns:
            The assistant reply and an updated ``session`` for the next turn.

        Raises:
            TypeError: ``session`` is not a ``QwenChatSession``.
            ValueError: ``message`` is blank or the session is incomplete.
            QwenClientError: Qwen returns an error or an unexpected response.
            QwenClientError: Qwen returns an invalid response or a request
                fails or times out.
        """
        return await self._client.continue_chat(
            session,
            message,
            feature_config=feature_config,
        )

    

llm_orchestrator = QwenService(client=qwen_client)
