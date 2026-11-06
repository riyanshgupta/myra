from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from agent.prompt import PromptBuilder
from agent.registry import ToolRegistry
from agent.runner import AgentRunner
from agent.tools.jiosaavn_tool import JioSaavnTool
from agent.tools.player_tool import PlayerControlTool
from agent.tools.sql_executor import SQLExecutor
from agent.table_schema_service import (
    ALLOWED_TABLES,
    generate_llm_schema_context,
    get_shared_tables,
)
from agent.tools.sql_tool import SQLTool
from clients.saavn_client import saavn_client
from db.session import get_session
from models.user import User
from repositories.playback_repo import PlaybackRepository
from repositories.playlist_repo import PlaylistRepository
from repositories.track_repo import TrackRepository
from repositories.user_repo import UserRepository
from services.assistant_service import AssistantService
from services.auth_service import decode_access_token
from services.user_service import UserService
from services.playback_service import PlaybackService
from services.playlist_service import PlaylistService
from services.track_service import TrackService
from services.qwen_service import llm_orchestrator

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repo(session: AsyncSession = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def get_user_service(repo: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(repo)


def get_track_service(session: AsyncSession = Depends(get_session)) -> TrackService:
    return TrackService(TrackRepository(session), saavn_client)


def get_playlist_service(
    session: AsyncSession = Depends(get_session),
    track_service: TrackService = Depends(get_track_service),
) -> PlaylistService:
    return PlaylistService(PlaylistRepository(session), track_service)


def get_playback_service(
    session: AsyncSession = Depends(get_session),
    track_service: TrackService = Depends(get_track_service),
) -> PlaybackService:
    return PlaybackService(PlaybackRepository(session), track_service, saavn_client)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    repo: UserRepository = Depends(get_user_repo),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized

    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise unauthorized

    user = await repo.get(user_id)
    if user is None :
        raise unauthorized
    return user


def get_table_schema_text() -> str:
    return generate_llm_schema_context()  # cached after the first call


def get_assistant_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AssistantService:
    track_service = TrackService(TrackRepository(session), saavn_client)
    playback_service = PlaybackService(PlaybackRepository(session), track_service, saavn_client)
    registry = ToolRegistry(
        [
            JioSaavnTool(saavn_client, playback_service=playback_service),
            SQLTool(
                SQLExecutor(session),
                allowed_tables=ALLOWED_TABLES,
                shared_tables=get_shared_tables(),
            ),
            PlayerControlTool(),  # remove until the app can handle function_call
        ]
    )
    prompts = PromptBuilder(registry, schema_text=get_table_schema_text())
    runner = AgentRunner(llm_orchestrator, registry)
    return AssistantService(runner, prompts)
