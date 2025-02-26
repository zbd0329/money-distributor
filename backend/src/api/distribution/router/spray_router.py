from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from ....db.database import get_db
from ..schema import SprayRequest, SprayResponse
from ..service.spray_service import SprayService
import logging

router = APIRouter()
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