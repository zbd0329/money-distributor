"""
Celery 태스크 정의

이 모듈은 비동기적으로 처리될 작업들을 정의합니다.
주요 태스크:
- process_receive_money: 돈 받기 요청 처리
"""

import asyncio
import logging
from .celery_app import celery_app
from ..db.database import async_session_maker

logger = logging.getLogger(__name__)

@celery_app.task(name="process_receive_money", bind=True)
def process_receive_money(self, *, token: str, user_id: int, room_id: str) -> dict:
    """
    돈 받기 요청을 처리하는 Celery 태스크
    
    이 태스크는 다음과 같은 순서로 처리됩니다:
    1. 비동기 DB 세션 생성
    2. ReceiveService를 통해 돈 받기 처리 (비관적 락 사용)
    3. 처리 결과 반환
    
    Args:
        token: 뿌리기 토큰
        user_id: 받기 요청한 사용자 ID
        room_id: 대화방 ID
        
    Returns:
        dict: 처리 결과를 담은 딕셔너리 {"received_amount": int}
    """
    logger.info(f"[Task {self.request.id}] Starting money receive processing")
    logger.info(f"Parameters - Token: {token}, User: {user_id}, Room: {room_id}")

    async def _process():
        # 순환 참조를 피하기 위해 함수 내부에서 import
        from ..api.distribution.service.receive_service import ReceiveService
        
        async with async_session_maker() as session:
            try:
                # ReceiveService 인스턴스 생성
                receive_service = ReceiveService(session)
                
                # 비관적 락을 사용하여 돈 받기 처리
                received_amount = await receive_service.receive_money(
                    token=token,
                    user_id=user_id,
                    room_id=room_id
                )
                
                logger.info(f"[Task {self.request.id}] Successfully processed. Amount: {received_amount}")
                return {"received_amount": received_amount}
                
            except Exception as e:
                logger.error(f"[Task {self.request.id}] Processing failed: {str(e)}")
                raise

    # 비동기 함수를 동기적으로 실행
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_process()) 