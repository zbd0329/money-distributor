from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List, Optional

class SprayRequest(BaseModel):
    total_amount: int = Field(..., description="뿌릴 총 금액", gt=0)
    recipient_count: int = Field(..., description="뿌릴 인원 수", gt=0)

    @field_validator('recipient_count')
    def validate_recipient_count(cls, v, info):
        total_amount = info.data.get('total_amount', 0)
        if total_amount > 0 and v > 0:
            if total_amount < v:
                raise ValueError("뿌릴 금액은 인원수보다 커야 합니다")
        return v

class SprayResponse(BaseModel):
    token: str = Field(..., description="생성된 뿌리기 토큰 (3자리)")

class ReceiveRequest(BaseModel):
    token: str

class ReceiveResponse(BaseModel):
    received_amount: int

class SprayReceiveDetail(BaseModel):
    """받기 완료된 정보"""
    amount: int = Field(..., description="받은 금액")
    user_id: int = Field(..., description="받은 사용자 ID")

class SprayStatusResponse(BaseModel):
    """뿌리기 조회 응답"""
    spray_time: datetime = Field(..., description="뿌린 시각")
    spray_amount: int = Field(..., description="뿌린 금액")
    received_amount: int = Field(..., description="받기 완료된 금액")
    received_list: List[SprayReceiveDetail] = Field(default_factory=list, description="받기 완료된 정보 목록") 