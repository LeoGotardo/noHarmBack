# noHarmBack

Backend do aplicativo **NoHarm** — app mobile de apoio à recuperação de vícios.

**Stack:** Python · FastAPI · PostgreSQL · WebSocket (Socket.IO) · SQLAlchemy · JWT

---

## Estrutura do Projeto

```
noHarmBack/
├── docs/
├── src/
│   ├── api/
│   │   ├── dependencies/
│   │   └── routes/
│   ├── core/
│   ├── domain/
│   │   ├── entities/
│   │   └── services/
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   └── external/
│   ├── schemas/
│   ├── security/
│   ├── websocket/
│   │   └── handlers/
│   └── main.py
```

---

## `docs/`

Documentação do projeto.

| Arquivo | Descrição |
|---|---|
| `README.md` | Visão geral do projeto |
| `TODO.md` | Contexto completo, decisões de arquitetura e plano de implementação |
| `security.md` | Guia detalhado de segurança — ataques cobertos e como se proteger |
| `requirements.txt` | Dependências Python do projeto |

---

## `src/`

Código-fonte da aplicação, organizado em camadas segundo a **Clean Architecture**.

---

### `src/api/`

Camada de apresentação. Responsável por expor a aplicação ao mundo externo via HTTP.

#### `src/api/dependencies/`

Dependências reutilizáveis injetadas nas rotas pelo FastAPI.

| Arquivo | Descrição |
|---|---|
| `auth.py` | Extrai e valida o usuário autenticado a partir do JWT (`getCurrentUser`) |
| `database.py` | Fornece a sessão do banco de dados (`getDb`) para as rotas |

#### `src/api/routes/`

Endpoints HTTP da aplicação. Cada arquivo agrupa as rotas de um domínio. As rotas **não contêm lógica de negócio** — apenas recebem a requisição, delegam ao `Service` correspondente e retornam a resposta.

| Arquivo | Descrição |
|---|---|
| `authRoutes.py` | Rotas de autenticação: login, logout, refresh token |
| `userRoutes.py` | Rotas de usuário: cadastro, perfil, atualização de dados |
| `streakRoutes.py` | Rotas de streak: consultar, incrementar e resetar dias limpos |
| `chatRoutes.py` | Rotas de mensagens: histórico de conversas |
| `badgesRoutes.py` | Rotas de conquistas: listar e consultar badges do usuário |

---

### `src/core/`

Configurações e recursos centrais compartilhados por toda a aplicação.

| Arquivo | Descrição |
|---|---|
| `config.py` | Carrega e valida as variáveis de ambiente via Dynaconf |
| `database.py` | Cria o engine do SQLAlchemy e a `SessionLocal` |
| `security.py` | Utilitários de segurança transversais (ex: hash de senha) |

---

### `src/domain/`

Núcleo da aplicação. Contém as regras de negócio, completamente isoladas de detalhes de infraestrutura (banco, HTTP, etc).

#### `src/domain/entities/`

Representação pura dos conceitos do domínio, sem acoplamento a ORM ou frameworks.

| Arquivo | Descrição |
|---|---|
| `user.py` | Entidade de usuário (id, username, email, status, timestamps) |
| `streak.py` | Entidade de streak (dias limpos, maior sequência, última data) |
| `chat.py` | Entidade de mensagem de chat |
| `badge.py` | Entidade de conquista/badge |
| `friendship.py` | Entidade de amizade entre usuários |

#### `src/domain/services/`

Orquestram as regras de negócio. Chamam os `Repositories` para acessar dados e aplicam as regras antes de retornar o resultado às rotas.

| Arquivo | Descrição |
|---|---|
| `userService.py` | Registro, atualização de perfil, busca de usuários |
| `streakService.py` | Incremento diário, verificação de expiração, reset com histórico |
| `chatsService.py` | Envio e recuperação de mensagens, validação de destinatário |
| `badgeService.py` | Concessão e listagem de conquistas |

---

### `src/infrastructure/`

Implementações concretas de acesso a dados e serviços externos.

#### `src/infrastructure/database/models/`

Mapeamento ORM das tabelas do banco via SQLAlchemy. Cada arquivo define **apenas a estrutura da tabela** — sem lógica de negócio.

| Arquivo | Tabela | Descrição |
|---|---|---|
| `userModel.py` | `tb_0` | Usuários com username e email criptografados + hash para busca |
| `streakModel.py` | — | Contagem de dias limpos por usuário |
| `chatModel.py` | — | Mensagens trocadas entre usuários |
| `badgeModel.py` | — | Conquistas associadas a usuários |
| `logsModel.py` | — | Registro de eventos de auditoria |

#### `src/infrastructure/database/repositories/`

Camada de acesso a dados. Cada arquivo encapsula as queries do banco para um modelo específico. Os `Services` chamam os `Repositories` — nunca acessam o banco diretamente.

| Arquivo | Descrição |
|---|---|
| `userRepository.py` | `findByEmail`, `findById`, `create`, `update` de usuários |
| `streakRepository.py` | `findByUserId`, `create`, `update`, `findTopStreaks` |
| `chatRepository.py` | `saveMessage`, `findConversation`, `markAsRead` |
| `badgeRepository.py` | `findByUserId`, `grant`, `listAll` |

#### `src/infrastructure/external/`

Integrações com serviços externos.

| Arquivo | Descrição |
|---|---|
| `emailService.py` | Envio de emails (verificação, recuperação de senha) |
| `storageService.py` | Upload e recuperação de arquivos (fotos de perfil) |

---

### `src/schemas/`

DTOs (Data Transfer Objects) definidos com **Pydantic**. Responsáveis por validar os dados de entrada e filtrar os dados de saída das rotas, garantindo que informações sensíveis (ex: `passwordHash`) nunca sejam expostas.

| Arquivo | Descrição |
|---|---|
| `userSchemas.py` | `UserRegisterRequest`, `UserResponse`, `UserUpdateRequest` |
| `streakSchemas.py` | `StreakResponse`, `StreakResetRequest` |
| `chatSchemas.py` | `MessageRequest`, `MessageResponse`, `ConversationResponse` |
| `badgeSchemas.py` | `BadgeResponse`, `BadgeListResponse` |

---

### `src/security/`

Módulos de segurança reutilizáveis por toda a aplicação.

| Arquivo | Descrição |
|---|---|
| `jwtHandler.py` | Geração e validação de Access e Refresh tokens com blacklist |
| `rateLimiter.py` | Rate limiting por IP e por usuário (sliding window) |
| `sanitizer.py` | Sanitização de inputs para prevenção de XSS e injeções |
| `encryption.py` | Criptografia simétrica de dados sensíveis (username, email) |

---

### `src/websocket/`

Comunicação em tempo real via Socket.IO.

| Arquivo | Descrição |
|---|---|
| `socketManager.py` | Gerencia conexões WebSocket: autenticação JWT, rate limiting de mensagens, validação de payloads e roteamento de eventos |

#### `src/websocket/handlers/`

Handlers isolados por responsabilidade, chamados pelo `socketManager`.

| Arquivo | Descrição |
|---|---|
| `chatHandlers.py` | Processamento de mensagens de chat em tempo real |
| `presenceHandlers.py` | Status online/offline dos usuários |

---

### `src/main.py`

Ponto de entrada da aplicação. Inicializa o FastAPI, registra os middlewares (CORS, rate limiting, segurança, CSRF), inclui as rotas e sobe o servidor Socket.IO junto ao HTTP.

---

## Fluxo de uma Requisição

```
Cliente (JSON)
    │
    ▼
Route  ──── valida schema (Pydantic) · extrai JWT (Dependency)
    │
    ▼
Service ──── aplica regras de negócio · orquestra repositórios
    │
    ▼
Repository ── executa queries no banco
    │
    ▼
Model ──────── ORM mapeia tabela ↔ objeto Python
    │
    ▼
PostgreSQL
```

---

## Primeiros Passos

```bash
# Ambiente virtual
python -m venv venv && source venv/bin/activate

# Dependências
pip install -r docs/requirements.txt

# Configuração
cp .env.example .env
# edite .env com seus valores

# Migrations
alembic upgrade head

# Servidor
uvicorn src.main:app --reload
```

### Gerar secrets para o `.env`

```python
import secrets
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"JWT_REFRESH_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"ENCRYPTION_MASTER_KEY={secrets.token_urlsafe(32)}")
```

---

## Convenções de Código

O projeto adota **camelCase** para variáveis, funções e atributos em Python:

```python
# ✅ Padrão do projeto
def getUserById(userId: str): ...
passwordHash = bcrypt.hashpw(...)
createdAt = datetime.utcnow()
```