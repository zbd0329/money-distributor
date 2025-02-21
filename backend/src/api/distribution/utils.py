import random
import string
from src.utils.token.token import TokenService

_token_service = TokenService()

def generate_token() -> str:
    """3자리 랜덤 토큰 생성"""
    return _token_service.generate_token()

def distribute_random_amount(total_amount: int, count: int) -> list[int]:
    """총액을 count만큼 랜덤하게 분배"""
    if count <= 0 or total_amount <= 0:
        raise ValueError("Invalid input values")
    
    # 최소 1원씩은 받을 수 있도록 보장
    if total_amount < count:
        raise ValueError("Total amount must be greater than recipient count")
    
    # 마지막 사람을 제외한 나머지 금액을 랜덤하게 분배
    amounts = []
    remaining_amount = total_amount
    remaining_count = count
    
    while remaining_count > 1:
        # 남은 사람들에게 최소 1원씩은 보장하고 랜덤 금액 설정
        max_possible = remaining_amount - (remaining_count - 1)
        if max_possible <= 1:
            current_amount = 1
        else:
            current_amount = random.randint(1, max_possible)
            
        amounts.append(current_amount)
        remaining_amount -= current_amount
        remaining_count -= 1
    
    # 마지막 금액 추가
    amounts.append(remaining_amount)
    
    # 금액 순서를 랜덤하게 섞기
    random.shuffle(amounts)
    
    return amounts 


def distribute_amount(total_amount: int, count: int) -> list[int]:
    """총액을 count만큼 동일하게 분배하고 잔액은 랜덤 분배"""
    if count <= 0 or total_amount <= 0:
        raise ValueError("Invalid input values")
    
    # 최소 1원씩은 받을 수 있도록 보장
    if total_amount < count:
        raise ValueError("Total amount must be greater than recipient count")
    
    # 기본 동일 분배 금액 계산
    base_amount = total_amount // count
    remaining = total_amount % count
    
    # 기본 금액으로 리스트 생성
    amounts = [base_amount] * count
    
    # 잔액이 있는 경우 랜덤하게 분배
    if remaining > 0:
        # 랜덤하게 선택된 인덱스들에게 1원씩 추가 분배
        lucky_indices = random.sample(range(count), remaining)
        for idx in lucky_indices:
            amounts[idx] += 1
    
    # 금액 순서를 랜덤하게 섞기
    random.shuffle(amounts)
    
    return amounts