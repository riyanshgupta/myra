from config import settings

from fastapi import APIRouter, Depends, HTTPException, status
from exceptions import AppError

from models.user import User
from routes.deps import get_current_user, get_user_service
from schemas.req import ChangePinReq, LoginReq, RegisterReq
from schemas.resp import AuthResp, UserResp
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

logger = settings.get_logger('user_route')


def _internal_error(action: str, exc: Exception) -> HTTPException:
    logger.exception("Unexpected error during %s", action, exc_info=(type(exc), exc, exc.__traceback__))
    return HTTPException(status_code=500, detail="Internal server error")

def _auth_response(user: User, token: str) -> AuthResp:
    return AuthResp(access_token=token, user=UserResp.model_validate(user))


@router.post("/register", response_model=AuthResp, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterReq, service: UserService = Depends(get_user_service)):
    try:
        return _auth_response(*await service.register(body.username, body.pin))
    except AppError:
        raise
    except Exception as e:
        raise _internal_error("register", e) from e


@router.post("/login", response_model=AuthResp)
async def login(body: LoginReq, service: UserService = Depends(get_user_service)):
    try:
        return _auth_response(*await service.login(body.username, body.pin))
    except AppError:
        raise
    except Exception as e:
        raise _internal_error("login", e) from e


@router.get("/me", response_model=UserResp)
async def me(current_user: User = Depends(get_current_user)):
    try:
        return current_user
    except Exception as e:
        raise _internal_error("get current user", e) from e


@router.patch("/me/pin", status_code=status.HTTP_204_NO_CONTENT)
async def change_pin(
    body: ChangePinReq,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    try:
        await service.change_pin(current_user, body.current_pin, body.new_pin)
    except AppError:
        raise
    except Exception as e:
        raise _internal_error("change PIN", e) from e
