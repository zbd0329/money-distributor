import pytest
from datetime import datetime
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
    UserWallet,
    TransactionHistory,
    TransactionTypeEnum,
    TransactionStatusEnum
)
from src.api.distribution.service.spray_service import SprayService

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
    # 1. 사용자 생성
    user = User(
        id=1,
        username="user1",
        password="dummy",
        email="user1@example.com"
    )
    db_session.add(user)
    
    # 2. 채팅방 멤버 추가
    member = ChatRoomMember(
        chat_room_id=test_chat_room.id,
        user_id=user.id
    )
    db_session.add(member)
    
    # 3. 사용자 지갑 생성 (10000원)
    wallet = UserWallet(
        user_id=user.id,
        balance=10000
    )
    db_session.add(wallet)
    
    await db_session.commit()
    return user

@pytest.fixture
def mock_token_service():
    """TokenService 모킹"""
    with patch('src.utils.token.token.TokenService') as mock:
        instance = mock.return_value
        instance.generate_token.return_value = "ABC"
        yield instance

async def test_create_spray_success(db_session: AsyncSession, setup_test_data: User, test_chat_room: ChatRoom, mock_token_service):
    """뿌리기 생성 성공 케이스 테스트"""
    service = SprayService(db_session)
    service._token_service = mock_token_service
    
    # When
    token = await service.create_spray(
        user_id=setup_test_data.id,
        room_id=test_chat_room.id,
        total_amount=3000,
        recipient_count=3
    )
    
    # Then
    assert token == "ABC"
    
    # 1. 뿌리기 건 생성 확인
    distribution = await db_session.execute(
        select(MoneyDistribution).where(MoneyDistribution.token == token)
    )
    distribution = distribution.scalar_one()
    assert distribution.total_amount == 3000
    assert distribution.recipient_count == 3
    assert distribution.creator_id == setup_test_data.id
    
    # 2. 분배 내역 생성 확인
    details = await db_session.execute(
        select(MoneyDistributionDetail)
        .where(MoneyDistributionDetail.distribution_id == distribution.id)
    )
    details = details.scalars().all()
    assert len(details) == 3
    assert sum(detail.allocated_amount for detail in details) == 3000
    assert all(detail.receiver_id is None for detail in details)
    
    # 3. 거래 내역 생성 확인
    transaction = await db_session.execute(
        select(TransactionHistory)
        .where(
            TransactionHistory.token == token,
            TransactionHistory.user_id == setup_test_data.id
        )
    )
    transaction = transaction.scalar_one()
    assert transaction.amount == -3000
    assert transaction.transaction_type == TransactionTypeEnum.SPRAY
    assert transaction.status == TransactionStatusEnum.SUCCESS
    
    # 4. 지갑 잔액 확인
    wallet = await db_session.execute(
        select(UserWallet).where(UserWallet.user_id == setup_test_data.id)
    )
    wallet = wallet.scalar_one()
    assert wallet.balance == 7000  # 10000 - 3000

async def test_create_spray_insufficient_balance(db_session: AsyncSession, setup_test_data: User, test_chat_room: ChatRoom, mock_token_service):
    """잔액 부족 시 실패 케이스 테스트"""
    service = SprayService(db_session)
    service._token_service = mock_token_service
    
    with pytest.raises(HTTPException) as exc_info:
        await service.create_spray(
            user_id=setup_test_data.id,
            room_id=test_chat_room.id,
            total_amount=20000,  # 잔액(10000)보다 큰 금액
            recipient_count=3
        )
    
    assert exc_info.value.status_code == 400
    assert "잔액이 부족합니다" in str(exc_info.value.detail)

async def test_create_spray_not_in_chat_room(db_session: AsyncSession, test_chat_room: ChatRoom, mock_token_service):
    """채팅방 멤버가 아닌 경우 실패 케이스 테스트"""
    # 채팅방 멤버가 아닌 새로운 사용자 생성
    user = User(
        id=999,
        username="outsider",
        password="dummy",
        email="outsider@example.com"
    )
    db_session.add(user)
    
    # 지갑 생성
    wallet = UserWallet(
        user_id=user.id,
        balance=10000
    )
    db_session.add(wallet)
    await db_session.commit()
    
    service = SprayService(db_session)
    service._token_service = mock_token_service
    
    with pytest.raises(HTTPException) as exc_info:
        await service.create_spray(
            user_id=user.id,
            room_id=test_chat_room.id,
            total_amount=3000,
            recipient_count=3
        )
    
    assert exc_info.value.status_code == 403
    assert "해당 대화방의 멤버가 아닙니다" in str(exc_info.value.detail)

def test_distribute_amount_success():
    """금액 분배 로직 테스트"""
    service = SprayService(None)  # DB 세션 불필요
    
    # Case 1: 나누어 떨어지는 경우
    amounts = service.distribute_amount(total_amount=3000, count=3)
    assert len(amounts) == 3
    assert sum(amounts) == 3000
    assert all(amount == 1000 for amount in amounts)
    
    # Case 2: 나누어 떨어지지 않는 경우
    amounts = service.distribute_amount(total_amount=3001, count=3)
    assert len(amounts) == 3
    assert sum(amounts) == 3001
    assert any(amount > 1000 for amount in amounts)  # 누군가는 1001원을 받아야 함

def test_distribute_amount_invalid_input():
    """금액 분배 로직의 유효하지 않은 입력 테스트"""
    service = SprayService(None)
    
    # Case 1: 음수 금액
    with pytest.raises(ValueError):
        service.distribute_amount(total_amount=-1000, count=3)
    
    # Case 2: 음수 인원
    with pytest.raises(ValueError):
        service.distribute_amount(total_amount=1000, count=-1)
    
    # Case 3: 인원수보다 적은 금액
    with pytest.raises(ValueError):
        service.distribute_amount(total_amount=2, count=3)

async def test_create_spray_rollback(db_session: AsyncSession, setup_test_data: User, test_chat_room: ChatRoom, mock_token_service):
    """오류 발생 시 롤백이 정상적으로 동작하는지 테스트"""
    service = SprayService(db_session)
    service._token_service = mock_token_service
    
    # 의도적으로 오류 발생시키기 위해 토큰 생성 실패 시뮬레이션
    mock_token_service.generate_token.side_effect = Exception("Token generation failed")
    
    with pytest.raises(HTTPException) as exc_info:
        await service.create_spray(
            user_id=setup_test_data.id,
            room_id=test_chat_room.id,
            total_amount=3000,
            recipient_count=3
        )
    
    assert exc_info.value.status_code == 500
    
    # 세션 리프레시
    await db_session.refresh(setup_test_data)
    
    # 롤백 확인: 어떤 데이터도 저장되지 않아야 함
    stmt = select(MoneyDistribution).where(MoneyDistribution.creator_id == setup_test_data.id)
    result = await db_session.execute(stmt)
    distribution = result.scalar_one_or_none()
    assert distribution is None
    
    # 지갑 잔액이 그대로인지 확인
    stmt = select(UserWallet).where(UserWallet.user_id == setup_test_data.id)
    result = await db_session.execute(stmt)
    wallet = result.scalar_one()
    assert wallet.balance == 10000  # 초기 금액 그대로 