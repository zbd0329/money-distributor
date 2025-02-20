from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ...db.database import get_db
from .schema import SprayRequest, SprayResponse, ReceiveRequest, ReceiveResponse, SprayStatusResponse, SprayReceiveDetail
from .service import SprayService
from datetime import datetime, timedelta
import logging

router = APIRouter(prefix="/api/v1")

logger = logging.getLogger(__name__)

@router.post("/spray", response_model=SprayResponse)
async def create_spray(
    request: SprayRequest,
    x_user_id: int = Header(...),
    x_room_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    service = SprayService(db)
    token = await service.create_spray(
        user_id=x_user_id,
        room_id=x_room_id,
        total_amount=request.total_amount,
        recipient_count=request.recipient_count
    )
    
    return SprayResponse(token=token)

@router.post("/receive", response_model=ReceiveResponse)
async def receive_money(
    request: ReceiveRequest,
    x_user_id: int = Header(...),  # 필수 헤더
    x_room_id: str = Header(...),  # 필수 헤더
    db: AsyncSession = Depends(get_db)
) -> ReceiveResponse:
    """
    뿌리기 건에 대한 받기 API
    
    Args:
        request: 토큰 정보를 포함한 요청 객체
        x_user_id: 요청자 식별 번호 (헤더)
        x_room_id: 대화방 식별자 (헤더)
        db: 데이터베이스 세션
    
    Returns:
        받은 금액 정보
    
    Raises:
        HTTPException: 받기 실패 시 발생
    """
    try:
        spray_service = SprayService(db)
        received_amount = await spray_service.receive_money(
            token=request.token,
            user_id=x_user_id,
            room_id=x_room_id
        )
        return ReceiveResponse(received_amount=received_amount)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    spray_service = SprayService(db)
    
    # 뿌리기 정보 조회
    spray = await spray_service.get_spray_by_token(token)
    if not spray:
        raise HTTPException(status_code=404, detail="해당 토큰의 뿌리기 건이 존재하지 않습니다.")
    
    # 뿌린 사람 본인인지 확인
    if spray.creator_id != x_user_id:
        raise HTTPException(status_code=403, detail="뿌리기 건은 생성자만 조회할 수 있습니다.")
    
    # 7일이 지났는지 확인
    if datetime.utcnow() - spray.created_at > timedelta(days=7):
        raise HTTPException(status_code=400, detail="뿌리기 후 7일이 지나 조회할 수 없습니다.")

    # 상세 정보 조회
    details = await spray_service.get_spray_details(spray.id)
    
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