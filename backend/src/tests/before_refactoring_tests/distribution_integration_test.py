# File: distribution_integration_test.py
import asyncio
import uuid
import random
import string
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.db.models import ChatRoom, MoneyDistribution, MoneyDistributionDetail, ChatRoomMember, User, UserWallet
from src.db.database import get_db
from src.api.distribution.service import DistributionService
from src.api.distribution.service.spray_service import SprayService

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def db_session():
    async for session in get_db():
        yield session

@pytest.fixture
async def test_chat_room(db_session: AsyncSession):
    room_id = str(uuid.uuid4())
    chat_room = ChatRoom(id=room_id, room_name="Test Room")
    db_session.add(chat_room)
    await db_session.commit()
    await db_session.refresh(chat_room)
    return chat_room

# dummy users: user 1,2,3,4
@pytest.fixture
async def add_dummy_users(db_session: AsyncSession):
    for uid in [1, 2, 3, 4]:
        result = await db_session.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=uid, username=f"user{uid}", password="dummy", email=f"user{uid}@example.com")
            db_session.add(user)
    await db_session.commit()
    return True

@pytest.fixture
async def fresh_spray(db_session: AsyncSession, test_chat_room: ChatRoom):
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    # recipient_count=3: 3명이 받을 수 있으나, 받기를 호출하지 않은 대상도 존재할 수 있습니다.
    spray = MoneyDistribution(
        token=token,
        creator_id=1,
        chat_room_id=test_chat_room.id,
        total_amount=5000,
        recipient_count=3,
        created_at=datetime.utcnow()
    )
    db_session.add(spray)
    await db_session.flush()
    amounts = SprayService.distribute_amount(5000, 3)
    for amt in amounts:
        detail = MoneyDistributionDetail(
            distribution_id=spray.id,
            allocated_amount=amt
        )
        db_session.add(detail)
    await db_session.commit()
    await db_session.refresh(spray)
    return spray

async def add_members(db_session: AsyncSession, chat_room: ChatRoom, user_ids: list[int]):
    for uid in user_ids:
        member = ChatRoomMember(chat_room_id=chat_room.id, user_id=uid)
        db_session.add(member)
    await db_session.commit()

"""통합 플로우 테스트: 뿌리기 생성 → 받기 → 조회"""
async def test_distribution_integration_flow(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_chat_room: ChatRoom,
    fresh_spray: MoneyDistribution,
    add_dummy_users,
):
    # 먼저, dummy users (user 1,2,3,4)가 자동으로 생성됨.
    # 채팅방에 모든 사용자(1,2,3,4)를 멤버로 추가합니다.
    await add_members(db_session, test_chat_room, [1, 2, 3, 4])
    
    # 1. 받기 시도: 뿌린 사람(1)이 받으려 하면 실패
    headers_distributor = {"X-USER-ID": "1", "X-ROOM-ID": test_chat_room.id}
    response_self = await async_client.post("/api/v1/receive", headers=headers_distributor, json={"token": fresh_spray.token})
    assert response_self.status_code == 400

    # 2. 받기 시도: 사용자 2와 사용자 3는 받기에 성공하고, 사용자 4는 받지 않음.
    headers_user2 = {"X-USER-ID": "2", "X-ROOM-ID": test_chat_room.id}
    headers_user3 = {"X-USER-ID": "3", "X-ROOM-ID": test_chat_room.id}
    
    response_user2 = await async_client.post("/api/v1/receive", headers=headers_user2, json={"token": fresh_spray.token})
    assert response_user2.status_code == 200
    received_amount2 = response_user2.json()["received_amount"]
    assert received_amount2 > 0

    response_user3 = await async_client.post("/api/v1/receive", headers=headers_user3, json={"token": fresh_spray.token})
    assert response_user3.status_code == 200
    received_amount3 = response_user3.json()["received_amount"]
    assert received_amount3 > 0

    # 사용자 4는 받기 호출하지 않음.

    # 3. 조회: 뿌린 사람(1)만 조회할 수 있음.
    headers_lookup = {"X-USER-ID": "1"}
    status_response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers_lookup)
    assert status_response.status_code == 200
    status_data = status_response.json()
    # 전체 뿌리기 금액은 그대로, 받은 금액은 사용자 2와 3의 합이어야 함.
    assert status_data["spray_amount"] == fresh_spray.total_amount
    expected_received = received_amount2 + received_amount3
    assert status_data["received_amount"] == expected_received
    # 받은 사용자 목록은 사용자 2와 3만 있어야 합니다.
    received_list = status_data["received_list"]
    assert len(received_list) == 2
    received_user_ids = [item["user_id"] for item in received_list]
    assert 2 in received_user_ids
    assert 3 in received_user_ids
    total_received = sum(item["amount"] for item in received_list)
    assert total_received == expected_received

    # 4. 조회 실패 테스트: 뿌리지않은 사용자(예: user 4)가 조회하면 403
    headers_non_creator = {"X-USER-ID": "4"}
    non_creator_response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers_non_creator)
    assert non_creator_response.status_code == 403
