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
                    raise redis.ConnectionError("Redis connection failed, 현재 서비스를 이용할 수 없습니다. 관리자에게 문의하세요.")

                with self._redis.pipeline() as pipe:
                    try:
                        pipe.watch(self._used_tokens_key, token_key)
                        
                        # Redis에서 중복 토큰 체크
                        if pipe.sismember(self._used_tokens_key, token):
                            token_ttl = self._redis.ttl(token_key)
                            if token_ttl > 0:  # 유효한 토큰이면 새로운 토큰 생성
                                continue
                            elif token_ttl == -2:  # 만료된 토큰이면 상태만 변경하여 재사용
                                pipe.multi()
                                pipe.hset(token_key, mapping={
                                    "created_at": datetime.now().isoformat(),
                                    "status": "active"
                                })
                                expiry_seconds = int(timedelta(days=self._token_expiry_days).total_seconds())
                                pipe.expire(token_key, expiry_seconds)
                                pipe.execute()
                                return token
                        else:  # 새로운 토큰인 경우에만 저장
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

