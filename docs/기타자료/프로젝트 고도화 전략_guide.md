# 고도화 개발전략

시스템의 확장성과 안정성을 위해 아래와 같은 고도화 전략을 수립합니다.  
각 항목은 향후 시스템 운영, 유지보수 및 장애 대응에 큰 도움이 될 것입니다.

---

# 최종 고도화 전략 요약

1. **캐싱 전략**: Redis와 같은 인메모리 캐시 시스템을 활용하여 잔액 정보 및 잦은 조회 데이터를 캐싱합니다.
2. **로깅 및 모니터링**: ELK Stack, Prometheus, Grafana 등을 사용해 시스템 로그와 실시간 모니터링을 수행합니다.
3. **배치 처리**: 오래된 데이터 정리와 거래 아카이빙, 통계 집계 작업을 배치 처리합니다.
4. **API 요율 제한**: Rate Limiting을 적용해 과도한 요청으로 인한 시스템 부하를 방지합니다.
5. **장애 복구 전략**: 데이터베이스 복제, 백업, Circuit Breaker 패턴 및 Celery를 통한 장애 복구 체계를 마련합니다.
6. **메시지 큐 도입**: Celery, RabbitMQ 등을 활용해 비동기 작업을 처리합니다.
7. **API 버전 관리**: 버전별 라우터를 사용하여 API 변경에 효율적으로 대응합니다.
8. **보안 강화**: API 키 관리, 요청 서명 검증, SQL Injection/XSS 방지, IP 화이트리스트 등을 적용합니다.
9. **에러 코드 정리**: 일관된 에러 메시지와 코드를 통해 디버깅 효율성을 높입니다.

---

이 문서는 시스템 고도화를 위해 고려해야 할 주요 전략들을 포함하고 있으며, 각 항목은 실제 구현 시 참고할 수 있는 예시와 코드 블록을 포함하고 있습니다.


---

## 1. 캐싱 전략

- **목적**: 자주 조회되는 데이터의 응답 속도를 개선하고 DB 부하를 줄입니다.
- **적용 대상**:
  - **잔액 정보**: 사용자의 지갑 잔액 및 거래 내역
  - **사용자 프로필**: 프로필 정보, 친구 목록 등 변경이 자주 발생하지 않는 데이터
  - **채팅방 정보**: 채팅방 상세 정보 및 멤버 목록
  - **뿌리기 토큰 유효성 검증**: 뿌리기 요청 시 토큰 검증 결과를 캐싱하여 빠른 응답 제공
- **도구**: Redis, Memcached 등 인메모리 캐시 스토어 활용

---

## 2. 로깅 및 모니터링

- **목적**: 시스템 동작 상태 및 문제 발생 시 원인 분석을 위한 로그 기록과 실시간 모니터링
- **구현 방안**:
  - **로깅**:  
    - `loguru`, **ELK Stack** (Elasticsearch, Logstash, Kibana) 등을 활용하여 애플리케이션 및 트랜잭션 로그를 별도로 기록
  - **모니터링**:  
    - Prometheus, Grafana 등을 활용해 서버 및 애플리케이션 상태를 실시간으로 모니터링

**로깅 설정 예시**:

```python
LOGGING_CONFIG = {
    'version': 1,
    'handlers': {
        'app_handler': {
            'level': 'INFO',
            'filename': 'app.log',
            'formatter': 'detailed'
        },
        'transaction_handler': {
            'level': 'INFO',
            'filename': 'transactions.log',
            'formatter': 'detailed'
        }
    }
}
```

---

## 3. 배치 처리

- **목적**: 데이터 정리 및 통계 집계 작업을 주기적으로 수행하여 시스템 성능을 유지합니다.
- **적용 대상**:
  - 오래된 뿌리기 데이터 정리: 만료된 뿌리기 데이터를 정리 및 삭제
  - 거래 내역 아카이빙: 일정 기간 지난 거래 내역을 별도 저장소로 이전하여 DB 부담 감소
  - 통계 데이터 집계: 사용량, 거래 패턴, 시스템 성능 관련 통계 집계 작업 수행

---

## 4. API 요율 제한 (Rate Limiting)

- **목적**: 특정 사용자나 IP에서 과도한 요청이 발생할 경우 시스템 부하를 방지
- **구현 방안**: 요청 수를 제한하여 일정 시간 내 최대 요청 수를 초과할 경우 HTTP 429 (Too Many Requests) 에러를 반환

**RateLimiter 예시**:

```python
from fastapi import HTTPException
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_requests: int, time_window: timedelta):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}

    async def check_rate_limit(self, user_id: int):
        current_time = datetime.now()
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # 시간 윈도우 밖의 요청 제거
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if current_time - req_time <= self.time_window
        ]

        if len(self.requests[user_id]) >= self.max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")

        self.requests[user_id].append(current_time)
```

---

## 5. 장애 복구 전략

- **목적**: 장애 발생 시 신속한 복구와 데이터 손실 최소화
- **구현 방안**:
  - 데이터베이스 복제 및 백업 전략: 정기적인 백업과 실시간 복제 시스템 구축
  - 서비스 장애 복구 프로세스: 자동화된 복구 및 수동 조치를 위한 문서화된 프로세스 마련
  - Circuit Breaker 패턴 적용: 외부 서비스 장애 시 전체 시스템에 미치는 영향을 줄이기 위한 패턴 도입
  - 비동기 작업 처리: Celery 등 메시지 큐를 활용하여 백그라운드 작업 및 장애 복구 작업을 비동기적으로 처리

**Celery 설정 예시**:

```python
CELERY_CONFIG = {
    'broker_url': 'redis://localhost:6379/0',
    'result_backend': 'redis://localhost:6379/0',
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json']
}
```

---

## 6. 메시지 큐 도입

- **목적**: 비동기 작업 및 분산 처리, 시스템 확장성을 위한 메시지 큐 도입
- **구현 방안**:  
  Celery, RabbitMQ, Redis Queue 등을 활용하여 비동기 작업을 처리  
  예: 대량의 뿌리기/받기 요청, 배치 처리, 로그 처리 등

**메시지 큐 설정 예시 (Celery)**:

```python
CELERY_CONFIG = {
    'broker_url': 'redis://localhost:6379/0',
    'result_backend': 'redis://localhost:6379/0',
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json']
}
```

---

## 7. API 버전 관리 상세화

- **목적**: 향후 API 변경 사항에 유연하게 대응하고 클라이언트와의 호환성을 유지
- **구현 방안**: API 경로에 버전 정보를 명시하여 버전별로 독립적인 라우터를 관리

**API 버전 관리 예시**:

```python
from fastapi import APIRouter, FastAPI

app = FastAPI()
v1_router = APIRouter(prefix="/api/v1")
v2_router = APIRouter(prefix="/api/v2")

# API 버전별 라우터 설정
app.include_router(v1_router)
app.include_router(v2_router)
```

---

## 8. 보안 강화

- **목적**: 시스템 전반의 보안성을 강화하여 악의적 공격 및 데이터 유출을 방지
- **구현 방안**:
  - API 키 순환 정책: 정기적으로 API 키를 갱신하여 보안을 강화
  - 요청 서명 검증: 각 요청에 대해 서명을 검증하여 위변조를 방지
  - Rate Limiting 적용 (위 4번 참고)
  - SQL Injection, XSS 방지: ORM 사용 및 철저한 입력값 검증
  - IP 화이트리스트: 특정 IP 또는 네트워크에서만 접근하도록 제한

---

## 9. 에러 코드 정리

- **목적**: API 응답 시 구체적인 에러 코드와 메시지를 제공하여 클라이언트와의 소통 및 디버깅을 용이하게 함
- **구현 방안**:  
  표준화된 에러 코드 체계를 수립하고 모든 API에서 일관된 포맷으로 에러 응답 반환  
  예시:  
  - ERR001: 잘못된 요청  
  - ERR002: 인증 실패  
  - ERR003: 서버 내부 오류

---




