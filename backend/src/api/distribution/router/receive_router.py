from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from ....db.database import get_db
from ..schema import ReceiveRequest, ReceiveResponse
from ..service.receive_service import ReceiveService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/receive", response_model=ReceiveResponse)
async def receive_money(
    request: ReceiveRequest,
    x_user_id: int = Header(...),  # 필수 헤더
    x_room_id: str = Header(...),  # 필수 헤더
    db: AsyncSession = Depends(get_db)
):
    """돈 받기 요청을 처리하는 엔드포인트"""
    service = ReceiveService(db)
    return await service.process_receive_request(
        token=request.token,
        user_id=x_user_id,
        room_id=x_room_id
    ) 