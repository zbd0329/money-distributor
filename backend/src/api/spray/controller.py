from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ...db.database import get_db
from .schema import SprayRequest, SprayResponse, ReceiveRequest, ReceiveResponse
from .service import SprayService

router = APIRouter()

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