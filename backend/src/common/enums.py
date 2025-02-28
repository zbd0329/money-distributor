from enum import Enum

class TransactionType(str, Enum):
    CHARGE = "CHARGE"
    SPRAY = "SPRAY"
    RECEIVE = "RECEIVE"

class TransactionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED" 