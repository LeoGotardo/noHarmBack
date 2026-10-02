"""The audit types are stored integers: they must never change meaning."""
from core.auditTypes import AuditType


def test_values_are_pinned():
    # Changing any of these re-labels every row already written.
    assert {t.name: t.value for t in AuditType} == {
        "LOGIN_SUCCESS": 1, "LOGIN_FAILURE": 2, "PASSWORD_CHANGE": 3,
        "EMAIL_CHANGE": 4, "ACCOUNT_STATUS": 5, "TOKEN_REVOKED": 6,
        "STREAK_RESET": 7, "BADGE_GRANTED": 8, "ADMIN_ACTION": 9, "REPORT": 10,
        "EVIDENCE_READ": 11, "NOTICE": 12, "CONSENT_GIVEN": 13,
        "CONSENT_WITHDRAWN": 14, "DATA_EXPORT": 15, "BOARD_READ": 16,
        "CONTENT_REMOVED": 17, "CONTENT_RESTORED": 18, "ADMIN_GRANTED": 19,
        "ADMIN_REVOKED": 20, "USER_BLOCKED": 21, "USER_UNBLOCKED": 22,
    }


def test_no_value_is_used_twice():
    values = [t.value for t in AuditType]
    assert len(values) == len(set(values))
