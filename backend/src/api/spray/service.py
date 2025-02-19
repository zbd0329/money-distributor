from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ...db.models import (
    MoneyDistribution,
    MoneyDistributionDetail,
    ChatRoomMember,
    TransactionHistory,
    TransactionTypeEnum as TransactionType,
    TransactionStatusEnum as TransactionStatus,
    UserWallet
)
from .utils import generate_token, distribute_amount
from ...common.enums import TransactionType, TransactionStatus

logger = logging.getLogger(__name__)

class SprayService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_spray(self, user_id: int, room_id: str, total_amount: int, recipient_count: int) -> str:
        # 1. 채팅방 멤버 확인
        member_query = select(ChatRoomMember).where(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        )
        member = await self.db.execute(member_query)
        if not member.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="해당 대화방의 멤버가 아닙니다.")

        # 2. 잔액 확인
        wallet_query = select(UserWallet).where(UserWallet.user_id == user_id)
        wallet = (await self.db.execute(wallet_query)).scalar_one_or_none()
        if not wallet or wallet.balance < total_amount:
            raise HTTPException(status_code=400, detail="잔액이 부족합니다.")

        # 3. 토큰 생성 (중복 방지)
        while True:
            token = generate_token()
            exists = await self.db.execute(
                select(MoneyDistribution).where(MoneyDistribution.token == token)
            )
            if not exists.scalar_one_or_none():
                break

        # 4. 금액 분배
        amounts = distribute_amount(total_amount, recipient_count)

        # 5. 뿌리기 건 생성
        distribution = MoneyDistribution(
            token=token,
            creator_id=user_id,
            chat_room_id=room_id,
            total_amount=total_amount,
            recipient_count=recipient_count
        )
        self.db.add(distribution)
        await self.db.flush()  # ID 생성을 위해 flush

        # 6. 분배 내역 생성
        for amount in amounts:
            detail = MoneyDistributionDetail(
                distribution_id=distribution.id,
                allocated_amount=amount
            )
            self.db.add(detail)

        # 7. 거래 내역 기록 및 잔액 차감
        wallet.balance -= total_amount
        
        transaction = TransactionHistory(
            transaction_type=TransactionType.SPRAY,
            user_id=user_id,
            amount=-total_amount,
            balance_after=wallet.balance,
            token=token,
            chat_room_id=room_id,
            description=f"{recipient_count}명에게 뿌리기",
            status=TransactionStatus.SUCCESS
        )
        
        self.db.add(transaction)
        await self.db.commit()

        return token 

    async def receive_money(self, token: str, user_id: int, room_id: str) -> int:
        """뿌린 금액 받기
        Args:
            token: 뿌리기 토큰
            user_id: 받기 요청한 사용자 ID
            room_id: 대화방 ID

        Returns:
            받은 금액

        Raises:
            ValueError: 받기 조건이 맞지 않을 경우 발생
        """
        # 1. 채팅방 멤버 확인
        member_query = select(ChatRoomMember).where(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        )
        member = await self.db.execute(member_query)
        if not member.scalar_one_or_none():
            raise ValueError("해당 대화방의 멤버가 아닙니다.")

        # 2. 뿌리기 건 조회
        distribution = await self._get_distribution(token, room_id)
        if not distribution:
            raise ValueError("유효하지 않은 뿌리기 토큰입니다.")

        # 3. 유효성 검증
        await self._validate_receive_conditions(distribution, user_id)

        # 4. 할당되지 않은 분배 내역 가져오기
        detail = await self._get_available_distribution_detail(distribution.id)
        if not detail:
            raise ValueError("받을 수 있는 금액이 없습니다.")

        # 5. 사용자 지갑 잔액 업데이트
        await self._update_user_wallet(user_id, detail.allocated_amount)

        # 6. 분배 내역 업데이트
        await self._update_distribution_detail(detail.id, user_id)

        # 7. 거래 이력 기록
        await self._create_transaction_history(
            user_id=user_id,
            amount=detail.allocated_amount,
            token=token,
            room_id=room_id,
            related_user_id=distribution.creator_id
        )

        return detail.allocated_amount

    async def _get_distribution(self, token: str, room_id: str) -> MoneyDistribution:
        """뿌리기 정보를 조회합니다."""
        query = select(MoneyDistribution).where(
            and_(
                MoneyDistribution.token == token,
                MoneyDistribution.chat_room_id == room_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _validate_receive_conditions(self, distribution: MoneyDistribution, user_id: int):
        """받기 조건을 검증합니다."""
        # 자신이 뿌린 건은 받을 수 없음
        if distribution.creator_id == user_id:
            raise ValueError("자신이 뿌린 건은 받을 수 없습니다.")

        # 10분 제한 확인
        if datetime.utcnow() > distribution.created_at + timedelta(minutes=10):
            raise ValueError("뿌린지 10분이 지나 받을 수 없습니다.")

        # 이미 받은 내역이 있는지 확인
        query = select(MoneyDistributionDetail).where(
            and_(
                MoneyDistributionDetail.distribution_id == distribution.id,
                MoneyDistributionDetail.receiver_id == user_id
            )
        )
        result = await self.db.execute(query)
        if result.scalar_one_or_none():
            raise ValueError("이미 받은 사용자입니다.")

    async def _get_available_distribution_detail(self, distribution_id: int) -> MoneyDistributionDetail:
        """할당되지 않은 분배 내역을 가져옵니다."""
        query = select(MoneyDistributionDetail).where(
            and_(
                MoneyDistributionDetail.distribution_id == distribution_id,
                MoneyDistributionDetail.receiver_id.is_(None)
            )
        ).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _update_user_wallet(self, user_id: int, amount: int):
        """사용자 지갑 잔액을 업데이트합니다."""
        query = update(UserWallet).where(
            UserWallet.user_id == user_id
        ).values(
            balance=UserWallet.balance + amount
        )
        await self.db.execute(query)

    async def _update_distribution_detail(self, detail_id: int, user_id: int):
        """분배 내역을 업데이트합니다."""
        query = update(MoneyDistributionDetail).where(
            MoneyDistributionDetail.id == detail_id
        ).values(
            receiver_id=user_id,
            claimed_at=datetime.utcnow()
        )
        await self.db.execute(query)

    async def _create_transaction_history(self, user_id: int, amount: int, 
                                        token: str, room_id: str, related_user_id: int):
        """거래 이력을 생성합니다."""
        # 현재 잔액 조회
        wallet_query = select(UserWallet.balance).where(UserWallet.user_id == user_id)
        result = await self.db.execute(wallet_query)
        current_balance = result.scalar_one()

        # 거래 이력 생성
        transaction = TransactionHistory(
            transaction_type=TransactionType.RECEIVE,
            user_id=user_id,
            amount=amount,
            balance_after=current_balance,
            related_user_id=related_user_id,
            token=token,
            chat_room_id=room_id,
            description="뿌리기 받기",
            status=TransactionStatus.SUCCESS
        )
        self.db.add(transaction) 