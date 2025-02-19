import sys
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# src 디렉토리를 Python 경로에 추가
src_path = str(Path(__file__).parent.parent)
if src_path not in sys.path:
    sys.path.append(src_path)

# 테스트용 DB URL
TEST_DB_URL = "mysql+aiomysql://root:12341234@localhost:3306/money-distributor"

@pytest_asyncio.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DB_URL)

@pytest_asyncio.fixture
async def async_session(engine):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback() 