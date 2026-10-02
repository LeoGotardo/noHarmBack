# Posts (Comunidade) — plano de implementação

> Status: **backend implementado (fases 1–3)** · 2026-09-30 — migration
> `20261001_01`, `PostService`, `postRoutes.py`, `tests/integration/test_posts.py`.
> O que o plano deixava em aberto e como ficou está em
> `FRONTEND_DESIGN_BRIEF.md` §8b. Feito depois: `TERMS_VERSION` /
> `PRIVACY_VERSION` = `2026-09-28` com o texto legal (seção 9), e o cron de
> `purge-removed-content` está no host (`docs/operations.md`).
> Revisão 1 (conferida contra o código): bloquear não-amigo (1.1, não existia),
> `blocked_by` porque o bloqueado podia se desbloquear, `CONSENT_REQUIRED` no
> servidor, `chatId` combinável com `postId`, D8 (evidência anexada em vez de
> 409), push `community` precisa de migration, export inclui removidos.
> Divisão: backend (`noHarmBack`) implementa as seções 2–7; frontend (`noHarm`)
> implementa a seção 8. A seção 3 é o **contrato** — os dois lados constroem
> contra ela, então qualquer mudança nela é combinada antes.
>
> **Nota de implementação (auditoria 2026-10-02):** o front não seguiu a seção 8
> à risca. `PostActionsSheet.jsx` virou `src/screens/community/ItemMenu.jsx`
> (apagar · denunciar · bloquear, em post e comentário). `RemoveContentSheet.jsx`
> **não foi construído**: as rotas de remover/restaurar existem e têm testes,
> mas o app não tem a tela do moderador — hoje só via API. `tests/posts.spec.js`
> também não existe ainda.

---

## 0. Decisões que precisam de "ok" antes de começar

Cada uma tem uma recomendação; o resto do plano assume a recomendação.

| # | Decisão | Recomendação | Por quê |
|---|---------|--------------|---------|
| D1 | Quem vê um post | Autor escolhe por post: `community` (todos os usuários logados) ou `friends` (só amigos aceitos) | App de recuperação: nem todo mundo quer falar com estranhos. Default do composer = `friends`, o mais seguro |
| D2 | Posts anônimos | **Não** na v1 | Anonimato + comentários de estranhos é o pior cenário de moderação. Reavaliar depois |
| D3 | Editar post/comentário | **Não** na v1 — apagar e postar de novo | Um post editado depois de curtido/comentado muda o sentido do que os outros responderam, e complica a evidência de denúncia |
| D4 | Onde fica no app | Nova aba **Community** no lugar de **Badges**; Badges vira tela empilhada a partir do Profile (que já mostra os badges ganhos) | 6 abas não cabem bem no `TabBar` de 480px. **Custo:** `MyProfile.onOpenBadges` hoje faz `resetTo("badges")` e vira `push`; ~50 referências a badges nos specs, inclusive `navigation` e `desktop` |
| D5 | Mostrar streak do autor no post | **Não** na v1 | É dado de saúde exposto a estranhos; exigiria opt-in próprio |
| D6 | Notificar curtidas | **Não** — só comentários notificam | Contador de curtidas empurrando notificação vira métrica de ansiedade; o tom do app é o oposto |
| D7 | Quem apaga comentário | O autor do comentário **e** o autor do post | Dá ao autor controle sobre a própria conversa sem esperar moderação |
| D8 | Denunciar de novo alguém com denúncia aberta | Anexar o post/comentário novo como evidência **à denúncia aberta** em vez do 409 | Hoje a segunda denúncia sobre a mesma pessoa é 409. Com posts isso perde evidência: o segundo post ofensivo nunca chega ao moderador |

---

## 1. Regras de domínio

- **Texto só.** Post: 1–1000 caracteres. Comentário: 1–500. `trim()`; só espaço
  em branco é 422. `Sanitizer.cleanHtml` na entrada. Quebras de linha mantidas.
  Sem imagem, sem link preview (upload nem existe no backend).
- **Visibilidade é regra do service, não só RLS** (igual `tb_0`). Um post é
  visível para o viewer quando **todas** valem:
  1. `status == enabled (1)`;
  2. autor com conta `enabled` — deletado (em carência), banido, suspenso ou
     desativado some do feed, junto com seus comentários e curtidas na contagem;
  3. nenhum bloqueio (`friendship status 3`) entre viewer e autor, em qualquer
     direção;
  4. `visibility == community`, ou viewer é o autor, ou há amizade `accepted (5)`.
- **Invisível = 404 `POST_NOT_FOUND`, nunca 403.** Um 403 confirma que o post
  existe (mesma lógica das rotas de moderação).
- Usuarios bloqueados por você não tem acesso aos seus posts
- Comentários seguem a visibilidade do post, mais a regra 2 e 3 aplicadas ao
  **autor do comentário** (comentário de quem você bloqueou não aparece pra você).
- **Comentar/curtir exige poder ver o post.** Mesma checagem, mesmo 404.
- **Quem pode postar/comentar:** conta `enabled` (403 `POSTER_NOT_ELIGIBLE`,
  mesmo racional de `REPORTER_NOT_ELIGIBLE`) **e sem consentimento pendente**
  de `terms`/`privacy` (403 `CONSENT_REQUIRED`). Hoje `pending_consents` só é
  barrado pelo `ConsentGate` do front; como são justamente os Termos novos que
  autorizam exibir posts, a API não pode aceitar um post de quem ainda não os
  aceitou. **Não** exige consentimento de dados de saúde — post não é o tracker.
- **Apagar pelo autor é delete de verdade** (cascade em comentários e curtidas).
  Quem apaga espera que suma. Se havia denúncia, a cópia já está em `tb_11`.
- **Remoção por moderador é `status = blocked (3)`**, não delete: some pra todos
  (autor incluído), gera notice, e pode ser restaurada em apelação. Um job purga
  depois de `REMOVED_CONTENT_RETENTION_DAYS` (sugestão: 30).
- **Conta excluída:** durante a carência, os posts somem pela regra 2; o purge
  apaga tudo por cascade de `tb_0` (`purgeAccounts.py` já depende só dos
  `ON DELETE` — nada a mudar no job).

### 1.1 Bloquear quem não é amigo (pré-requisito — hoje não existe)

Hoje bloquear é `POST /friendships/{friendshipId}/block`: **só existe em cima de
uma linha de `tb_2`**. Até aqui isso bastava, porque só amigos conversam. Na
Community um estranho pode comentar em você, e sem isso não há como bloqueá-lo.

- Nova rota `POST /users/{userId}/block` (e `DELETE` para desbloquear): cria a
  linha em `tb_2` com `status=blocked` se não houver nenhuma, ou move a
  existente para `blocked`. Resposta igual à do block atual.
- **Registrar quem bloqueou.** `tb_2` não guarda isso, e `unblock` hoje aceita
  *qualquer* participante — ou seja, o bloqueado pode se desbloquear pela API.
  Entre amigos era improvável; com estranhos vira o caminho óbvio de quem está
  assediando. Nova coluna `cl_2g blocked_by` (FK `tb_0`, nullable, preenchida
  no block — **também** pelo `POST /friendships/{id}/block` existente), e
  `unblock` só para `blocked_by`. Linhas antigas com `NULL` mantêm a regra
  atual (não há como saber quem bloqueou), por isso o texto legal não promete
  "só quem bloqueou desfaz".
- Não enviar push nem notificação visível ao bloqueado (o evento WS
  `friend_block` pode continuar, o front já só refaz a lista).

---

## 2. Banco (Alembic `20261001_01_posts.py`)

Seguindo a convenção de nomes ofuscados e criptografia de campo.

**`tb_16` — posts**

| Coluna | Tipo | Nota |
|--------|------|------|
| `cl_16a` | UUID PK | |
| `cl_16b` | String FK `tb_0.cl_0a` **ON DELETE CASCADE** | autor |
| `cl_16c` | `StringEncryptedType(Text)` AES-GCM | conteúdo, igual `tb_4.cl_4d` |
| `cl_16d` | SmallInt | visibilidade: `0 = friends`, `1 = community` (ou String curta, a seu gosto — a API expõe string) |
| `cl_16e` | Integer | status (1 / 3) |
| `created_at`, `updated_at` | `TimestampMixin` | **em claro** — o cursor ordena por eles |

Índices: `(cl_16e, created_at DESC, cl_16a DESC)` para o feed community;
`(cl_16b, created_at DESC)` para feed de amigos e perfil.

**`tb_17` — comentários**

| Coluna | Tipo |
|--------|------|
| `cl_17a` | UUID PK |
| `cl_17b` | UUID FK `tb_16.cl_16a` ON DELETE CASCADE |
| `cl_17c` | String FK `tb_0.cl_0a` ON DELETE CASCADE (autor) |
| `cl_17d` | Text criptografado |
| `cl_17e` | Integer status |
| timestamps | |

Índice `(cl_17b, created_at, cl_17a)`.

**`tb_18` — curtidas**

`cl_18a` post FK cascade · `cl_18b` user FK cascade · `created_at`.
**PK composta `(cl_18a, cl_18b)`** — é ela que torna o like idempotente.

**RLS** (mesma migration, mesmo estilo de `20260831_02`):

| Tabela | Regra |
|--------|-------|
| `tb_16` | SELECT aberto (visibilidade é do service); INSERT só com `cl_16b = current_user`; UPDATE só sem contexto (moderação); DELETE autor ou sem contexto |
| `tb_17` | SELECT aberto; INSERT só o próprio autor; UPDATE só sem contexto; DELETE autor do comentário, **autor do post** (subquery em `tb_16`) ou sem contexto |
| `tb_18` | SELECT aberto (contagem); INSERT/DELETE só a própria linha |

**`tb_2` — nova coluna `cl_2g blocked_by`** (String FK `tb_0.cl_0a` ON DELETE
SET NULL, nullable) — ver 1.1. A checagem de bloqueio da visibilidade roda por
post do feed: garantir que o par `(cl_2b, cl_2c)` tem índice, nos dois sentidos.

Adicionar as três tabelas a `models/__init__.py` (lembrar do problema de registry
documentado em Known Issues).

---

## 3. Contrato da API

Todas autenticadas, `getDbWithRLS`, camelCase no request, snake_case no response
(como o resto).

### Formas

```jsonc
// PostResponse
{
  "id": "uuid",
  "author": {                       // reusar FriendUserInfo (friendshipSchemas.py) — role via publicRole
    "id": "firebase-uid",
    "username": "ana",
    "profile_picture": "https://…" | null,
    "role": "official" | "admin" | null
  },
  "content": "texto",
  "visibility": "community" | "friends",
  "like_count": 3,
  "comment_count": 1,
  "liked_by_me": true,
  "is_mine": false,
  "created_at": "2026-10-01T12:00:00"
}

// CommentResponse
{
  "id": "uuid",
  "post_id": "uuid",
  "author": { …mesmo shape… },
  "content": "texto",
  "is_mine": false,
  "can_delete": true,               // meu comentário OU meu post
  "created_at": "…"
}

// Página (cursor, não page/pageSize — ver nota)
{ "posts": [PostResponse], "next_cursor": "opaque-string" | null }
{ "comments": [CommentResponse], "next_cursor": "opaque-string" | null }
```

**Por que cursor:** o feed muda enquanto se rola. Com `page=2` um post novo no
topo empurra tudo e o cliente vê o último da página 1 repetido na página 2.
O cursor é `base64(created_at|id)`, opaco para o front.

`like_count` / `comment_count` contam só o que o viewer poderia ver? **Não** —
contam linhas ativas de autores `enabled`, iguais para todos. Duas queries
agrupadas por página (padrão de `ReportService.signalsFor`), nunca por linha.

### Endpoints

| Método | Rota | Corpo / query | Resposta | Rate limit |
|--------|------|---------------|----------|-----------|
| GET | `/posts` | `?scope=community\|friends&cursor=&limit=20` (max 50) | página de posts, mais novos primeiro | 60/min |
| GET | `/posts/{postId}` | | `PostResponse` | 60/min |
| POST | `/posts` | `{ "content": str, "visibility": "community"\|"friends" }` | 201 `PostResponse` | 5/min + cota |
| DELETE | `/posts/{postId}` | | 204 (só autor; outro = 404) | 20/min |
| GET | `/users/{userId}/posts` | `?cursor=&limit=` | página (fase 3 — perfil público) | 60/min |
| PUT | `/posts/{postId}/like` | | `{ "liked": true, "like_count": n }` | 60/min |
| DELETE | `/posts/{postId}/like` | | `{ "liked": false, "like_count": n }` | 60/min |
| GET | `/posts/{postId}/comments` | `?cursor=&limit=30` | página, **mais antigos primeiro** | 60/min |
| POST | `/posts/{postId}/comments` | `{ "content": str }` | 201 `CommentResponse` | 20/min + cota |
| DELETE | `/posts/{postId}/comments/{commentId}` | | 204 | 20/min |

- `scope=friends` = posts meus + de amigos aceitos (qualquer visibilidade).
  `scope=community` = todos os `community` visíveis + os meus.
- **Like é PUT/DELETE idempotente**, não toggle. Dois PUTs = uma curtida. Isso
  importa: o front tem tap guards justamente porque nada aqui era idempotente.
  PUT duplicado = `INSERT … ON CONFLICT DO NOTHING`.
- Pydantic com `extra="forbid"` em todo request.

### Erros

| Código | HTTP | Quando |
|--------|------|--------|
| `POST_NOT_FOUND` | 404 | não existe **ou** não é visível pro viewer |
| `COMMENT_NOT_FOUND` | 404 | idem |
| `POSTER_NOT_ELIGIBLE` | 403 | conta do autor não `enabled` |
| `CONSENT_REQUIRED` | 403 | `terms`/`privacy` pendentes (post e comentário; curtir não) |
| `POST_QUOTA_EXCEEDED` | 429 | > `POST_MAX_PER_DAY` (20); `details.retryAt` |
| `COMMENT_QUOTA_EXCEEDED` | 429 | > `COMMENT_MAX_PER_DAY` (200); `details.retryAt` |
| 422 padrão | 422 | tamanho / vazio / visibilidade inválida |

Cotas por conta em Redis, no molde de `ReportQuotaLimiter` (o limiter por IP
sozinho tem os mesmos buracos descritos em "Report abuse ceilings"). Gastar a
cota **depois** de a linha existir.

---

## 4. Denúncia de post e comentário

**Reaproveita o sistema de reports**, não cria outro. Uma denúncia continua
sendo *sobre uma pessoa*; o post/comentário é a evidência — exatamente como o
`chatId` hoje.

`ReportRequest` ganha dois campos opcionais:

```python
postId: Optional[UUID] = None
commentId: Optional[UUID] = None
```

- `postId` e `commentId` são **mutuamente exclusivos** (400
  `REPORT_TARGET_AMBIGUOUS`), mas **combinam com `chatId`**: o front já manda o
  chat sempre que denunciante e denunciado têm um (`app.jsx`, `onReport`), e
  denunciar um post de alguém com quem você conversa não deve jogar fora a
  conversa como evidência.
- **Id, nunca conteúdo** — mesmo princípio. O servidor copia o texto.
- O alvo tem que ser visível pro denunciante (senão 404) e o autor do alvo tem
  que ser o `{userId}` da rota (senão 400 `REPORT_TARGET_MISMATCH`).
- `_captureEvidence` ganha dois `kind`:
  - `post` — conteúdo, `source_id` = post id, `author_id`, `occurred_at`;
  - `comment` — o comentário **e** o post onde foi feito (como um item `post`
    adicional), porque comentário sem contexto é meia conversa — mesmo argumento
    de capturar os dois lados do chat.
  - O perfil continua sendo capturado sempre.
- Tetos (cota, `TOO_MANY_OPEN_REPORTS`, cooldown) **ficam como estão**.
- **Duplicado (D8):** se já há denúncia aberta deste denunciante sobre esta
  pessoa e o pedido traz `postId`/`commentId`, capturar a evidência nova **na
  denúncia existente** e responder 200 com a própria denúncia e
  `"appended": true`, em vez de 409. Sem alvo novo, continua 409. Não gasta cota
  (nenhuma denúncia nova foi criada) e não reabre cooldown. O `details` do
  pedido é descartado — a denúncia já tem o texto do denunciante; se quiser
  guardar, vira item de evidência `kind="note"`.
- `ReportResponse` / `ModeratedReportResponse` ganham `target_kind`
  (`"chat" | "post" | "comment" | null`) para a fila mostrar de onde veio.

---

## 5. Moderação

Novas ações, admin-only, respondendo **404** para não-admin (como todo o resto):

| Rota | Corpo | Efeito |
|------|-------|--------|
| `PUT /posts/{postId}/remove` | `{ reason: NoticeReason, message?: str(500), reportId?: uuid }` | `status=3`, notice `kind="post_removed"`, audit log |
| `PUT /posts/{postId}/comments/{commentId}/remove` | idem | `status=3`, notice `kind="comment_removed"`, audit log |
| `PUT /posts/{postId}/restore` / `…/comments/{id}/restore` | | volta `status=1` (apelação), audit log |

- Admin via `getAdminUser` (já responde 404 a não-admin).
- Post/comentário já apagado pelo autor → 404 `POST_NOT_FOUND`; a evidência
  continua na denúncia. O front mostra "already deleted by its author" e só
  oferece as outras ações.
- Remover conteúdo **não** resolve o report nem sanciona a conta — três decisões
  separadas, mesmo princípio do "Resolving never changes an account".
- `NoticeResponse.kind` passa a aceitar `post_removed` e `comment_removed`. O
  notice mostra o **trecho removido** (primeiros ~200 chars, lidos do próprio
  post) — sem isso a pessoa não sabe o que foi removido. Nunca nomeia quem
  denunciou.
- `self_harm` como reason de remoção: permitido (diferente de warning) — tirar
  do ar um post de crise pode ser certo — mas o notice nesse caso deve carregar
  o link de recursos de crise. O front cuida da copy.
- Job `purge-removed-content` (cron): apaga `status=3` mais velhos que
  `REMOVED_CONTENT_RETENTION_DAYS`.
- (Fase 3) `AdminService`: série "posts por dia" no board.

---

## 6. Tempo real e push (fase 3)

- WebSocket: evento `post_comment` para o **autor do post** (`{post_id,
  comment_id, author: {id, username}}`), exceto quando o comentário é dele.
  Sem evento de like (D6). O feed **não** é ao vivo — puxa ao abrir/voltar à aba
  e no pull-to-refresh.
- Push: nova categoria **`community`**. Hoje as categorias são colunas booleanas
  do device token (`fcmService.CATEGORIES = ("messages", "friends")`,
  `addDevice(…, body.messages, body.friends)`), então é **migration nova** em
  `tb_9` no molde de `20260928_01_push_preferences`, campo novo no body de
  `POST /notifications` (default `true`, para apps antigos que não o enviam) e
  entrada em `CATEGORIES`. Corpo do push: só "*ana
  comentou no seu post*" — **sem o texto do comentário**. O texto passaria pelo
  FCM/APNs, e a política hoje só declara isso para mensagens (200 chars).

---

## 7. Resto do backend

- **Export de dados** (`ExportService`): incluir meus posts, meus comentários e
  os ids dos posts que curti — **inclusive os removidos por moderação** durante
  os 30 dias em que ainda existem, marcados como removidos. Enquanto o dado
  existe, o direito de acesso (LGPD art. 18) vale para ele.
- **Config nova:** `POST_MAX_PER_DAY` (20), `COMMENT_MAX_PER_DAY` (200),
  `REMOVED_CONTENT_RETENTION_DAYS` (30). Documentar em "Configuration".
- **Versões legais:** bumpar `TERMS_VERSION` e `PRIVACY_VERSION` quando o texto
  novo (seção 9) entrar — é o que faz todo mundo passar pelo `ConsentGate`.
- **Testes:** unit dos services (visibilidade é a parte que mais quebra: bloqueio
  nos dois sentidos, amizade desfeita, autor suspenso, post removido; bloquear
  estranho; bloqueado tentando desbloquear → 403; D8 anexando evidência), RLS em
  `test_rls.py`, integração das rotas.
- `CLAUDE.md` do backend: tabela RLS, status codes, seção "Posts".
- `FRONTEND_DESIGN_BRIEF.md`: seção de posts apontando pra este contrato.

---

## 8. Frontend (eu)

### Arquivos

| Caminho | O quê |
|---------|-------|
| `src/services/api/post.js` | `getFeed`, `getPost`, `createPost`, `deletePost`, `likePost`, `unlikePost`, `getComments`, `createComment`, `deleteComment`, `getUserPosts`; constantes `POST_MAX`, `COMMENT_MAX` |
| `src/services/api/report.js` | `reportUser(userId, reason, details, target)` — `target = {chatId?, postId?, commentId?}`; o único chamador hoje (`app.jsx`, `onReport`) passa a mandar `{chatId}` e, vindo de um post, `{chatId, postId}`; tratar `appended: true` (D8) com a copy "Added to your earlier report" |
| `src/services/api/user.js` | `blockUser(userId)` / `unblockUser(userId)` (seção 1.1) |
| `src/store/usePosts.js` | feed por escopo, cursor, append, refetch ao focar a aba, **like otimista** com rollback, remoção local ao apagar |
| `src/store/useComments.js` | comentários de um post, paginação, criar/apagar |
| `src/screens/community/CommunityScreen.jsx` | raiz da aba: `SegTabs` Friends / Community, feed, botão de novo post, empty states |
| `src/screens/community/PostCard.jsx` | autor (`Avatar` + `RoleBadge`), texto, tempo relativo, curtir, comentários, menu `…` |
| `src/screens/community/ComposeSheet.jsx` | `BottomSheet` com textarea, contador, escolha de visibilidade (default friends), aviso de privacidade |
| `src/screens/community/PostDetail.jsx` | overlay `postDetail`: post + comentários + campo de comentário (padrão do `ChatThread`) |
| `src/screens/community/PostActionsSheet.jsx` | apagar (meu) · denunciar · bloquear autor (não é meu) via `blockUser` — funciona com estranhos; ao bloquear, some com posts e comentários dele da lista local |
| `src/screens/friends/ReportSheet.jsx` | aceitar `target` e trocar a copy ("Report this post") |
| `src/screens/moderation/ReportReview.jsx` | hoje só lê `kind === "profile"` e `"message"`: renderizar `post`/`comment` (e `note`, D8); ações "Remove post/comment"; 404 na remoção → "already deleted by its author" |
| `src/screens/moderation/RemoveContentSheet.jsx` | reason + mensagem, no molde de `WarnSheet` |
| `src/components/NoticeSheet.jsx` | `FOOTER`/`ICON` ganham `post_removed` / `comment_removed` (com trecho; `self_harm` → link `CrisisResources`) |
| `src/components/TabBar.jsx` + `SideNav` | aba `community` no lugar de `badges`; ícone novo em `Icon` |
| `src/app.jsx` | `case "community"`, overlays `postDetail` e `badges`; Profile ganha linha para Badges |
| `src/screens/friends/PublicProfile.jsx` | (fase 3) posts da pessoa |

### Detalhes que importam

- **Tap guards:** o coração do like e o enviar comentário são `<button>` crus →
  `useGuardedCallback`. Mesmo com o PUT idempotente, evita flicker do otimista.
- **Like otimista:** vira na hora, usa `like_count` da resposta como verdade,
  desfaz em erro.
- **404 em qualquer ação** (post apagado/removido/bloqueio no meio do caminho):
  tira o post da lista e mostra toast "This post isn't available anymore" — sem
  tela de erro.
- **Aviso no composer** quando `community`: "Everyone on NoHarm can read this.
  Avoid details that identify you." Tom acolhedor, não jurídico.
- **Crise:** o composer e o `PostDetail` têm um link discreto para
  `CrisisResources`. Um post é onde alguém em crise vai escrever, e o feed não
  é atendimento — a denúncia `self_harm` já prioriza a fila, mas quem lê precisa
  de um caminho na hora.
- **`CONSENT_REQUIRED`** não deve acontecer (o `ConsentGate` vem antes), mas se
  vier, refazer `GET /users/me` para o gate aparecer.
- **Desktop (≥900px):** feed na coluna `--content-max`; sem `SplitView` (mesmo
  argumento do `publicProfile`); `ComposeSheet` vira dialog sozinho.
- **Sem cache em localStorage** para o feed (conteúdo de terceiros, muda rápido);
  cache em memória por escopo na sessão.
- **Denúncia com evidência:** do `PostCard` passa `{postId}`, do comentário
  `{commentId}`, mais o `chatId` quando houver conversa — nunca o texto.
- **Notificações (fase 3):** `useNotifications` escuta `post_comment`; IDs locais
  **4000–4999**; switch "Comments on my posts" em Settings → categoria `community`.

### Testes e docs

- `tests/posts.spec.js`: postar, visibilidade friends vs community entre duas
  contas, curtir 2× num tick = 1 PUT efetivo, comentar, apagar, denunciar post
  (checa `postId` no body e ausência de texto), bloqueio esconde posts, projeto
  `desktop` reroda o feed.
- `tests/helpers/cleanup.js`: incluir `tb_16/17/18` na contagem de sobras
  (o delete já vem por cascade de `tb_0`).
- `TESTING.md`: seção Community com 🤖 onde coberto. `CLAUDE.md`: aba, overlays,
  domínio, IDs de notificação.

---

## 9. Textos legais (bloqueia o lançamento)

> **Rascunho feito** na branch `feat/posts` do front (`legalContent.js` +
> `public/terms.html` / `privacy.html` regenerados). Falta: `EFFECTIVE` com a
> data de lançamento e o bump das versões no backend. Cada frase ali descreve
> este plano — se uma decisão da seção 0 mudar, o texto muda junto.

Hoje os Termos dizem, sobre o que o usuário escreve: *"We do not sell it, use it
for advertising, **or publish it**."* Com posts `community` isso fica falso.

- Termos (feito): seção "Posts and comments"; licença para exibir posts a quem
  o autor escolheu; conduta vale para posts; denúncia a partir de post; moderador
  pode remover; conta excluída leva os posts.
- Privacidade (feito): nova categoria (posts, comentários, curtidas), quem vê,
  curtidas sem nomes, cópia na denúncia, retenção (autor: imediato; moderação:
  30 dias; evidência: 180 dias), export.
- **Fica para a fase 3:** o push de comentário (sem conteúdo) entra na seção
  "Notifications" da Privacidade só quando existir — hoje seria afirmar algo
  que o app não faz.
- **Base legal — para um advogado olhar.** O texto usa execução de contrato
  (art. 7 V) para posts, como já faz para mensagens, mais uma frase dizendo que
  o conteúdo e o público são escolha do titular. Post que fala de saúde é dado
  sensível, e contrato não é uma das bases do art. 11; o mesmo vale hoje para
  mensagens. "Tornado manifestamente público pelo titular" (art. 7 §4) só
  cobriria posts `community`, não `friends`. Não bloqueia a v1, mas é a parte
  do documento com menos chão.
- `npm run legal` → `public/terms.html` / `privacy.html`; `about.html` ("Your
  data"), `llms.txt`, `sitemap.xml` `<lastmod>`.
- Backend bumpa `TERMS_VERSION` / `PRIVACY_VERSION` no mesmo deploy.

---

## 10. Ordem sugerida

| Fase | Backend | Frontend |
|------|---------|----------|
| **1 — núcleo** | migration + models + repos · `PostService` (visibilidade!) · rotas de post, like, comentário · cotas · **bloquear não-amigo + `blocked_by`** (1.1) · testes | `post.js`, stores, aba Community, feed, composer, detalhe, like, comentário, apagar, bloquear |
| **2 — segurança** | report com `postId`/`commentId` + evidência + D8 · remover/restaurar · notices novos · job de purge · export · `CONSENT_REQUIRED` · bump de versões legais | `ReportSheet` com alvo, `ReportReview` + `RemoveContentSheet`, `NoticeSheet`, textos legais (`EFFECTIVE`) |
| **3 — engajamento** | WS `post_comment` · push `community` · posts no perfil · série no admin board | notificações, switch em Settings, posts no `PublicProfile` |

Bloquear está na fase 1, não na 2, porque é o que a fase 1 introduz de novo:
contato com estranhos. **Não lançar sem a fase 2.** Conteúdo público sem denúncia e remoção em um app
de recuperação é o cenário que o resto do sistema de moderação existe para evitar.
Fase 1 pode ir pra dev/staging sozinha.

Posso começar o frontend da fase 1 contra este contrato antes do backend estar
pronto; os testes e2e só rodam quando as rotas existirem.
