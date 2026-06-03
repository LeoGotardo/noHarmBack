import pytest

_BADGE_PAYLOAD = {
    "name": "7-day streak",
    "description": "7 days clean",
    "milestone": 7,
    "icon": "🌟",
    "status": 1,
}


def _create_badge(client, headers, payload=None):
    payload = payload or _BADGE_PAYLOAD
    resp = client.post("/badges", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestBadgeCRUD:
    def test_create_badge_returns_201(self, client, user_a):
        resp = client.post("/badges", json=_BADGE_PAYLOAD, headers=user_a["headers"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == _BADGE_PAYLOAD["name"]
        assert body["milestone"] == 7

    def test_list_badges_includes_created(self, client, user_a):
        badge = _create_badge(client, user_a["headers"])
        resp = client.get("/badges", headers=user_a["headers"])
        assert resp.status_code == 200
        ids = [b["id"] for b in resp.json()["badges"]]
        assert badge["id"] in ids

    def test_get_badge_by_id(self, client, user_a):
        badge = _create_badge(client, user_a["headers"])
        resp = client.get(f"/badges/{badge['id']}", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["id"] == badge["id"]

    def test_update_badge_name(self, client, user_a):
        badge = _create_badge(client, user_a["headers"])
        updated = {**_BADGE_PAYLOAD, "name": "30-day streak"}
        resp = client.put(f"/badges/update/{badge['id']}", json=updated, headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["name"] == "30-day streak"

    def test_delete_badge_removes_from_list(self, client, user_a):
        badge = _create_badge(client, user_a["headers"])
        client.delete(f"/badges/{badge['id']}", headers=user_a["headers"])
        resp = client.get("/badges", headers=user_a["headers"])
        ids = [b["id"] for b in resp.json()["badges"]]
        assert badge["id"] not in ids

    def test_get_nonexistent_badge_returns_404(self, client, user_a):
        import uuid
        resp = client.get(f"/badges/{uuid.uuid4()}", headers=user_a["headers"])
        assert resp.status_code == 404


class TestUserBadges:
    def test_grant_badge_to_user(self, client, user_a, user_b):
        badge = _create_badge(client, user_a["headers"])
        resp = client.post(
            f"/user-badges/{user_b['uid']}/{badge['id']}",
            headers=user_a["headers"],
        )
        assert resp.status_code in (200, 201)

    def test_revoke_badge_from_user(self, client, user_a, user_b):
        badge = _create_badge(client, user_a["headers"])
        client.post(f"/user-badges/{user_b['uid']}/{badge['id']}", headers=user_a["headers"])
        resp = client.post(
            f"/user-badges/revoke/{user_b['uid']}/{badge['id']}",
            headers=user_a["headers"],
        )
        assert resp.status_code in (200, 204)
