from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ....db.database import get_db
from ..schema import SprayStatusResponse, SprayReceiveDetail
from ..service.lookup_service import LookupService
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/spray/{token}", response_model=SprayStatusResponse)
async def get_spray_status(
    token: str,
    x_user_id: int = Header(..., alias="X-USER-ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    뿌리기 건의 현재 상태를 조회합니다.
    - 뿌린 사람 자신만 조회 가능
    - 뿌린 시점으로부터 7일 동안 조회 가능
    """
    lookup_service = LookupService(db)
    
    # 뿌리기 정보 조회
    spray = await lookup_service.get_spray_by_token(token)
    if not spray:
        raise HTTPException(status_code=404, detail="해당 토큰의 뿌리기 건이 존재하지 않습니다.")
    
    # 뿌린 사람 본인인지 확인
    if spray.creator_id != x_user_id:
        raise HTTPException(status_code=403, detail="뿌리기 건은 생성자만 조회할 수 있습니다.")
    
    # 상세 정보 조회
    details = await lookup_service.get_spray_details(spray.id)
    
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