# File: lookup_test.py
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
from src.db.models import ChatRoom, MoneyDistribution, ChatRoomMember, User
from src.db.database import get_db
from src.api.spray.service import SprayService

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
async def test_user():
    return {"id": 1, "username": "testuser"}

@pytest.fixture
async def add_dummy_users(db_session: AsyncSession):
    for uid in [1]:
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
    await db_session.commit()
    await db_session.refresh(spray)
    return spray

# Lookup: 정상적인 조회 테스트
async def test_get_spray_status_success(
    async_client: AsyncClient,
    test_user: dict,
    fresh_spray: MoneyDistribution
):
    headers = {"X-USER-ID": str(test_user["id"])}
    response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "spray_time" in data
    assert data["spray_amount"] == fresh_spray.total_amount
    assert "received_amount" in data
    assert "received_list" in data

# Lookup: 권한 없는 사용자 조회 테스트
async def test_get_spray_status_unauthorized(
    async_client: AsyncClient,
    fresh_spray: MoneyDistribution
):
    headers = {"X-USER-ID": "999"}
    response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers)
    assert response.status_code == 403

# Lookup: 만료된 뿌리기 조회 테스트
async def test_get_spray_status_expired(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    fresh_spray: MoneyDistribution
):
    fresh_spray.created_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()
    headers = {"X-USER-ID": str(test_user["id"])}
    response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers)
    assert response.status_code == 400

# Lookup: 토큰을 통해 뿌리기 건 조회 테스트
async def test_get_spray_by_token(db_session: AsyncSession, fresh_spray: MoneyDistribution):
    service = SprayService(db_session)
    distribution = await service.get_spray_by_token(fresh_spray.token)
    assert distribution is not None
    assert distribution.id == fresh_spray.id

# Lookup: 조회 실패 케이스 테스트
async def test_get_spray_status_failures(
    async_client: AsyncClient,
    fresh_spray: MoneyDistribution,
    db_session: AsyncSession
):
    headers = {"X-USER-ID": str(fresh_spray.creator_id)}
    response = await async_client.get("/api/v1/spray/XXX", headers=headers)
    assert response.status_code == 404

    other_user_headers = {"X-USER-ID": "999"}
    response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=other_user_headers)
    assert response.status_code == 403

    fresh_spray.created_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()
    response = await async_client.get(f"/api/v1/spray/{fresh_spray.token}", headers=headers)
    assert response.status_code == 400
