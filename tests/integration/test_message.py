import pytest
from helpers import open_chat, register


class TestSendMessage:
    def test_send_message_returns_201_unread(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        resp = client.post(
            "/messages",
            json={"chatId": chat_id, "content": "hello integration"},
            headers=user_a["headers"],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == 7  # unread
        assert body["content"] == "hello integration"

    def test_get_messages_by_chat(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        client.post("/messages", json={"chatId": chat_id, "content": "msg1"}, headers=user_a["headers"])
        client.post("/messages", json={"chatId": chat_id, "content": "msg2"}, headers=user_a["headers"])

        resp = client.get(f"/messages/chat/{chat_id}", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_get_unread_messages(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        client.post("/messages", json={"chatId": chat_id, "content": "unread msg"}, headers=user_a["headers"])

        resp = client.get(f"/messages/chat/{chat_id}/unread", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


class TestMarkRead:
    def test_mark_single_message_as_read(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        msg = client.post(
            "/messages",
            json={"chatId": chat_id, "content": "read me"},
            headers=user_a["headers"],
        ).json()

        resp = client.put(f"/messages/{msg['id']}/read", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 8  # read

    def test_mark_all_messages_as_read(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        for i in range(3):
            client.post("/messages", json={"chatId": chat_id, "content": f"msg{i}"}, headers=user_a["headers"])

        resp = client.put(f"/messages/chat/{chat_id}/read", headers=user_b["headers"])
        assert resp.status_code == 200

        unread = client.get(f"/messages/chat/{chat_id}/unread", headers=user_b["headers"])
        assert unread.json()["total"] == 0


class TestMessageRLS:
    def test_user_c_cannot_read_messages_in_a_b_chat(self, client, user_a, user_b):
        user_c = register(client)
        chat_id = open_chat(client, user_a, user_b)
        client.post("/messages", json={"chatId": chat_id, "content": "secret"}, headers=user_a["headers"])

        resp = client.get(f"/messages/chat/{chat_id}", headers=user_c["headers"])
        if resp.status_code == 200:
            assert resp.json()["total"] == 0
        else:
            assert resp.status_code in (403, 404)
