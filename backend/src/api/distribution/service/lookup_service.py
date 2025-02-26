from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from src.utils.token.token import TokenService

from ....db.models import (
    MoneyDistribution,
    MoneyDistributionDetail
)

logger = logging.getLogger(__name__)

class LookupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._token_service = TokenService()

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