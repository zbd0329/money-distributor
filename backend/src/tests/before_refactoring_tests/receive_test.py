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

# 더미 User 등록: user 1, 2 (이미 add_dummy_users가 주입되면 값이 자동 주입됨)
@pytest.fixture
async def add_dummy_users(db_session: AsyncSession):
    for uid in [1, 2]:
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

# 받기 실패 및 중복 받기 테스트
async def test_receive_money_failures(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_chat_room: ChatRoom,
    fresh_spray: MoneyDistribution,
    add_dummy_users,  # fixture로 주입됨 (이미 실행됨)
):
    from src.db.models import ChatRoomMember
    # 채팅방에 user 1과 user 2를 멤버로 추가
    for uid in [1, 2]:
        member = ChatRoomMember(chat_room_id=test_chat_room.id, user_id=uid)
        db_session.add(member)
    await db_session.commit()
    
    # 뿌린 사람(user 1)이 받으려 하면 실패
    headers = {"X-USER-ID": "1", "X-ROOM-ID": test_chat_room.id}
    response = await async_client.post("/api/v1/receive", headers=headers, json={"token": fresh_spray.token})
    assert response.status_code == 400

    # User 2가 받기 시도 후, 같은 사용자가 다시 받으려 하면 실패
    headers["X-USER-ID"] = "2"
    first_response = await async_client.post("/api/v1/receive", headers=headers, json={"token": fresh_spray.token})
    assert first_response.status_code == 200
    second_response = await async_client.post("/api/v1/receive", headers=headers, json={"token": fresh_spray.token})
    assert second_response.status_code == 400

# 받기 성공 테스트: 단일 사용자
async def test_receive_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_chat_room: ChatRoom,
    fresh_spray: MoneyDistribution,
    add_dummy_users,
):
    from src.db.models import ChatRoomMember
    # 채팅방에 user 2를 멤버로 추가
    member = ChatRoomMember(chat_room_id=test_chat_room.id, user_id=2)
    db_session.add(member)
    await db_session.commit()
    
    headers = {"X-USER-ID": "2", "X-ROOM-ID": test_chat_room.id}
    response = await async_client.post("/api/v1/receive", headers=headers, json={"token": fresh_spray.token})
    assert response.status_code == 200
    data = response.json()
    assert "received_amount" in data
    assert data["received_amount"] > 0
