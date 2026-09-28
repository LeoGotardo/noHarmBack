"""Integration tests for consent records, the age gate and the data export.

Three things meet here that only meet in a real request:

- **Registration is now a gate.** Terms and privacy are refused in the service,
  not the schema, so the status code depends on the order the checks run in —
  and a missing field would answer 422 for a reason that has nothing to do with
  consent.
- **Withdrawal is destructive across two tables.** `DELETE /users/me/consents/health`
  stamps `tb_13` and deletes from `tb_1`, both under RLS, and the thing worth
  proving is that afterwards the streak cannot simply be started again.
- **The export is mostly a list of exclusions**, and an exclusion is only real
  if the data it excludes actually existed. So the tests that matter here are
  the ones that put something in the database first.
"""

import uuid
from datetime import date

import pytest

from core.config import config
from helpers import body_for, make_friends, new_identity, open_chat


def _register_body(**overrides):
    identity = new_identity()
    return {**body_for(identity), **overrides}


# ── the gate at registration ──────────────────────────────────────────────────

class TestRegistrationGate:
    @pytest.mark.parametrize("missing", ["acceptedTerms", "acceptedPrivacy"])
    def test_without_a_binding_consent_returns_400(self, client, missing):
        resp = client.post("/auth/register", json=_register_body(**{missing: False}))

        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "CONSENT_REQUIRED"
        assert missing.replace("accepted", "").lower() in resp.json()["details"]["missing"]

    def test_declining_health_data_still_creates_the_account(self, client):
        """Declining is a real choice, not a checkbox in the way of the button."""
        resp = client.post("/auth/register", json=_register_body(healthDataConsent=False))
        assert resp.status_code == 201

        headers = {"Authorization": f"Bearer {resp.json()['accessToken']}"}
        me = client.get("/users/me", headers=headers).json()

        assert me["health_data_consent"] is False
        assert me["pending_consents"] == []

    def test_under_the_minimum_age_returns_403(self, client):
        today = date.today()
        tooYoung = today.replace(year=today.year - config.MINIMUM_AGE_YEARS + 1)

        resp = client.post("/auth/register", json=_register_body(birthDate=tooYoung.isoformat()))

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "UNDERAGE"
        assert resp.json()["details"]["minimumAge"] == config.MINIMUM_AGE_YEARS

    def test_a_future_birth_date_is_a_400_not_underage(self, client):
        today = date.today()
        resp = client.post(
            "/auth/register",
            json=_register_body(birthDate=today.replace(year=today.year + 1).isoformat()),
        )

        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "INVALID_BIRTH_DATE"

    def test_a_refused_registration_leaves_no_account(self, client):
        """Gated before anything is written.

        A row created first and refused afterwards is an account that exists
        having agreed to nothing, and nothing in the API can undo that.
        """
        identity = new_identity()
        body = {**body_for(identity), "acceptedTerms": False}

        assert client.post("/auth/register", json=body).status_code == 400

        # Same identity, this time accepting: it must be a fresh registration,
        # not a 409 against a half-made row.
        assert client.post("/auth/register", json=body_for(identity)).status_code == 201


# ── the consent record ────────────────────────────────────────────────────────

class TestConsentRecords:
    def test_registration_records_all_three(self, client, user_a):
        body = client.get("/users/me/consents", headers=user_a["headers"]).json()

        documents = {c["document"] for c in body["consents"]}
        assert documents == {"terms", "privacy", "health_data"}
        assert body["pending"] == []
        assert body["health_data_consent"] is True

    def test_the_stored_version_is_the_one_in_force(self, client, user_a):
        body = client.get("/users/me/consents", headers=user_a["headers"]).json()

        assert body["versions"]["terms"] == config.TERMS_VERSION
        stored = next(c for c in body["consents"] if c["document"] == "terms")
        assert stored["version"] == config.TERMS_VERSION

    def test_accepting_again_appends_rather_than_replacing(self, client, user_a):
        """Append-only: two taps on a slow connection are one intention, and
        the history has to survive either way."""
        before = len(client.get("/users/me/consents", headers=user_a["headers"]).json()["consents"])

        resp = client.post(
            "/users/me/consents",
            json={"documents": ["terms"]},
            headers=user_a["headers"],
        )
        assert resp.status_code == 201

        after = resp.json()["consents"]
        assert len(after) == before + 1
        assert sum(1 for c in after if c["document"] == "terms") == 2

    def test_a_new_version_re_gates_an_existing_account(self, client, user_a, monkeypatch):
        """The whole point of storing a version instead of a boolean.

        An account that agreed months ago has a row saying so. Publishing a new
        revision must put the app behind the gate again for that account — a
        stored signature refers to a text that no longer exists, and treating
        it as consent to the new one is the failure `tb_13` was built to make
        impossible.
        """
        before = client.get("/users/me", headers=user_a["headers"]).json()
        assert before["pending_consents"] == []

        # What publishing a revision actually is: a config change and nothing
        # else. In production it is an env var and a redeploy; the service
        # reads config per call, so nothing caches the old number.
        monkeypatch.setattr(config, "TERMS_VERSION", "2.0")

        after = client.get("/users/me", headers=user_a["headers"]).json()
        assert after["pending_consents"] == ["terms"]

        status = client.get("/users/me/consents", headers=user_a["headers"]).json()
        assert status["versions"]["terms"] == "2.0"
        assert status["pending"] == ["terms"]

    def test_accepting_the_new_version_clears_the_gate_and_keeps_the_old_row(
        self, client, user_a, monkeypatch
    ):
        monkeypatch.setattr(config, "TERMS_VERSION", "2.0")

        resp = client.post(
            "/users/me/consents",
            json={"documents": ["terms"]},
            headers=user_a["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["pending"] == []

        terms = [c for c in resp.json()["consents"] if c["document"] == "terms"]
        # Both revisions on file. The old row is the evidence of what was
        # agreed while that text was the one in force, and the past is not
        # edited.
        assert {c["version"] for c in terms} == {config.TERMS_VERSION, "1.0"} or len(terms) == 2

        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert me["pending_consents"] == []

    def test_both_binding_documents_can_go_stale_at_once(self, client, user_a, monkeypatch):
        monkeypatch.setattr(config, "TERMS_VERSION", "2.0")
        monkeypatch.setattr(config, "PRIVACY_VERSION", "3.1")

        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert sorted(me["pending_consents"]) == ["privacy", "terms"]

        client.post(
            "/users/me/consents",
            json={"documents": ["terms", "privacy"]},
            headers=user_a["headers"],
        )
        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert me["pending_consents"] == []

    def test_a_new_health_version_re_asks_only_a_live_consent(
        self, client, user_a, monkeypatch
    ):
        """Never given and withdrawn are both answers, and re-asking is
        nagging someone for opting out."""
        monkeypatch.setattr(config, "HEALTH_CONSENT_VERSION", "2.0")

        # user_a registered with health data consent, so it is live and stale.
        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert me["pending_consents"] == ["health_data"]

        # Withdrawing answers the question. The gate must not come back.
        client.delete("/users/me/consents/health", headers=user_a["headers"])
        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert me["pending_consents"] == []
        assert me["health_data_consent"] is False

    def test_a_stale_health_version_never_blocks_a_declined_account(
        self, client, monkeypatch
    ):
        """An account that said no at registration has no row at all, and a
        new revision of a document it declined is not its problem."""
        resp = client.post(
            "/auth/register",
            json=_register_body(healthDataConsent=False),
        )
        assert resp.status_code == 201
        headers = {"Authorization": f"Bearer {resp.json()['accessToken']}"}

        monkeypatch.setattr(config, "HEALTH_CONSENT_VERSION", "2.0")

        me = client.get("/users/me", headers=headers).json()
        assert me["pending_consents"] == []

    def test_the_body_cannot_name_a_version(self, client, user_a):
        """A client able to say which revision it agreed to could record
        agreement to a text it never displayed."""
        resp = client.post(
            "/users/me/consents",
            json={"documents": ["terms"], "version": "99.0"},
            headers=user_a["headers"],
        )
        assert resp.status_code == 422

    def test_an_unknown_document_is_refused(self, client, user_a):
        resp = client.post(
            "/users/me/consents",
            json={"documents": ["cookies"]},
            headers=user_a["headers"],
        )
        assert resp.status_code == 422

    def test_consents_need_authentication(self, client):
        assert client.get("/users/me/consents").status_code in (401, 403)


# ── withdrawing health-data consent ───────────────────────────────────────────

class TestHealthDataWithdrawal:
    def test_withdrawing_deletes_the_streaks(self, client, user_a):
        assert client.post("/streaks/start", headers=user_a["headers"]).status_code == 201

        resp = client.delete("/users/me/consents/health", headers=user_a["headers"])

        assert resp.status_code == 200
        assert resp.json()["withdrawn"] is True
        assert resp.json()["streaks_deleted"] >= 1

    def test_after_withdrawing_a_streak_cannot_be_started_again(self, client, user_a):
        """Without this the withdrawal lasts as long as it takes to tap start."""
        client.delete("/users/me/consents/health", headers=user_a["headers"])

        resp = client.post("/streaks/start", headers=user_a["headers"])

        assert resp.status_code == 403
        # `/streaks/start` lets NoHarmException reach the handler in main.py,
        # so the body carries `errorCode` and `message` rather than the `detail`
        # a converted HTTPException produces. The code is the point: without it
        # this is an unlabelled 403, and the app cannot say which consent is
        # missing or where to give it again.
        body = resp.json()
        assert body["errorCode"] == "HEALTH_CONSENT_REQUIRED"
        assert "consent" in body["message"].lower()

    def test_the_record_survives_the_withdrawal(self, client, user_a):
        client.delete("/users/me/consents/health", headers=user_a["headers"])

        body = client.get("/users/me/consents", headers=user_a["headers"]).json()
        health = [c for c in body["consents"] if c["document"] == "health_data"]

        assert len(health) == 1
        assert health[0]["withdrawn_at"] is not None
        assert body["health_data_consent"] is False
        # Answered, so never asked again.
        assert "health_data" not in body["pending"]

    def test_withdrawing_twice_is_idempotent(self, client, user_a):
        client.delete("/users/me/consents/health", headers=user_a["headers"])

        resp = client.delete("/users/me/consents/health", headers=user_a["headers"])

        assert resp.status_code == 200
        assert resp.json() == {"withdrawn": False, "streaks_deleted": 0}

    def test_the_account_is_otherwise_untouched(self, client, user_a, user_b):
        make_friends(client, user_a, user_b)

        client.delete("/users/me/consents/health", headers=user_a["headers"])

        me = client.get("/users/me", headers=user_a["headers"])
        assert me.status_code == 200
        assert me.json()["health_data_consent"] is False
        friends = client.get("/friendships", headers=user_a["headers"])
        assert friends.status_code == 200

    def test_consent_can_be_given_again(self, client, user_a):
        client.delete("/users/me/consents/health", headers=user_a["headers"])

        resp = client.post(
            "/users/me/consents",
            json={"documents": ["health_data"]},
            headers=user_a["headers"],
        )

        assert resp.status_code == 201
        assert resp.json()["health_data_consent"] is True
        assert client.post("/streaks/start", headers=user_a["headers"]).status_code == 201


# ── the export ────────────────────────────────────────────────────────────────

class TestDataExport:
    def test_export_has_every_section_and_nothing_incomplete(self, client, user_a):
        body = client.get("/users/me/export", headers=user_a["headers"]).json()

        assert body["incomplete"] == []
        assert body["account_id"] == user_a["uid"]
        for section in (
            "profile", "consents", "streaks", "friendships", "badges",
            "conversations", "devices", "moderation_notices", "reports_filed",
            "activity_log",
        ):
            assert section in body

    def test_export_carries_both_sides_of_a_conversation(self, client, user_a, user_b):
        chat_id = open_chat(client, user_a, user_b)
        client.post("/messages", json={"chatId": chat_id, "content": "from a"},
                    headers=user_a["headers"])
        client.post("/messages", json={"chatId": chat_id, "content": "from b"},
                    headers=user_b["headers"])

        body = client.get("/users/me/export", headers=user_a["headers"]).json()
        conversation = next(c for c in body["conversations"] if c["id"] == chat_id)
        bodies = {m["body"] for m in conversation["messages"]}

        assert {"from a", "from b"} <= bodies
        assert any(m["from_me"] for m in conversation["messages"])
        assert any(not m["from_me"] for m in conversation["messages"])

    def test_export_does_not_name_the_people_this_account_reported(self, client, user_a, user_b):
        """The reporter's own words are their data; the accusation tied to a
        name is a liability the moment the file leaves the device."""
        filed = client.post(
            f"/reports/{user_b['uid']}",
            json={"reason": "harassment", "details": "they would not stop"},
            headers=user_a["headers"],
        )
        assert filed.status_code == 201

        body = client.get("/users/me/export", headers=user_a["headers"]).json()

        assert any(r["details"] == "they would not stop" for r in body["reports_filed"])
        assert user_b["uid"] not in str(body["reports_filed"])

    def test_export_does_not_carry_reports_about_this_account(self, client, user_a, user_b):
        """The promise that a reported user is never told who complained is
        what makes reporting usable at all."""
        client.post(
            f"/reports/{user_b['uid']}",
            json={"reason": "harassment", "details": "unmistakable-marker-text"},
            headers=user_a["headers"],
        )

        body = client.get("/users/me/export", headers=user_b["headers"]).json()

        assert body["reports_filed"] == []
        assert "unmistakable-marker-text" not in str(body)
        assert user_a["uid"] not in str(body["reports_filed"])

    def test_export_never_carries_a_push_token(self, client, user_a):
        token = f"fcm-{uuid.uuid4()}"
        client.post("/notifications", json={"deviceFCM": token}, headers=user_a["headers"])

        body = client.get("/users/me/export", headers=user_a["headers"]).json()

        assert token not in str(body)

    def test_export_needs_authentication(self, client):
        assert client.get("/users/me/export").status_code in (401, 403)
