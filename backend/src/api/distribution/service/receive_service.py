from datetime import datetime, timedelta
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ....db.models import (
    MoneyDistribution,
    MoneyDistributionDetail,
    ChatRoomMember,
    TransactionHistory,
    TransactionTypeEnum as TransactionType,
    TransactionStatusEnum as TransactionStatus,
    UserWallet
)

logger = logging.getLogger(__name__)

class ReceiveService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def receive_money(self, token: str, user_id: int, room_id: str) -> int:
        """뿌린 금액 받기 - 비관적 락을 사용하여 동시성 처리"""
        try:
            # 1. 뿌리기 건 조회 - 비관적 락 적용
            distribution_query = select(MoneyDistribution).where(
                and_(
                    MoneyDistribution.token == token,
                    MoneyDistribution.chat_room_id == room_id
                )
            ).with_for_update()
            
            distribution = (await self.db.execute(distribution_query)).scalar_one_or_none()
            if not distribution:
                raise ValueError("유효하지 않은 뿌리기 토큰입니다.")

            # 2. 유효성 검증
            await self._validate_receive_conditions(distribution, user_id)

            # 3. 할당되지 않은 분배 내역 가져오기 - 비관적 락 적용
            detail_query = select(MoneyDistributionDetail).where(
                and_(
                    MoneyDistributionDetail.distribution_id == distribution.id,
                    MoneyDistributionDetail.receiver_id.is_(None)
                )
            ).with_for_update().limit(1)
            
            detail = (await self.db.execute(detail_query)).scalar_one_or_none()
            if not detail:
                raise ValueError("받을 수 있는 금액이 없습니다.")

            # 4. 사용자 지갑 잔액 업데이트 - 비관적 락 적용
            wallet_query = select(UserWallet).where(
                UserWallet.user_id == user_id
            ).with_for_update()
            
            wallet = (await self.db.execute(wallet_query)).scalar_one_or_none()
            if not wallet:
                raise ValueError("사용자 지갑을 찾을 수 없습니다.")
                
            wallet.balance += detail.allocated_amount

            # 5. 분배 내역 업데이트
            detail.receiver_id = user_id
            detail.claimed_at = datetime.utcnow()

            # 6. 거래 이력 기록
            transaction = TransactionHistory(
                transaction_type=TransactionType.RECEIVE,
                user_id=user_id,
                amount=detail.allocated_amount,
                balance_after=wallet.balance,
                related_user_id=distribution.creator_id,
                token=token,
                chat_room_id=room_id,
                description="뿌리기 받기",
                status=TransactionStatus.SUCCESS
            )
            self.db.add(transaction)

            await self.db.commit()
            return detail.allocated_amount

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error in receive_money: {str(e)}")
            raise

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

    async def validate_receive_request(self, token: str, user_id: int, room_id: str) -> None:
        """돈 받기 요청에 대한 기본 검증을 수행합니다."""
        # 1. 채팅방 멤버 확인
        member_query = select(ChatRoomMember).where(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        )
        member = await self.db.execute(member_query)
        if not member.scalar_one_or_none():
            raise ValueError("해당 대화방의 멤버가 아닙니다.")

        # 2. 뿌리기 건 조회
        distribution_query = select(MoneyDistribution).where(
            and_(
                MoneyDistribution.token == token,
                MoneyDistribution.chat_room_id == room_id
            )
        )
        distribution = (await self.db.execute(distribution_query)).scalar_one_or_none()
        if not distribution:
            raise ValueError("유효하지 않은 뿌리기 토큰입니다.")

        # 3. 기본 유효성 검증
        await self._validate_receive_conditions(distribution, user_id) 