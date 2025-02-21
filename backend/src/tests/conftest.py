import pytest
import os
from unittest.mock import patch
from pydantic_settings import BaseSettings, SettingsConfigDict

# ✅ 테스트용 가짜 설정 클래스
class TestSettings(BaseSettings):
    DATABASE_URL: str = "mysql+asyncmy://test:test@test-db:3306/test_db"
    REDIS_HOST: str = "test-redis"
    REDIS_PORT: int = 6379
    PROJECT_NAME: str = "Test Project"
    API_V1_STR: str = "/api/v1"

    model_config = SettingsConfigDict(extra="ignore")  # ✅ Pydantic v2 대응

# ✅ `settings = Settings()` 실행 전에 환경 변수 설정
os.environ["DATABASE_URL"] = "mysql+asyncmy://test:test@test-db:3306/test_db"
os.environ["REDIS_HOST"] = "test-redis"
os.environ["REDIS_PORT"] = "6379"

# ✅ `src.core.config.settings`를 가져오기 전에 환경 변수가 설정되어야 함
from src.core.config import settings

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """테스트 환경에서 settings 값을 가짜 설정으로 대체"""
    test_settings = TestSettings()

    # ✅ settings 객체 자체를 테스트용 설정으로 교체
    monkeypatch.setattr("src.core.config.settings", test_settings)
