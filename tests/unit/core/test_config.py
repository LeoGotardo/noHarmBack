"""Config refuses combinations that would quietly change what production does."""
import pytest

from core.config import Config


@pytest.mark.parametrize("mode", ["prod", "production", "staging", "test"])
def test_debug_outside_dev_refuses_to_start(monkeypatch, mode):
    # Starlette serves a traceback page before any handler when debug is on.
    monkeypatch.setenv("EXEC_MODE", mode)
    monkeypatch.setenv("DEBUG", "true")
    with pytest.raises(Exception, match="DEBUG=true is only allowed"):
        Config()


@pytest.mark.parametrize("mode", ["dev", "development"])
def test_debug_in_dev_is_fine(monkeypatch, mode):
    monkeypatch.setenv("EXEC_MODE", mode)
    monkeypatch.setenv("DEBUG", "true")
    assert Config().DEBUG is True


def test_no_debug_anywhere_is_fine(monkeypatch):
    monkeypatch.setenv("EXEC_MODE", "prod")
    monkeypatch.setenv("DEBUG", "false")
    assert Config().DEBUG is False
