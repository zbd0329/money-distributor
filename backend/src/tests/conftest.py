import pytest
import os
from unittest.mock import patch
from pydantic_settings import BaseSettings, SettingsConfigDict
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.db.models import Base

# 테스트용 가짜 설정 클래스
class TestSettings(BaseSettings):
    TEST_DATABASE_URL: str
    TEST_REDIS_HOST: str
    TEST_REDIS_PORT: int
    TEST_RABBITMQ_HOST: str
    TEST_RABBITMQ_PORT: int
    TEST_RABBITMQ_USER: str
    TEST_RABBITMQ_PASSWORD: str
    PROJECT_NAME: str = "Test Project"
    API_V1_STR: str = "/api/v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# `src.core.config.settings`를 가져오기 전에 환경 변수가 설정되어야 함
from src.core.config import settings

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """테스트 환경에서 settings 값을 가짜 설정으로 대체"""
    test_settings = TestSettings()
    monkeypatch.setattr("src.core.config.settings", test_settings)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    """MySQL 테스트 DB 세션 생성"""
    if not settings.TEST_DATABASE_URL or 'test' not in settings.TEST_DATABASE_URL.lower():
        raise ValueError(
            "TEST_DATABASE_URL must be set and must contain 'test' in the database name for safety"
        )
    
    print(f"Using test database URL: {settings.TEST_DATABASE_URL}")
    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        echo=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
