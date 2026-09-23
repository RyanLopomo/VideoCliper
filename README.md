# AxisClip

AxisClip e uma aplicacao para transformar videos longos em clips curtos, com transcricao, selecao de trechos por IA, renderizacao vertical com legendas, gerenciamento de projetos e fila de publicacao. O projeto combina um frontend React, uma API FastAPI, workers de processamento em Redis/RQ, banco PostgreSQL e integracao com YouTube.

## Tecnologias

- Frontend: React, TypeScript, Vite, React Router, TanStack Query, Axios.
- Backend: Python 3.12, FastAPI, SQLAlchemy, Pydantic.
- Fila e jobs: Redis e RQ.
- Banco de dados: PostgreSQL 16.
- Video/audio: FFmpeg, ffprobe, yt-dlp, faster-whisper.
- IA local: Ollama via API HTTP.
- Publicacao: YouTube Data API e OAuth.
- Infra local: Docker Compose.

## Arquitetura

```text
Frontend Vite/React
   |
   | HTTP, SSE e download/upload de arquivos
   v
FastAPI
   |
   +--> PostgreSQL: projetos, videos, clips, publicacoes, contas e notificacoes
   +--> Redis/RQ: fila de processamento de videos
   +--> /storage: videos originais, transcricoes, clips, thumbs e configs
   +--> YouTube API: OAuth, upload, status, thumbnails e agenda
   +--> Ollama: sugestao de clips, configuracao e estilos

Workers
   |
   +--> worker: executa pipeline de video
   +--> publisher: processa publicacoes pendentes/agendadas
```

A API sobe em `http://localhost:8000`, o frontend em `http://localhost:5173` e os arquivos gerados ficam em `storage/`, montado como `/storage` nos containers.

## Estrutura de pastas

```text
backend/
  app/
    api/          Rotas FastAPI.
    core/         Retry, timeout, validacao e constantes.
    db/           Sessao SQLAlchemy e migrations imperativas.
    models/       Entidades SQLAlchemy.
    pipeline/     Orquestracao do processamento de videos.
    queue/        Conexao Redis/RQ.
    schemas/      Schemas Pydantic.
    services/     Regras de negocio e servicos de video/IA/agendamento.
    utils/        Helpers de arquivos, ffmpeg, log e tempo.
    workers/      Worker RQ, publisher, recovery e manutencao.
    youtube/      OAuth, upload, status, queue e adaptadores de publicacao.
  assets/         Imagens do backend.

frontend/
  src/
    api/          Cliente HTTP e chamadas para a API.
    components/   Componentes reutilizaveis antigos/auxiliares.
    pages/        Pagina simples legada.
    types/        Tipos compartilhados no frontend.
    App.tsx       Shell, rotas e telas principais.
    App.css       Estilos principais.
  public/         Icones e favicon.

storage/          Volume local para arquivos gerados.
postgres-data/    Dados locais do PostgreSQL quando usados fora do volume Docker nomeado.
docker-compose.yml
```

## Instalação e execução

Requisitos:

- Docker e Docker Compose.
- Para executar fora do Docker: Python 3.12, Node 22, FFmpeg, Redis e PostgreSQL.
- Para IA local: Ollama acessivel pela URL configurada.
- Para publicar no YouTube: credenciais OAuth do Google em `backend/app/youtube/client_secret.json`.

Execucao recomendada:

```bash
docker compose up --build
```

Servicos principais:

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Comandos uteis:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f publisher
docker compose restart publisher
```

Execucao manual do frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

Execucao manual do backend exige que PostgreSQL e Redis estejam acessiveis com os hosts esperados pelo codigo ou por rede Docker. A URL do banco esta definida em `backend/app/db/database.py`; revise esse arquivo antes de executar fora do Compose.

## Variaveis de ambiente

O Compose carrega `.env` na raiz. Nao armazene secrets reais no repositorio. Use `.env.example` como referencia.

Principais variaveis:

- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`: presentes no `.env`, mas o fluxo real do OAuth tambem depende de `backend/app/youtube/client_secret.json`.
- `YOUTUBE_REDIRECT_URI`: callback OAuth, por padrao `http://localhost:8000/youtube/callback`.
- `FRONTEND_BASE_URL`: URL usada no redirect apos OAuth, por padrao `http://localhost:5173`.
- `YOUTUBE_AUTO_PUBLISH`: habilita criacao automatica de publicacoes ao concluir clips quando nao ha plano de publicacao.
- `YOUTUBE_PRIVACY_STATUS`: privacidade do upload imediato: `private`, `unlisted` ou `public`.
- `PUBLICATION_SETTINGS_FILE`: arquivo JSON de configuracoes de publicacao; padrao `/storage/publication_settings.json`.
- `MAX_UPLOADS_PER_DAY`, `PUBLISH_SCHEDULE`, `PUBLISH_TIMEZONE`: limites e janelas de publicacao.
- `MANUAL_UPLOAD_COUNTS_TOWARD_DAILY_LIMIT`: define se uploads manuais contam no limite diario.
- `PUBLISHER_MAX_ATTEMPTS`, `PUBLISHER_RETRY_DELAYS`, `PUBLISHER_POLL_INTERVAL`: politica do publisher.
- `PUBLISHER_UPLOAD_TIMEOUT`, `PUBLISHER_PROCESSING_TIMEOUT`, `RECOVERY_INTERVAL`, `WORKER_STALE_TIMEOUT`: timeouts e recovery.
- `YOUTUBE_PROCESSING_POLL_INTERVAL`: intervalo de consulta do processamento no YouTube.
- `CLEANUP_AFTER_PUBLISHED`, `CLEANUP_DELAY_HOURS`: limpeza de arquivos apos publicacao.
- `WORKER_RUN_ONCE`: executa uma iteracao do publisher e encerra.
- `TIKTOK_ENABLED`: habilita adaptador TikTok fake existente.
- `PIPELINE_JOB_TIMEOUT`: timeout do job RQ de pipeline.
- `OLLAMA_URL`: endpoint do Ollama; o codigo tambem tenta `http://host.docker.internal:11434/api/generate` e `http://ollama:11434/api/generate`.
- `STYLE_AI_ENABLED`, `STYLE_AI_TIMEOUT_SECONDS`, `STYLE_AI_MAX_TEXT_CHARS`, `STYLE_AI_MAX_ATTEMPTS`: controle da sugestao de estilo por IA.
- `CLIP_FINDER_MAX_DISCOVERY_ATTEMPTS`: tentativas de descoberta de clips.
- `VITE_API_BASE_URL`: URL da API usada pelo frontend; padrao `http://localhost:8000`.
- `VITE_POLL_INTERVAL`, `VITE_STALE_AFTER_MS`: polling e deteccao de processamento sem atualizacao no frontend.

## Scripts

Frontend:

- `npm run dev`: inicia Vite em desenvolvimento.
- `npm run build`: executa TypeScript build e gera bundle Vite.
- `npm run lint`: executa Oxlint.
- `npm run preview`: serve o build localmente.

Backend:

- O container backend inicia `uvicorn app.main:app --host 0.0.0.0`.
- O container worker executa `rq worker videos --url redis://redis:6379`.
- O container publisher executa `python -m app.workers.publisher_worker`.

## Funcionalidades implementadas

- Cadastro, listagem e exclusao de projetos.
- Upload de video local.
- Importacao de video por URL com `yt-dlp`, eventos SSE de progresso e cancelamento.
- Sugestao de quantidade/duracao de clips.
- Pipeline assincorno de transcricao, selecao de clips, corte, adaptacao vertical, legenda, thumbnail e validacao.
- Pausa, retomada, restart e recovery de processamento.
- Estilos de edicao por preset e sugestao de estilo por IA.
- Galeria de clips com stream, download, thumbnail e preview de estilo.
- Planejamento de publicacoes por dia/horario.
- Publicacao imediata ou agendada.
- OAuth de YouTube, upload, status de processamento, thumbnail e sincronizacao de estado.
- Publisher com retry para falhas transientes.
- Notificacoes internas, historico e notificacoes nativas do navegador.
- Health check com status de banco, Redis, worker e metricas de publicacao.

## Fluxos importantes

### Criacao de clips

1. O frontend envia um arquivo ou URL para `/videos/upload` ou `/videos/url`.
2. A API cria um `Video` em status `PENDING` e enfileira `process-video-{id}` no Redis.
3. O worker RQ executa `VideoPipeline`.
4. O pipeline prepara storage, transcreve audio, encontra candidatos com IA, gera clips, aplica estilo, legenda e thumbnail.
5. Clips validos ficam `COMPLETED`.
6. Se houver plano de publicacao, a aplicacao cria publicacoes `SCHEDULED`; caso contrario, se `YOUTUBE_AUTO_PUBLISH=true`, cria publicacoes `PENDING`.

### Publicacao

1. Publicacoes `PENDING`, `WAITING_RETRY` elegiveis ou `SCHEDULED` com `scheduled_at <= now` sao reivindicadas pelo publisher.
2. O status muda para `UPLOADING`.
3. O adaptador da plataforma envia arquivo e metadados.
4. A publicacao passa para `PROCESSING`.
5. Quando o processamento da plataforma conclui, o publisher envia thumbnail quando aplicavel, marca `PUBLISHED` e registra `published_at`.
6. Em erro real, o publisher classifica o erro e aplica retry ou falha definitiva.

Importante: uma publicacao agendada nao e considerada falha apenas porque `scheduled_at <= now`; nesse caso ela fica elegivel para processamento imediato.

## Manutencao

- Telas e fluxos do frontend: `frontend/src/App.tsx`.
- Chamadas HTTP do frontend: `frontend/src/api/`.
- Tipos do frontend: `frontend/src/types/`.
- Estilos: `frontend/src/App.css` e `frontend/src/index.css`.
- APIs: `backend/app/api/`.
- Modelos e banco: `backend/app/models/`, `backend/app/db/`.
- Pipeline de video: `backend/app/pipeline/` e `backend/app/services/`.
- Fila RQ: `backend/app/services/video_jobs.py` e `backend/app/workers/jobs.py`.
- Publisher: `backend/app/workers/publisher_worker.py`.
- Recovery: `backend/app/workers/recovery.py` e `backend/app/pipeline/recovery.py`.
- YouTube/OAuth/upload: `backend/app/youtube/`.
- Regras de agendamento: `backend/app/services/publication_scheduler.py` e `backend/app/services/video_publication_plan.py`.

## Documentacao complementar

- [Arquitetura](docs/architecture.md)
- [Setup e configuracao](docs/setup.md)
- [API](docs/api.md)
- [Regras de negocio e banco](docs/business-rules.md)
