from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from src.utils.token.token import TokenService

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

    async def receive_money(self, token: str, user_id: int, room_id: str) -> int:
        """뿌린 금액 받기 - 비관적 락을 사용하여 동시성 처리
        
        Args:
            token: 뿌리기 토큰
            user_id: 받기 요청한 사용자 ID
            room_id: 대화방 ID

        Returns:
            받은 금액

        Raises:
            ValueError: 받기 조건이 맞지 않을 경우 발생
        """
        try:
            # 1. 뿌리기 건 조회 - 비관적 락 적용
            distribution_query = select(MoneyDistribution).where(
                and_(
                    MoneyDistribution.token == token,
                    MoneyDistribution.chat_room_id == room_id
                )
            ).with_for_update()  # 비관적 락 적용
            
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
            ).with_for_update().limit(1)  # 비관적 락 적용
            
            detail = (await self.db.execute(detail_query)).scalar_one_or_none()
            if not detail:
                raise ValueError("받을 수 있는 금액이 없습니다.")

            # 4. 사용자 지갑 잔액 업데이트 - 비관적 락 적용
            wallet_query = select(UserWallet).where(
                UserWallet.user_id == user_id
            ).with_for_update()  # 비관적 락 적용
            
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

            # 모든 변경사항 커밋
            await self.db.commit()
            
            return detail.allocated_amount

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error in receive_money: {str(e)}")
            raise

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
        try:
            query = update(MoneyDistributionDetail).where(
                MoneyDistributionDetail.id == detail_id
            ).values(
                receiver_id=user_id,
                claimed_at=datetime.utcnow()
            )
            result = await self.db.execute(query)
            await self.db.commit()  # commit 추가
            
            # 업데이트 확인을 위한 로깅
            logger.debug(f"Updated distribution detail {detail_id} for user {user_id}")
            
            # 업데이트된 레코드 확인
            check_query = select(MoneyDistributionDetail).where(
                MoneyDistributionDetail.id == detail_id
            )
            updated_detail = (await self.db.execute(check_query)).scalar_one_or_none()
            logger.debug(f"Updated detail record: {updated_detail}")
            
        except Exception as e:
            logger.error(f"Error updating distribution detail: {e}")
            await self.db.rollback()
            raise

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

    async def get_spray_by_token(self, token: str) -> MoneyDistribution:
        """토큰으로 뿌리기 건을 조회합니다."""
        # Redis에서 토큰 유효성 먼저 확인
        if not self._token_service.validate_token(token):
            raise ValueError("유효하지 않은 토큰입니다.")

        # MySQL에서 상세 정보 조회
        query = select(MoneyDistribution).where(MoneyDistribution.token == token)
        distribution = (await self.db.execute(query)).scalar_one_or_none()

        if not distribution:
            raise ValueError("존재하지 않는 토큰입니다.")

        # 7일 이내 조회 가능 확인
        if datetime.utcnow() > distribution.created_at + timedelta(days=7):
            raise ValueError("조회 가능 기간이 만료되었습니다.")

        return distribution

    async def get_spray_details(self, distribution_id: int) -> list[MoneyDistributionDetail]:
        """뿌리기 건의 상세 내역을 조회합니다."""
        query = select(MoneyDistributionDetail).where(
            MoneyDistributionDetail.distribution_id == distribution_id
        ).order_by(MoneyDistributionDetail.claimed_at)  # 받은 시간순으로 정렬
        
        result = await self.db.execute(query)
        details = result.scalars().all()
        
        # 디버깅을 위한 로그 추가
        logger.debug(f"Distribution details for ID {distribution_id}: {details}")
        for detail in details:
            logger.debug(f"Detail - amount: {detail.allocated_amount}, receiver: {detail.receiver_id}, claimed: {detail.claimed_at}")
        
        return details 

    async def validate_receive_request(self, token: str, user_id: int, room_id: str) -> None:
        """
        돈 받기 요청에 대한 기본 검증을 수행합니다.
        
        Args:
            token: 뿌리기 토큰
            user_id: 받기 요청한 사용자 ID
            room_id: 대화방 ID
            
        Raises:
            ValueError: 검증 실패 시 발생
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
        # 자신이 뿌린 건은 받을 수 없음
        if distribution.creator_id == user_id:
            raise ValueError("자신이 뿌린 건은 받을 수 없습니다.")

        # 10분 제한 확인
        if datetime.utcnow() > distribution.created_at + timedelta(minutes=10):
            raise ValueError("뿌린지 10분이 지나 받을 수 없습니다.")

        # 이미 받은 내역이 있는지 확인
        detail_query = select(MoneyDistributionDetail).where(
            and_(
                MoneyDistributionDetail.distribution_id == distribution.id,
                MoneyDistributionDetail.receiver_id == user_id
            )
        )
        if (await self.db.execute(detail_query)).scalar_one_or_none():
            raise ValueError("이미 받은 사용자입니다.") 