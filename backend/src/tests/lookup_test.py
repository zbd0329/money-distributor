import asyncio
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from unittest.mock import patch, MagicMock

from src.db.models import (
    MoneyDistribution,
    MoneyDistributionDetail,
    ChatRoom,
    ChatRoomMember,
    User,
    UserWallet
)
from src.api.distribution.service.lookup_service import LookupService

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def test_chat_room(db_session: AsyncSession):
    """테스트용 채팅방 생성"""
    chat_room = ChatRoom(id="test_room", room_name="Test Room")
    db_session.add(chat_room)
    await db_session.commit()
    return chat_room

@pytest.fixture
async def setup_test_data(db_session: AsyncSession, test_chat_room: ChatRoom):
    """테스트에 필요한 기본 데이터 설정"""
    # 1. 사용자 생성 (뿌린 사람: 1, 받을 사람: 2)
    users = []
    for uid in [1, 2]:
        user = User(
            id=uid,
            username=f"user{uid}",
            password="dummy",
            email=f"user{uid}@example.com"
        )
        db_session.add(user)
        users.append(user)
    
    # 2. 채팅방 멤버 추가
    for user in users:
        member = ChatRoomMember(
            chat_room_id=test_chat_room.id,
            user_id=user.id
        )
        db_session.add(member)
    
    # 3. 뿌리기 건 생성
    spray = MoneyDistribution(
        token="ABC",
        creator_id=1,
        chat_room_id=test_chat_room.id,
        total_amount=3000,
        recipient_count=3,
        created_at=datetime.utcnow()
    )
    db_session.add(spray)
    await db_session.flush()

    # 4. 분배 내역 생성 (3명에게 각각 1000원씩)
    amounts = [1000, 1000, 1000]
    for amount in amounts:
        detail = MoneyDistributionDetail(
            distribution_id=spray.id,
            allocated_amount=amount
        )
        db_session.add(detail)
    
    await db_session.commit()
    return spray

@pytest.fixture
def mock_token_service():
    """TokenService 모킹"""
    with patch('src.utils.token.token.TokenService') as mock:
        instance = mock.return_value
        instance.validate_token.return_value = True
        yield instance

async def test_get_spray_status_success(db_session: AsyncSession, setup_test_data: MoneyDistribution, mock_token_service):
    """뿌리기 건이 정상적으로 생성된 상태에서, 아직 아무도 받지 않은 경우를 테스트"""
    service = LookupService(db_session)
    service._token_service = mock_token_service
    
    # 뿌린 사람이 조회
    response = await service.get_spray_status(
        token=setup_test_data.token,
        user_id=1  # creator_id
    )
    
    assert response.spray_time == setup_test_data.created_at
    assert response.spray_amount == 3000
    assert response.received_amount == 0  # 아직 아무도 받지 않음
    assert len(response.received_list) == 0

async def test_get_spray_status_with_received(db_session: AsyncSession, setup_test_data: MoneyDistribution, mock_token_service):
    """분배 내역 중 일부가 실제로 수령된 경우(받은 내역이 존재할 때)의 응답을 테스트"""
    # 받기 내역 생성
    detail = await db_session.execute(
        select(MoneyDistributionDetail)
        .where(MoneyDistributionDetail.distribution_id == setup_test_data.id)
        .limit(1)
    )
    detail = detail.scalar_one()
    detail.receiver_id = 2
    detail.claimed_at = datetime.utcnow()
    await db_session.commit()

    service = LookupService(db_session)
    service._token_service = mock_token_service
    
    response = await service.get_spray_status(
        token=setup_test_data.token,
        user_id=1
    )
    
    assert response.spray_amount == 3000
    assert response.received_amount == 1000
    assert len(response.received_list) == 1
    assert response.received_list[0].user_id == 2
    assert response.received_list[0].amount == 1000

async def test_get_spray_status_unauthorized(db_session: AsyncSession, setup_test_data: MoneyDistribution, mock_token_service):
    """뿌리기를 생성한 사용자가 아닌 다른 사용자가 조회할 경우 예외가 발생하는지 테스트"""
    service = LookupService(db_session)
    service._token_service = mock_token_service
    
    with pytest.raises(HTTPException) as exc_info:
        await service.get_spray_status(
            token=setup_test_data.token,
            user_id=2  # 뿌린 사람이 아님
        )
    
    assert exc_info.value.status_code == 403
    assert "뿌리기 건은 생성자만 조회할 수 있습니다" in str(exc_info.value.detail)

async def test_get_spray_status_expired(db_session: AsyncSession, setup_test_data: MoneyDistribution, mock_token_service):
    """뿌리기 건 생성 후 7일이 지난 경우, 조회할 수 없도록 하는 제약 테스트"""
    # 7일 전으로 생성 시간 수정
    setup_test_data.created_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()

    service = LookupService(db_session)
    service._token_service = mock_token_service
    
    with pytest.raises(ValueError) as exc_info:
        await service.get_spray_by_token(setup_test_data.token)
    
    assert "조회 가능 기간이 만료되었습니다" in str(exc_info.value)

async def test_get_spray_by_token_not_found(db_session: AsyncSession, mock_token_service):
    """존재하지 않는 토큰으로 조회시 알맞은 에러 메세지 뜨는지 확인하는 테스트"""
    service = LookupService(db_session)
    service._token_service = mock_token_service
    mock_token_service.validate_token.return_value = False  # 이 테스트에서만 토큰이 유효하지 않음
    
    with pytest.raises(ValueError) as exc_info:
        await service.get_spray_by_token("XYZ")
    
    assert "유효하지 않은 토큰입니다" in str(exc_info.value)

async def test_get_spray_details(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """뿌리기 상세 내역 조회 테스트"""
    service = LookupService(db_session)
    details = await service.get_spray_details(setup_test_data.id)
    
    assert len(details) == 3  # 3개의 분배 내역
    assert all(detail.allocated_amount == 1000 for detail in details)
    assert all(detail.receiver_id is None for detail in details)  # 아직 받지 않음

async def test_valid_token_but_no_distribution(db_session: AsyncSession, mock_token_service):
    """유효한 토큰이지만 DB에 해당 분배 건이 없는 경우 테스트"""
    service = LookupService(db_session)
    service._token_service = mock_token_service
    mock_token_service.validate_token.return_value = True  # Redis에서는 토큰이 유효하다고 가정
    
    with pytest.raises(ValueError) as exc_info:
        await service.get_spray_by_token("VALID_BUT_NOT_EXISTS")
    
    assert "해당 토큰으로 분배된 내역이 없습니다" in str(exc_info.value)  # DB에 해당 토큰의 분배 건이 없는 경우

async def test_invalid_token(db_session: AsyncSession, mock_token_service):
    """Redis에서 유효하지 않은 토큰인 경우 테스트"""
    service = LookupService(db_session)
    service._token_service = mock_token_service
    mock_token_service.validate_token.return_value = False  # Redis에서 토큰이 유효하지 않음
    
    with pytest.raises(ValueError) as exc_info:
        await service.get_spray_by_token("INVALID_TOKEN")
    
    assert "유효하지 않은 토큰입니다" in str(exc_info.value)

async def test_multiple_received_details(db_session: AsyncSession, setup_test_data: MoneyDistribution, mock_token_service):
    """여러 건의 수령 내역이 있는 경우의 조회 테스트"""
    # 3건의 분배 내역 중 2건이 수령된 상황 설정
    details = await db_session.execute(
        select(MoneyDistributionDetail)
        .where(MoneyDistributionDetail.distribution_id == setup_test_data.id)
    )
    details = details.scalars().all()
    
    # 첫 번째 수령: user 2가 500원 수령 (2분 전)
    details[0].receiver_id = 2
    details[0].claimed_at = datetime.utcnow() - timedelta(minutes=2)
    details[0].allocated_amount = 500
    
    # 두 번째 수령: user 3이 1500원 수령 (1분 전)
    details[1].receiver_id = 3
    details[1].claimed_at = datetime.utcnow() - timedelta(minutes=1)
    details[1].allocated_amount = 1500
    
    # 세 번째 건은 미수령 상태로 둠 (1000원)
    await db_session.commit()

    service = LookupService(db_session)
    service._token_service = mock_token_service
    
    response = await service.get_spray_status(
        token=setup_test_data.token,
        user_id=1
    )
    
    # 검증
    assert response.spray_amount == 3000  # 총 뿌린 금액
    assert response.received_amount == 2000  # 받은 금액 합계 (500 + 1500)
    assert len(response.received_list) == 2  # 받은 사람 2명
    
    # 수령 시간 순서대로 정렬되어 있는지 확인
    received_list = response.received_list
    assert received_list[0].user_id == 2
    assert received_list[0].amount == 500
    assert received_list[1].user_id == 3
    assert received_list[1].amount == 1500 