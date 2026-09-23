# Setup e configuracao

## Execucao com Docker

Na raiz do projeto:

```bash
docker compose up --build
```

Servicos definidos:

- `postgres`: PostgreSQL 16.
- `redis`: Redis 7.
- `backend`: FastAPI em `8000`.
- `worker`: RQ worker da fila `videos`.
- `publisher`: worker de publicacao.
- `frontend`: Vite em `5173`.

## Arquivos e volumes

- `storage/` e montado como `/storage`.
- `backend/` e montado como `/app` nos containers Python.
- `frontend/` e montado como `/app` no container frontend.
- O volume Docker `postgres-data` persiste o banco.

## Variaveis

Use `.env.example` como base para `.env`. Nao coloque credenciais reais na documentacao.

Configuracoes por arquivo:

- `.env`: carregado pelo Docker Compose.
- `/storage/publication_settings.json`: atualizado por `PUT /publication-settings`.
- `backend/app/youtube/client_secret.json`: credencial OAuth do Google.
- `backend/app/youtube/token.json`: token OAuth salvo apos conexao.
- `backend/app/youtube/oauth_state.json`: state temporario do fluxo OAuth.

## YouTube OAuth

Para conectar o YouTube:

1. Configure o app OAuth no Google Cloud.
2. Coloque o `client_secret.json` em `backend/app/youtube/client_secret.json`.
3. Garanta que `YOUTUBE_REDIRECT_URI` combine com a URI autorizada.
4. Abra a tela de configuracoes no frontend e clique para conectar.
5. O callback salva token e cria/atualiza a conta em `publication_accounts`.

## Ollama

O cliente tenta usar:

- `OLLAMA_URL`, quando definida.
- `http://host.docker.internal:11434/api/generate`.
- `http://ollama:11434/api/generate`.

O modelo esta fixo no codigo como `qwen3:8b`.

## Banco de dados

A URL do banco esta fixa em `backend/app/db/database.py`. No Compose isso funciona porque o host do servico e `postgres`. Para rodar fora do Docker, ajuste o codigo ou exponha um host com esse nome.

## Validacao local

Com o stack ativo:

```bash
docker compose ps
docker compose exec backend python -m unittest app.youtube.test_scheduled_publication_due
```

No frontend:

```bash
cd frontend
npm run build
npm run lint
```
