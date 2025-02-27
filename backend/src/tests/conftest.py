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
    DATABASE_URL: str
    REDIS_HOST: str
    REDIS_PORT: int
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
    print(f"Using database URL: {settings.DATABASE_URL}")  # 디버깅을 위해 URL 출력
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # 기존 테이블 삭제
        await conn.run_sync(Base.metadata.create_all)  # 새로운 테이블 생성
    
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
