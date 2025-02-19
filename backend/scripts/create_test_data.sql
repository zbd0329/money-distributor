-- 테스트 사용자 생성
INSERT INTO users (username, password, email) 
VALUES ('testuser', 'hashedpassword', 'test@example.com');

-- 사용자 지갑 생성 (10000원)
INSERT INTO user_wallet (user_id, balance) 
VALUES (1, 10000);

-- 테스트 채팅방 생성
INSERT INTO chat_rooms (id, room_name) 
VALUES ('TEST-ROOM-1', '테스트방');

-- 채팅방 멤버 추가
INSERT INTO chat_room_members (chat_room_id, user_id) 
VALUES ('TEST-ROOM-1', 1); 