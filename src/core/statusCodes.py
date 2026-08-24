"""Status-code coercion shared by the repositories.

`STATUS_CODES` maps a name to an integer (`{"disabled": 0, "enabled": 1, ...}`).
Path parameters arrive as strings, so indexing the map with the raw value blew up
with `KeyError: '0'`. This resolves either form — name or numeric code — into the
integer stored in the database, and rejects anything else with a 400 instead of a
500.
"""

from core.config import config
from exceptions.baseExceptions import NoHarmException


def resolveStatusCode(status) -> int:
    """Return the integer status code for a name ("enabled") or a code (1, "1")."""
    if isinstance(status, bool):
        raise _invalid(status)

    if isinstance(status, str):
        text = status.strip()
        if text in config.STATUS_CODES:
            return int(config.STATUS_CODES[text])
        try:
            status = int(text)
        except ValueError:
            raise _invalid(status)

    if isinstance(status, int) and status in set(config.STATUS_CODES.values()):
        return status

    raise _invalid(status)


def _invalid(status) -> NoHarmException:
    valid = ", ".join(f"{name}={code}" for name, code in config.STATUS_CODES.items())
    return NoHarmException(
        statusCode=400,
        errorCode="INVALID_STATUS",
        message=f"Unknown status {status!r}. Valid values: {valid}."
    )
