from datetime import datetime
from security.persistentHashTable import PersistentHashTable
from security.encryption import Encryption
from core.config import config


class TokenBlacklist:
    """
    Blacklist de tokens JWT revogados.

    Tokens adicionados nunca são removidos manualmente — só saem
    quando expiram naturalmente, via cleanup.

    O JTI é armazenado como hash SHA-256 para não expor o valor
    original em disco.

    Uso:
        blacklist = TokenBlacklist()
        blacklist.add(jti, expiresAt)
        blacklist.isBlacklisted(jti)  # True/False
        blacklist.cleanup()           # remove expirados
    """

    _STORAGE_PATH = str(config.STORAGE_PATH + '/blacklist.jsonl')

    def __init__(self):
        self._storage = PersistentHashTable(self._STORAGE_PATH)
        self.cleanup()


    # ── Interface pública ──────────────────────────────────────────────────────

    def add(self, jti: str, expiresAt: datetime) -> None:
        """
        Revoga um token adicionando seu JTI à blacklist.

        Args:
            jti:       ID único do token (claim 'jti' do JWT)
            expiresAt: momento em que o token expira naturalmente
        """
        hashedJti = self._hash(jti)
        self._storage.set(hashedJti, expiresAt.isoformat())


    def isBlacklisted(self, jti: str) -> bool:
        """
        Verifica se um token está revogado.

        Args:
            jti: ID único do token (claim 'jti' do JWT)

        Returns:
            True se o token está na blacklist, False caso contrário
        """
        hashedJti = self._hash(jti)
        return self._storage.exists(hashedJti)


    def cleanup(self) -> None:
        """
        Remove da memória e do arquivo todos os tokens já expirados.
        Chamado automaticamente na inicialização e pode ser chamado
        periodicamente para manter o arquivo compacto.
        """
        now = datetime.utcnow()

        self._storage.cleanup(
            isExpired=lambda exp: datetime.fromisoformat(exp) < now
        )


    # ── Interno ───────────────────────────────────────────────────────────────

    def _hash(self, jti: str) -> str:
        """
        Retorna o hash SHA-256 do JTI.
        Nunca armazenamos o JTI em plaintext em disco.
        """
        return Encryption.hash(jti)