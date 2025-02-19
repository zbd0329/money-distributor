import pytest
from httpx import AsyncClient
from main import app
from db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from api.spray.service import SprayService
from api.spray.utils import distribute_amount, generate_token

# 비동기 테스트를 위한 설정
pytestmark = pytest.mark.asyncio

# 테스트 데이터
TEST_USER_ID = 1
TEST_ROOM_ID = "TEST-ROOM-1"

# Fixture for async client
@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# Utils 테스트
def test_generate_token():
    """토큰 생성 테스트"""
    token = generate_token()
    assert len(token) == 3
    assert token.isalnum()

def test_distribute_amount():
    """금액 분배 테스트"""
    total = 1000
    count = 3
    amounts = distribute_amount(total, count)
    assert len(amounts) == count
    assert sum(amounts) == total
    assert all(amount > 0 for amount in amounts)

    with pytest.raises(ValueError):
        distribute_amount(10, 20)  # 총액이 인원수보다 작은 경우

# # API 엔드포인트 테스트
# async def test_create_spray(async_client):
#     # 정상 케이스
#     response = await async_client.post(
#         "/api/v1/spray",
#         json={"total_amount": 5000, "recipient_count": 3},
#         headers={"X-USER-ID": str(TEST_USER_ID), "X-ROOM-ID": TEST_ROOM_ID}
#     )
    
#     assert response.status_code == 200
#     data = response.json()
#     assert "token" in data
#     assert len(data["token"]) == 3

#     # 잘못된 입력 케이스
#     response = await async_client.post(
#         "/api/v1/spray",
#         json={"total_amount": 100, "recipient_count": 200},  # 금액 < 인원수
#         headers={"X-USER-ID": str(TEST_USER_ID), "X-ROOM-ID": TEST_ROOM_ID}
#     )
    
#     assert response.status_code == 422  # Validation Error

# # Service 레이어 테스트
# async def test_spray_service(async_session: AsyncSession):
#     service = SprayService(async_session)
    
#     # 정상 케이스
#     spray_token = await service.create_spray(
#         user_id=TEST_USER_ID,
#         room_id=TEST_ROOM_ID,
#         total_amount=5000,
#         recipient_count=3
#     )
    
#     assert len(spray_token) == 3
    
#     # 잔액 부족 케이스
#     with pytest.raises(Exception):
#         await service.create_spray(
#             user_id=TEST_USER_ID,
#             room_id=TEST_ROOM_ID,
#             total_amount=1000000000,  # 매우 큰 금액
#             recipient_count=3
#         )

#     # 채팅방 멤버가 아닌 경우
#     with pytest.raises(Exception):
#         await service.create_spray(
#             user_id=999,  # 존재하지 않는 사용자
#             room_id=TEST_ROOM_ID,
#             total_amount=5000,
#             recipient_count=3
#         )

# # DB 세션 Fixture
# @pytest.fixture
# async def async_session():
#     async for session in get_db():
#         yield session
