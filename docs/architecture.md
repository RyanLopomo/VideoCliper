# Arquitetura

## Visao geral

AxisClip e dividido em quatro blocos principais:

- Frontend React/Vite para operacao do produto.
- API FastAPI para contratos HTTP, persistencia e orquestracao.
- Worker RQ para processamento pesado de videos.
- Publisher dedicado para publicacoes em plataformas externas.

O storage de arquivos e compartilhado por volumes Docker. O banco guarda metadados e estados; arquivos grandes ficam fora do banco.

## Camadas

### Frontend

`frontend/src/App.tsx` concentra o shell, rotas e telas: dashboard, projetos, videos, detalhe do video, publicacoes e configuracoes. Os modulos em `frontend/src/api/` encapsulam as chamadas HTTP e os tipos em `frontend/src/types/` descrevem as respostas esperadas.

Estado de tela e mantido com `useState`, `useEffect` e polling periodico. O frontend tambem usa `EventSource` para progresso de downloads e `XMLHttpRequest` para progresso de upload.

### API

`backend/app/main.py` cria o app FastAPI, registra routers, aplica CORS, cria tabelas, executa migrations imperativas e expoe `/health`.

Routers:

- `api/projects.py`: CRUD basico de projetos.
- `api/videos.py`: upload, importacao por URL, status e controle do processamento.
- `api/clips.py`: stream, download, thumbnail e estilo dos clips.
- `api/publications.py`: contas, OAuth, configuracoes e publicacoes.
- `api/notifications.py`: historico e leitura de notificacoes.

### Pipeline

O pipeline vive em `backend/app/pipeline/`:

1. `load_video`: carrega video/projeto e marca processamento.
2. `prepare_storage`: prepara `/storage/project_{id}` e pasta `clips`.
3. `recover_stage`: reaproveita checkpoints e arquivos existentes quando possivel.
4. `transcribe_video`: usa faster-whisper e salva `transcript.json`.
5. `find_video_clips`: usa Ollama para sugerir janelas de corte e salva `suggested_clips.json`.
6. `process_clips`: gera cada clip com FFmpeg, legenda, formato vertical, thumbnail e validacao.
7. `apply_publication_step`: cria publicacoes conforme auto publish ou plano.

O worker RQ chama `app.workers.jobs.process_video`, que instancia `VideoPipeline`.

### Publisher

`backend/app/workers/publisher_worker.py` roda em loop separado. Ele:

- procura publicacoes elegiveis;
- transforma a publicacao em `UPLOADING`;
- gera metadados;
- chama o adaptador da plataforma;
- acompanha processamento;
- envia thumbnail no YouTube;
- marca `PUBLISHED` ou registra retry/falha.

Publicacoes agendadas sao processadas quando `scheduled_at <= now`. O horario vencido nao aciona reagendamento automatico.

### Recovery

Ha dois tipos de recovery:

- `pipeline/recovery.py`: retoma etapas e clips do processamento de video.
- `workers/recovery.py`: detecta publicacoes presas em `UPLOADING` ou `PROCESSING` e aplica retry.

O startup da API tambem reenfileira videos recuperaveis que ficaram em etapas intermediarias.

## Persistencia

O banco usa SQLAlchemy com tabelas:

- `projects`
- `videos`
- `clips`
- `publication_accounts`
- `publications`
- `notifications`

As migrations sao comandos SQL imperativos em `backend/app/db/migrations.py`, executados no startup da API e no publisher.

## Comunicacao entre camadas

```text
Usuario
  -> Frontend
  -> FastAPI
  -> PostgreSQL
  -> Redis/RQ
  -> Worker de pipeline
  -> /storage

Publisher
  -> PostgreSQL
  -> /storage
  -> YouTube Data API
```

## Servicos externos

- YouTube Data API: OAuth, upload, status, thumbnail e agenda.
- Ollama: geracao de candidatos de clips, sugestao de configuracao e estilo.
- yt-dlp: metadados e download de videos por URL.
- FFmpeg/ffprobe: duracao, corte, adaptacao, legenda e thumbnail.

## Decisoes relevantes

- Arquivos grandes ficam em `/storage`, nao no banco.
- Jobs de video usam `job_id=process-video-{id}` para evitar duplicidade na fila.
- O pipeline usa checkpoints e arquivos cacheados (`transcript.json`, `suggested_clips.json`) para retomar trabalho.
- Publicacoes possuem maquina de estados propria, separada do status do clip.
- Configuracoes de publicacao podem vir de ambiente ou de `/storage/publication_settings.json`.
