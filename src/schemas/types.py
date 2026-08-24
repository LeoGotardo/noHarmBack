"""Shared Pydantic field types."""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import BeforeValidator

from core.config import config


def _validateEmail(value):
    """Validate an email, allowing RFC 2606 reserved domains in dev.

    Production keeps rejecting `.test` / `.example` / `.invalid`, but automated
    fixtures need them — the E2E suite had to fall back to `example.com` because
    `e2e@something.test` was a hard 422.
    """
    if not isinstance(value, str):
        raise ValueError("email must be a string")

    try:
        result = validate_email(
            value,
            check_deliverability=False,
            test_environment=config.IS_DEV,
        )
    except EmailNotValidError as e:
        raise ValueError(str(e))

    return result.normalized


Email = Annotated[str, BeforeValidator(_validateEmail)]
