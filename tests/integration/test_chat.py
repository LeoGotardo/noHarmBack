import pytest
from helpers import make_friends, open_chat, register


class TestChatCreate:
    def test_create_chat_returns_201(self, client, user_a, user_b):
        make_friends(client, user_a, user_b)
        resp = client.post("/chats", json={"receiverId": user_b["uid"]}, headers=user_a["headers"])
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body

    def test_create_chat_idempotent(self, client, user_a, user_b):
        make_friends(client, user_a, user_b)
        resp1 = client.post("/chats", json={"receiverId": user_b["uid"]}, headers=user_a["headers"])
        resp2 = client.post("/chats", json={"receiverId": user_b["uid"]}, headers=user_a["headers"])
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] == resp2.json()["id"]


class TestChatLifecycle:
    def test_accept_chat_changes_status_to_enabled(self, client, user_a, user_b):
        make_friends(client, user_a, user_b)
        chat = client.post("/chats", json={"receiverId": user_b["uid"]}, headers=user_a["headers"]).json()
        resp = client.post(f"/chats/{chat['id']}/accept", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 1  # enabled

    def test_end_chat_changes_status_to_disabled(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        resp = client.post(f"/chats/{chat_id}/end", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 0  # disabled

    def test_delete_chat_removes_from_list(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        client.delete(f"/chats/{chat_id}", headers=user_a["headers"])

        resp = client.get("/chats", headers=user_a["headers"])
        ids = [c["id"] for c in resp.json()["chats"]]
        assert chat_id not in ids


class TestChatRLS:
    def test_user_b_cannot_see_user_a_private_chat(self, client, user_a, user_b):
        user_c = register(client)
        chat_id = open_chat(client, user_a, user_c)

        resp = client.get(f"/chats/{chat_id}", headers=user_b["headers"])
        assert resp.status_code in (403, 404)

    def test_my_chats_list_only_own(self, client, user_a, user_b):
        open_chat(client, user_a, user_b)
        resp = client.get("/chats", headers=user_b["headers"])
        chat_ids = [c["id"] for c in resp.json()["chats"]]
        assert len(chat_ids) >= 1

        user_c = register(client)
        a_c_chat_id = open_chat(client, user_a, user_c)

        resp2 = client.get("/chats", headers=user_b["headers"])
        ids2 = [c["id"] for c in resp2.json()["chats"]]
        assert a_c_chat_id not in ids2
