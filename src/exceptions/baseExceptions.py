from typing import Optional, Any

class NoHarmException(Exception):
    """
    Base exception for all NoHarm project errors.

    Defines a contract: every exception carries statusCode, message,
    errorCode, and details so the global handler in main.py can process
    any exception uniformly without knowing each subclass.
    """

    # Class-level defaults — subclasses override these for specificity.
    statusCode: int = 500
    errorCode: str = "INTERNAL_ERROR"
    defaultMessage: str = "An internal server error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        statusCode: Optional[int] = None,
        errorCode: Optional[str] = None,
        details: Optional[Any] = None
    ):
        self.message = message or self.defaultMessage

        self.statusCode = statusCode or self.__class__.statusCode
        self.errorCode = errorCode or self.__class__.errorCode

        self.details = details

        super().__init__(self.message)

    def toDict(self) -> dict:
        """Serialize to a dict ready for a JSON HTTP response."""
        response = {
            "errorCode": self.errorCode,
            "message": self.message,
        }

        if self.details is not None:
            response["details"] = self.details

        return response