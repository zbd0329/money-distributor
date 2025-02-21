from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.mysql import UUID
from uuid import uuid4
from ..core.config import settings

# 데이터베이스 엔진 생성
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True
)

# 세션 팩토리 생성
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base 클래스 생성
Base = declarative_base()

# UUID 생성 함수
def generate_uuid():
    return str(uuid4())

# 의존성 주입을 위한 제너레이터 함수
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close() 