from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from security.jwtHandler import jwtHandler

security = HTTPBearer()

def getCurrentUser(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Retorna o userId do token. Injete nas rotas que precisam de autenticação."""
    payload = jwtHandler.verifyAccessToken(credentials.credentials)

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    return payload["sub"]  # userId como string