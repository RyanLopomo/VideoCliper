# API

Base local: `http://localhost:8000`.

## Health

### GET `/health`

Retorna status da aplicacao, banco, Redis, heartbeat dos workers, contadores de publicacao e metricas gerais.

## Projetos

### GET `/projects`

Lista projetos.

### POST `/projects`

Cria projeto.

Body:

```json
{ "name": "Nome do projeto" }
```

Erros:

- `422`: nome ausente ou vazio.

### GET `/projects/{project_id}`

Retorna um projeto.

Erros:

- `404`: projeto nao encontrado.

### DELETE `/projects/{project_id}`

Remove o projeto e apaga `/storage/project_{id}` quando o caminho esta dentro de `/storage`.

## Videos

### GET `/videos`

Lista videos.

### GET `/videos/{video_id}/status`

Retorna status operacional do video.

### POST `/videos/upload`

Upload multipart.

Campos:

- `project_id`: obrigatorio.
- `file`: obrigatorio.
- `publication_plan_enabled`: opcional.
- `publication_max_per_day`: opcional.
- `publication_start_date`: opcional.
- `publication_times`: JSON string opcional.
- `publication_timezone`: opcional.
- `editing_style`: opcional, padrao `AUTO`.
- `target_clip_count`: opcional.
- `target_clip_duration`: opcional.

Cria o video e enfileira processamento.

### POST `/videos/upload/{project_id}`

Endpoint legado para upload simples por projeto.

### POST `/videos/url`

Alias para importacao por URL.

Body principal:

```json
{
  "project_id": 1,
  "url": "https://...",
  "target_clip_count": 3,
  "target_clip_duration": 60,
  "publication_plan_enabled": false,
  "publication_max_per_day": null,
  "publication_start_date": null,
  "publication_times": null,
  "publication_timezone": null,
  "editing_style": "AUTO"
}
```

### POST `/videos/from-url`

Importa video com `yt-dlp`, publica progresso via SSE e enfileira processamento.

### POST `/videos/url-metadata`

Le metadados da URL e retorna duracao quando disponivel.

Body:

```json
{ "url": "https://..." }
```

### POST `/videos/clip-config/suggest`

Sugere quantidade e duracao dos clips.

Body:

```json
{ "duration": 3600 }
```

### GET `/videos/downloads/events`

SSE para progresso de downloads.

### POST `/videos/downloads/{download_id}/cancel`

Cancela download ativo.

### POST `/videos/{video_id}/start`

Enfileira processamento se o video esta `PENDING`.

### POST `/videos/{video_id}/pause`

Pausa video em `PENDING` ou `PROCESSING`.

### POST `/videos/{video_id}/resume`

Retoma video `PAUSED` e reenfileira processamento.

### POST `/videos/{video_id}/restart`

Remove artefatos de clips/transcricao/sugestoes, limpa clips do banco e reenfileira.

### POST `/videos/{video_id}/publication-plan/retry`

Tenta aplicar novamente o plano de publicacao para videos com clips concluidos.

## Clips

### GET `/clips/video/{video_id}`

Lista clips de um video com URLs de thumbnail, stream, download e dados da publicacao associada mais recente nao cancelada.

### GET `/clips/{clip_id}/thumbnail`

Retorna JPEG da thumbnail.

### GET `/clips/{clip_id}/stream`

Retorna MP4 do clip com suporte a range.

### GET `/clips/{clip_id}/download`

Baixa o MP4 final.

### GET `/clips/styles/presets`

Lista estilos e presets disponiveis.

### POST `/clips/{clip_id}/style`

Atualiza estilo do clip. Quando `render` nao e enviado ou e `true`, tenta renderizar novamente se os arquivos base existem.

Body:

```json
{ "style": "CLEAN", "render": true }
```

### POST `/clips/{clip_id}/style/suggest`

Sugere estilo para o clip com base na transcricao.

### GET `/clips/{clip_id}/style-preview/{style}`

Gera ou reutiliza preview do estilo informado.

## Publicacoes e YouTube

### GET `/publication-settings`

Retorna configuracoes atuais de publicacao.

### PUT `/publication-settings`

Atualiza configuracoes de publicacao.

Body:

```json
{
  "youtube_auto_publish": false,
  "max_uploads_per_day": 5,
  "publish_schedule": ["09:00", "12:00", "18:00"],
  "publish_timezone": "America/Sao_Paulo",
  "manual_upload_counts_toward_daily_limit": true
}
```

### GET `/publication-accounts`

Lista contas de publicacao.

### GET `/publication-accounts/{account_id}`

Retorna conta.

### POST `/publication-accounts/{account_id}/set-default`

Define conta padrao da plataforma.

### DELETE `/publication-accounts/{account_id}`

Desabilita conta.

### GET `/youtube/account`

Retorna status da conexao YouTube.

### GET `/youtube/auth`

Cria URL de autorizacao OAuth.

### GET `/youtube/callback`

Callback OAuth. Salva credenciais e redireciona para o frontend.

### POST `/youtube/disconnect`

Remove token local e desabilita contas YouTube.

### POST `/publication-accounts/youtube/connect`

Cria/atualiza conta usando credenciais ja salvas.

### GET `/publications`

Lista publicacoes. Para YouTube com `platform_post_id`, tenta sincronizar estado real antes de serializar.

### GET `/publications/{publication_id}`

Retorna publicacao.

### POST `/publications`

Cria publicacao imediata ou agendada.

Body:

```json
{
  "clip_id": 1,
  "platform": "YOUTUBE",
  "publication_account_id": null,
  "scheduled_at": "2026-09-23T13:00:00Z"
}
```

Sem `scheduled_at`, o status inicial e `PENDING`. Com `scheduled_at`, o status inicial e `SCHEDULED`.

### PATCH `/publications/{publication_id}/schedule`

Edita horario de publicacao `SCHEDULED`.

### POST `/publications/{publication_id}/cancel`

Cancela publicacao `SCHEDULED`.

### POST `/publications/schedule/suggestions`

Sugere horarios para um limite diario.

### POST `/publications/schedule/preview`

Monta plano sem criar publicacoes.

### POST `/publications/schedule/confirm`

Cria ou atualiza publicacoes agendadas para os clips elegiveis.

## Notificacoes

### GET `/notifications`

Lista as 50 notificacoes mais recentes.

### POST `/notifications/read-all`

Marca todas como lidas.

### POST `/notifications/test`

Cria ou retorna notificacao de teste.
