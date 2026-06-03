import pytest
from exceptions.baseExceptions import NoHarmException
from exceptions.databaseExceptions import NoEngineException, NoSessionException, NoDatabaseParamterException


class TestNoHarmException:
    def test_defaults(self):
        exc = NoHarmException()
        assert exc.statusCode == 500
        assert exc.errorCode == "INTERNAL_ERROR"
        assert exc.message == "An internal server error occurred."
        assert exc.details is None

    def test_custom_fields(self):
        exc = NoHarmException(statusCode=404, errorCode="NOT_FOUND", message="Gone")
        assert exc.statusCode == 404
        assert exc.errorCode == "NOT_FOUND"
        assert exc.message == "Gone"

    def test_details(self):
        exc = NoHarmException(details={"field": "value"})
        assert exc.details == {"field": "value"}

    def test_toDict_without_details(self):
        exc = NoHarmException(statusCode=400, errorCode="BAD", message="Bad input")
        d = exc.toDict()
        assert d == {"errorCode": "BAD", "message": "Bad input"}
        assert "details" not in d

    def test_toDict_with_details(self):
        exc = NoHarmException(statusCode=422, errorCode="VALIDATION", message="Invalid", details=["field"])
        d = exc.toDict()
        assert d["details"] == ["field"]

    def test_is_exception(self):
        exc = NoHarmException()
        assert isinstance(exc, Exception)

    def test_statusCode_zero_uses_class_default(self):
        # statusCode=0 is falsy → falls back to class default 500
        exc = NoHarmException(statusCode=0)
        assert exc.statusCode == 500


class TestDatabaseExceptions:
    def test_no_engine_exception(self):
        exc = NoEngineException()
        assert exc.statusCode == 404
        assert exc.errorCode == "NOT_FOUND"
        assert "engine" in exc.message.lower()

    def test_no_session_exception(self):
        exc = NoSessionException()
        assert exc.statusCode == 404
        assert exc.errorCode == "NOT_FOUND"

    def test_no_database_param_exception(self):
        exc = NoDatabaseParamterException()
        assert exc.statusCode == 500
        assert exc.errorCode == "INTERNAL_ERROR"

    def test_all_are_noharm_subclasses(self):
        for cls in [NoEngineException, NoSessionException, NoDatabaseParamterException]:
            assert issubclass(cls, NoHarmException)
