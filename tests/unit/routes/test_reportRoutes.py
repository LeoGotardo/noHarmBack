"""Route-level tests for /reports.

Wiring and authorisation only: the service is patched out, so nothing here
touches a database. The admin routes are the point — `getAdminUser` answers 404
for a non-admin, and these assert the queue and the resolve endpoint sit behind
it.
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

from exceptions.baseExceptions import NoHarmException


_USER_ID = "uid-reporter"


def _make_report_dict(reporter=_USER_ID, status=4):
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "reporter": reporter,
        "reported": "uid-reported",
        "reason": "harassment",
        "details": "They keep messaging me.",
        "status": status,
        "created_at": now,
        "updated_at": now,
    }


def _build_app(admin: bool = True):
    from api.routes.reportRoutes import router
    from api.dependencies.database import getDb, getDbWithRLS
    from api.dependencies.auth import getCurrentUser, getAdminUser
    from fastapi import HTTPException

    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
    app.dependency_overrides[getDbWithRLS] = lambda: MagicMock()
    app.dependency_overrides[getDb] = lambda: MagicMock()
    app.dependency_overrides[getCurrentUser] = lambda: _USER_ID

    def _admin():
        if not admin:
            # What the real dependency does for a caller outside ADMIN_USER_IDS.
            raise HTTPException(status_code=404, detail="Not found.")
        return "uid-admin"

    app.dependency_overrides[getAdminUser] = _admin

    # `POST /reports/{userId}` lets NoHarmException reach the app's handler
    # rather than flattening it into an HTTPException: its refusals carry
    # distinct error codes, and REPORT_RECENTLY_DISMISSED carries the date it
    # lifts in `details`. This mirrors the handler main.py registers; without
    # it the fixture answers 500 to every domain error and the assertions below
    # would be testing the gap rather than the route.
    @app.exception_handler(NoHarmException)
    def _noHarmHandler(request, exc: NoHarmException):
        return JSONResponse(status_code=exc.statusCode, content=exc.toDict())
    return app


@pytest.fixture
def client():
    return TestClient(_build_app(), raise_server_exceptions=False)


@pytest.fixture
def nonAdminClient():
    return TestClient(_build_app(admin=False), raise_server_exceptions=False)


class TestReportUserRoute:
    def test_success_returns_201(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.return_value = _make_report_dict()
            res = client.post("/reports/uid-reported", json={"reason": "harassment"})
        assert res.status_code == 201

    def test_details_are_forwarded_to_the_service(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.return_value = _make_report_dict()
            client.post(
                "/reports/uid-reported",
                json={"reason": "spam", "details": "unsolicited links"},
            )
        MockService.return_value.report.assert_called_once_with(
            _USER_ID, "uid-reported", "spam", "unsolicited links", None
        )

    def test_chat_id_is_forwarded_as_an_id_and_nothing_else(self, client):
        """The body names a conversation; the server is what reads it.

        A field carrying the quoted text would let a reporter attribute words
        to someone, so `extra="forbid"` refuses one and only the id travels.
        """
        chatId = "2e8f9c2a-0c1e-4a1f-9f7a-5c9d1b2e3f40"
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.return_value = _make_report_dict()
            res = client.post(
                "/reports/uid-reported",
                json={"reason": "harassment", "chatId": chatId},
            )
        assert res.status_code == 201
        args = MockService.return_value.report.call_args[0]
        assert str(args[4]) == chatId

    def test_message_text_in_the_body_is_refused(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = client.post(
                "/reports/uid-reported",
                json={"reason": "harassment", "messages": ["a line I made up"]},
            )
        assert res.status_code == 422
        MockService.return_value.report.assert_not_called()

    def test_unknown_reason_is_rejected_before_the_service(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = client.post("/reports/uid-reported", json={"reason": "because"})
        assert res.status_code == 422
        MockService.return_value.report.assert_not_called()

    def test_details_over_the_limit_are_rejected(self, client):
        with patch("api.routes.reportRoutes.ReportService"):
            res = client.post(
                "/reports/uid-reported",
                json={"reason": "other", "details": "x" * 1001},
            )
        assert res.status_code == 422

    def test_reporting_yourself_returns_400(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.side_effect = NoHarmException(
                statusCode=400, errorCode="SELF_REPORT", message="You cannot report yourself."
            )
            res = client.post("/reports/" + _USER_ID, json={"reason": "spam"})
        assert res.status_code == 400

    def test_duplicate_open_report_returns_409(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.side_effect = NoHarmException(
                statusCode=409, errorCode="REPORT_ALREADY_OPEN", message="You already reported this user."
            )
            res = client.post("/reports/uid-reported", json={"reason": "spam"})
        assert res.status_code == 409

    def test_a_refusal_keeps_its_error_code_and_details(self, client):
        """Four refusals share a status code and mean different things to the app."""
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.report.side_effect = NoHarmException(
                statusCode=409,
                errorCode="REPORT_RECENTLY_DISMISSED",
                message="Our team reviewed your last report about this user.",
                details={"canReportAgainAt": "2026-10-14T00:00:00Z"},
            )
            res = client.post("/reports/uid-reported", json={"reason": "spam"})

        assert res.status_code == 409
        body = res.json()
        assert body["errorCode"] == "REPORT_RECENTLY_DISMISSED"
        assert body["details"]["canReportAgainAt"] == "2026-10-14T00:00:00Z"


class TestMyReportsRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getMine.return_value = []
            res = client.get("/reports/mine")
        assert res.status_code == 200
        assert "reports" in res.json()

    def test_reads_only_the_callers_own_reports(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getMine.return_value = []
            client.get("/reports/mine")
        MockService.return_value.getMine.assert_called_once_with(_USER_ID)


class TestModerationQueueRoute:
    def test_admin_gets_the_queue(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getAll.return_value = []
            res = client.get("/reports")
        assert res.status_code == 200

    def test_status_filter_is_forwarded(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getAll.return_value = []
            client.get("/reports?status=4")
        MockService.return_value.getAll.assert_called_once_with(4, None, "newest")

    def test_priority_sort_is_forwarded(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getAll.return_value = []
            client.get("/reports?sort=priority")
        MockService.return_value.getAll.assert_called_once_with(None, None, "priority")

    def test_an_unknown_sort_is_refused(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = client.get("/reports?sort=whatever")
        assert res.status_code == 422
        MockService.return_value.getAll.assert_not_called()

    def test_non_admin_gets_404(self, nonAdminClient):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = nonAdminClient.get("/reports")
        assert res.status_code == 404
        MockService.return_value.getAll.assert_not_called()


class TestResolveReportRoute:
    def test_admin_can_resolve(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.resolve.return_value = _make_report_dict(status=5)
            res = client.put("/reports/report-001/resolve/accepted")
        assert res.status_code == 200
        MockService.return_value.resolve.assert_called_once_with("report-001", "accepted", "uid-admin")

    def test_non_admin_gets_404(self, nonAdminClient):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = nonAdminClient.put("/reports/report-001/resolve/accepted")
        assert res.status_code == 404
        MockService.return_value.resolve.assert_not_called()


def _make_evidence_dict(kind="message", content="you should give up"):
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "report": uuid4(),
        "kind": kind,
        "source_id": "msg-1",
        "author_id": "uid-reported",
        "content": content,
        "content_hash": "a" * 64,
        "occurred_at": now,
        "created_at": now,
    }


class TestReportEvidenceRoute:
    def test_admin_reads_the_evidence(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getEvidence.return_value = [_make_evidence_dict()]
            res = client.get("/reports/report-001/evidence")
        assert res.status_code == 200
        assert res.json()["total"] == 1
        # The caller's own id is what the audit entry is written against.
        MockService.return_value.getEvidence.assert_called_once_with("report-001", "uid-admin")

    def test_non_admin_gets_404(self, nonAdminClient):
        """Including the reporter: filing a report is not a licence to re-read
        the captured conversation through the moderation surface."""
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            res = nonAdminClient.get("/reports/report-001/evidence")
        assert res.status_code == 404
        MockService.return_value.getEvidence.assert_not_called()

    def test_unknown_report_returns_404(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.getEvidence.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="Report not found"
            )
            res = client.get("/reports/nope/evidence")
        assert res.status_code == 404


class TestReviewLockRoutes:
    def test_admin_claims_a_report(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.claim.return_value = _make_report_dict()
            res = client.post("/reports/report-001/claim")
        assert res.status_code == 200
        MockService.return_value.claim.assert_called_once_with("report-001", "uid-admin")

    def test_a_held_report_answers_409(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.claim.side_effect = NoHarmException(
                statusCode=409, errorCode="REPORT_LOCKED",
                message="Another moderator is reviewing this report."
            )
            res = client.post("/reports/report-001/claim")
        assert res.status_code == 409

    def test_admin_releases_a_report(self, client):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            MockService.return_value.release.return_value = _make_report_dict()
            res = client.delete("/reports/report-001/claim")
        assert res.status_code == 200
        MockService.return_value.release.assert_called_once_with("report-001", "uid-admin")

    def test_non_admin_can_do_neither(self, nonAdminClient):
        with patch("api.routes.reportRoutes.ReportService") as MockService:
            assert nonAdminClient.post("/reports/report-001/claim").status_code == 404
            assert nonAdminClient.delete("/reports/report-001/claim").status_code == 404
        MockService.return_value.claim.assert_not_called()
        MockService.return_value.release.assert_not_called()

    def test_the_reporters_own_list_never_names_a_moderator(self, client):
        """`GET /reports/mine` uses the plain response shape: telling a reporter
        who is reading their report names a person to complain about."""
        from types import SimpleNamespace

        with patch("api.routes.reportRoutes.ReportService") as MockService:
            # An entity, the way the service really answers — it carries the
            # lock, and the response shape is what decides who sees it.
            report = SimpleNamespace(**_make_report_dict(), locked_by="uid-admin", locked_at=None)
            MockService.return_value.getMine.return_value = [report]
            res = client.get("/reports/mine")

        assert res.status_code == 200
        assert "locked_by" not in res.json()["reports"][0]
