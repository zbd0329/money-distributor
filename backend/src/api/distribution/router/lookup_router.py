from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ....db.database import get_db
from ..schema import SprayStatusResponse
from ..service.lookup_service import LookupService
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
    return await lookup_service.get_spray_status(token, x_user_id) 