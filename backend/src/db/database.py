from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from ..core.config import settings

# Async 엔진 생성 (echo=True로 SQL 로그 확인 가능)
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# AsyncSession 생성기; expire_on_commit=False 설정
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base 클래스 (모델 클래스들이 상속받을 베이스)
Base = declarative_base()

async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close() 