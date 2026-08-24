# Frontend — proxy, sockets e o que muda no cliente

Handoff do backend para o repo `noHarm` (Vite + Capacitor).

O backend passou a funcionar em múltiplas instâncias e a devolver motivos de recusa
específicos no socket. **Dois itens quebram hoje**; o resto é a migração para o proxy.

---

## O que mudou no backend

Três mudanças já estão em `main`. Duas afetam o cliente imediatamente.

### Entrega de eventos deixou de depender da sala do chat

`new_message`, `messages_read` e `message_read` agora vão só para a sala pessoal
`user_<id>` de cada participante, não mais para `chat_<chatId>`. Todo socket entra na
própria sala pessoal no `connect`, então **nada muda para o cliente**: cada evento chega
exatamente uma vez, com ou sem `join_chat`.

Motivo: a associação de salas é local a cada instância. Com mais de uma instância no ar,
o backend emitia para a sala do chat *e* para a sala pessoal do mesmo usuário, e ele
recebia duplicado. Dedupe defensivo por `messageId` pode ficar, mas não é mais necessário.

### Presença virou multi-dispositivo e cross-instância

`get_online_status` lê de um registro em Redis em vez de um dicionário em memória. Um
usuário conectado em outra instância não aparece mais como offline, e quem está em três
dispositivos continua online até o último desconectar. O formato de `online_status` não
mudou.

### `join_chat` continua necessário

Só para receber `typing_indicator`, que continua indo para a sala do chat com `skip_sid`.
Mensagens chegam sem ele.

---

## Fase 1 — Corrigir agora (independe do proxy)

### 01. Tratar os códigos de recusa do socket — **quebrado**

`src/connectors/socket.js`

O comentário no arquivo já promete isso, mas até agora era mentira: o backend levantava o
`ConnectionRefusedError` *builtin* do Python em vez do de `socketio.exceptions`, e a
biblioteca substituía todo motivo por `"Connection refused by server"`. Corrigido — os
códigos abaixo chegam de verdade em `connect_error`.

| Código | Significa | Ação sugerida |
|---|---|---|
| `missing_token` | Handshake sem token | Bug de cliente — não reconectar em loop |
| `invalid_token` | Assinatura inválida ou expirado | Refresh silencioso, depois `reauth()` |
| `account_unavailable` | Conta deletada, banida ou bloqueada | Encerrar sessão, ir para o login |
| `too_many_connections` | Mais de 3 sockets para o mesmo usuário | Backoff — reconectar já falha de novo |

Hoje o handler é um `console.warn` e o socket.io tenta 5 reconexões para qualquer um dos
quatro. Em `account_unavailable` e `too_many_connections` isso é ruído garantido.

```js
_socket.on("connect_error", (e) => {
  switch (e.message) {
    case "invalid_token":
      return refreshAndReauth();
    case "account_unavailable":
      _socket.disconnect();
      return signOut();
    case "too_many_connections":
      _socket.disconnect();
      return scheduleRetry(30_000);
    default:
      console.warn("[socket] connect_error:", e.message);
  }
});
```

### 02. Parar de forjar `X-Forwarded-For` nos testes — **quebrado**

`tests/helpers/api.js` · `tests/helpers/socket.js` · `tests/README.md`

Os helpers mandam um `X-Forwarded-For` por usuário para dar a cada teste um bucket de rate
limit próprio. Funcionava porque o backend aceitava o header sem validar — a vulnerabilidade
que o `tests/README.md` descreve. Ela foi corrigida: o header só é considerado se o peer
estiver em `TRUSTED_PROXIES`.

Resultado: os headers viraram no-op e **todos os testes caem no mesmo bucket**. Suites
maiores vão colher 429 aleatórios.

Substituição: limpar o rate limit entre testes em vez de fingir IPs. O Redis de teste é o
mesmo que o backend usa, então `FLUSHDB` no `beforeEach` resolve. O `tests/README.md`
também precisa perder a seção que descreve o furo como presente.

---

## Fase 2 — Proxy (depende da decisão de infra)

O backend fica privado, alcançável só a partir de projetos Vercel autorizados via Trusted
Sources. Como o `noHarm` é build estático, ele não tem runtime para apresentar o token
OIDC — a função de proxy é o que o torna uma origem válida.

### 03. Criar a função de proxy no próprio projeto

`api/[...path].ts` (novo)

Não precisa de projeto Vercel separado. Um diretório `api/` na raiz faz a Vercel servir os
estáticos pela CDN e rodar as funções no mesmo deploy. O token OIDC é emitido por projeto,
então o `noHarm` passa a ser trusted source legítimo.

```ts
import { getVercelOidcToken } from '@vercel/oidc';

export async function GET(req: Request)  { return forward(req); }
export async function POST(req: Request) { return forward(req); }

async function forward(req: Request) {
  const url = new URL(req.url);
  const target = process.env.BACKEND_ORIGIN + url.pathname.replace(/^\/api/, '') + url.search;

  const headers = new Headers(req.headers);
  headers.delete('x-forwarded-for');                 // descarta o que o cliente mandou
  headers.set('x-forwarded-for', realClientIp(req)); // sobrescreve com o valor da borda
  headers.set('x-vercel-trusted-oidc-idp-token', await getVercelOidcToken());

  return fetch(target, { method: req.method, headers, body: req.body });
}
```

> **Não erre isto.** Sobrescrever o `X-Forwarded-For`, nunca concatenar. O backend lê a
> cadeia da direita para a esquerda; se o valor do cliente for preservado, um APK modificado
> injeta um hop falso e o rate limit volta a ser burlável — exatamente o furo que o item 02
> acabou de fechar.

### 04. Relay do WebSocket

`api/ws.ts` (novo)

Com o backend privado, o socket não conecta direto: nem o navegador nem o app Capacitor têm
token OIDC para o handshake. O relay abre um WS upstream carregando o token e encana os dois
lados.

O caminho no backend é literalmente `/ws/socket.io/` — o prefixo do mount faz parte do
`socketio_path`, porque a pilha de middleware impede o Starlette de removê-lo. O relay tem
que encaminhar para esse path exato.

> **Limite de payload.** `experimental_upgradeWebSocket` corta frames em 256 KB por padrão;
> o backend aceita 2 MB (`max_http_buffer_size`). Sem alinhar, mensagem grande morre no meio
> sem erro claro.

A favor: o cliente já usa `transports: ["websocket"]`, sem long-polling. Isso elimina o pior
problema de proxiar socket.io em serverless — não há requisições de polling com `sid`
exigindo afinidade de instância. Depois do upgrade é repasse de bytes.

### 05. Repontar as URLs para a própria origem

`.env.local` · `src/connectors/api.js` · `src/connectors/socket.js`

```bash
# antes
VITE_API_URL=https://noharm-back.vercel.app
VITE_SOCKET_URL=https://noharm-back.vercel.app

# depois — mesma origem, o proxy resolve o resto
VITE_API_URL=/api
VITE_SOCKET_URL=
```

Os conectores já leem esses valores com fallback para string vazia, então a mudança é só de
ambiente. `SOCKET_PATH` continua `/ws/socket.io`.

Efeito colateral bom: o navegador passa a chamar a própria origem, então CORS deixa de
existir para o tráfego web — sem preflight, e `ALLOWED_ORIGINS` no backend para de importar
para a SPA.

> **Build do mobile.** O app Capacitor não tem "própria origem" — carrega de `capacitor://`
> ou do filesystem. O build mobile precisa da URL absoluta do proxy
> (`https://noharm.vercel.app/api`), não de `/api`. São dois valores para o mesmo `.env`,
> então vira variável por target de build.

### 06. Considerar cadência de deploy do mobile

Com web e mobile no mesmo proxy, um deploy do frontend que quebre o contrato derruba o app
junto — e o usuário do APK não tem rollback. Não é custo (projeto Vercel não tem taxa fixa),
é acoplamento.

Recomendação: começar junto, separar depois se doer. Separar é copiar o diretório `api/`
para um projeto novo e adicionar o token dele à lista de trusted sources.

---

## Contrato de eventos

Nada aqui mudou de formato.

| Evento | Direção | Entregue em |
|---|---|---|
| `new_message` | servidor → cliente | sala pessoal de cada participante |
| `messages_read` | servidor → cliente | sala pessoal de cada participante |
| `message_read` | servidor → cliente | sala pessoal de cada participante |
| `typing_indicator` | servidor → cliente | sala do chat, pulando o remetente |
| `online_status` | servidor → cliente | só o socket que perguntou |
| `join_chat` | cliente → servidor | necessário só para typing |
| `send_message` | cliente → servidor | 30/min por usuário |
| `typing` | cliente → servidor | 60/min por usuário |

---

## O que ainda não está decidido

A Fase 2 depende de duas confirmações em aberto do lado da infra. Nenhuma bloqueia a Fase 1.

- **Gating de plano do Trusted Sources.** Recursos de Deployment Protection são escalonados
  por plano e isso não foi confirmado nos docs.
- **Custo do relay de WebSocket.** Cada sessão passa a segurar duas funções abertas — proxy
  e backend — pela duração da conexão. A cobrança de conexão mantida aberta não está
  documentada; medir com um spike de um dia, ~50 conexões seguradas por uma hora.

**Alternativa em avaliação:** manter o WebSocket num processo longo (container) em vez de
relay serverless elimina o item 04 inteiro e a incerteza de custo, ao preço de infra em dois
lugares. O `docker/compose.yaml` já roda essa configuração.
