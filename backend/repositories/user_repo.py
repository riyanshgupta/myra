import uuid
from datetime import timedelta

from sqlalchemy import update
from sqlmodel import select

from db.base_model import utcnow
from models.user import User
from repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        """Get user model by username, or None if not found."""
        stmt = select(User).where(User.username == username)
        result = await self.session.exec(stmt)
        return result.first()

    async def username_exists(self, username: str) -> bool:
        """Check if a user with the given username exists."""
        return await self.get_by_username(username) is not None

    async def set_pin_hash(self, user: User, pin_hash: str) -> User:
        """Set the user's PIN hash and reset failed attempts and lockout."""
        return await self.update(
            user, {"pin_hash": pin_hash, "failed_attempts": 0, "locked_until": None}
        )

    async def record_failed_attempt(
        self, user_id: uuid.UUID, max_attempts: int, lock_for: timedelta
    ) -> None:
        # Atomic increment so parallel guesses can't dodge the counter
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_attempts=User.failed_attempts + 1)
            .returning(User.failed_attempts)
        )
        result = await self.session.exec(stmt)
        attempts = result.scalar_one()
        if attempts >= max_attempts:
            await self.session.exec(
                update(User)
                .where(User.id == user_id)
                .values(locked_until=utcnow() + lock_for)
            )
        await self.session.commit()

    async def reset_failed_attempts(self, user: User) -> User:
        return await self.update(user, {"failed_attempts": 0, "locked_until": None})