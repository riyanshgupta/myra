""" App initialization, middleware, & lifecycle events """

import asyncio
from contextlib import asynccontextmanager
from clients import qwen_client
from clients.qwen_client import QwenChatSession, QwenClientError
from db.session import init_db, close_db
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from schemas.req import TestChatRequest
import schemas.music as music_resp
from routes.user_route import router as user_router
from routes.track_route import router as track_router
from routes.library_route import router as library_router
from routes.playback_route import router as playback_router
from routes.playlist_route import router as playlist_router
from routes.assistant_route import router as assistant_router
from core.session import base_session
from services.qwen_service import llm_orchestrator
from exceptions import AppError

from time import perf_counter
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        yield
    finally:
        await asyncio.gather(
            close_db(), 
            base_session.close()
        )


app = FastAPI(
    title="FastAPI backend for Myra",
    description="API for Myra, a music streaming service that provides access to songs and playlists with power of AI",
    version="1.0.0",
    contact={"name": "Riyansh Gupta", "email": "riyanshgupta750@gmail.com"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    headers = exc.headers or {}
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

app.include_router(user_router)
app.include_router(track_router)
app.include_router(library_router)
app.include_router(playback_router)
app.include_router(playlist_router)
app.include_router(assistant_router)

@app.get("/health", response_model=music_resp.HealthResponse)
def health_check():
    return {"status": "healthy"}


@app.post("/test", response_model=music_resp.TestChatResponse)
async def test_endpoint(request: TestChatRequest | None = None):
    """Smoke-test Qwen with a new chat or continue a previous test chat.

    Send no body to start with the default greeting. To continue, send the
    ``session`` object returned by the previous response and a new ``message``.
    The response returns an updated session for the next turn.
    """
    request = request or TestChatRequest()
    started_at = perf_counter()

    try:
        if request.session is None:
            result = await llm_orchestrator.new_chat(request.message)
        else:
            session = QwenChatSession(**request.session.model_dump())
            result = await llm_orchestrator.continue_chat(session, request.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QwenClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "reply": result.reply,
        "elapsed_seconds": round(perf_counter() - started_at, 3),
        "session": {
            "chat_id": result.session.chat_id,
            "bx_umidtoken": result.session.bx_umidtoken,
            "model": result.session.model,
            "parent_id": result.session.parent_id,
        },
    }

@app.post('/test-saavn', response_model=music_resp.TestSaavnResponse)
async def test_saavn(query: str):
    """Smoke-test JioSaavn search."""
    started_at = perf_counter()
    from clients.saavn_client import saavn_client
    results = await saavn_client.search(query)
    
    
    return {
        "results": results,
        "elapsed_seconds": round(perf_counter() - started_at, 3),
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
