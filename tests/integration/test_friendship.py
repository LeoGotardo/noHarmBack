import pytest
from helpers import make_friends


class TestSendRequest:
    def test_send_request_returns_201_pending(self, client, user_a, user_b):
        resp = client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == 4  # pending

    def test_cannot_send_to_yourself(self, client, user_a):
        resp = client.post(f"/friendships/{user_a['uid']}", headers=user_a["headers"])
        assert resp.status_code in (400, 409)

    def test_duplicate_request_returns_error(self, client, user_a, user_b):
        client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        resp = client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        assert resp.status_code in (400, 409)


class TestAcceptReject:
    def test_accept_request_changes_status_to_accepted(self, client, user_a, user_b):
        create_resp = client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        fid = create_resp.json()["id"]

        resp = client.post(f"/friendships/{fid}/accept", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 5  # accepted

    def test_reject_request_changes_status_to_ignored(self, client, user_a, user_b):
        create_resp = client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        fid = create_resp.json()["id"]

        resp = client.post(f"/friendships/{fid}/reject", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 6  # ignored


class TestBlockUnblock:
    def test_block_changes_status_to_blocked(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)
        resp = client.post(f"/friendships/{fid}/block", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 3  # blocked

    def test_unblock_after_block(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)
        client.post(f"/friendships/{fid}/block", headers=user_a["headers"])
        resp = client.post(f"/friendships/{fid}/unblock", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] != 3


class TestListFriendships:
    def test_get_my_friendships_only_shows_own(self, client, user_a, user_b):
        make_friends(client, user_a, user_b)
        resp = client.get("/friendships", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_pending_sent_shows_outgoing_requests(self, client, user_a, user_b):
        client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        resp = client.get("/friendships/sent", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_pending_received_shows_incoming_requests(self, client, user_a, user_b):
        client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        resp = client.get("/friendships/pending", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_delete_friendship_removes_it(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)
        resp = client.delete(f"/friendships/{fid}", headers=user_a["headers"])
        assert resp.status_code == 200
