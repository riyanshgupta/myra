import logging

from pydantic import ValidationError

from agent.prompt import PromptBuilder
from agent.runner import AgentResult, AgentRunner
from clients.qwen_client import QwenChatSession, QwenClientError  # adjust to your paths
from exceptions import LLMUnavailableError
from models.user import User
from schemas.req import ChatRequest, ChatSession
from schemas.resp import (
    ChatSession as ChatSessionResp,
    ChatResponse,
    ChatResponseMessageType,
    FunctionCallMetadata,
    SongMetadata,
)

logger = logging.getLogger(__name__)


class AssistantService:
    """One chat turn: build the message, run the agent, shape the response."""

    def __init__(self, runner: AgentRunner, prompts: PromptBuilder) -> None:
        self._runner = runner
        self._prompts = prompts

    async def chat(self, user: User, request: ChatRequest) -> ChatResponse:
        message = self._prompts.build_message(
            request.message,
            request.metaData,
            first_turn=request.session is None,
        )
        session = QwenChatSession(**request.session.model_dump()) if request.session else None

        try:
            result = await self._runner.run(message, session, user.id)
        except QwenClientError as exc:
            logger.warning("Qwen request failed: %s", exc)
            raise LLMUnavailableError() from exc
        return self._to_response(result)

    @staticmethod
    def _to_response(result: AgentResult) -> ChatResponse:
        s = result.session
            
    #     chat_id: str,
    # bx_umidtoken: str,
    # model: str = "qwen3.7-plus",
    # parent_id: str | None = None
        session = ChatSessionResp(
            chat_id=s.chat_id,
            bx_umidtoken=s.bx_umidtoken,
            model=s.model,
            parent_id=s.parent_id,
        )

        event = result.event
        if event is not None:
            try:
                if event.type.lower() == "song":
                    return ChatResponse(
                        message=result.reply,
                        message_type=ChatResponseMessageType.SONG,
                        metadata=SongMetadata(**event.payload),
                        session=session
                    )
                return ChatResponse(
                    message=result.reply,
                    message_type=ChatResponseMessageType.FUNCTION_CALL,
                    metadata=FunctionCallMetadata(**event.payload),
                    session=session
                )
            except ValidationError:
                # A bad payload should not break the chat; fall back to the text reply
                logger.exception("Invalid %s payload from a tool", event.type)

        return ChatResponse(message=result.reply, session=session)
