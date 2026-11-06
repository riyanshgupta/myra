# POST /assistant/chat
from fastapi import APIRouter, Depends
from models.user import User
from routes.deps import get_assistant_service, get_current_user
from schemas.resp import ChatResponse
from schemas.req import ChatRequest
from services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request_body: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: AssistantService = Depends(get_assistant_service),
):
    # No try/except needed: service errors are AppError subclasses and are turned
    # into HTTP responses by the handler in main.py.
    return await service.chat(current_user, request_body)