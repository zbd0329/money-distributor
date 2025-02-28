from locust import HttpUser, task, between
import random
import string
import logging

logger = logging.getLogger(__name__)

def generate_room_id():
    """무작위 채팅방 ID 생성"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

class MoneyDistributorUser(HttpUser):
    wait_time = between(0.1, 0.5)  # 더 빈번한 요청을 위해 대기 시간 감소
    
    def on_start(self):
        """사용자 초기화"""
        self.room_id = generate_room_id()  # 각 사용자마다 다른 방 사용
        self.token = None
        self.current_recipients = []
        self.received_users = set()
        
        # 각 사용자마다 고유한 ID 할당
        self.sprayer_id = random.randint(1, 1000)
        self.receiver_ids = [random.randint(1001, 2000) for _ in range(3)]
    
    @task(1)
    def create_spray(self):
        """뿌리기 생성 테스트"""
        headers = {
            "x-user-id": str(self.sprayer_id),
            "x-room-id": self.room_id
        }
        recipient_count = random.randint(1, 3)
        data = {
            "total_amount": random.randint(1000, 10000),
            "recipient_count": recipient_count
        }
        with self.client.post("/api/v1/spray", json=data, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response_data = response.json()
                self.token = response_data.get("token")
                self.current_recipients = recipient_count
                self.received_users = set()
                response.success()
            else:
                logger.error(f"Spray creation failed: {response.text}")
                response.failure(f"Failed to create spray: {response.text}")
    
    @task(2)
    def receive_money(self):
        """받기 테스트"""
        if not self.token or self.current_recipients <= 0:
            return
            
        available_receivers = [uid for uid in self.receiver_ids if uid not in self.received_users]
        if not available_receivers:
            return
            
        receiver_id = random.choice(available_receivers)
        headers = {
            "x-user-id": str(receiver_id),
            "x-room-id": self.room_id
        }
        data = {
            "token": self.token
        }
        with self.client.post("/api/v1/receive", json=data, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                self.received_users.add(receiver_id)
                self.current_recipients -= 1
                response.success()
            else:
                logger.error(f"Money receive failed: {response.text}")
                response.failure(f"Failed to receive money: {response.text}")
    
    @task(1)
    def lookup_spray(self):
        """조회 테스트"""
        if not self.token:
            return
            
        headers = {
            "x-user-id": str(self.sprayer_id)
        }
        with self.client.get(f"/api/v1/spray/{self.token}", headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                logger.error(f"Spray lookup failed: {response.text}")
                response.failure(f"Failed to lookup spray: {response.text}") 