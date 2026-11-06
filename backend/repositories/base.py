""" Generic CRUD repository """
import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

ModelT = TypeVar("ModelT", bound=SQLModel)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: uuid.UUID | int) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def list(self, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.exec(
            select(self.model).offset(offset).limit(limit)
        )
        return result.all()

    async def create(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(obj)
        return obj

    def add(self, obj: ModelT) -> None:
        """Stage an object in the current unit of work without committing it."""
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def refresh(self, obj: ModelT) -> ModelT:
        await self.session.refresh(obj)
        return obj

    async def stage_delete(self, obj: ModelT) -> None:
        """Stage a delete so a service can commit it with related changes."""
        await self.session.delete(obj)

    async def update(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        obj.sqlmodel_update(data)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.commit()
