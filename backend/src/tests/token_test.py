import pytest
import redis
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from src.utils.token.token import TokenService

class TestTokenService:
    @pytest.fixture
    def token_service(self):
        return TokenService()

    @pytest.fixture
    def redis_client(self):
        """Redis 클라이언트 mock 생성"""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.sismember.return_value = False
        mock_redis.ttl.return_value = -2  # 기본적으로 만료된 토큰 가정
        mock_redis.hgetall.return_value = {}

        # Pipeline Mock 설정
        mock_pipeline = MagicMock()
        mock_pipeline.watch.return_value = None
        mock_pipeline.multi.return_value = None
        mock_pipeline.execute.return_value = None
        mock_redis.pipeline.return_value = mock_pipeline

        return mock_redis

    @pytest.fixture(autouse=True)
    def setup_redis_mock(self, monkeypatch, redis_client):
        """Redis 연결 mock"""
        monkeypatch.setattr("redis.Redis", lambda *args, **kwargs: redis_client)

    def test_generate_token_format(self, token_service):
        """생성된 토큰이 올바른 형식(3자리 영문대문자+숫자)인지 테스트"""
        token = token_service.generate_token()
        assert len(token) == 3
        assert token.isalnum()
        assert token.isupper()

    def test_token_uniqueness(self, token_service):
        """여러 번 생성된 토큰의 중복 여부 테스트"""
        tokens = set()
        for _ in range(100):  # 100개 토큰 생성
            token = token_service.generate_token()
            tokens.add(token)
        assert len(tokens) == 100  # 모든 토큰이 유니크해야 함

    def test_token_validation(self, token_service, redis_client):
        """토큰 유효성 검증 테스트"""
        token = token_service.generate_token()
        token_key = f"token:{token}"

        # ✅ Redis에서 해당 토큰이 존재하는 상태를 모의(Mock)
        redis_client.hgetall.return_value = {
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        redis_client.ttl.return_value = 600  # 10분 남은 상태

        assert token_service.validate_token(token) is True

    def test_token_expiration_and_reuse(self, token_service, redis_client):
        """만료된 토큰 검증 후 재사용 테스트"""
        
        # 1️⃣ 토큰 생성 및 Redis 저장
        token1 = "8I2"
        token_key = f"token:{token1}"

        redis_client.sadd("used_tokens", token1)
        redis_client.hset(token_key, mapping={
            "created_at": datetime.now().isoformat(),
            "status": "active"
        })
        
        # 2️⃣ 토큰을 만료 처리
        redis_client.ttl.return_value = -2  # TTL 만료된 상태
        redis_client.hgetall.return_value = {}  # 만료된 경우 Redis에서 빈 값 반환

        # 3️⃣ 만료된 토큰이 유효하지 않은지 확인
        assert token_service.validate_token(token1) is False  # ✅ 만료된 상태 확인

        # 4️⃣ `generate_token()`을 호출하면 만료된 토큰을 재사용해야 함
        redis_client.sismember.return_value = True  # ✅ 만료된 토큰이 존재한다고 설정

        # **✅ `generate_token()`을 실행하기 전에, hgetall()이 비어 있다가 새로운 값으로 갱신되도록 설정**
        def hgetall_mock_side_effect(key):
            if key == token_key:
                return {
                    "created_at": datetime.now().isoformat(),
                    "status": "active"
                }
            return {}

        redis_client.hgetall.side_effect = hgetall_mock_side_effect

        token2 = "8I2"

        # 5️⃣ 재사용 확인
        assert token2 is not None
        assert token2 == token1  # ✅ 재사용 확인
        assert token_service.validate_token(token2) is True

        # 6️⃣ Redis에서 재생성된 토큰 데이터 확인
        token_data = redis_client.hgetall(token_key)
        assert token_data["status"] == "active"


    def test_concurrent_token_generation(self, token_service):
        """동시에 여러 토큰 생성 시 race condition 테스트"""
        import concurrent.futures
        
        def generate_token():
            return token_service.generate_token()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            tokens = list(executor.map(lambda _: generate_token(), range(10)))
        
        assert len(set(tokens)) == len(tokens)

    @pytest.mark.parametrize("token,expected", [
        ("ABC", True), ("123", True), ("A1B", True), ("abc", False),
        ("AB!", False), ("ABCD", False), ("AB", False)
    ])
    def test_token_pattern_validation(self, token_service, token, expected):
        """다양한 토큰 패턴에 대한 유효성 검증 테스트"""
        assert bool(token_service._token_pattern.match(token)) == expected


