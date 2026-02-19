# 📋 README - Contexto Completo: Backend NoHarm

## 📌 Visão Geral do Projeto

**NoHarm** é um aplicativo mobile (React Native/Expo) de apoio à recuperação de vícios, focado em:
- Contador de dias limpos (streak)
- Sistema de amigos e suporte mútuo
- Chat em tempo real
- Recursos de emergência (CVV, CAPS, etc)
- Sistema de badges/conquistas

**Stack Tecnológica:**
- **Frontend:** React Native, Expo, Tailwind CSS
- **Backend:** Python, FastAPI, WebSocket (Socket.IO)
- **Banco:** PostgreSQL (principal), possível MongoDB
- **Autenticação:** JWT (Access + Refresh Tokens)
- **Real-time:** WebSockets para chat

---

## 🎯 Tópicos Discutidos Nesta Conversa

### 1. **Segurança do Backend**
Discussão completa sobre proteção contra ataques com código Python implementável.

### 2. **Arquitetura de Software**
Comparação entre estruturas e recomendação de Clean Architecture.

### 3. **Organização de Código**
Debate sobre separar Models de Repositories vs juntos.

---

## 🛡️ 1. SEGURANÇA - Resumo

### Documento Criado
**Arquivo:** `GUIA_SEGURANCA_BACKEND.md` (89KB)

### Ataques Cobertos

#### **1.1 Ataques de Autenticação**

**JWT Token Theft (Roubo de Token)**
- **Problema:** Atacante rouba token JWT e se passa pelo usuário
- **Solução:** 
  - Access token curto (15 minutos)
  - Refresh token longo (7 dias)
  - JTI único para cada token
  - Blacklist de tokens revogados (Redis)
  - Rotação de refresh tokens
- **Arquivo:** `security/jwtHandler.py`

**Brute Force Attack**
- **Problema:** Atacante tenta milhares de senhas
- **Solução:**
  - Rate limiting por IP e usuário
  - Lockout progressivo (5 tentativas = 30min bloqueio)
  - CAPTCHA após 3 tentativas
  - Tempo constante de resposta (anti timing attack)
- **Arquivo:** `security/rateLimiter.py`

#### **1.2 Ataques de Injeção**

**SQL Injection**
- **Problema:** Atacante injeta código SQL malicioso
- **Solução:**
  - Usar ORM (SQLAlchemy) sempre
  - Parametrização automática
  - Validação de entrada com Pydantic
  - Whitelist de caracteres permitidos
- **Arquivo:** `database/userRepository.py`

**NoSQL Injection (MongoDB)**
- **Problema:** Operadores MongoDB ($ne, $gt) em inputs
- **Solução:**
  - Validar que entrada é STRING (não objeto)
  - Remover $ e . de inputs
  - Validação de tipos rigorosa
- **Arquivo:** `database/mongoRepository.py`

**XSS (Cross-Site Scripting)**
- **Problema:** JavaScript malicioso executado no navegador
- **Solução:**
  - Sanitização HTML (Bleach)
  - Remover tags perigosas
  - Content Security Policy (CSP)
  - Validação client + server
- **Arquivo:** `security/sanitizer.py`

#### **1.3 Ataques de Sessão**

**CSRF (Cross-Site Request Forgery)**
- **Problema:** Site malicioso faz requisições em nome do usuário
- **Solução:**
  - CSRF tokens únicos
  - SameSite cookies (Strict)
  - Validação de origem
  - Double submit cookie pattern
- **Arquivo:** `security/csrfProtection.py`

**Session Fixation**
- **Problema:** Atacante força vítima a usar session ID conhecido
- **Solução:**
  - Regenerar session ID após login
  - Validar IP e User-Agent
  - Session timeout
- **Arquivo:** `security/sessionManager.py`

#### **1.4 Ataques DoS (Denial of Service)**

**Application Layer DoS**
- **Problema:** Milhares de requisições legítimas mas excessivas
- **Solução:**
  - Rate limiting multicamadas (IP + usuário + endpoint)
  - Sliding window algorithm
  - Burst protection (10 req/seg)
  - IP blacklist temporária
  - Limites diferentes por endpoint
- **Arquivo:** `security/advancedRateLimiter.py`

**Slowloris Attack**
- **Problema:** Atacante mantém conexões abertas lentamente
- **Solução:**
  - Timeouts curtos (5-10s)
  - Limite de conexões simultâneas
  - Nginx como proxy reverso
  - Header size limits
- **Configuração:** `main.py` + `nginx.conf`

#### **1.5 Ataques de Dados**

**Data Exposure (Vazamento)**
- **Problema:** Dados sensíveis expostos em APIs/logs
- **Solução:**
  - DTOs separados (Public vs Private)
  - response_model no FastAPI
  - Sanitização de logs
  - Nunca retornar password_hash
- **Arquivo:** `models/userModel.py`

**Mass Assignment**
- **Problema:** Atacante envia campos que não deveria modificar
- **Solução:**
  - Whitelist explícita de campos (Pydantic)
  - Campos sensíveis em endpoints separados
  - Auditoria de mudanças
  - Requer senha para mudanças críticas
- **Arquivo:** `routes/userRoutes.py`

#### **1.6 Ataques WebSocket**

**WebSocket Hijacking**
- **Problema:** Atacante intercepta/injeta mensagens
- **Solução:**
  - Autenticação JWT obrigatória
  - Rate limiting de mensagens (20/min)
  - Validação rigorosa de payloads
  - Limite de conexões (5 por usuário)
  - CORS restrito
  - Max payload size (100KB)
- **Arquivo:** `websocket/socketManager.py`

### Arquivos de Segurança Criados

```python
security/
├── jwtHandler.py           # JWT generation/validation
├── rateLimiter.py          # Basic rate limiting
├── advancedRateLimiter.py  # Multi-layer rate limiting
├── sanitizer.py            # HTML/input sanitization
├── encryption.py           # Data encryption
├── csrfProtection.py       # CSRF tokens
├── sessionManager.py       # Session handling
└── middleware.py           # Security middlewares
```

### Configurações Importantes

```python
# .env
JWT_SECRET_KEY=secrets.token_urlsafe(32)
JWT_REFRESH_SECRET_KEY=secrets.token_urlsafe(32)
ENCRYPTION_MASTER_KEY=secrets.token_urlsafe(32)
ENCRYPTION_SALT=secrets.token_urlsafe(16)

ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

MAX_REQUESTS_PER_MINUTE=60
MAX_WEBSOCKET_CONNECTIONS=5
BCRYPT_ROUNDS=12
```

### Checklist de Implementação

- [ ] Implementar JwtHandler com blacklist (Redis)
- [ ] Configurar rate limiting em todas rotas
- [ ] Adicionar sanitização em todos inputs
- [ ] Configurar CSRF tokens
- [ ] Implementar session management
- [ ] Configurar WebSocket authentication
- [ ] Adicionar security headers middleware
- [ ] Configurar CORS corretamente
- [ ] Implementar audit logging
- [ ] Configurar Nginx com SSL

---

## 🏗️ 2. ARQUITETURA - Resumo

### Estrutura Atual (Problemática)

```
src/
├── controller/     # Rotas + Lógica + DB = TUDO JUNTO ❌
├── model/          # SQLAlchemy models
└── utils/          # Utilidades
```

**Problemas:**
- Controller faz tudo (violação SRP)
- Sem camada de Service (lógica de negócio)
- Sem camada de Repository (acesso a dados)
- Difícil de testar
- Código duplicado

### Estrutura Recomendada (Clean Architecture)

```
noHarmBack/
├── src/
│   ├── api/                        # Camada de Apresentação
│   │   ├── routes/                 # Endpoints HTTP
│   │   │   ├── authRoutes.py
│   │   │   ├── userRoutes.py
│   │   │   ├── streakRoutes.py
│   │   │   ├── chatRoutes.py
│   │   │   └── badgeRoutes.py
│   │   │
│   │   └── dependencies/           # FastAPI dependencies
│   │       ├── auth.py
│   │       └── database.py
│   │
│   ├── core/                       # Configurações centrais
│   │   ├── config.py
│   │   ├── security.py
│   │   └── database.py
│   │
│   ├── domain/                     # Lógica de Negócio
│   │   ├── entities/               # Entidades de domínio
│   │   │   ├── user.py
│   │   │   ├── streak.py
│   │   │   ├── chat.py
│   │   │   └── badge.py
│   │   │
│   │   └── services/               # Regras de negócio
│   │       ├── userService.py
│   │       ├── streakService.py
│   │       ├── chatService.py
│   │       └── badgeService.py
│   │
│   ├── infrastructure/             # Infraestrutura
│   │   ├── database/
│   │   │   ├── models/             # SQLAlchemy Models
│   │   │   │   ├── userModel.py
│   │   │   │   ├── streakModel.py
│   │   │   │   ├── chatModel.py
│   │   │   │   └── badgeModel.py
│   │   │   │
│   │   │   └── repositories/       # Acesso a dados
│   │   │       ├── userRepository.py
│   │   │       ├── streakRepository.py
│   │   │       ├── chatRepository.py
│   │   │       └── badgeRepository.py
│   │   │
│   │   └── external/               # Serviços externos
│   │       ├── emailService.py
│   │       └── storageService.py
│   │
│   ├── schemas/                    # Pydantic DTOs
│   │   ├── userSchemas.py
│   │   ├── streakSchemas.py
│   │   ├── chatSchemas.py
│   │   └── badgeSchemas.py
│   │
│   ├── security/                   # Segurança
│   │   ├── jwtHandler.py
│   │   ├── rateLimiter.py
│   │   ├── sanitizer.py
│   │   └── encryption.py
│   │
│   ├── websocket/                  # WebSocket
│   │   ├── socketManager.py
│   │   └── handlers/
│   │       ├── chatHandlers.py
│   │       └── presenceHandlers.py
│   │
│   └── main.py                     # Entry point
│
├── tests/                          # Testes
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── alembic/                        # Migrations
├── .env.example
├── requirements.txt
└── README.md
```

### Separação de Responsabilidades

#### **1. Model (SQLAlchemy)**
```python
# infrastructure/database/models/userModel.py
class UserModel(Base):
    """
    APENAS define estrutura da tabela
    """
    __tablename__ = 'users'
    
    id = Column(String(50), primary_key=True)
    username = Column(String(100), unique=True)
    email = Column(String(200), unique=True)
    passwordHash = Column(String(200))
    createdAt = Column(DateTime)
```

#### **2. Repository (Data Access)**
```python
# infrastructure/database/repositories/userRepository.py
class UserRepository:
    """
    APENAS queries ao banco
    SEM lógica de negócio
    """
    def findById(self, userId: str) -> Optional[UserModel]:
        return self.db.query(UserModel).filter(UserModel.id == userId).first()
    
    def findByEmail(self, email: str) -> Optional[UserModel]:
        return self.db.query(UserModel).filter(UserModel.email == email).first()
    
    def create(self, user: UserModel) -> UserModel:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
```

#### **3. Service (Business Logic)**
```python
# domain/services/userService.py
class UserService:
    """
    TODA a lógica de negócio
    Orquestra repositories
    """
    def registerUser(self, request: UserRegisterRequest) -> UserResponse:
        # REGRA: verificar se email existe
        existing = self.userRepo.findByEmail(request.email)
        if existing:
            raise ValueError("Email já cadastrado")
        
        # REGRA: hash de senha com bcrypt
        passwordHash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt(12))
        
        # REGRA: criar usuário
        user = UserModel(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            passwordHash=passwordHash.decode(),
            createdAt=datetime.utcnow()
        )
        
        return self.userRepo.create(user)
```

#### **4. Schema (Validation)**
```python
# schemas/userSchemas.py
class UserRegisterRequest(BaseModel):
    """
    Validação de entrada
    """
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=8)
    
    @validator('username')
    def validateUsername(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username inválido')
        return v

class UserResponse(BaseModel):
    """
    Resposta (SEM dados sensíveis)
    """
    id: str
    username: str
    email: EmailStr
    createdAt: datetime
    
    # NÃO inclui: passwordHash
    
    class Config:
        orm_mode = True
```

#### **5. Route (HTTP Handler)**
```python
# api/routes/userRoutes.py
@router.post("/register", response_model=UserResponse)
async def register(
    request: UserRegisterRequest,
    service: UserService = Depends(getUserService)
):
    """
    APENAS trata HTTP
    Delega tudo ao service
    """
    try:
        return service.registerUser(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### Fluxo de uma Requisição

```
CLIENT (JSON)
    ↓
ROUTE (userRoutes.py)
    - Valida com Pydantic Schema
    - Extrai userId do JWT (Dependency)
    ↓
SERVICE (userService.py)
    - Aplica REGRAS DE NEGÓCIO
    - Orquestra múltiplos repositories
    - Valida regras de domínio
    ↓
REPOSITORY (userRepository.py)
    - Executa QUERIES
    - Retorna dados brutos
    ↓
MODEL (userModel.py)
    - ORM mapeia tabela → objeto Python
    ↓
DATABASE (PostgreSQL)
```

### Benefícios da Arquitetura

| Aspecto | Antes | Depois |
|---------|-------|--------|
| **Testabilidade** | Precisa banco real | Mock repositories |
| **Manutenção** | Código espalhado | Responsabilidades claras |
| **Reutilização** | Lógica duplicada | Services reutilizáveis |
| **Segurança** | Validação espalhada | Centralizada em schemas |
| **Performance** | Queries N+1 | Otimização no repository |

---

## 📊 3. MODEL vs REPOSITORY - Decisão

### Questão Levantada
"Devo colocar o Model e Repository no mesmo arquivo ou separar?"

### ✅ RECOMENDAÇÃO: SEPARAR

#### **Estrutura Separada (RECOMENDADO)**

```python
# infrastructure/database/models/streakModel.py
class StreakModel(Base):
    """APENAS estrutura da tabela"""
    __tablename__ = 'streaks'
    id = Column(String(50), primary_key=True)
    userId = Column(String(50), ForeignKey('users.id'))
    currentDays = Column(Integer, default=0)

# infrastructure/database/repositories/streakRepository.py
class StreakRepository:
    """APENAS queries"""
    def findByUserId(self, userId: str) -> Optional[StreakModel]:
        return self.db.query(StreakModel).filter(...).first()
```

**Vantagens:**
- ✅ Separação de responsabilidades (SRP)
- ✅ Model só define estrutura (DDL)
- ✅ Repository só faz queries (DML)
- ✅ Fácil de testar (mock repository)
- ✅ Fácil trocar ORM (só muda repository)
- ✅ Segue SOLID principles

#### **Estrutura Junta (NÃO RECOMENDADO)**

```python
# database/streakModelAndRepo.py ❌
class StreakModel(Base):
    __tablename__ = 'streaks'
    
    @staticmethod
    def findByUserId(db: Session, userId: str):  # ❌ Métodos no Model
        return db.query(StreakModel).filter(...).first()
```

**Problemas:**
- ❌ Viola Single Responsibility Principle
- ❌ Model faz duas coisas
- ❌ Dificulta testes
- ❌ Acopla ORM ao domínio

---

## 🔄 4. PLANO DE MIGRAÇÃO

### Passo 1: Criar Nova Estrutura

```bash
cd noHarmBack/src

# Criar pastas
mkdir -p api/{routes,dependencies}
mkdir -p core
mkdir -p domain/{entities,services}
mkdir -p infrastructure/database/{models,repositories}
mkdir -p infrastructure/external
mkdir -p schemas
mkdir -p security
mkdir -p websocket/handlers
```

### Passo 2: Mover Arquivos Existentes

```bash
# Models
mv model/userModel.py infrastructure/database/models/
mv model/streakModel.py infrastructure/database/models/
mv model/chatModel.py infrastructure/database/models/
mv model/badgeModel.py infrastructure/database/models/
mv model/logsModel.py infrastructure/database/models/

# Controllers → Routes
mv controller/userController.py api/routes/userRoutes.py
mv controller/streakController.py api/routes/streakRoutes.py
mv controller/chatController.py api/routes/chatRoutes.py
mv controller/bedgecontroller.py api/routes/badgeRoutes.py
mv controller/connectionController.py api/routes/authRoutes.py

# Utils
mv utils/config.py core/
mv utils/enc.py security/encryption.py
mv utils/validators.py security/sanitizer.py
```

### Passo 3: Criar Novos Arquivos

```bash
# Repositories (CRIAR NOVO)
touch infrastructure/database/repositories/userRepository.py
touch infrastructure/database/repositories/streakRepository.py
touch infrastructure/database/repositories/chatRepository.py
touch infrastructure/database/repositories/badgeRepository.py

# Services (CRIAR NOVO)
touch domain/services/userService.py
touch domain/services/streakService.py
touch domain/services/chatService.py
touch domain/services/badgeService.py

# Schemas (CRIAR NOVO)
touch schemas/userSchemas.py
touch schemas/streakSchemas.py
touch schemas/chatSchemas.py
touch schemas/badgeSchemas.py

# Security (CRIAR NOVO)
touch security/jwtHandler.py
touch security/rateLimiter.py
touch security/csrfProtection.py
touch security/sessionManager.py

# Dependencies
touch api/dependencies/auth.py
touch api/dependencies/database.py
```

### Passo 4: Refatorar Código

#### **Exemplo: User**

**ANTES (controller fazendo tudo):**
```python
# controller/userController.py ❌
@router.post("/register")
async def register(username: str, email: str, password: str, db: Session = Depends(getDb)):
    # Validação manual
    if len(password) < 8:
        raise HTTPException(400, "Senha muito curta")
    
    # Lógica de negócio no controller
    passwordHash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    
    # Query direto no controller
    user = UserModel(id=str(uuid.uuid4()), username=username, ...)
    db.add(user)
    db.commit()
    
    return user
```

**DEPOIS (separado em camadas):**

```python
# 1. Schema (validação)
# schemas/userSchemas.py
class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=8)

# 2. Repository (queries)
# infrastructure/database/repositories/userRepository.py
class UserRepository:
    def create(self, user: UserModel) -> UserModel:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def findByEmail(self, email: str) -> Optional[UserModel]:
        return self.db.query(UserModel).filter(UserModel.email == email).first()

# 3. Service (lógica de negócio)
# domain/services/userService.py
class UserService:
    def registerUser(self, request: UserRegisterRequest) -> UserResponse:
        # Verificar duplicata
        if self.userRepo.findByEmail(request.email):
            raise ValueError("Email já existe")
        
        # Hash senha
        passwordHash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt(12))
        
        # Criar
        user = UserModel(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            passwordHash=passwordHash.decode(),
            createdAt=datetime.utcnow()
        )
        
        return self.userRepo.create(user)

# 4. Route (HTTP)
# api/routes/userRoutes.py
@router.post("/register", response_model=UserResponse)
async def register(
    request: UserRegisterRequest,
    service: UserService = Depends(getUserService)
):
    try:
        return service.registerUser(request)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
```

### Passo 5: Atualizar Imports

```python
# main.py
from api.routes import userRoutes, streakRoutes, chatRoutes, badgeRoutes, authRoutes
from core.config import settings
from core.database import engine, Base
from security.middleware import SecurityHeadersMiddleware, RateLimitMiddleware

app = FastAPI()

# Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# Routes
app.include_router(authRoutes.router, prefix="/api/auth", tags=["Auth"])
app.include_router(userRoutes.router, prefix="/api/users", tags=["Users"])
app.include_router(streakRoutes.router, prefix="/api/streaks", tags=["Streaks"])
app.include_router(chatRoutes.router, prefix="/api/chat", tags=["Chat"])
app.include_router(badgeRoutes.router, prefix="/api/badges", tags=["Badges"])
```

---

## 📚 5. EXEMPLO COMPLETO: Streak Feature

### Arquivos Necessários

```
1. infrastructure/database/models/streakModel.py      # Tabela
2. infrastructure/database/repositories/streakRepository.py  # Queries
3. domain/services/streakService.py                   # Lógica
4. schemas/streakSchemas.py                           # Validação
5. api/routes/streakRoutes.py                         # Endpoints
```

### 1. Model (Estrutura da Tabela)

```python
# infrastructure/database/models/streakModel.py
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean
from core.database import Base

class StreakModel(Base):
    __tablename__ = 'streaks'
    
    id = Column(String(50), primary_key=True)
    userId = Column(String(50), ForeignKey('users.id'), nullable=False)
    currentDays = Column(Integer, default=0)
    longestStreak = Column(Integer, default=0)
    lastResetDate = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, nullable=False)
    updatedAt = Column(DateTime, nullable=False)
    isActive = Column(Boolean, default=True)
```

### 2. Repository (Acesso a Dados)

```python
# infrastructure/database/repositories/streakRepository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from infrastructure.database.models.streakModel import StreakModel

class StreakRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def findByUserId(self, userId: str) -> Optional[StreakModel]:
        return self.db.query(StreakModel)\
            .filter(StreakModel.userId == userId)\
            .filter(StreakModel.isActive == True)\
            .first()
    
    def create(self, streak: StreakModel) -> StreakModel:
        self.db.add(streak)
        self.db.commit()
        self.db.refresh(streak)
        return streak
    
    def update(self, streak: StreakModel) -> StreakModel:
        self.db.commit()
        self.db.refresh(streak)
        return streak
    
    def findTopStreaks(self, limit: int = 10) -> List[StreakModel]:
        return self.db.query(StreakModel)\
            .filter(StreakModel.isActive == True)\
            .order_by(StreakModel.currentDays.desc())\
            .limit(limit)\
            .all()
```

### 3. Service (Lógica de Negócio)

```python
# domain/services/streakService.py
from datetime import datetime, timedelta
import uuid
from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.models.streakModel import StreakModel
from schemas.streakSchemas import StreakResponse, StreakResetRequest

class StreakService:
    def __init__(self, streakRepo: StreakRepository):
        self.streakRepo = streakRepo
    
    def getStreakByUserId(self, userId: str) -> Optional[StreakResponse]:
        """Retorna streak com validação de expiração"""
        streak = self.streakRepo.findByUserId(userId)
        
        if not streak:
            return None
        
        # REGRA: verificar se expirou (>24h)
        if self.isStreakExpired(streak):
            streak.currentDays = 0
            streak.lastResetDate = datetime.utcnow()
            self.streakRepo.update(streak)
        
        return StreakResponse.from_orm(streak)
    
    def isStreakExpired(self, streak: StreakModel) -> bool:
        """REGRA: expira após 24h"""
        if not streak.updatedAt:
            return False
        
        return (datetime.utcnow() - streak.updatedAt) > timedelta(hours=24)
    
    def incrementStreak(self, userId: str) -> StreakResponse:
        """REGRA: incrementa 1x por dia"""
        streak = self.streakRepo.findByUserId(userId)
        
        if not streak:
            # Criar novo
            streak = StreakModel(
                id=str(uuid.uuid4()),
                userId=userId,
                currentDays=1,
                longestStreak=1,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow()
            )
            return self.streakRepo.create(streak)
        
        # REGRA: só incrementa 1x por dia
        if not self.canIncrementToday(streak):
            raise ValueError("Já incrementado hoje")
        
        streak.currentDays += 1
        
        # REGRA: atualizar longest
        if streak.currentDays > streak.longestStreak:
            streak.longestStreak = streak.currentDays
        
        streak.updatedAt = datetime.utcnow()
        return self.streakRepo.update(streak)
    
    def canIncrementToday(self, streak: StreakModel) -> bool:
        """REGRA: último update foi ontem ou antes"""
        if not streak.updatedAt:
            return True
        
        return streak.updatedAt.date() < datetime.utcnow().date()
    
    def resetStreak(self, userId: str, request: StreakResetRequest) -> StreakResponse:
        """REGRA: reset com histórico"""
        streak = self.streakRepo.findByUserId(userId)
        
        if not streak:
            raise ValueError("Streak não encontrado")
        
        # Salvar histórico antes de resetar
        self.saveHistory(streak)
        
        # Resetar
        streak.currentDays = 0
        streak.lastResetDate = datetime.utcnow()
        streak.updatedAt = datetime.utcnow()
        
        return self.streakRepo.update(streak)
    
    def saveHistory(self, streak: StreakModel):
        """Salva no histórico"""
        # TODO: implementar tabela de histórico
        pass
```

### 4. Schema (Validação)

```python
# schemas/streakSchemas.py
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional

class StreakResponse(BaseModel):
    id: str
    userId: str
    currentDays: int = Field(ge=0)
    longestStreak: int = Field(ge=0)
    lastResetDate: Optional[datetime]
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        orm_mode = True

class StreakResetRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=500)
    
    @validator('note')
    def sanitizeNote(cls, v):
        if v:
            from security.sanitizer import InputSanitizer
            return InputSanitizer().sanitizeHtml(v)
        return v
```

### 5. Route (HTTP Endpoints)

```python
# api/routes/streakRoutes.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.database import getDb
from api.dependencies.auth import getCurrentUser
from domain.services.streakService import StreakService
from infrastructure.database.repositories.streakRepository import StreakRepository
from schemas.streakSchemas import StreakResponse, StreakResetRequest

router = APIRouter()

def getStreakService(db: Session = Depends(getDb)) -> StreakService:
    streakRepo = StreakRepository(db)
    return StreakService(streakRepo)

@router.get("/me", response_model=StreakResponse)
async def getMyStreak(
    currentUserId: str = Depends(getCurrentUser),
    service: StreakService = Depends(getStreakService)
):
    streak = service.getStreakByUserId(currentUserId)
    if not streak:
        raise HTTPException(404, "Streak não encontrado")
    return streak

@router.post("/increment", response_model=StreakResponse)
async def incrementStreak(
    currentUserId: str = Depends(getCurrentUser),
    service: StreakService = Depends(getStreakService)
):
    try:
        return service.incrementStreak(currentUserId)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

@router.post("/reset", response_model=StreakResponse)
async def resetStreak(
    request: StreakResetRequest,
    currentUserId: str = Depends(getCurrentUser),
    service: StreakService = Depends(getStreakService)
):
    try:
        return service.resetStreak(currentUserId, request)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
```

---

## 📦 6. DEPENDÊNCIAS (requirements.txt)

```txt
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
alembic==1.13.0

# Validation & Sanitization
bleach==6.1.0
email-validator==2.1.0

# Monitoring
python-json-logger==2.0.7
sentry-sdk==1.39.1

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
```

---

## 🎯 7. PRÓXIMOS PASSOS

### Fase 1: Reestruturação (1-2 semanas)
- [ ] Criar nova estrutura de pastas
- [ ] Mover arquivos existentes
- [ ] Criar camada de Repository
- [ ] Criar camada de Service
- [ ] Criar Schemas Pydantic
- [ ] Atualizar imports

### Fase 2: Segurança (1-2 semanas)
- [ ] Implementar JwtHandler com Redis
- [ ] Configurar Rate Limiting
- [ ] Adicionar Input Sanitization
- [ ] Implementar CSRF Protection
- [ ] Configurar Security Headers
- [ ] Implementar Audit Logging

### Fase 3: WebSocket (1 semana)
- [ ] Autenticação WebSocket
- [ ] Rate limiting de mensagens
- [ ] Validação de payloads
- [ ] Handlers de eventos
- [ ] Presença online

### Fase 4: Testes (1 semana)
- [ ] Testes unitários (Services)
- [ ] Testes de integração (Repositories)
- [ ] Testes E2E (Routes)
- [ ] Testes de segurança

### Fase 5: DevOps (1 semana)
- [ ] Docker + Docker Compose
- [ ] CI/CD (GitHub Actions)
- [ ] Nginx configurado
- [ ] SSL/HTTPS
- [ ] Monitoring (Sentry)

---

## 📖 8. REFERÊNCIAS E DOCUMENTAÇÃO

### Documentos Criados Nesta Conversa

1. **GUIA_SEGURANCA_BACKEND.md** (89KB)
   - Todos os ataques explicados
   - Código Python completo
   - Exemplos práticos

2. **README_CONTEXTO_NOHARM.md** (este arquivo)
   - Resumo completo da conversa
   - Plano de implementação
   - Estrutura do projeto

### Links Úteis

**FastAPI:**
- https://fastapi.tiangolo.com/
- https://fastapi.tiangolo.com/tutorial/security/

**SQLAlchemy:**
- https://docs.sqlalchemy.org/
- https://docs.sqlalchemy.org/en/20/orm/

**Pydantic:**
- https://docs.pydantic.dev/

**Security:**
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- JWT Best Practices: https://tools.ietf.org/html/rfc8725

**Clean Architecture:**
- Robert C. Martin - Clean Architecture
- Domain-Driven Design - Eric Evans

---

## 🔐 9. COMANDOS ÚTEIS

### Iniciar Projeto

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate    # Windows

# Instalar dependências
pip install -r requirements.txt

# Criar .env
cp .env.example .env
# Editar .env com seus valores

# Criar migrations
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head

# Rodar servidor
uvicorn src.main:app --reload
```

### Gerar Secrets

```python
import secrets

# JWT Secret
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"JWT_REFRESH_SECRET_KEY={secrets.token_urlsafe(32)}")

# Encryption
print(f"ENCRYPTION_MASTER_KEY={secrets.token_urlsafe(32)}")
print(f"ENCRYPTION_SALT={secrets.token_urlsafe(16)}")
```

### Redis (para Blacklist)

```bash
# Instalar Redis
sudo apt install redis-server  # Ubuntu
brew install redis             # Mac

# Iniciar
redis-server

# Testar
redis-cli ping  # Deve retornar PONG
```

### Testes

```bash
# Rodar todos testes
pytest

# Com coverage
pytest --cov=src tests/

# Testes específicos
pytest tests/unit/test_streak_service.py
```

---

## ⚠️ 10. AVISOS IMPORTANTES

### Convenções de Código (camelCase)

Como solicitado, **código Python usa camelCase**:

```python
# ✅ CORRETO (seu padrão)
def getUserById(userId: str):
    passwordHash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    createdAt = datetime.utcnow()

# ❌ ERRADO (PEP 8 padrão)
def get_user_by_id(user_id: str):
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    created_at = datetime.utcnow()
```

### Prioridades de Segurança

**CRÍTICO (implementar primeiro):**
1. JWT com blacklist
2. Rate limiting
3. Input sanitization
4. HTTPS obrigatório

**IMPORTANTE (implementar logo):**
5. CSRF protection
6. Password hashing (bcrypt)
7. Security headers
8. Audit logging

**BOAS PRÁTICAS (implementar quando possível):**
9. 2FA/MFA
10. IP geolocation
11. Anomaly detection

### Não Esquecer

- ❗ **NUNCA** commitar `.env` no Git
- ❗ **SEMPRE** usar HTTPS em produção
- ❗ **SEMPRE** validar inputs (client + server)
- ❗ **NUNCA** retornar `passwordHash` em APIs
- ❗ **SEMPRE** logar eventos de segurança
- ❗ **NUNCA** confiar em dados do cliente

---

## 💬 11. COMO CONTINUAR EM OUTRO CHAT

### Informações para Compartilhar

Ao iniciar nova conversa, forneça:

1. **Contexto do Projeto:**
```
Estou desenvolvendo o backend (Python/FastAPI) de um app de recuperação de vícios 
chamado NoHarm. Já discuti segurança e arquitetura em chat anterior.
```

2. **Arquivos de Referência:**
```
Tenho dois documentos:
- GUIA_SEGURANCA_BACKEND.md (estratégias de segurança)
- README_CONTEXTO_NOHARM.md (contexto completo)
```

3. **Onde Parou:**
```
Estou na fase de [implementação/refatoração/testes/etc]
Preciso ajuda com [específico do que precisa]
```

### Perguntas Frequentes para Próximas Conversas

**Implementação:**
- "Como implemento Redis para blacklist de JWT?"
- "Como faço migration da estrutura antiga para nova?"
- "Como testo o StreakService com pytest?"

**Segurança:**
- "Como configuro CORS corretamente?"
- "Como implemento 2FA/MFA?"
- "Como faço auditoria de logs?"

**WebSocket:**
- "Como autentico conexão WebSocket?"
- "Como implemento presença online?"
- "Como faço rate limiting de mensagens?"

**DevOps:**
- "Como configuro Docker?"
- "Como faço deploy na AWS?"
- "Como configuro CI/CD?"

---

## ✅ 12. CHECKLIST DE IMPLEMENTAÇÃO

### Setup Inicial
- [ ] Criar ambiente virtual
- [ ] Instalar dependências
- [ ] Criar .env com secrets
- [ ] Configurar banco de dados
- [ ] Configurar Redis

### Reestruturação
- [ ] Criar nova estrutura de pastas
- [ ] Mover Models
- [ ] Criar Repositories
- [ ] Criar Services
- [ ] Criar Schemas
- [ ] Criar Routes
- [ ] Atualizar imports

### Segurança - Autenticação
- [ ] JwtHandler com access + refresh tokens
- [ ] Blacklist de tokens (Redis)
- [ ] Password hashing (bcrypt rounds=12)
- [ ] Rate limiting de login
- [ ] CAPTCHA após tentativas

### Segurança - Input
- [ ] Sanitização HTML (bleach)
- [ ] Validação com Pydantic
- [ ] Whitelist de caracteres
- [ ] Limite de tamanho

### Segurança - Headers
- [ ] CORS configurado
- [ ] Content-Security-Policy
- [ ] X-Content-Type-Options
- [ ] X-Frame-Options
- [ ] Strict-Transport-Security

### Segurança - CSRF
- [ ] CSRF tokens
- [ ] SameSite cookies
- [ ] Validação de origem

### WebSocket
- [ ] Autenticação JWT
- [ ] Rate limiting de mensagens
- [ ] Validação de payloads
- [ ] Limite de conexões
- [ ] Handlers de eventos

### Testes
- [ ] Unit tests (Services)
- [ ] Integration tests (Repositories)
- [ ] E2E tests (Routes)
- [ ] Security tests

### DevOps
- [ ] Dockerfile
- [ ] docker-compose.yml
- [ ] Nginx configurado
- [ ] SSL/HTTPS
- [ ] CI/CD

---

## 📞 CONTATO E SUPORTE

Se tiver dúvidas sobre este documento ou implementação:

1. **Revise os documentos criados**
   - GUIA_SEGURANCA_BACKEND.md
   - README_CONTEXTO_NOHARM.md

2. **Consulte código de exemplo**
   - Todos os exemplos estão completos e prontos para usar

3. **Inicie nova conversa** com contexto:
   ```
   "Tenho o contexto do NoHarm backend em README_CONTEXTO_NOHARM.md.
   Preciso ajuda com [tópico específico]"
   ```

---

**Última atualização:** Conversa de 18/02/2026  
**Versão:** 1.0  
**Status:** Pronto para implementação

---

## 🎓 GLOSSÁRIO

**Clean Architecture:** Separação em camadas independentes (presentation, business, data)

**Repository Pattern:** Camada que abstrai acesso a dados

**Service Layer:** Camada com lógica de negócio

**DTO (Data Transfer Object):** Objeto para transferência de dados (Pydantic schemas)

**ORM (Object-Relational Mapping):** SQLAlchemy mapeia tabelas em objetos

**JWT (JSON Web Token):** Token para autenticação stateless

**CSRF (Cross-Site Request Forgery):** Ataque que força ações não autorizadas

**XSS (Cross-Site Scripting):** Injeção de JavaScript malicioso

**DoS (Denial of Service):** Ataque para sobrecarregar servidor

**Rate Limiting:** Limite de requisições por tempo

**Sanitization:** Limpeza de inputs perigosos

**camelCase:** convenção de nomenclatura usada no projeto (getUserById)

---

**🚀 Bom desenvolvimento! Agora você tem tudo para criar um backend seguro e bem arquitetado!**