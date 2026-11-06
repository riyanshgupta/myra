"""User business rules: registration, login with lockout, PIN change."""
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from db.base_model import utcnow
from exceptions import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
    SamePinError,
    UsernameTakenError,
)
from models.user import User
from repositories.user_repo import UserRepository
from services.auth_service import (
    DUMMY_PIN_HASH,
    create_access_token,
    hash_pin,
    verify_pin,
)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def register(self, username: str, pin: str) -> tuple[User, str]:
        if await self.repo.username_exists(username):
            raise UsernameTakenError()

        user = User(username=username, pin_hash=await hash_pin(pin))
        try:
            user = await self.repo.create(user)
        except IntegrityError:  # two requests raced for the same username
            raise UsernameTakenError()
        return user, create_access_token(user.id)

    async def login(self, username: str, pin: str) -> tuple[User, str]:
        user = await self._authenticate(username, pin)
        return user, create_access_token(user.id)

    async def change_pin(self, user: User, current_pin: str, new_pin: str) -> None:
        if new_pin == current_pin:
            raise SamePinError()
        user = await self._authenticate(user.username, current_pin)
        await self.repo.set_pin_hash(user, await hash_pin(new_pin))

    async def _authenticate(self, username: str, pin: str) -> User:
        user = await self.repo.get_by_username(username)
        if user is None:
            await verify_pin(DUMMY_PIN_HASH, pin)  # keep timing similar to a real check
            raise InvalidCredentialsError()

        now = utcnow()
        if user.locked_until and user.locked_until > now:
            retry_after = int((user.locked_until - now).total_seconds()) + 1
            raise AccountLockedError(retry_after)

        if not await verify_pin(user.pin_hash, pin):
            await self.repo.record_failed_attempt(user.id, MAX_FAILED_ATTEMPTS, LOCKOUT)
            raise InvalidCredentialsError()

       

        if user.failed_attempts or user.locked_until:
            user = await self.repo.reset_failed_attempts(user)
        return user