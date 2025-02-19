from pydantic import BaseModel, Field, field_validator

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