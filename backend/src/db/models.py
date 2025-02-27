from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    BigInteger,
    Enum,
    JSON,
    UniqueConstraint,
    func,
    CHAR,
)
from sqlalchemy.orm import relationship
from .database import Base, generate_uuid
import enum
from uuid import uuid4

# -----------------------------------------------------------------
# Enum 타입 정의 (TransactionHistory 테이블에서 사용)
# -----------------------------------------------------------------
class TransactionTypeEnum(enum.Enum):
    CHARGE = "CHARGE"
    SPRAY = "SPRAY"
    RECEIVE = "RECEIVE"


class TransactionStatusEnum(enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# -----------------------------------------------------------------
# users 테이블 (회원 정보)
# -----------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 1:1 관계 -> 회원가입 시 초기 잔액 생성
    wallet = relationship("UserWallet", back_populates="user", uselist=False)
    # 친구 관계 (내가 요청한 친구)
    friends = relationship("Friend", back_populates="user", foreign_keys="Friend.user_id")
    # 친구 관계 (다른 사용자가 나를 친구로 등록한 경우)
    friend_of = relationship("Friend", back_populates="friend", foreign_keys="Friend.friend_id")


# -----------------------------------------------------------------
# user_wallet 테이블 (잔액 관리)
# -----------------------------------------------------------------
class UserWallet(Base):
    __tablename__ = "user_wallet"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    balance = Column(BigInteger, nullable=False, server_default="0")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="wallet")


# -----------------------------------------------------------------
# friends 테이블 (친구 관계)
# -----------------------------------------------------------------
class Friend(Base):
    __tablename__ = "friends"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_user_friend"),)

    user = relationship("User", foreign_keys=[user_id], back_populates="friends")
    friend = relationship("User", foreign_keys=[friend_id], back_populates="friend_of")


# -----------------------------------------------------------------
# chat_rooms 테이블 (채팅방)
# -----------------------------------------------------------------
class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id = Column(String(36), primary_key=True, index=True, default=generate_uuid)
    room_name = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

    members = relationship("ChatRoomMember", back_populates="chat_room")


# -----------------------------------------------------------------
# chat_room_members 테이블 (채팅방 멤버)
# -----------------------------------------------------------------
class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"

    id = Column(Integer, primary_key=True)
    chat_room_id = Column(String(36), ForeignKey("chat_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("chat_room_id", "user_id", name="uq_chatroom_user"),)

    chat_room = relationship("ChatRoom", back_populates="members")
    user = relationship("User")


# -----------------------------------------------------------------
# money_distribution 테이블 (뿌리기 기록)
# -----------------------------------------------------------------
class MoneyDistribution(Base):
    __tablename__ = "money_distribution"

    id = Column(Integer, primary_key=True)
    token = Column(CHAR(3), unique=True, nullable=False, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_room_id = Column(String(36), ForeignKey("chat_rooms.id"), nullable=False)
    total_amount = Column(BigInteger, nullable=False)
    recipient_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    details = relationship("MoneyDistributionDetail", back_populates="distribution")
    creator = relationship("User")
    chat_room = relationship("ChatRoom")


# -----------------------------------------------------------------
# money_distribution_details 테이블 (뿌리기 상세 내역)
# -----------------------------------------------------------------
class MoneyDistributionDetail(Base):
    __tablename__ = "money_distribution_details"

    id = Column(Integer, primary_key=True)
    distribution_id = Column(Integer, ForeignKey("money_distribution.id"), nullable=False)
    allocated_amount = Column(BigInteger, nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    distribution = relationship("MoneyDistribution", back_populates="details")
    receiver = relationship("User")


# -----------------------------------------------------------------
# transaction_history 테이블 (거래 이력)
# -----------------------------------------------------------------
class TransactionHistory(Base):
    __tablename__ = "transaction_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(BigInteger, nullable=False)
    balance_after = Column(BigInteger, nullable=False)
    related_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    token = Column(CHAR(3), nullable=True, index=True)
    chat_room_id = Column(String(36), ForeignKey("chat_rooms.id"), nullable=True)
    description = Column(String(255))
    target_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    status = Column(Enum(TransactionStatusEnum), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    related_user = relationship("User", foreign_keys=[related_user_id])
    chat_room = relationship("ChatRoom") 