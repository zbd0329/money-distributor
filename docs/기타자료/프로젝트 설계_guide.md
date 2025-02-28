# 개발 문서

본 문서는 FastAPI + MySQL 8.0 환경에서 기능 구현 목록을 충족하기 위한 개발 문서입니다.
모듈 기반 설계(예: user, room, spray, receive)와 계층별 구조(Controller, Service, Repository, Model/Schema)에 맞춰 작성되었습니다.

## 목차
1. [DB 설계](#1-db-설계)
2. [API 명세서](#2-api-명세서)
3. [추가 고려사항](#3-추가-고려사항)

## 1. DB 설계

### 1.1. users 테이블 (회원 정보)
**목적**: 회원가입, 로그인, 친구 추가 등 사용자 관련 기본 정보를 저장합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT): 회원 고유 식별자
- username (VARCHAR(50), UNIQUE, NOT NULL): 로그인용 아이디
- password (VARCHAR(255), NOT NULL): 해시 처리된 비밀번호
- email (VARCHAR(100), UNIQUE, NOT NULL): 이메일
- created_at (DATETIME, DEFAULT CURRENT_TIMESTAMP): 회원가입 시각
- updated_at (DATETIME, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP): 최근 수정 시각

### 1.2. user_wallet 테이블 (잔액 관리)
**목적**: 사용자의 돈 충전 및 잔액 조회 기능을 위한 잔액 정보를 관리합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT)
- user_id (INT, NOT NULL): users.id를 참조하는 외래키
- balance (BIGINT, NOT NULL, DEFAULT 0): 현재 잔액
- updated_at (DATETIME, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)

**제약조건**:
- user_id에 UNIQUE 제약 조건 (1:1 관계)

### 1.3. friends 테이블 (친구 관계)
**목적**: 사용자 간 친구 관계를 저장합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT)
- user_id (INT, NOT NULL): 친구 관계를 요청한 사용자 (users.id 참조)
- friend_id (INT, NOT NULL): 친구로 등록된 사용자 (users.id 참조)
- created_at (DATETIME, DEFAULT CURRENT_TIMESTAMP)

**제약조건**:
- (user_id, friend_id) 복합 UNIQUE 인덱스를 추가하여 중복 친구 추가 방지

### 1.4. chat_rooms 테이블 (채팅방)
**목적**: 채팅방의 기본 정보를 저장합니다.

**필드**:
- id (VARCHAR(36), PK): UUID 형식 또는 고유 문자열 (요청 Header "X-ROOM-ID"와 연계)
- room_name (VARCHAR(100)): 채팅방 이름 (옵션)
- created_at (DATETIME, DEFAULT CURRENT_TIMESTAMP)

### 1.5. chat_room_members 테이블 (채팅방 멤버)
**목적**: 채팅방에 참여한 사용자 목록을 관리합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT)
- chat_room_id (VARCHAR(36), NOT NULL): chat_rooms.id를 참조
- user_id (INT, NOT NULL): users.id를 참조
- joined_at (DATETIME, DEFAULT CURRENT_TIMESTAMP)

**제약조건**:
- (chat_room_id, user_id) 복합 UNIQUE 인덱스 (중복 참여 방지)

### 1.6. money_distribution 테이블 (뿌리기 기록)
**목적**: 뿌리기 API 호출 시 생성되는 전체 분배 건 정보를 저장합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT)
- token (CHAR(3), UNIQUE, NOT NULL): 3자리 예측 불가능 토큰
- creator_id (INT, NOT NULL): 뿌리기 요청자 (users.id 참조)
- chat_room_id (VARCHAR(36), NOT NULL): 뿌리기가 진행된 채팅방 (chat_rooms.id 참조)
- total_amount (BIGINT, NOT NULL): 뿌릴 총 금액
- recipient_count (INT, NOT NULL): 뿌릴 인원 수
- created_at (DATETIME, DEFAULT CURRENT_TIMESTAMP): 뿌리기 시각

**비즈니스 고려**:
- 생성 후 10분 동안 받기 가능, 7일 동안 조회 가능 (created_at 활용)

### 1.7. money_distribution_details 테이블 (뿌리기 상세 내역)
**목적**: money_distribution 내 각 분배 금액(랜덤 분배 결과)과 수령 상태를 저장합니다.

**필드**:
- id (INT, PK, AUTO_INCREMENT)
- distribution_id (INT, NOT NULL): money_distribution.id 참조
- allocated_amount (BIGINT, NOT NULL): 분배된 금액
- receiver_id (INT, NULL): 수령한 사용자 (users.id 참조), 기본값 NULL
- claimed_at (DATETIME, NULL): 수령 시각

**비즈니스 고려**:
- 아직 할당되지 않은 건은 receiver_id가 NULL
- 각 사용자는 단 한 번만 수령 가능하도록 서비스 계층에서 검증

### 1.8. transaction_history 테이블 (거래 이력)
**목적**: 모든 금전 거래(충전, 뿌리기, 받기)의 이력을 저장하여 추적성을 확보합니다.

**필드**:
- id (BIGINT, PK, AUTO_INCREMENT)
- transaction_type (ENUM('CHARGE', 'SPRAY', 'RECEIVE'), NOT NULL): 거래 유형
- user_id (INT, NOT NULL): 거래 주체 사용자 (users.id 참조)
- amount (BIGINT, NOT NULL): 거래 금액
- balance_after (BIGINT, NOT NULL): 거래 후 잔액
- related_user_id (INT, NULL): 관련된 상대 사용자 (뿌리기/받기의 경우)
- token (CHAR(3), NULL): 뿌리기/받기와 관련된 토큰
- chat_room_id (VARCHAR(36), NULL): 뿌리기/받기가 발생한 채팅방
- description (VARCHAR(255)): 거래 설명
- target_details (JSON, NULL): SPRAY 거래 시, 대상자 및 거래 금액 등의 세부 정보를 저장  
    예: [{"user_id": 2, "received_amount": 3000}, {"user_id": 3, "received_amount": 7000}]
- created_at (DATETIME, DEFAULT CURRENT_TIMESTAMP): 거래 발생 시각
- status (ENUM('SUCCESS', 'FAILED', 'CANCELLED'), NOT NULL): 거래 상태

**인덱스**:
- user_id에 대한 인덱스 (거래 내역 조회 성능 향상)
- transaction_type + created_at 복합 인덱스 (유형별 조회 성능 향상)
- token 인덱스 (뿌리기 관련 조회)

**사용 예시**:
1. 충전 시:
```json
{
  "transaction_type": "CHARGE",
  "user_id": 1,
  "amount": 10000,
  "balance_after": 25000,
  "description": "카드 충전",
  "status": "SUCCESS"
}
```

2. 뿌리기 시:
```json
{
  "transaction_type": "SPRAY",
  "user_id": 1,
  "amount": -10000,
  "balance_after": 15000,
  "token": "ABC",
  "chat_room_id": "room123",
  "description": "3명에게 뿌리기",
  "target_details": [
    { "user_id": 2, "received_amount": 3000 },
    { "user_id": 3, "received_amount": 7000 }
  ],
  "status": "SUCCESS"
}
```

3. 받기 시:
```json
{
  "transaction_type": "RECEIVE",
  "user_id": 2,
  "amount": 3000,
  "balance_after": 8000,
  "related_user_id": 1,
  "token": "ABC",
  "chat_room_id": "room123",
  "description": "뿌리기 받기",
  "status": "SUCCESS"
}
```

## 2. API 명세서

모든 API는 Swagger를 통해 문서화되며, pydantic 스키마를 이용해 요청/응답 데이터를 검증합니다.
API 기본 경로는 `/api/v1/`로 시작합니다.

### 2.1. 회원가입 API
**URL**: `/api/v1/users/register`

**Method**: POST

**Summary**: 신규 사용자 등록

**Request Body (JSON)**:
```json
{
  "username": "exampleUser",
  "password": "password123",
  "email": "user@example.com"
}
```

**Response (성공)**:
```json
{
  "message": "회원가입에 성공하였습니다.",
  "user_id": 1
}
```

**설명**: 사용자의 기본 정보를 입력 받아 users 테이블에 저장하며, 가입 시 user_wallet 테이블에도 초기 잔액(예: 0)을 생성합니다.

### 2.2. 로그인 후 친구 목록 조회 API
**URL**: `/api/v1/users/{user_id}/friends`

**Method**: GET

**Summary**: 사용자의 친구 목록 조회

**Path Parameter**:
- user_id (int): 사용자 고유 식별자

**Response (성공)**:
```json
{
  "friends": [
    { "id": 2, "username": "friendUser1" },
    { "id": 3, "username": "friendUser2" }
  ]
}
```

**설명**: 로그인 후 사용자 식별자를 기반으로 friends 테이블에서 친구 관계를 조회합니다.

### 2.3. 아이디로 친구 추가 API
**URL**: `/api/v1/friends`

**Method**: POST

**Summary**: 특정 아이디의 사용자를 친구로 추가

**Request Body (JSON)**:
```json
{
  "friend_username": "friendUser1"
}
```

**Response (성공)**:
```json
{
  "message": "친구 추가에 성공하였습니다."
}
```

**설명**: 요청자의 아이디와 입력받은 친구 아이디를 기반으로 friends 테이블에 새로운 레코드를 생성합니다.

### 2.4. 채팅방 생성 API
**URL**: `/api/v1/rooms`

**Method**: POST

**Summary**: 새로운 채팅방 생성

**Request Body (JSON)**:
```json
{
  "room_name": "스터디방"
}
```

**Response (성공)**:
```json
{
  "room_id": "abc123-uuid",
  "room_name": "스터디방"
}
```

**설명**: 채팅방 정보를 chat_rooms 테이블에 저장하며, 생성 시 자동으로 생성된 고유 식별자(ID)를 반환합니다.

### 2.5. 채팅방에 멤버 초대 API
**URL**: `/api/v1/rooms/{room_id}/invite`

**Method**: POST

**Summary**: 채팅방에 사용자를 초대

**Path Parameter**:
- room_id (string): 채팅방 식별자

**Request Body (JSON)**:
```json
{
  "user_id": 4
}
```

**Response (성공)**:
```json
{
  "message": "채팅방에 멤버 초대에 성공하였습니다."
}
```

**설명**: 지정된 room_id의 채팅방에 사용자를 초대하여 chat_room_members 테이블에 신규 레코드를 추가합니다.

### 2.6. 돈 충전 API
**URL**: `/api/v1/wallet/charge`

**Method**: POST

**Summary**: 사용자의 잔액에 금액 충전

**Headers**:
- X-USER-ID: {사용자 식별번호 (숫자)}

**Request Body (JSON)**:
```json
{
  "amount": 5000
}
```

**Response (성공)**:
```json
{
  "message": "충전에 성공하였습니다.",
  "new_balance": 15000
}
```

**설명**: 요청 Header의 사용자 식별번호를 기준으로 user_wallet 테이블의 잔액을 증가시킵니다.

### 2.7. 잔액조회 API
**URL**: `/api/v1/wallet/balance`

**Method**: GET

**Summary**: 사용자의 현재 잔액 조회

**Headers**:
- X-USER-ID: {사용자 식별번호 (숫자)}

**Response (성공)**:
```json
{
  "user_id": 1,
  "balance": 15000
}
```

**설명**: Header에 전달된 사용자 식별번호를 기반으로 user_wallet의 잔액 정보를 조회하여 반환합니다.

### 2.8. 뿌리기 API
**URL**: `/api/v1/spray`

**Method**: POST

**Summary**: 채팅방에서 뿌리기(금액 분배) 요청

**Headers**:
- X-USER-ID: {요청자 식별번호 (숫자)}
- X-ROOM-ID: {대화방 식별자 (문자)}

**Request Body (JSON)**:
```json
{
  "total_amount": 10000,
  "recipient_count": 3
}
```

**Response (성공)**:
```json
{
  "token": "ABC"
}
```

**설명**: 요청자의 정보와 대화방 정보를 검증한 후, money_distribution 테이블에 뿌리기 건을 생성하고 내부 로직을 통해 총액을 분할하여 money_distribution_details 테이블에 저장합니다.

### 2.9. 받기 API
**URL**: `/api/v1/receive`

**Method**: POST

**Summary**: 뿌리기 건에서 분배 금액 받기

**Headers**:
- X-USER-ID: {요청자 식별번호 (숫자)}
- X-ROOM-ID: {대화방 식별자 (문자)}

**Request Body (JSON)**:
```json
{
  "token": "ABC"
}
```

**Response (성공)**:
```json
{
  "received_amount": 3500
}
```

**오류 응답 (예시)**:
```json
{
  "error": "받기 실패: 조건에 맞지 않습니다."
}
```

**설명**: 
- 입력받은 토큰을 기반으로 해당 뿌리기 건을 조회한 후,
- 요청 사용자가 이미 받은 기록이 있는지, 뿌린 본인이 아닌지,
- 채팅방 일치 여부, 및 뿌리기 생성 후 10분 이내인지를 체크합니다.
- 조건 만족 시 아직 할당되지 않은 분배 내역 하나를 선택하여 요청자에게 할당하고 금액을 반환합니다.

### 2.10. 조회 API
**URL**: `/api/v1/spray/{token}`

**Method**: GET

**Summary**: 뿌리기 건에 대한 현재 상태 조회 (뿌린 본인만 가능)

**Headers**:
- X-USER-ID: {요청자 식별번호 (숫자)}

**Path Parameter**:
- token (string): 뿌리기 건 식별 토큰

**Response (성공)**:
```json
{
  "spray_time": "2025-02-18T14:30:00",
  "spray_amount": 10000,
  "received_amount": 7000,
  "received_list": [
    {
      "amount": 3500,
      "user_id": 4
    },
    {
      "amount": 3500,
      "user_id": 5
    }
  ]
}
```

**오류 응답 (예시)**:
```json
{
  "error": "조회 실패: 권한이 없거나 토큰이 유효하지 않습니다."
}
```

**설명**: 
- 토큰에 해당하는 뿌리기 건의 생성 시각, 총 금액, 현재까지 받기 완료된 금액과 받기 완료된 정보 목록을 반환합니다.
- 받기 완료된 정보 목록에는 받은 금액과 받은 사용자 ID가 포함됩니다.
- 단, 오직 뿌리기를 요청한 사용자가 조회할 수 있으며, 조회 가능 기간은 생성 후 7일입니다.

### 2.11. 거래 내역 조회 API
**URL**: `/api/v1/transactions`

**Method**: GET

**Summary**: 사용자의 거래 내역 조회

**Headers**:
- X-USER-ID: {사용자 식별번호 (숫자)}

**Query Parameters**:
- type (선택): 거래 유형 필터 (CHARGE, SPRAY, RECEIVE)
- start_date (선택): 조회 시작일
- end_date (선택): 조회 종료일
- page (선택): 페이지 번호 (기본값: 1)
- per_page (선택): 페이지당 항목 수 (기본값: 20)

**Response (성공)**:
```json
{
  "total_count": 50,
  "total_pages": 3,
  "current_page": 1,
  "transactions": [
    {
      "id": 123,
      "transaction_type": "CHARGE",
      "amount": 10000,
      "balance_after": 25000,
      "description": "카드 충전",
      "created_at": "2025-02-18T14:30:00",
      "status": "SUCCESS"
    },
    {
      "id": 124,
      "transaction_type": "SPRAY",
      "amount": -10000,
      "balance_after": 15000,
      "token": "ABC",
      "chat_room_id": "room123",
      "description": "3명에게 뿌리기",
      "created_at": "2025-02-18T14:35:00",
      "status": "SUCCESS"
    }
  ]
}
```

**설명**: 
- 사용자의 모든 금전 거래 내역을 조회할 수 있습니다.
- 거래 유형, 기간 등으로 필터링이 가능합니다.
- 페이지네이션을 지원하여 대량의 거래 내역도 효율적으로 조회할 수 있습니다.

### 2.12. 내 지갑 조회 API
**URL**: `/api/v1/wallet`

**Method**: GET

**Summary**: 사용자의 현재 지갑 잔액과 일정 기간 동안의 거래 내역(충전, 뿌리기, 받기)을 조회합니다.

**Headers**:
- X-USER-ID: {사용자 식별번호 (숫자)}

**Query Parameters**:
- start_date (선택): 조회 시작일 (예: "2025-02-01")
- end_date (선택): 조회 종료일 (예: "2025-02-28")
- type (선택): 거래 유형 필터 (CHARGE, SPRAY, RECEIVE)
- page (선택): 페이지 번호 (기본값: 1)
- per_page (선택): 페이지당 항목 수 (기본값: 20)

**Response (성공)**:
기본적으로 최근 30일치 거래 내역만 요약 정보로 반환합니다. 각 거래의 요약 정보에는 기본 항목(예: id, 거래 유형, 금액, 생성일)만 포함됩니다.
```json
{
  "balance": 15000,
  "total_count": 10,
  "current_page": 1,
  "total_pages": 1,
  "transactions": [
    {
      "id": 123,
      "transaction_type": "CHARGE",
      "amount": 10000,
      "created_at": "2025-02-18T14:30:00"
    },
    {
      "id": 124,
      "transaction_type": "RECEIVE",
      "amount": 3000,
      "created_at": "2025-02-19T10:30:00"
    },
    {
      "id": 125,
      "transaction_type": "SPRAY",
      "amount": -10000,
      "created_at": "2025-02-19T10:31:00"
    }
  ]
}
```

**설명**:
- 사용자의 지갑 잔액은 `user_wallet` 테이블에서 조회합니다.
- 거래 내역은 `transaction_history` 테이블에서 사용자별로 조회됩니다. 기본적으로 별도의 날짜 파라미터가 없으면 최근 30일치 거래 내역만 요약 정보(예: id, 거래 유형, 거래 금액, 생성일)로 반환합니다.
- 목록에 노출되는 요약 정보는 간단한 목록 형태로 제공하며, 사용자가 특정 거래를 '상세히 보기' 요청하면 해당 거래의 전체 정보(예: description, balance_after, token, target_details 등)를 확인할 수 있는 별도의 상세 조회 API 또는 추가 필드를 제공할 수 있습니다.
- 페이지네이션을 지원하여 대량의 거래 내역도 효율적으로 조회할 수 있습니다.

### 2.13. 내 거래 상세 조회 API
**URL**: `/api/v1/transactions/{transaction_id}`

**Method**: GET

**Summary**: 사용자가 선택한 거래의 상세 정보를 조회합니다.

**Headers**:
- X-USER-ID: {사용자 식별번호 (숫자)}

**Path Parameter**:
- transaction_id (숫자): 상세 조회할 거래의 고유 ID

**Response (성공)**:
```json
{
  "id": 125,
  "transaction_type": "SPRAY",
  "amount": -10000,
  "balance_after": 15000,
  "related_user_id": null,
  "token": "ABC",
  "chat_room_id": "room123",
  "description": "3명에게 뿌리기",
  "target_details": [
    { "user_id": 2, "received_amount": 3000 },
    { "user_id": 3, "received_amount": 7000 }
  ],
  "created_at": "2025-02-19T10:31:00",
  "status": "SUCCESS"
}
```

**설명**:
- 이 API는 사용자가 거래 목록에서 선택한 항목의 상세 정보를 반환합니다.
- 반환되는 정보에는 요약 응답에 포함되지 않는 추가 정보들(예: `balance_after`, `description`, `token`, `target_details` 등)이 포함되어 있습니다.
- 목록에서 '상세히 보기' 요청 시 활용되어, 보다 구체적인 거래 내역을 확인할 수 있습니다.

## 3. 추가 고려사항

### 동시성 및 트랜잭션 관리
- 특히 뿌리기/받기 기능은 여러 서버 인스턴스 환경에서도 데이터 정합성을 유지하기 위해
- 비동기 세션(AsyncSession) 및 트랜잭션, 락 처리를 적용합니다.

### 유효성 검증 및 에러 처리
- pydantic 스키마로 요청 데이터를 검증하고, FastAPI의 HTTPException을 활용해
- 적절한 상태 코드와 에러 메시지를 반환합니다.

### Swagger 문서화
- 각 API 엔드포인트에 summary와 description을 추가하여 Swagger UI에서 자동 문서화합니다.

### 단위 테스트
- 각 API 및 서비스 로직에 대해 pytest와 FastAPI의 TestClient를 활용하여
- 다양한 정상 및 비정상 시나리오에 대한 단위 테스트를 작성합니다.

### 보안 모듈 적용
- 환경 변수 관리
- 입력값 검증
- JWT 인증
- RBAC
- 로깅 및 감사 등을 적용하여 보안성을 강화합니다.
