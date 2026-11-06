# Async Engine & Sessionmaker

from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings

logger = settings.get_logger('db.session')

def _build_engine_args():
    """
    Koyeb gives a URL like postgres://user:pass@host/db?sslmode=require
    asyncpg needs the postgresql+asyncpg driver and doesn't understand
    `sslmode` as a query param, so translate it to connect_args.
    """
    url = make_url(settings.POSTGRES_URL).set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    url = url.set(query=query)

    connect_args = {}
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode
    return url, connect_args


_url, _connect_args = _build_engine_args()

engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=True,   # drop dead connections (serverless Postgres sleeps)
    pool_size=5,          # keep small, Koyeb DB plans have low connection limits
    max_overflow=5,
    pool_recycle=1800,
    connect_args=_connect_args,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables. Fine to start with; switch to Alembic before prod."""
    # Import models so they register on SQLModel.metadata
    logger.info("Initializing database...")
    from models import tracks, user  # noqa: F401
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database initialized.")


async def close_db() -> None:
    await engine.dispose()