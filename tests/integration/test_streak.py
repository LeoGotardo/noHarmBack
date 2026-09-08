import pytest


class TestStreakLifecycle:
    def test_start_streak_returns_201(self, client, user_a):
        resp = client.post("/streaks/start", headers=user_a["headers"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["owner_id"] == user_a["uid"]
        assert body["status"] is not None

    def test_start_streak_twice_returns_409(self, client, user_a):
        client.post("/streaks/start", headers=user_a["headers"])
        resp = client.post("/streaks/start", headers=user_a["headers"])
        assert resp.status_code == 409

    def test_get_current_streak_after_start(self, client, user_a):
        client.post("/streaks/start", headers=user_a["headers"])
        resp = client.get("/streaks/current", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["owner_id"] == user_a["uid"]

    def test_checkin_returns_200(self, client, user_a):
        client.post("/streaks/start", headers=user_a["headers"])
        resp = client.post("/streaks/checkin", headers=user_a["headers"])
        assert resp.status_code == 200

    def test_end_streak_starts_new_one(self, client, user_a):
        start_resp = client.post("/streaks/start", headers=user_a["headers"])
        original_id = start_resp.json()["id"]

        end_resp = client.post("/streaks/end", headers=user_a["headers"])
        assert end_resp.status_code == 200
        new_id = end_resp.json()["id"]
        assert new_id != original_id

    def test_history_includes_ended_streak(self, client, user_a):
        client.post("/streaks/start", headers=user_a["headers"])
        client.post("/streaks/end", headers=user_a["headers"])

        resp = client.get("/streaks/history", headers=user_a["headers"])
        assert resp.status_code == 200
        # At least 2 streaks: the ended one and the new active one
        assert resp.json()["total"] >= 2


class TestStreakRLS:
    def test_user_b_cannot_see_user_a_streak(self, client, user_a, user_b):
        client.post("/streaks/start", headers=user_a["headers"])

        # user_b fetching /streaks/current sees their own (none → 404 or empty)
        resp = client.get("/streaks/current", headers=user_b["headers"])
        # user_b has no streak → should get 404, not user_a's streak
        assert resp.status_code == 404
