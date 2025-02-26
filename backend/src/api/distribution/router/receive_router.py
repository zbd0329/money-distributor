from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ....db.database import get_db
from ..schema import ReceiveRequest, ReceiveResponse
from ..service.receive_service import ReceiveService
import logging
from ....worker.tasks import process_receive_money

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/receive", response_model=ReceiveResponse)
async def receive_money(
    request: ReceiveRequest,
    x_user_id: int = Header(...),  # 필수 헤더
    x_room_id: str = Header(...),  # 필수 헤더
    db: AsyncSession = Depends(get_db)
):
    """
    돈 받기 요청을 비동기적으로 처리하는 엔드포인트
    
    1. 기본 유효성 검증 수행
    2. Celery 태스크로 실제 처리 위임
    3. 처리 결과 반환
    """
    try:
        logger.info(f"Received money request - Token: {request.token}, User: {x_user_id}, Room: {x_room_id}")
        
        # 기본 검증 (채팅방 멤버십, 토큰 유효성 등)
        receive_service = ReceiveService(db)
        await receive_service.validate_receive_request(
            token=request.token,
            user_id=x_user_id,
            room_id=x_room_id
        )
        logger.info("Request validation passed")
        
        # Celery 태스크로 실제 처리 위임
        task_kwargs = {
            "token": request.token,
            "user_id": x_user_id,
            "room_id": x_room_id
        }
        
        # 태스크 실행 및 결과 대기
        logger.info("Delegating to Celery worker...")
        task = process_receive_money.apply_async(
            kwargs=task_kwargs,
            queue='receive_requests'
        )
        
        try:
            # 결과 대기 시간을 10초로 설정
            result = task.get(timeout=10)
            logger.info(f"Task completed. Result: {result}")
            return result  # {"received_amount": amount} 형식으로 반환됨
            
        except TimeoutError:
            logger.error("Task processing timed out")
            raise HTTPException(
                status_code=408,
                detail="요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            )
            
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") 