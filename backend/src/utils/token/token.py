import random
import string
import re
from datetime import datetime, timedelta
from typing import Optional
import redis
from src.core.config import settings  # Redis 설정을 위한 import

class TokenService:
    def __init__(self):
        self._token_pattern = re.compile(r'^[A-Z0-9]{3}$')
        self._token_expiry_days = 7
        self._redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True
        )
        self._token_prefix = "token:"  # Redis key prefix
        self._used_tokens_key = "used_tokens"  # Set of all used tokens

    def generate_token(self) -> str:
        """중복되지 않는 3자리 랜덤 토큰 생성"""
        while True:
            token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
            token_key = f"{self._token_prefix}{token}"

            try:
                if not self._redis.ping():
                    raise redis.ConnectionError("Redis connection failed")

                with self._redis.pipeline() as pipe:
                    try:
                        pipe.watch(self._used_tokens_key, token_key)
                        if not pipe.sismember(self._used_tokens_key, token):
                            pipe.multi()
                            pipe.sadd(self._used_tokens_key, token)
                            pipe.hset(token_key, mapping={
                                "created_at": datetime.now().isoformat(),
                                "status": "active"
                            })
                            expiry_seconds = int(timedelta(days=self._token_expiry_days).total_seconds())
                            pipe.expire(token_key, expiry_seconds)
                            pipe.expire(self._used_tokens_key, expiry_seconds + 60)
                            pipe.execute()

                            # TTL 설정 확인 및 재시도
                            max_retries = 3
                            for retry in range(max_retries):
                                token_ttl = self._redis.ttl(token_key)
                                if token_ttl == -1 or token_ttl == -2:  # TTL이 설정되지 않았거나 키가 없는 경우
                                    self._redis.expire(token_key, expiry_seconds)
                                    self._redis.expire(self._used_tokens_key, expiry_seconds + 60)
                                else:
                                    break
                            else:  # max_retries 횟수만큼 시도했지만 실패
                                self.release_token(token)
                                continue

                            return token

                    except redis.WatchError:
                        continue

            except redis.RedisError as e:
                raise

    def validate_token(self, token: str) -> bool:
        """토큰 유효성 검증"""
        # 형식 검증
        if not self._token_pattern.match(token):
            return False
        
        # Redis에서 토큰 정보 조회
        token_key = f"{self._token_prefix}{token}"
        token_data = self._redis.hgetall(token_key)
        
        if not token_data:
            return False
            
        # 만료 여부 검증
        created_at = datetime.fromisoformat(token_data["created_at"])
        if self.is_token_expired(created_at):
            return False

        return token_data.get("status") == "active"

    def is_token_expired(self, created_at: datetime) -> bool:
        """토큰 만료 여부 확인"""
        return datetime.now() - created_at >= timedelta(days=self._token_expiry_days)

    def release_token(self, token: str) -> None:
        """토큰 해제 (재사용 가능하도록)"""
        self._redis.srem(self._used_tokens_key, token)
        self._redis.delete(f"{self._token_prefix}{token}")

    def get_expiry_date(self, token: str) -> Optional[datetime]:
        """토큰 만료일 계산"""
        token_key = f"{self._token_prefix}{token}"
        token_data = self._redis.hgetall(token_key)
        if not token_data:
            return None
        
        created_at = datetime.fromisoformat(token_data["created_at"])
        return created_at + timedelta(days=self._token_expiry_days)

    def get_remaining_time(self, token: str) -> Optional[timedelta]:
        """토큰의 남은 유효 시간 반환"""
        expiry_date = self.get_expiry_date(token)
        if not expiry_date:
            return None
        
        remaining = expiry_date - datetime.now()
        return remaining if remaining.total_seconds() > 0 else None 