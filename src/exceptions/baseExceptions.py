from typing import Optional, Any

class NoHarmException(Exception):
    """
    Classe base de todas as exceções do projeto NoHarm.

    O objetivo dela não é apenas ser "pai" das outras exceções —
    ela define um CONTRATO: toda exceção do projeto vai ter
    statusCode, message, errorCode e details.

    Isso garante que o exception handler global no main.py
    possa tratar QUALQUER exceção do projeto de forma uniforme,
    sem precisar conhecer cada subclasse individualmente.
    """

    # Valores padrão da classe base — representam o caso mais genérico possível.
    # As subclasses vão sobrescrever esses valores para serem mais específicas.
    statusCode: int = 500
    errorCode: str = "INTERNAL_ERROR"
    defaultMessage: str = "Ocorreu um erro interno no servidor."

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
        """
        Serializa a exceção para um dicionário pronto para
        ser retornado como JSON na resposta HTTP.

        O exception handler global no main.py vai chamar este método,
        garantindo que todas as respostas de erro do projeto
        tenham exatamente o mesmo formato — o que é muito importante
        para o frontend saber como tratar os erros.
        """
        response = {
            "errorCode": self.errorCode,
            "message": self.message,
        }

        if self.details is not None:
            response["details"] = self.details

        return response