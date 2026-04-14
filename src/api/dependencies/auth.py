from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist

security = HTTPBearer()
TokenBlacklist = TokenBlacklist()
jwtHandler = JwtHandler(TokenBlacklist)

def getCurrentUser(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Retorna o userId do token. Injete nas rotas que precisam de autenticação."""
    payload = jwtHandler.verifyToken(credentials.credentials, "access")

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    return payload["sub"]  # userId como string