"""A limiter that fell back to memory is reported, not just logged."""
import asyncio
from unittest.mock import MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_nothing_happens_when_redis_was_reachable():
    import main
    with patch("security.limiter.degradedReason", None), \
         patch.object(main, "ErrorLogService") as svc, \
         patch.object(main.emitter, "notifyAdmins") as notify:
        _run(main._reportDegradedLimiter())
    svc.assert_not_called()
    notify.assert_not_called()


def test_degraded_limiter_is_recorded_and_alerted():
    import main
    with patch("security.limiter.degradedReason", ConnectionError("refused")), \
         patch.object(main, "ErrorLogService") as svc, \
         patch.object(main.emitter, "notifyAdmins") as notify:
        _run(main._reportDegradedLimiter())
    exc = svc.return_value.capture.call_args.args[0]
    assert "in-memory" in str(exc) and "refused" in str(exc)
    assert notify.call_args.args[0] == "rate_limiter_degraded"


def test_a_failing_record_still_alerts_and_never_raises():
    import main
    with patch("security.limiter.degradedReason", ConnectionError("refused")), \
         patch.object(main, "ErrorLogService", side_effect=RuntimeError("db down")), \
         patch.object(main.emitter, "notifyAdmins") as notify:
        _run(main._reportDegradedLimiter())
    notify.assert_called_once()
