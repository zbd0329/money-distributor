# File: spray_test.py
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
from src.db.models import (
    ChatRoom,
    MoneyDistribution,
    MoneyDistributionDetail,
    ChatRoomMember,
    User,
    UserWallet
)
from src.db.database import get_db
from src.api.distribution.service.spray_service import SprayService
from src.api.spray.utils import distribute_amount

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

@pytest.fixture
async def add_dummy_users(db_session: AsyncSession):
    # 필요한 경우 user 1만 사용 (뿌리기 생성 시 creator_id가 1)
    for uid in [1]:
        result = await db_session.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=uid, username=f"user{uid}", password="dummy", email=f"user{uid}@example.com")
            db_session.add(user)
    await db_session.commit()
    return True

# Spray creation test (POST /api/v1/spray)
async def test_create_spray(async_client: AsyncClient, db_session: AsyncSession, test_chat_room: ChatRoom, add_dummy_users):
    # 뿌리기 생성을 위해, creator (user 1)를 해당 채팅방의 멤버로 추가
    from src.db.models import ChatRoomMember
    member = ChatRoomMember(chat_room_id=test_chat_room.id, user_id=1)
    db_session.add(member)
    await db_session.commit()

    headers = {"X-USER-ID": "1", "X-ROOM-ID": test_chat_room.id}
    payload = {"total_amount": 5000, "recipient_count": 3}
    response = await async_client.post("/api/v1/spray", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert len(data["token"]) == 3
