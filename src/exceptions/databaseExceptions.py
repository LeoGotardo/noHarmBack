from exceptions.baseExceptions import NoHarmException
from typing import Optional, Any

class NoEngineException(NoHarmException):
    statusCode = 404
    errorCode = "NOT_FOUND"
    defaultMessage = "Database engine not found."
        

class NoSessionException(NoHarmException):
    statusCode = 404
    errorCode = "NOT_FOUND"
    defaultMessage = "Database session not found."
        

class NoDatabaseParamterException(NoHarmException):
    statusCode = 500
    errorCode = "INTERNAL_ERROR"
    defaultMessage = f"Missing database connection parameter."
    
    
    def __init__(self, message: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(message, details=details)