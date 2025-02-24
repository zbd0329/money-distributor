"""
Celery 애플리케이션 설정

이 모듈은 Celery 워커의 기본 설정을 정의합니다.
- broker_url: RabbitMQ 연결 설정
- result_backend: 작업 결과 저장소 설정
- task_routes: 작업별 큐 설정
"""

import os
from celery import Celery
from ..core.config import settings

# RabbitMQ 연결 URL 구성
RABBITMQ_URL = f"amqp://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}//"

# Celery 앱 초기화
celery_app = Celery(
    'money_distributor',
    broker=RABBITMQ_URL,
    backend='rpc://',  # RPC 백엔드 사용 (작업 결과를 RabbitMQ를 통해 반환)
    include=['src.worker.tasks']  # 태스크 모듈 등록
)

# Celery 기본 설정
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_default_queue='receive_requests',  # 기본 큐 이름
    task_routes={
        'process_receive_money': {'queue': 'receive_requests'},  # 돈 받기 요청 처리 큐
    }
) 