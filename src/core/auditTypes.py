"""The audit log's event types (`tb_7.cl_7b`).

One place for the numbers, which used to be bare integers in eight services.
They are stored, so a value never changes meaning and is never reused — add a
new member at the end. 3, 4 and 9 were reserved for events the backend never
sees (password and e-mail changes happen in Firebase) and stay unused.
"""
from enum import IntEnum


class AuditType(IntEnum):
    LOGIN_SUCCESS = 1
    LOGIN_FAILURE = 2
    PASSWORD_CHANGE = 3      # reserved — Firebase owns passwords
    EMAIL_CHANGE = 4         # reserved — Firebase owns e-mail
    ACCOUNT_STATUS = 5       # bans, suspensions, sanctions, restores
    TOKEN_REVOKED = 6        # logout, logout on every device
    STREAK_RESET = 7
    BADGE_GRANTED = 8
    ADMIN_ACTION = 9         # reserved
    REPORT = 10              # filed, appended to, claimed, released, resolved
    EVIDENCE_READ = 11
    NOTICE = 12
    CONSENT_GIVEN = 13
    CONSENT_WITHDRAWN = 14
    DATA_EXPORT = 15
    BOARD_READ = 16
    CONTENT_REMOVED = 17
    CONTENT_RESTORED = 18
    ADMIN_GRANTED = 19
    ADMIN_REVOKED = 20
    USER_BLOCKED = 21
    USER_UNBLOCKED = 22
