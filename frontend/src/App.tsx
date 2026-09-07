import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { API_BASE_URL } from './api/client'
import { listVideoClips } from './api/clips'
import { getHealth } from './api/health'
import { listNotifications, markNotificationsRead, testNotification } from './api/notifications'
import { cancelPublication, confirmPublicationSchedule, disconnectYouTube, getPublicationSettings, getYouTubeAccount, listPublications, previewPublicationSchedule, publishClipNow, savePublicationSettings, scheduleClipPublication, startYouTubeAuth, suggestPublicationTimes, updatePublicationSchedule } from './api/publications'
import { createProject, deleteProject, listProjects } from './api/projects'
import { importVideoFromUrl, listVideos, pauseVideo, restartVideo, resumeVideo, startVideo, uploadVideo } from './api/videos'
import type { Clip } from './types/clip'
import type { Health } from './types/health'
import type { AxisNotification } from './types/notification'
import type { Publication, PublicationSchedulePlan, PublicationSettings, YouTubeAccount } from './types/publication'
import type { Project } from './types/projects'
import type { Video } from './types/video'
import './App.css'

const POLL_MS = Number(import.meta.env.VITE_POLL_INTERVAL || 8000)
type Toast = { type: 'success' | 'error' | 'warning' | 'info'; text: string }
type NotificationPrefs = { enabled: boolean; system: boolean; sound: boolean; background: boolean; history: boolean }

function statusClass(status?: string) {
  return `badge ${String(status || 'UNKNOWN').toLowerCase()}`
}

function fmtDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}
function fmtScheduleShort(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return `${date.toLocaleDateString()} - ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}
function platformName(value?: string | null) {
  return String(value || '').toUpperCase() === 'TIKTOK' ? 'TikTok' : 'YouTube'
}
function clipTitle(clip: Clip) {
  return clip.title?.trim() || `Clip #${clip.id}`
}
function publicationErrorText(item: { publication_error_details?: string | null; publication_error_type?: string | null; error_details?: string | null; error_type?: string | null }) {
  const details = item.publication_error_details || item.error_details || ''
  try {
    const parsed = JSON.parse(details)
    const yt = parsed.youtube_error
    return yt?.reason || yt?.message || item.publication_error_type || item.error_type || 'Erro'
  } catch {
    return item.publication_error_type || item.error_type || details || 'Erro'
  }
}
function todayInputDate() {
  return new Date().toLocaleDateString('en-CA')
}
function Shell({ health, refresh, notifications, onReadNotifications, children }: { health?: Health; refresh: () => void; notifications: AxisNotification[]; onReadNotifications: () => void; children: ReactNode }) {
  const nav = [['/', 'Dashboard'], ['/projects', 'Projetos'], ['/videos', 'Videos'], ['/publications', 'Publicacoes'], ['/settings', 'Configuracoes']]
  const online = health?.status === 'ok'
  return <div className="app"><aside className="sidebar"><div className="brand">AxisClip</div><nav>{nav.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'active' : ''}>{label}</NavLink>)}</nav></aside><section className="workspace"><header className="topbar"><div><strong>AxisClip</strong><span className={online ? 'dot on' : 'dot off'}>{online ? 'ONLINE' : 'OFFLINE'}</span></div><div className="top-actions"><NotificationBell notifications={notifications} onRead={onReadNotifications} /><button onClick={refresh}>Atualizar</button></div></header><main>{children}</main></section></div>
}

function NotificationBell({ notifications, onRead }: { notifications: AxisNotification[]; onRead: () => void }) {
  const [open, setOpen] = useState(false)
  const unread = notifications.filter(n => !n.read).length
  const toggle = () => { const next = !open; setOpen(next); if (next && unread) onRead() }
  return <div className="notification-wrap"><button className="bell" aria-label="Notificacoes" onClick={toggle}>○{unread > 0 && <b>{unread}</b>}</button>{open && <div className="notification-panel"><div className="notification-head"><strong>Notificacoes</strong><span>{notifications.length}</span></div>{notifications.length === 0 ? <p className="muted">Nenhuma notificacao.</p> : notifications.map(n => <article className={`notification ${n.type.toLowerCase()}`} key={n.id}><div><strong>{n.title}</strong><span>{fmtDate(n.created_at)}</span></div><p>{n.message}</p>{n.platform && <span className="badge">{platformName(n.platform)}</span>}{n.url && <a href={n.url} target="_blank" rel="noopener noreferrer">Abrir no {platformName(n.platform)}</a>}</article>)}</div>}</div>
}

function Dashboard({ health, projects, videos }: { health?: Health; projects: Project[]; videos: Video[] }) {
  const metrics = health?.metrics || {}
  const processed = videos.filter(v => v.status === 'COMPLETED').length
  return <Page title="Dashboard" subtitle="Operacao e saude do sistema"><div className="stats"><Stat label="Videos processados" value={processed} /><Stat label="Clips gerados" value={metrics.clips_generated || 0} /><Stat label="Publicacoes" value={metrics.publications || 0} /><Stat label="Publicados" value={metrics.publications_success || health?.published || 0} /><Stat label="Falhas" value={metrics.failures || health?.failed || 0} /></div><div className="panel grid2">{['application', 'database', 'redis', 'worker'].map(key => { const value = String(key === 'worker' ? health?.worker || health?.worker_status || 'UNKNOWN' : health?.[key as keyof Health] || 'OFFLINE'); return <div className="health" key={key}><span>{key}</span><b className={statusClass(value)}>{value}</b></div> })}</div><div className="panel"><h2>Projetos recentes</h2><Table rows={projects.slice(-5).reverse()} columns={['name', 'status', 'created_at']} /></div></Page>
}

function Projects({ projects, videos, selectProject, onCreateProject, onDeleteProject }: { projects: Project[]; videos: Video[]; selectProject: (id: number) => void; onCreateProject: (name: string) => void; onDeleteProject: (id: number) => void }) {
  const [name, setName] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); if (name.trim()) { onCreateProject(name); setName('') } }
  return <Page title="Projetos" subtitle="Crie e acompanhe projetos"><form className="form panel" onSubmit={submit}><label>Nome do projeto<input value={name} onChange={e => setName(e.target.value)} placeholder="Novo projeto" /></label><button>Criar projeto</button></form><div className="cards">{projects.map(p => <article className="card" key={p.id}><h3>{p.name}</h3><span className={statusClass(p.status)}>{p.status}</span><p>{fmtDate(p.created_at)}</p><p>{videos.filter(v => v.project_id === p.id).length} videos</p><div className="actions"><button onClick={() => selectProject(p.id)}>Abrir</button><button className="danger" onClick={() => onDeleteProject(p.id)}>Excluir</button></div></article>)}</div></Page>
}

function ProjectDetail({ project, videos, onVideo, onUpload, onUrl }: { project?: Project; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File) => void; onUrl: (id: number, url: string) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<'file' | 'url'>('file')
  const [url, setUrl] = useState('')
  const own = videos.filter(v => v.project_id === project?.id)
  if (!project) return <Empty text="Projeto nao encontrado" />
  return <Page title={project.name} subtitle={`${own.length} videos`}><div className="panel upload" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setMode('file'); setFile(e.dataTransfer.files[0]) }}><div className="segmented"><button className={mode === 'file' ? 'active' : ''} onClick={() => setMode('file')}>Arquivo</button><button className={mode === 'url' ? 'active' : ''} onClick={() => setMode('url')}>URL</button></div>{mode === 'file' ? <><label>Adicionar video MP4<input type="file" accept="video/mp4" onChange={e => setFile(e.target.files?.[0] || null)} /></label>{file && <p>{file.name} - {(file.size / 1024 / 1024).toFixed(1)} MB</p>}<button disabled={!file} onClick={() => file && onUpload(project.id, file)}>Enviar</button></> : <><label>URL do video<input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." /></label><button disabled={!url.trim()} onClick={() => onUrl(project.id, url)}>Processar video</button></>}</div><VideoList videos={own} onVideo={onVideo} /></Page>
}

function Videos({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <Page title="Videos" subtitle="Processamento"><VideoList videos={videos} onVideo={onVideo} /></Page>
}

function VideoList({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <div className="panel table">{videos.map(v => <button className="row" key={v.id} onClick={() => onVideo(v.id)}><span>Video #{v.id}</span><span>{v.processing_stage || v.status}</span><span>{v.duration ? `${v.duration}s` : '-'}</span><span>{fmtDate(v.created_at)}</span></button>)}</div>
}

function VideoDetail({ video, clips, publicationSettings, onStart, onPause, onResume, onRestart, onPublishNow, onSchedule, onConfirmPlan }: { video?: Video; clips: Clip[]; publicationSettings?: PublicationSettings; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfirmPlan: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void> }) {
  const [playing, setPlaying] = useState<Clip | null>(null)
  const [planning, setPlanning] = useState(false)
  const schedulable = clips.filter(c => c.status === 'COMPLETED' && (!c.publication_status || c.publication_status === 'SCHEDULED'))
  const hasScheduled = clips.some(c => c.publication_status === 'SCHEDULED')
  if (!video) return <Empty text="Video nao encontrado" />
  return <Page title={`Video #${video.id}`} subtitle={video.file_path}><div className="panel"><div className="video-actions"><span className={statusClass(video.status)}>{video.status}</span>{video.status === 'PENDING' && <button onClick={() => onStart(video.id)}>Iniciar</button>}{video.status === 'PROCESSING' && <button onClick={() => onPause(video.id)}>Pausar</button>}{video.status === 'PAUSED' && <button onClick={() => onResume(video.id)}>Retomar</button>}{['PAUSED', 'FAILED', 'COMPLETED'].includes(video.status) && <button className="danger" onClick={() => onRestart(video.id)}>Reiniciar</button>}</div>{video.error_message && <p className="error">Falha no processamento.</p>}<Steps stage={video.status === 'PAUSED' ? 'PAUSED' : video.processing_stage || video.status} /></div>{schedulable.length > 0 && <div className="panel plan-strip"><div><strong>{schedulable.length} clipes prontos</strong><p className="muted">Planeje publicacoes em lote para o YouTube.</p></div><button className="primary" onClick={() => setPlanning(true)}>{hasScheduled ? 'EDITAR AGENDAMENTO' : 'CONFIGURAR PUBLICACOES'}</button></div>}<ClipGallery clips={clips} publicationSettings={publicationSettings} onPlay={setPlaying} onPublishNow={onPublishNow} onSchedule={onSchedule} onConfigurePlan={() => setPlanning(true)} />{planning && <PublicationPlannerModal clips={schedulable} settings={publicationSettings} onClose={() => setPlanning(false)} onConfirm={async (clipIds, maxPerDay, startDate, times) => { await onConfirmPlan(clipIds, maxPerDay, startDate, times); setPlanning(false) }} />}{playing && <Player clip={playing} onClose={() => setPlaying(null)} />}</Page>
}

function ClipGallery({ clips, publicationSettings, onPlay, onPublishNow, onSchedule, onConfigurePlan }: { clips: Clip[]; publicationSettings?: PublicationSettings; onPlay: (clip: Clip) => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfigurePlan: () => void }) {
  const [uploading, setUploading] = useState<Clip | null>(null)
  const [scheduledClip, setScheduledClip] = useState<Clip | null>(null)
  const scheduledOrder = clips.filter(c => c.publication_scheduled_at).sort((a, b) => String(a.publication_scheduled_at).localeCompare(String(b.publication_scheduled_at)))
  const positionFor = (clip: Clip) => Math.max(1, scheduledOrder.findIndex(item => item.id === clip.id) + 1)
  return <><div className="cards clips">{clips.map(c => <article className="clip-card" key={c.id}><div className="thumb"><img loading="lazy" src={`${API_BASE_URL}${c.thumbnail_url}`} alt={clipTitle(c)} /><div className="thumb-badges"><span className={statusClass(c.status)}>{c.status}</span>{c.publication_status && <span className={statusClass(c.publication_status || undefined)}>{c.publication_status === 'SCHEDULED' ? 'AGENDADO' : c.publication_status === 'FAILED' ? 'ERRO' : c.publication_status}</span>}</div></div><div className="clip-body"><h3>{clipTitle(c)}</h3><p className="muted">Trecho #{c.id}</p><div className="meta"><span>{c.duration}s</span><span>{platformName(c.publication_platform || 'YOUTUBE')}</span>{c.publication_scheduled_at && <span>{fmtScheduleShort(c.publication_scheduled_at)}</span>}</div>{c.publication_status === 'FAILED' && <p className="error-text">Motivo: {publicationErrorText(c)}</p>}<div className="actions"><button className="primary" aria-label={`Assistir ${clipTitle(c)}`} onClick={() => onPlay(c)}>Assistir</button>{c.publication_status === 'SCHEDULED' ? <button onClick={() => setScheduledClip(c)}>AGENDADO</button> : c.publication_status === 'PUBLISHED' && c.publication_url ? <a href={c.publication_url} target="_blank" rel="noopener noreferrer">Publicado</a> : ['UPLOADING', 'PROCESSING', 'WAITING_RETRY'].includes(String(c.publication_status)) ? <span className={statusClass(c.publication_status || undefined)}>{c.publication_status}</span> : c.publication_status === 'FAILED' ? <button onClick={() => onPublishNow(c)}>Republicar</button> : <><button onClick={onConfigurePlan}>CONFIGURAR</button><button onClick={() => onPublishNow(c)}>Fazer upload</button></>}</div></div></article>)}</div>{uploading && <UploadModal clip={uploading} tiktokEnabled={Boolean(publicationSettings?.tiktok_enabled)} onClose={() => setUploading(null)} onPublishNow={clip => { onPublishNow(clip); setUploading(null) }} onSchedule={(clip, value) => { onSchedule(clip, value); setUploading(null) }} />}{scheduledClip && <ScheduledClipModal clip={scheduledClip} position={positionFor(scheduledClip)} onClose={() => setScheduledClip(null)} />}</>
}

function ScheduledClipModal({ clip, position, onClose }: { clip: Clip; position: number; onClose: () => void }) {
  return <div className="modal" role="dialog" aria-modal="true"><div className="player scheduled-modal"><button className="close" onClick={onClose}>Fechar</button><h2>Agendado</h2><div className="panel grid2"><Info label="Clip" value={`Trecho #${clip.id}`} /><Info label="Plataforma" value={platformName(clip.publication_platform || 'YOUTUBE')} /><Info label="Data e horario" value={fmtDate(clip.publication_scheduled_at || undefined)} /><Info label="Posicao" value={String(position)} /></div>{clip.publication_url && <div className="panel"><a href={clip.publication_url} target="_blank" rel="noopener noreferrer">Abrir publicacao</a></div>}</div></div>
}

function UploadModal({ clip, tiktokEnabled, onClose, onPublishNow, onSchedule }: { clip: Clip; tiktokEnabled: boolean; onClose: () => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void }) {
  const [scheduledAt, setScheduledAt] = useState('')
  return <div className="modal" role="dialog" aria-modal="true"><div className="player upload-modal"><button className="close" onClick={onClose}>Fechar</button><img src={`${API_BASE_URL}${clip.thumbnail_url}`} alt={clipTitle(clip)} /><h2>{clipTitle(clip)}</h2><p className="muted">{clip.duration}s</p><div className="panel"><h3>YouTube</h3><div className="actions"><button className="primary" onClick={() => window.confirm('Publicar este clip agora?') && onPublishNow(clip)}>Publicar agora</button></div><label>Agendar<input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} /></label><button disabled={!scheduledAt} onClick={() => onSchedule(clip, scheduledAt)}>Agendar</button></div><div className="panel"><h3>TikTok</h3><button disabled={!tiktokEnabled}>Indisponivel</button></div></div></div>
}

function PublicationPlannerModal({ clips, settings, onClose, onConfirm }: { clips: Clip[]; settings?: PublicationSettings; onClose: () => void; onConfirm: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void> }) {
  const [maxPerDay, setMaxPerDay] = useState(Math.max(1, settings?.max_uploads_per_day || 10))
  const [startDate, setStartDate] = useState(todayInputDate())
  const [times, setTimes] = useState(settings?.publish_schedule?.length ? settings.publish_schedule : ['09:00', '13:00', '18:00', '21:00'])
  const [plan, setPlan] = useState<PublicationSchedulePlan | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const clipIds = useMemo(() => clips.map(c => c.id), [clips])

  const refreshPlan = useCallback(async () => {
    try {
      setError('')
      setPlan(await previewPublicationSchedule({ clip_ids: clipIds, max_per_day: maxPerDay, start_date: startDate, times }))
    } catch (e) {
      setPlan(null)
      setError(e instanceof Error ? e.message : 'Nao foi possivel calcular o planejamento.')
    }
  }, [clipIds, maxPerDay, startDate, times])

  useEffect(() => { refreshPlan() }, [refreshPlan])

  const setTimeAt = (index: number, value: string) => setTimes(items => items.map((item, itemIndex) => itemIndex === index ? value : item))
  const addTime = () => setTimes(items => [...items, '09:00'])
  const removeTime = (index: number) => setTimes(items => items.length > 1 ? items.filter((_, itemIndex) => itemIndex !== index) : items)

  const suggest = async () => {
    try {
      const result = await suggestPublicationTimes(maxPerDay)
      setTimes(result.times)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nao foi possivel sugerir horarios.')
    }
  }

  const confirm = async () => {
    try {
      setSaving(true)
      await onConfirm(clipIds, maxPerDay, startDate, times)
    } finally {
      setSaving(false)
    }
  }

  return <div className="modal" role="dialog" aria-modal="true"><div className="player planner-modal"><button className="close" onClick={onClose}>Fechar</button><header className="planner-head"><h2>Planejamento de publicacoes</h2><p className="muted">Configure quando e quantos clips serao publicados.</p></header><section className="planner-layout"><div className="panel planner-config"><h3>Configuracoes de publicacao</h3><Info label="Total de clips" value={String(clips.length)} /><label>Clipes por dia<input type="number" min="1" value={maxPerDay} onChange={e => setMaxPerDay(Math.max(1, Number(e.target.value) || 1))} /></label><label>Data inicial<input type="date" min={todayInputDate()} value={startDate} onChange={e => setStartDate(e.target.value)} /></label><Info label="Fuso horario" value={settings?.publish_timezone || 'America/Sao_Paulo'} /><div className="time-editor"><span>Horarios</span><div>{times.map((item, index) => <label key={`${index}-${item}`}>Horario {index + 1}<input type="time" value={item} onChange={e => setTimeAt(index, e.target.value)} /><button type="button" onClick={() => removeTime(index)}>Remover</button></label>)}</div></div><div className="actions"><button onClick={addTime}>+ Adicionar horario</button><button onClick={suggest}>Sugerir horarios</button></div></div><div className="panel planner-config"><h3>Resumo do planejamento</h3><div className="planner-metrics"><Stat label="Total" value={clips.length} /><Stat label="Por dia" value={maxPerDay} /><Stat label="Dias" value={plan?.estimated_days || 0} /></div>{error && <p className="error-text">{error}</p>}<div className="actions"><button onClick={refreshPlan}>Editar planejamento</button><button className="primary" disabled={saving || !plan || plan.total_clips === 0} onClick={confirm}>{saving ? 'Agendando...' : 'Confirmar agendamento'}</button></div></div></section><h3>Distribuicao dos dias</h3><div className="schedule-summary">{plan?.days.map((day, index) => <article key={day.date}><strong>Dia {index + 1}<br />{new Date(`${day.date}T12:00:00`).toLocaleDateString()}</strong><span>{day.count} clips</span><div>{day.times.map((item, timeIndex) => <small key={`${day.date}-${item}-${timeIndex}`}>{item}</small>)}</div></article>)}</div><h3>Clips gerados</h3><div className="planner-clips">{clips.map(clip => <article key={clip.id}><img src={`${API_BASE_URL}${clip.thumbnail_url}`} alt={clipTitle(clip)} /><div><strong>{clipTitle(clip)}</strong><span>Trecho #{clip.id} - {clip.duration}s - YouTube</span></div></article>)}</div></div></div>
}

function Player({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  return <div className="modal" role="dialog" aria-modal="true"><div className="player"><button className="close" onClick={onClose}>Fechar</button><h2>{clip.title}</h2><video src={`${API_BASE_URL}${clip.stream_url}`} controls autoPlay /></div></div>
}

function Publications({ publications, onCancel, onEdit }: { publications: Publication[]; onCancel: (id: number) => void; onEdit: (id: number) => void }) {
  return <Page title="Publicacoes" subtitle="Fila e historico"><div className="pub-table"><div className="pub-row head"><span>Clip</span><span>Platform</span><span>Status</span><span>Attempts</span><span>Scheduled</span><span>Published</span><span>Action</span></div>{publications.map(p => <div className="pub-row" key={p.id}><span>{p.title || `Clip #${p.clip_id}`}</span><span>{platformName(p.platform)}</span><span className={statusClass(p.status)}>{p.status === 'FAILED' ? `ERRO: ${publicationErrorText(p)}` : p.status}</span><span>{p.attempts || 0}</span><span>{fmtDate(p.scheduled_at || undefined)}</span><span>{fmtDate(p.published_at || undefined)}</span>{p.status === 'SCHEDULED' ? <span className="inline-actions"><button onClick={() => onEdit(p.id)}>Editar</button><button className="danger" onClick={() => onCancel(p.id)}>Cancelar</button></span> : p.status === 'PUBLISHED' && p.publication_url ? <a href={p.publication_url} target="_blank" rel="noopener noreferrer">Abrir</a> : p.status === 'FAILED' ? <span className="muted">{publicationErrorText(p)}</span> : <span className="muted">-</span>}</div>)}</div></Page>
}

function PublicationRoute({ publications }: { publications: Publication[] }) {
  const id = Number(useParams().id)
  const publication = publications.find(p => p.id === id)
  if (!publication) return <Empty text="Publicacao nao encontrada" />
  return <Page title={`Publicacao #${publication.id}`} subtitle={publication.title || `Clip #${publication.clip_id}`}><div className="panel grid2"><Info label="Plataforma" value={publication.platform} /><Info label="Status" value={publication.status} /><Info label="Video ID" value={publication.platform_post_id || '-'} /><Info label="Tentativas" value={String(publication.attempts || 0)} /><Info label="Criada em" value={fmtDate(publication.created_at)} /><Info label="Publicada em" value={fmtDate(publication.published_at || undefined)} /></div>{publication.status === 'PUBLISHED' && publication.publication_url && <div className="panel"><a href={publication.publication_url} target="_blank" rel="noopener noreferrer">ABRIR PUBLICACAO</a></div>}</Page>
}

function ProjectRoute({ projects, videos, onVideo, onUpload, onUrl }: { projects: Project[]; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File) => void; onUrl: (id: number, url: string) => void }) {
  const id = Number(useParams().id)
  return <ProjectDetail project={projects.find(p => p.id === id)} videos={videos} onVideo={onVideo} onUpload={onUpload} onUrl={onUrl} />
}

function VideoRoute({ videos, clips, publicationSettings, onStart, onPause, onResume, onRestart, onPublishNow, onSchedule, onConfirmPlan }: { videos: Video[]; clips: Clip[]; publicationSettings?: PublicationSettings; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfirmPlan: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void> }) {
  const id = Number(useParams().id)
  return <VideoDetail video={videos.find(v => v.id === id)} clips={clips} publicationSettings={publicationSettings} onStart={onStart} onPause={onPause} onResume={onResume} onRestart={onRestart} onPublishNow={onPublishNow} onSchedule={onSchedule} onConfirmPlan={onConfirmPlan} />
}

function Settings({ health, youtube, connecting, publicationSettings, notificationPrefs, notificationPermission, onNotificationPref, onTestNotification, onConnect, onDisconnect, onSavePublicationSettings }: { health?: Health; youtube?: YouTubeAccount; connecting: boolean; publicationSettings?: PublicationSettings; notificationPrefs: NotificationPrefs; notificationPermission: NotificationPermission | 'unsupported'; onNotificationPref: (key: keyof NotificationPrefs, value: boolean) => void; onTestNotification: () => void; onConnect: () => void; onDisconnect: () => void; onSavePublicationSettings: (settings: PublicationSettings) => void }) {
  const connected = youtube?.connected
  const status = connecting ? 'CONNECTING' : youtube?.status || 'DISCONNECTED'
  const channel = youtube?.channel_title || youtube?.channel_name || 'YouTube'
  return <Page title="Configuracoes" subtitle="Integracoes"><div className="panel grid2"><Info label="Backend URL" value={API_BASE_URL} /><Info label="API status" value={health?.status || 'offline'} /><Info label="Versao" value="0.0.0" /><Info label="TikTok" value={publicationSettings?.tiktok_enabled ? 'Ativo' : 'Desabilitado'} /></div><div className="panel"><h2>YouTube</h2><p>{connected ? `Canal: ${channel}` : 'Nenhuma conta conectada'}</p><span className={statusClass(status)}>{status}</span><div className="actions"><button onClick={onConnect} disabled={connecting}>{connecting ? 'CONECTANDO...' : connected ? 'TROCAR CONTA' : 'CONECTAR YOUTUBE'}</button>{connected && <button onClick={onDisconnect}>DESCONECTAR</button>}</div></div>{publicationSettings && <PublicationSettingsForm settings={publicationSettings} onSave={onSavePublicationSettings} />}<div className="panel settings-panel"><h2>Notificacoes</h2><Toggle label="Ativar notificacoes" checked={notificationPrefs.enabled} onChange={v => onNotificationPref('enabled', v)} /><Toggle label="Notificacoes do sistema" checked={notificationPrefs.system} onChange={v => onNotificationPref('system', v)} /><Toggle label="Som" checked={notificationPrefs.sound} onChange={v => onNotificationPref('sound', v)} /><Toggle label="Notificacoes em segundo plano" checked={notificationPrefs.background} onChange={v => onNotificationPref('background', v)} /><Toggle label="Historico" checked={notificationPrefs.history} onChange={v => onNotificationPref('history', v)} /><p className="muted">Permissao: {notificationPermission.toUpperCase()}</p>{notificationPermission === 'denied' && <p className="error-text">As notificacoes do navegador estao bloqueadas.</p>}<button onClick={onTestNotification}>Testar notificacao</button></div></Page>
}

function PublicationSettingsForm({ settings, onSave }: { settings: PublicationSettings; onSave: (settings: PublicationSettings) => void }) {
  const [form, setForm] = useState(settings)
  useEffect(() => setForm(settings), [settings])
  const setSchedule = (value: string) => setForm({ ...form, publish_schedule: value.split(',').map(item => item.trim()).filter(Boolean) })
  return <div className="panel settings-panel"><h2>Publicacao</h2><Toggle label="Publicacao automatica" checked={form.youtube_auto_publish} onChange={v => setForm({ ...form, youtube_auto_publish: v })} /><div className="settings-row"><label>Maximo por dia<input type="number" min="0" value={form.max_uploads_per_day} onChange={e => setForm({ ...form, max_uploads_per_day: Number(e.target.value) })} /></label><label>Horarios<input value={form.publish_schedule.join(', ')} onChange={e => setSchedule(e.target.value)} placeholder="09:00, 12:00, 18:00" /></label></div><label>Fuso horario<input value={form.publish_timezone} onChange={e => setForm({ ...form, publish_timezone: e.target.value })} /></label><Toggle label="Manual conta no limite" checked={form.manual_upload_counts_toward_daily_limit} onChange={v => setForm({ ...form, manual_upload_counts_toward_daily_limit: v })} /><button className="primary" onClick={() => onSave(form)}>Salvar</button></div>
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="toggle"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} /><span>{label}</span></label>
}

function Steps({ stage }: { stage: string }) {
  const steps = ['Upload', 'Transcricao', 'Analise', 'Clips', 'Finalizacao']
  const order = ['PENDING', 'TRANSCRIBING', 'FINDING_CLIPS', 'GENERATING_CLIPS', 'COMPLETED']
  const current = Math.max(order.findIndex(s => s === stage), stage === 'COMPLETED' ? 4 : 0)
  return <div className="steps" aria-label="Status do processamento">{steps.map((s, i) => { const state = stage === 'FAILED' ? 'failed' : i < current || stage === 'COMPLETED' ? 'done' : i === current ? 'run' : 'pending'; return <span key={s} className={state}><i>{state === 'done' ? '✓' : state === 'failed' ? '!' : state === 'run' ? '•' : ''}</i>{s}</span> })}</div>
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <><div className="pagehead"><h1>{title}</h1><p>{subtitle}</p></div>{children}</> }
function Stat({ label, value }: { label: string; value: number }) { return <div className="stat"><span>{label}</span><strong>{value}</strong></div> }
function Info({ label, value }: { label: string; value: string }) { return <div className="info"><span>{label}</span><b>{value}</b></div> }
function Empty({ text }: { text: string }) { return <div className="panel empty">{text}</div> }
function Table<T extends object>({ rows, columns }: { rows: T[]; columns: (keyof T & string)[] }) { return <div className="table">{rows.map((r, i) => <div className="row" key={i}>{columns.map(c => <span key={c}>{c.includes('date') || c.endsWith('_at') ? fmtDate(String(r[c] || '')) : String(r[c] || '-')}</span>)}</div>)}</div> }

function App() {
  const [selectedVideo, setSelectedVideo] = useState<number>()
  const [projects, setProjects] = useState<Project[]>([])
  const [videos, setVideos] = useState<Video[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [publications, setPublications] = useState<Publication[]>([])
  const [publicationSettings, setPublicationSettings] = useState<PublicationSettings>()
  const [youtube, setYoutube] = useState<YouTubeAccount>()
  const [health, setHealth] = useState<Health>()
  const [toast, setToast] = useState<Toast | null>(null)
  const [notifications, setNotifications] = useState<AxisNotification[]>([])
  const [seenNotifications, setSeenNotifications] = useState<Set<string>>(new Set())
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission | 'unsupported'>('Notification' in window ? Notification.permission : 'unsupported')
  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPrefs>(() => {
    const saved = window.localStorage.getItem('axisclip.notificationPrefs')
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch {
        window.localStorage.removeItem('axisclip.notificationPrefs')
      }
    }
    return { enabled: true, system: false, sound: true, background: true, history: true }
  })

  const playNotificationSound = useCallback(() => {
    if (!notificationPrefs.sound) return
    try {
      const ctx = new AudioContext()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.frequency.value = 660
      gain.gain.value = 0.035
      osc.connect(gain); gain.connect(ctx.destination); osc.start()
      window.setTimeout(() => { osc.stop(); ctx.close() }, 120)
    } catch {
      return
    }
  }, [notificationPrefs.sound])

  const showNativeNotification = useCallback((item: AxisNotification) => {
    if (!notificationPrefs.enabled || !notificationPrefs.system || notificationPermission !== 'granted') return
    if (!notificationPrefs.background && !document.hidden) return
    new Notification(item.title, { body: item.message, silent: !notificationPrefs.sound })
  }, [notificationPermission, notificationPrefs])

  const load = useCallback(async () => {
    try {
      const yt = await getYouTubeAccount()
      setYoutube(yt)
    } catch {
      setYoutube({ connected: false, status: 'DISCONNECTED' })
    }
    try {
      const [h, p, v, pubs, pubSettings, notes] = await Promise.all([getHealth(), listProjects(), listVideos(), listPublications(), getPublicationSettings(), notificationPrefs.history ? listNotifications() : Promise.resolve([])])
      setHealth(h); setProjects(p); setVideos(v); setPublications(pubs)
      setPublicationSettings(pubSettings)
      setNotifications(notes)
      const fresh = notes.filter(n => !seenNotifications.has(n.id))
      if (fresh.length && notificationPrefs.enabled) {
        const latest = fresh[0]
        setToast({ type: latest.type === 'ERROR' ? 'error' : latest.type === 'RETRY' ? 'warning' : 'success', text: latest.title })
        showNativeNotification(latest)
        playNotificationSound()
      }
      if (fresh.length) setSeenNotifications(prev => new Set([...prev, ...fresh.map(n => n.id)]))
      if (selectedVideo) setClips(await listVideoClips(selectedVideo))
    } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro de conexao' }) }
  }, [notificationPrefs.enabled, notificationPrefs.history, playNotificationSound, selectedVideo, seenNotifications, showNativeNotification])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const active = videos.some(v => !['COMPLETED', 'FAILED'].includes(v.status))
    if (!active) return
    const id = window.setInterval(load, POLL_MS)
    return () => window.clearInterval(id)
  }, [videos, load])

  const updateNotificationPref = async (key: keyof NotificationPrefs, value: boolean) => {
    if (key === 'system' && value && 'Notification' in window && Notification.permission === 'default') {
      const permission = await Notification.requestPermission()
      setNotificationPermission(permission)
      if (permission !== 'granted') value = false
    }
    const next = { ...notificationPrefs, [key]: value }
    setNotificationPrefs(next)
    window.localStorage.setItem('axisclip.notificationPrefs', JSON.stringify(next))
    if (key === 'history' && !value) setNotifications([])
  }

  return <BrowserRouter><AppRoutes projects={projects} videos={videos} clips={clips} publications={publications} publicationSettings={publicationSettings} notifications={notifications} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} youtube={youtube} health={health} load={load} setClips={setClips} setToast={setToast} setSelectedVideo={setSelectedVideo} setNotifications={setNotifications} updateNotificationPref={updateNotificationPref} showNativeNotification={showNativeNotification} playNotificationSound={playNotificationSound} toast={toast} /></BrowserRouter>
}

function AppRoutes({ projects, videos, clips, publications, publicationSettings, notifications, notificationPrefs, notificationPermission, youtube, health, load, setClips, setToast, setSelectedVideo, setNotifications, updateNotificationPref, showNativeNotification, playNotificationSound, toast }: { projects: Project[]; videos: Video[]; clips: Clip[]; publications: Publication[]; publicationSettings?: PublicationSettings; notifications: AxisNotification[]; notificationPrefs: NotificationPrefs; notificationPermission: NotificationPermission | 'unsupported'; youtube?: YouTubeAccount; health?: Health; load: () => Promise<void>; setClips: (clips: Clip[]) => void; setToast: (toast: Toast | null) => void; setSelectedVideo: (id: number) => void; setNotifications: (items: AxisNotification[]) => void; updateNotificationPref: (key: keyof NotificationPrefs, value: boolean) => Promise<void>; showNativeNotification: (item: AxisNotification) => void; playNotificationSound: () => void; toast: Toast | null }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [youtubeConnecting, setYoutubeConnecting] = useState(false)
  const openVideo = (id: number) => { setSelectedVideo(id); listVideoClips(id).then(setClips); navigate(`/videos/${id}`) }
  const create = async (name: string) => { try { await createProject(name); setToast({ type: 'success', text: 'Projeto criado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro' }) } }
  const upload = async (id: number, file: File) => { try { setToast({ type: 'info', text: 'Enviando...' }); const video = await uploadVideo(id, file); setSelectedVideo(video.id); setToast({ type: 'success', text: 'Video enviado com sucesso' }); await load(); navigate(`/videos/${video.id}`) } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha no upload' }) } }
  const uploadUrl = async (id: number, url: string) => { try { setToast({ type: 'info', text: 'Baixando video...' }); const video = await importVideoFromUrl(id, url); setSelectedVideo(video.id); setToast({ type: 'success', text: 'Video enviado com sucesso' }); await load(); navigate(`/videos/${video.id}`) } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao processar URL' }) } }
  const removeProject = async (id: number) => { if (!window.confirm('Tem certeza que deseja excluir este projeto?')) return; try { await deleteProject(id); setToast({ type: 'success', text: 'Projeto excluido' }); await load(); navigate('/projects') } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao excluir projeto' }) } }
  const start = async (id: number) => { try { await startVideo(id); setToast({ type: 'success', text: 'Processamento iniciado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao iniciar' }) } }
  const pause = async (id: number) => { try { await pauseVideo(id); setToast({ type: 'success', text: 'Processamento pausado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao pausar' }) } }
  const resume = async (id: number) => { try { await resumeVideo(id); setToast({ type: 'success', text: 'Processamento retomado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao retomar' }) } }
  const restart = async (id: number) => { if (!window.confirm('Tem certeza que deseja reiniciar o processamento? Os clips atuais serao substituidos.')) return; try { await restartVideo(id); setToast({ type: 'success', text: 'Processamento reiniciado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao reiniciar' }) } }
  const publishNow = async (clip: Clip) => { try { await publishClipNow(clip.id); setToast({ type: 'success', text: 'Clip adicionado a fila de publicacao.' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao publicar' }) } }
  const scheduleClip = async (clip: Clip, value: string) => { try { const when = new Date(value); if (Number.isNaN(when.getTime()) || when <= new Date()) throw new Error('Data de agendamento invalida.'); await scheduleClipPublication(clip.id, when.toISOString()); setToast({ type: 'success', text: `Publicacao agendada para ${when.toLocaleString()}` }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao agendar' }) } }
  const confirmPlan = async (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => { try { const result = await confirmPublicationSchedule({ clip_ids: clipIds, max_per_day: maxPerDay, start_date: startDate, times }); setToast({ type: 'success', text: `${result.created_publications || 0} clipes agendados` }); await load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao confirmar agendamento' }); throw e } }
  const cancelSchedule = async (id: number) => { if (!window.confirm('Cancelar este agendamento?')) return; try { await cancelPublication(id); setToast({ type: 'success', text: 'Agendamento cancelado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao cancelar' }) } }
  const editSchedule = async (id: number) => { const value = window.prompt('Nova data/hora ISO ou local para agendamento'); if (!value) return; try { const when = new Date(value); if (Number.isNaN(when.getTime()) || when <= new Date()) throw new Error('Data de agendamento invalida.'); await updatePublicationSchedule(id, when.toISOString()); setToast({ type: 'success', text: 'Agendamento atualizado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao editar' }) } }
  const disconnect = async () => { try { await disconnectYouTube(); setToast({ type: 'success', text: 'YouTube desconectado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel desconectar' }) } }
  const connect = async () => { try { setYoutubeConnecting(true); await startYouTubeAuth() } catch (e) { setYoutubeConnecting(false); setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel conectar a conta do YouTube.' }) } }
  const readNotifications = async () => { await markNotificationsRead(); setNotifications(notifications.map(n => ({ ...n, read: true }))) }
  const runTestNotification = async () => { const item = await testNotification(); setNotifications([item, ...notifications.filter(n => n.id !== item.id)]); setToast({ type: 'success', text: item.title }); showNativeNotification(item); playNotificationSound() }
  const savePubSettings = async (settings: PublicationSettings) => { try { await savePublicationSettings(settings); setToast({ type: 'success', text: 'Configuracoes salvas' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao salvar' }) } }

  useEffect(() => {
    const result = new URLSearchParams(location.search).get('youtube')
    if (result === 'connected') {
      setYoutubeConnecting(false)
      setToast({ type: 'success', text: 'YouTube conectado' })
      load()
      navigate('/settings', { replace: true })
    }
    if (result === 'error') {
      setYoutubeConnecting(false)
      setToast({ type: 'error', text: 'Nao foi possivel conectar a conta do YouTube.' })
      load()
      navigate('/settings', { replace: true })
    }
  }, [location.search, load, navigate, setToast])

  return <Shell health={health} refresh={load} notifications={notificationPrefs.history ? notifications : []} onReadNotifications={readNotifications}><Routes><Route path="/" element={<Dashboard health={health} projects={projects} videos={videos} />} /><Route path="/projects" element={<Projects projects={projects} videos={videos} selectProject={id => navigate(`/projects/${id}`)} onCreateProject={create} onDeleteProject={removeProject} />} /><Route path="/projects/:id" element={<ProjectRoute projects={projects} videos={videos} onVideo={openVideo} onUpload={upload} onUrl={uploadUrl} />} /><Route path="/videos" element={<Videos videos={videos} onVideo={openVideo} />} /><Route path="/videos/:id" element={<VideoRoute videos={videos} clips={clips} publicationSettings={publicationSettings} onStart={start} onPause={pause} onResume={resume} onRestart={restart} onPublishNow={publishNow} onSchedule={scheduleClip} onConfirmPlan={confirmPlan} />} /><Route path="/publications" element={<Publications publications={publications} onCancel={cancelSchedule} onEdit={editSchedule} />} /><Route path="/publications/:id" element={<PublicationRoute publications={publications} />} /><Route path="/settings" element={<Settings health={health} youtube={youtube} connecting={youtubeConnecting} publicationSettings={publicationSettings} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} onNotificationPref={updateNotificationPref} onTestNotification={runTestNotification} onConnect={connect} onDisconnect={disconnect} onSavePublicationSettings={savePubSettings} />} /></Routes>{toast && <div className={`toast ${toast.type}`} onAnimationEnd={() => setToast(null)}>{toast.text}</div>}</Shell>
}
export default App
