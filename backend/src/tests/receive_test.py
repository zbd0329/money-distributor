import asyncio
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from unittest.mock import patch, MagicMock
from fastapi import status

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
from src.api.distribution.service.receive_service import ReceiveService

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
    # 1. 사용자 생성 (뿌린 사람: 1, 받을 사람들: 2, 3, 4)
    users = []
    for uid in range(1, 5):
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
    
    # 3. 사용자 지갑 생성 (각각 10000원)
    for user in users:
        wallet = UserWallet(
            user_id=user.id,
            balance=10000
        )
        db_session.add(wallet)
    
    # 4. 뿌리기 건 생성 (3000원을 3명에게)
    spray = MoneyDistribution(
        token="TEST123",
        creator_id=1,
        chat_room_id=test_chat_room.id,
        total_amount=3000,
        recipient_count=3,
        created_at=datetime.utcnow()
    )
    db_session.add(spray)
    await db_session.flush()
    
    # 5. 분배 내역 생성 (1000원씩 3건)
    for _ in range(3):
        detail = MoneyDistributionDetail(
            distribution_id=spray.id,
            allocated_amount=1000
        )
        db_session.add(detail)
    
    await db_session.commit()
    return spray

@pytest.mark.asyncio
async def test_receive_money_success(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """돈 받기 성공 케이스 테스트"""
    # Given
    service = ReceiveService(db_session)
    token = setup_test_data.token
    user_id = 2  # 받을 사람
    room_id = setup_test_data.chat_room_id
    
    # When
    received_amount = await service.receive_money(token, user_id, room_id)
    
    # Then
    assert received_amount == 1000
    
    # 1. 분배 내역 업데이트 확인
    detail = await db_session.execute(
        select(MoneyDistributionDetail)
        .where(
            MoneyDistributionDetail.distribution_id == setup_test_data.id,
            MoneyDistributionDetail.receiver_id == user_id
        )
    )
    detail = detail.scalar_one()
    assert detail.receiver_id == user_id
    assert detail.claimed_at is not None
    
    # 2. 지갑 잔액 업데이트 확인
    wallet = await db_session.execute(
        select(UserWallet).where(UserWallet.user_id == user_id)
    )
    wallet = wallet.scalar_one()
    assert wallet.balance == 11000  # 기존 10000 + 받은 금액 1000
    
    # 3. 거래 내역 생성 확인
    transaction = await db_session.execute(
        select(TransactionHistory)
        .where(
            TransactionHistory.user_id == user_id,
            TransactionHistory.token == token
        )
    )
    transaction = transaction.scalar_one()
    assert transaction.amount == 1000
    assert transaction.balance_after == 11000
    assert transaction.status == TransactionStatusEnum.SUCCESS
    assert transaction.transaction_type == TransactionTypeEnum.RECEIVE

@pytest.mark.asyncio
async def test_receive_money_creator_cannot_receive(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """뿌린 사람이 받으려고 할 때 실패하는 케이스 테스트"""
    service = ReceiveService(db_session)
    
    with pytest.raises(ValueError) as exc_info:
        await service.receive_money(
            token=setup_test_data.token,
            user_id=1,  # creator_id
            room_id=setup_test_data.chat_room_id
        )
    
    assert "자신이 뿌린 건은 받을 수 없습니다" in str(exc_info.value)

@pytest.mark.asyncio
async def test_receive_money_duplicate_receive(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """동일한 사용자가 두 번 받으려고 할 때 실패하는 케이스 테스트"""
    service = ReceiveService(db_session)
    token = setup_test_data.token
    user_id = 2
    room_id = setup_test_data.chat_room_id
    
    # 첫 번째 받기 성공
    await service.receive_money(token, user_id, room_id)
    
    # 두 번째 받기 시도 실패
    with pytest.raises(ValueError) as exc_info:
        await service.receive_money(token, user_id, room_id)
    
    assert "이미 받은 사용자입니다" in str(exc_info.value)

@pytest.mark.asyncio
async def test_receive_money_expired(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """10분이 지난 뿌리기는 받을 수 없음을 테스트"""
    # 뿌리기 시간을 11분 전으로 설정
    setup_test_data.created_at = datetime.utcnow() - timedelta(minutes=11)
    await db_session.commit()
    
    service = ReceiveService(db_session)
    
    with pytest.raises(ValueError) as exc_info:
        await service.receive_money(
            token=setup_test_data.token,
            user_id=2,
            room_id=setup_test_data.chat_room_id
        )
    
    assert "뿌린지 10분이 지나 받을 수 없습니다" in str(exc_info.value)

@pytest.mark.asyncio
async def test_receive_money_not_in_chat_room(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """대화방 멤버가 아닌 사용자가 받으려고 할 때 실패하는 케이스 테스트"""
    # 대화방 멤버가 아닌 새로운 사용자 생성
    new_user = User(
        id=999,
        username="outsider",
        password="dummy",
        email="outsider@example.com"
    )
    db_session.add(new_user)
    
    # 지갑 생성
    wallet = UserWallet(
        user_id=999,
        balance=10000
    )
    db_session.add(wallet)
    await db_session.commit()
    
    service = ReceiveService(db_session)
    
    with pytest.raises(HTTPException) as exc_info:  # ValueError 대신 HTTPException 기대
        await service.validate_receive_request(
            token=setup_test_data.token,
            user_id=999,
            room_id=setup_test_data.chat_room_id
        )
    
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "해당 대화방의 멤버가 아닙니다" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_receive_money_no_more_money(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """모든 금액이 소진된 후 받으려고 할 때 실패하는 케이스 테스트"""
    service = ReceiveService(db_session)
    token = setup_test_data.token
    room_id = setup_test_data.chat_room_id
    
    # 3명이 순차적으로 받기
    for user_id in [2, 3, 4]:
        await service.receive_money(token, user_id, room_id)
    
    # 새로운 사용자 생성 (이전에 받지 않은 사용자)
    new_user = User(
        id=5,
        username="user5",
        password="dummy",
        email="user5@example.com"
    )
    db_session.add(new_user)
    
    # 채팅방 멤버 추가
    member = ChatRoomMember(
        chat_room_id=room_id,
        user_id=5
    )
    db_session.add(member)
    
    # 지갑 생성
    wallet = UserWallet(
        user_id=5,
        balance=10000
    )
    db_session.add(wallet)
    await db_session.commit()
    
    # 4번째 사용자가 받으려고 시도
    with pytest.raises(ValueError) as exc_info:
        await service.receive_money(token, 5, room_id)
    
    assert "받을 수 있는 금액이 없습니다" in str(exc_info.value)

@pytest.mark.asyncio
async def test_process_receive_request_timeout(db_session: AsyncSession, setup_test_data: MoneyDistribution):
    """받기 요청 처리 시 타임아웃 발생 케이스 테스트"""
    with patch('src.worker.tasks.process_receive_money.apply_async') as mock_task:
        # 태스크가 타임아웃되도록 설정
        mock_async_result = MagicMock()
        mock_async_result.get.side_effect = TimeoutError()
        mock_task.return_value = mock_async_result
        
        service = ReceiveService(db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            await service.process_receive_request(
                token=setup_test_data.token,
                user_id=2,
                room_id=setup_test_data.chat_room_id
            )
        
        assert exc_info.value.status_code == 408
        assert "요청 처리 시간이 초과되었습니다" in str(exc_info.value.detail)

# @pytest.mark.asyncio
# async def test_receive_money_concurrent(db_session: AsyncSession, setup_test_data: MoneyDistribution):
#     """동시에 여러 사용자가 받기를 시도할 때 동시성 제어 테스트"""
#     token = setup_test_data.token
#     room_id = setup_test_data.chat_room_id

#     async def receive_attempt(user_id: int):
#         # 각 시도마다 새로운 세션 생성
#         async with AsyncSession(db_session.bind, expire_on_commit=False) as session:
#             try:
#                 service = ReceiveService(session)
#                 result = await service.receive_money(token, user_id, room_id)
#                 await session.commit()
#                 return result
#             except Exception as e:
#                 await session.rollback()
#                 return e

#     # 2, 3, 4번 사용자가 동시에 시도
#     results = await asyncio.gather(
#         receive_attempt(2),
#         receive_attempt(3),
#         receive_attempt(4),
#         return_exceptions=True
#     )

#     # 성공한 케이스 수 확인
#     success_count = sum(1 for r in results if isinstance(r, int))
#     assert success_count == 3  # 3명 모두 받아야 함

#     # 최종 상태 확인
#     async with AsyncSession(db_session.bind) as session:
#         # 모든 분배 내역이 할당되었는지 확인
#         details_query = select(MoneyDistributionDetail).where(
#             MoneyDistributionDetail.distribution_id == setup_test_data.id
#         )
#         details = (await session.execute(details_query)).scalars().all()
        
#         assert len(details) == 3  # 총 3개의 분배 내역
#         assert all(detail.receiver_id is not None for detail in details)  # 모두 할당됨
#         assert all(detail.allocated_amount == setup_test_data.total_amount // 3 for detail in details)  # 모든 금액이 동일
#         assert sum(detail.allocated_amount for detail in details) == setup_test_data.total_amount  # 총액 일치

# @pytest.mark.asyncio
# async def test_receive_money_concurrent_with_remaining(db_session: AsyncSession, test_chat_room: ChatRoom):
#     """동시에 여러 사용자가 받기를 시도할 때 잔액이 있는 경우의 동시성 제어 테스트"""
#     # 1. 사용자 생성 (뿌린 사람: 1, 받을 사람들: 2, 3, 4)
#     users = []
#     for uid in range(1, 5):
#         user = User(
#             id=uid,
#             username=f"user{uid}",
#             password="dummy",
#             email=f"user{uid}@example.com"
#         )
#         db_session.add(user)
#         users.append(user)
    
#     # 2. 채팅방 멤버 추가
#     for user in users:
#         member = ChatRoomMember(
#             chat_room_id=test_chat_room.id,
#             user_id=user.id
#         )
#         db_session.add(member)
    
#     # 3. 사용자 지갑 생성
#     for user in users:
#         wallet = UserWallet(
#             user_id=user.id,
#             balance=10000
#         )
#         db_session.add(wallet)
    
#     # 4. 뿌리기 건 생성 (4000원을 3명에게 -> 1333원씩 + 1원 잔액)
#     spray = MoneyDistribution(
#         token="TEST456",
#         creator_id=1,
#         chat_room_id=test_chat_room.id,
#         total_amount=4000,
#         recipient_count=3,
#         created_at=datetime.utcnow()
#     )
#     db_session.add(spray)
#     await db_session.flush()
    
#     # 5. 분배 내역 생성 (1333원씩 3건, 잔액 1원은 랜덤하게 추가)
#     base_amount = 4000 // 3  # 1333
#     remaining = 4000 % 3     # 1
    
#     amounts = [base_amount] * 3
#     if remaining > 0:
#         lucky_index = 0  # 테스트의 일관성을 위해 첫 번째 사람에게 잔액 부여
#         amounts[lucky_index] += remaining
    
#     for amount in amounts:
#         detail = MoneyDistributionDetail(
#             distribution_id=spray.id,
#             allocated_amount=amount
#         )
#         db_session.add(detail)
    
#     await db_session.commit()

#     async def receive_attempt(user_id: int):
#         async with AsyncSession(db_session.bind, expire_on_commit=False) as session:
#             try:
#                 service = ReceiveService(session)
#                 result = await service.receive_money(spray.token, user_id, test_chat_room.id)
#                 await session.commit()
#                 return result
#             except Exception as e:
#                 await session.rollback()
#                 return e

#     # 2, 3, 4번 사용자가 동시에 시도
#     results = await asyncio.gather(
#         receive_attempt(2),
#         receive_attempt(3),
#         receive_attempt(4),
#         return_exceptions=True
#     )

#     # 성공한 케이스 수 확인
#     success_count = sum(1 for r in results if isinstance(r, int))
#     assert success_count == 3  # 3명 모두 받아야 함

#     # 받은 금액 확인
#     received_amounts = [r for r in results if isinstance(r, int)]
#     assert sum(received_amounts) == 4000  # 총액이 정확히 4000원
#     assert 1334 in received_amounts  # 잔액(1원)을 받은 금액이 존재
#     assert received_amounts.count(1333) == 2  # 나머지 두 명은 1333원

#     # 최종 상태 확인
#     async with AsyncSession(db_session.bind) as session:
#         details_query = select(MoneyDistributionDetail).where(
#             MoneyDistributionDetail.distribution_id == spray.id
#         )
#         details = (await session.execute(details_query)).scalars().all()
        
#         assert len(details) == 3  # 총 3개의 분배 내역
#         assert all(detail.receiver_id is not None for detail in details)  # 모두 할당됨
#         assert len(set(detail.receiver_id for detail in details)) == 3  # 중복 수령자 없음
        
#         # 금액 검증
#         amounts = [detail.allocated_amount for detail in details]
#         assert sum(amounts) == 4000  # 총액 일치
#         assert 1334 in amounts  # 잔액 포함된 금액 존재
#         assert amounts.count(1333) == 2  # 기본 금액 2개 