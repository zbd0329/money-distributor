from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from src.utils.token.token import TokenService

from ....db.models import (
    MoneyDistribution,
    MoneyDistributionDetail,
    ChatRoomMember,
    TransactionHistory,
    TransactionTypeEnum as TransactionType,
    TransactionStatusEnum as TransactionStatus,
    UserWallet
)
from ..utils import distribute_amount

logger = logging.getLogger(__name__)

class SprayService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._token_service = TokenService()

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

        try:
            # Redis에서 토큰 생성 
            token = self._token_service.generate_token()
            
            # 뿌리기 건 생성 (MySQL에 저장)
            distribution = MoneyDistribution(
                token=token,
                creator_id=user_id,
                chat_room_id=room_id,
                total_amount=total_amount,
                recipient_count=recipient_count
            )
            self.db.add(distribution)
            await self.db.flush()

            # 3. 금액 분배
            amounts = distribute_amount(total_amount, recipient_count)

            # 4. 분배 내역 생성
            for amount in amounts:
                detail = MoneyDistributionDetail(
                    distribution_id=distribution.id,
                    allocated_amount=amount
                )
                self.db.add(detail)

            # 5. 거래 내역 기록 및 잔액 차감
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

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error in create_spray: {e}")
            raise HTTPException(status_code=500, detail="뿌리기 생성에 실패했습니다.") 