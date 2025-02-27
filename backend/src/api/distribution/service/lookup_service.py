from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from src.utils.token.token import TokenService
from fastapi import HTTPException
from ..schema import SprayStatusResponse, SprayReceiveDetail

from ....db.models import (
    MoneyDistribution,
    MoneyDistributionDetail
)

logger = logging.getLogger(__name__)

class LookupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._token_service = TokenService()

    async def get_spray_status(self, token: str, user_id: int) -> SprayStatusResponse:
        """
        뿌리기 건의 현재 상태를 조회합니다.
        - 뿌린 사람 자신만 조회 가능
        - 뿌린 시점으로부터 7일 동안 조회 가능
        """
        # 뿌리기 정보 조회
        spray = await self.get_spray_by_token(token)
        if not spray:
            raise HTTPException(status_code=404, detail="해당 토큰의 뿌리기 건이 존재하지 않습니다.")
        
        # 뿌린 사람 본인인지 확인
        if spray.creator_id != user_id:
            raise HTTPException(status_code=403, detail="뿌리기 건은 생성자만 조회할 수 있습니다.")
        
        # 상세 정보 조회
        details = await self.get_spray_details(spray.id)
        
        # 디버깅을 위한 로그 추가
        logger.debug(f"Spray details - token: {token}, details count: {len(details)}")
        logger.debug(f"Details with receivers: {[d for d in details if d.receiver_id is not None]}")
        
        # 받기 완료된 금액 총합 계산
        total_received = sum(detail.allocated_amount for detail in details if detail.receiver_id is not None)
        
        # 받기 완료된 정보 목록 생성
        received_list = [
            SprayReceiveDetail(
                amount=detail.allocated_amount,
                user_id=detail.receiver_id
            )
            for detail in details
            if detail.receiver_id is not None  # 받은 건만 포함
        ]
        
        response = SprayStatusResponse(
            spray_time=spray.created_at,
            spray_amount=spray.total_amount,
            received_amount=total_received,
            received_list=received_list
        )
        
        # 최종 응답 로깅
        logger.debug(f"Final response: {response}")
        
        return response

    async def get_spray_by_token(self, token: str) -> MoneyDistribution:
        """토큰으로 뿌리기 건을 조회합니다."""
        # Redis에서 토큰 유효성 먼저 확인
        if not self._token_service.validate_token(token):
            raise ValueError("유효하지 않은 토큰입니다.")

        # MySQL에서 상세 정보 조회
        query = select(MoneyDistribution).where(MoneyDistribution.token == token)
        distribution = (await self.db.execute(query)).scalar_one_or_none()

        if not distribution:
            raise ValueError("해당 토큰으로 분배된 내역이 없습니다.")

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