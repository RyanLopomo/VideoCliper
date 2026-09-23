# Regras de negocio e banco

## Entidades

### Project

Tabela `projects`.

- Agrupa videos.
- Possui `status`, iniciado como `CREATED`.
- Ao excluir projeto, os videos e clips sao removidos por cascade ORM e a pasta `/storage/project_{id}` e apagada quando segura.

### Video

Tabela `videos`.

- Pertence a um projeto.
- Guarda origem (`upload` ou `youtube`), caminho do arquivo e duracao.
- Controla pipeline por `status`, `processing_stage`, progresso, mensagem e heartbeat.
- Pode ter plano de publicacao por dia/horario.
- Pode ter estilo de edicao padrao.

Status usados no codigo incluem `PENDING`, `PROCESSING`, `PAUSED`, `COMPLETED` e `FAILED`.

### Clip

Tabela `clips`.

- Pertence a um video.
- Representa uma janela `start_time`/`end_time`.
- Guarda arquivos final, legenda e thumbnail.
- Pode ter estilo selecionado, preset aplicado e recomendacao de IA.
- Publicacoes dependem de clips.

### PublicationAccount

Tabela `publication_accounts`.

- Representa uma conta externa de publicacao.
- Atualmente o fluxo real implementado e YouTube.
- Pode ser habilitada/desabilitada e marcada como padrao.

### Publication

Tabela `publications`.

- Pertence a um clip.
- Tem unicidade por `(clip_id, platform)`.
- Estados principais: `SCHEDULED`, `PENDING`, `UPLOADING`, `PROCESSING`, `WAITING_RETRY`, `PUBLISHED`, `FAILED`, `CANCELLED`.
- `scheduled_at` guarda horario planejado em UTC sem timezone.
- `platform_post_id` guarda ID externo quando existe.
- `next_retry` controla proxima tentativa apos falha transiente.

### Notification

Tabela `notifications`.

- Usa `event_key` unico para evitar duplicidade.
- Pode referenciar video, clip, publicacao, plataforma e URL.

## Regras de processamento de videos

- Um projeto precisa existir antes de receber upload/importacao.
- Upload sem arquivo retorna erro.
- URL precisa ter scheme `http` ou `https` e host.
- A quantidade de clips deve ser pelo menos 1.
- A duracao alvo dos clips deve ficar entre 15 e 180 segundos.
- O pipeline reaproveita transcricao e sugestoes ja salvas quando os arquivos existem.
- Janelas de clips duplicadas dentro de tolerancia de 0,05s sao reaproveitadas.
- Um clip so e marcado `COMPLETED` apos validacao dos arquivos de video, legenda e thumbnail.
- O pipeline pode ser pausado; a pausa e respeitada entre etapas e entre clips.
- Reiniciar video remove clips gerados, transcript e sugestoes daquele projeto/video e reenfileira.

## Regras de estilos

- Estilos aceitos: `AUTO`, `DRAMATIC`, `HAPPY`, `ENERGETIC`, `CINEMATIC`, `PODCAST`, `CLEAN`.
- Aliases em portugues sao normalizados para IDs internos.
- `AUTO` renderiza como `CLEAN` quando nao ha recomendacao concreta.
- Sugestao de estilo por IA tem timeout e fallback local/heuristico.
- Preview de estilo so e gerado quando clip final, raw clip e SRT existem.

## Regras de publicacao

- `YOUTUBE_AUTO_PUBLISH=false` impede criacao automatica de publicacoes ao fim do pipeline quando nao ha plano.
- Se o video tem plano de publicacao, clips completos sao agendados segundo `publication_max_per_day`, `publication_start_date`, horarios e timezone.
- Agendamento manual nao pode ser criado no passado.
- Dois agendamentos `SCHEDULED` da mesma plataforma nao podem ocupar o mesmo `scheduled_at`.
- O limite diario considera publicacoes `SCHEDULED` do dia local configurado.
- Publicacao sem `scheduled_at` entra como `PENDING`.
- Publicacao com `scheduled_at` entra como `SCHEDULED`.
- `SCHEDULED` com `scheduled_at > now` permanece aguardando.
- `SCHEDULED` com `scheduled_at <= now` e elegivel para upload imediato pelo publisher.
- `scheduled_at <= now` nao e tratado como falha por si so.
- `MISSED_SLOT` so deve ser usado por politica explicita; a funcao de reschedule por missed slot nao executa automaticamente por padrao.
- Publicacoes `WAITING_RETRY` so voltam a ser elegiveis quando `next_retry <= now`.
- Falhas transientes recebem retry; falhas nao transientes ou tentativas maximas levam a `FAILED`.
- O publisher envia thumbnail do YouTube apos processamento bem sucedido, quando ainda nao foi enviada.

## Regras de retry e recovery

- Erros classificados como transientes incluem rede, timeout, erro de servidor, metadata, HTTP e recovery timeout.
- `QUOTA_EXCEEDED` agenda retry para o dia seguinte as 08:00 UTC no codigo atual.
- `AUTH_REVOKED`, validacoes e erros definitivos podem marcar publicacao como `FAILED`.
- Recovery de publicacao atua sobre itens presos em `UPLOADING` ou `PROCESSING` alem do timeout.
- Recovery nao reagenda automaticamente publicacoes apenas porque o horario passou.

## Regras YouTube

- Upload imediato usa `YOUTUBE_PRIVACY_STATUS`.
- Upload agendado passa `publishAt`; nesse caso o corpo enviado ao YouTube usa `privacyStatus=private`.
- `publishAt` precisa ser ISO 8601 com timezone e futuro.
- Titulos sao obrigatorios e limitados a 100 caracteres.
- Descricoes sao limitadas a 5000 bytes UTF-8.
- Tags vazias/duplicadas sao removidas e no maximo 15 tags sao enviadas.
- Category ID precisa ser numerico.
- A sincronizacao com YouTube pode marcar publicacao como `PUBLISHED`, `SCHEDULED`, `PROCESSING` ou `CANCELLED` dependendo de upload status, privacidade e `publishAt`.

## Migrations

As migrations em `backend/app/db/migrations.py`:

- adicionam colunas de progresso, heartbeat, erros e plano de publicacao em `videos`;
- adicionam campos de retry/estilo em `clips`;
- corrigem coluna antiga `tittle` para `title` se existir;
- criam `publication_accounts`, `publications` e `notifications`;
- adicionam campos recentes em `publications`.

Nao ha seeds dedicados no projeto.

## Pontos de atencao

- `backend/app/db/database.py` tem `DATABASE_URL` fixo para o ambiente Docker.
- `backend/app/queue/redis_connectiuon.py` tem erro de grafia no nome do arquivo, mas e o nome importado pelo codigo.
- `frontend/src/App.tsx` concentra muitas telas e regras de UI em um unico arquivo.
- `frontend/src/pages/Dashboard.tsx` e `frontend/src/components/*` existem, mas parte relevante da UI atual esta em `App.tsx`.
- O adaptador TikTok existe como implementacao fake quando `TIKTOK_ENABLED=true`.
- As migrations sao imperativas e executadas no startup, nao ha historico Alembic versionado apesar da dependencia estar instalada.
- Alguns textos do codigo aparecem com caracteres quebrados em logs/mensagens antigas; isso nao altera o fluxo, mas merece padronizacao futura.
