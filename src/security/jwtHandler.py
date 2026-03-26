import secrets
import os

from datetime import datetime, timedelta
from typing import Optional

import jwt

from security.tokenBlacklist import TokenBlacklist
from core.config import config

class JwtHandler:
    """
    Geração e validação de tokens JWT.

    Emite dois tipos de token:
        - access:  vida curta (15 min), usado em cada requisição
        - refresh: vida longa (7 dias), usado para emitir novos access tokens

    Cada token carrega um JTI único que permite revogação individual
    via blacklist, sem invalidar todos os tokens do usuário.

    Uso:
        handler = JwtHandler()

        accessToken  = handler.createAccessToken(userId)
        refreshToken = handler.createRefreshToken(userId)

        payload = handler.verifyToken(accessToken, "access")
        payload = handler.verifyToken(refreshToken, "refresh")

        handler.revokeToken(payload["jti"], payload["exp"])
    """

    _ACCESS_TYPE  = "access"
    _REFRESH_TYPE = "refresh"
    _ALGORITHM    = config.JWT_ALGORITHM

    _ACCESS_EXPIRE_MINUTES  = config.ACCESS_TOKEN_EXPIRE_MINUTES
    _REFRESH_EXPIRE_DAYS    = config.REFRESH_TOKEN_EXPIRE_DAYS

    _REQUIRED_CLAIMS = ["sub", "type", "exp", "iat", "jti"]


    def __init__(self, blacklist: TokenBlacklist):
        self._blacklist       = blacklist
        self._accessKey    = config.JWT_ACCESS_KEY
        self._refreshKey   = config.JWT_REFRESH_KEY


    # ── Geração ───────────────────────────────────────────────────────────────

    def createAccessToken(self, userId: str) -> str:
        """
        Gera um access token de vida curta (15 minutos).

        Args:
            userId: ID do usuário dono do token

        Returns:
            Token JWT assinado em formato string
        """
        expiresAt = datetime.utcnow() + timedelta(minutes=self._ACCESS_EXPIRE_MINUTES)

        return self._buildToken(
            userId    = userId,
            tokenType = self._ACCESS_TYPE,
            expiresAt = expiresAt,
            secret    = self._accessKey
        )


    def createRefreshToken(self, userId: str) -> str:
        """
        Gera um refresh token de vida longa (7 dias).

        Args:
            userId: ID do usuário dono do token

        Returns:
            Token JWT assinado em formato string
        """
        expiresAt = datetime.utcnow() + timedelta(days=self._REFRESH_EXPIRE_DAYS)

        return self._buildToken(
            userId    = userId,
            tokenType = self._REFRESH_TYPE,
            expiresAt = expiresAt,
            secret    = self._refreshKey
        )


    # ── Validação ─────────────────────────────────────────────────────────────

    def verifyToken(self, token: str, tokenType: str) -> Optional[dict]:
        """
        Valida um token JWT e retorna o payload se válido.

        Verificações realizadas em ordem:
            1. Assinatura e expiração (PyJWT)
            2. Claims obrigatórios presentes
            3. Tipo do token corresponde ao esperado
            4. Token não está na blacklist

        Args:
            token:     token JWT em formato string
            tokenType: tipo esperado — "access" ou "refresh"

        Returns:
            Payload do token se válido, None caso contrário
        """
        secret = self._secretForType(tokenType)

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms = [self._ALGORITHM],
                options    = {
                    "verify_exp": True,
                    "verify_iat": True,
                    "require":    self._REQUIRED_CLAIMS
                }
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        if not self._hasValidType(payload, tokenType):
            return None

        if self._blacklist.isBlacklisted(payload["jti"]):
            return None

        return payload


    # ── Revogação ─────────────────────────────────────────────────────────────

    def revokeToken(self, jti: str, exp: int) -> None:
        """
        Revoga um token adicionando seu JTI à blacklist.

        Deve ser chamado no logout (access + refresh)
        e na rotação de refresh tokens (refresh antigo).

        Args:
            jti: claim 'jti' do payload do token
            exp: claim 'exp' do payload (timestamp Unix)
        """
        expiresAt = datetime.utcfromtimestamp(exp)
        self._blacklist.add(jti, expiresAt)


    # ── Interno ───────────────────────────────────────────────────────────────

    def _buildToken(
        self,
        userId:    str,
        tokenType: str,
        expiresAt: datetime,
        secret:    str
    ) -> str:
        payload = {
            "sub":  userId,
            "type": tokenType,
            "exp":  expiresAt,
            "iat":  datetime.utcnow(),
            "jti":  secrets.token_urlsafe(16)
        }

        return jwt.encode(payload, secret, algorithm=self._ALGORITHM)


    def _secretForType(self, tokenType: str) -> str:
        if tokenType == self._ACCESS_TYPE:
            return self._accessKey

        if tokenType == self._REFRESH_TYPE:
            return self._refreshKey

        raise ValueError(f"Tipo de token inválido: {tokenType}")


    def _hasValidType(self, payload: dict, expectedType: str) -> bool:
        return payload.get("type") == expectedType


    def _loadSecret(self, envKey: str) -> str:
        secret = os.getenv(envKey)

        if not secret:
            raise EnvironmentError(
                f"Variável de ambiente obrigatória não encontrada: {envKey}"
            )

        return secret