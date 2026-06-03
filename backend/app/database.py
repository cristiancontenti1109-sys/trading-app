from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

_is_postgres = settings.database_url.startswith("postgresql")
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"ssl": "require"} if _is_postgres else {},
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        from app.models import user, instrument, signal, notification  # noqa
        await conn.run_sync(Base.metadata.create_all)
