import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { API_BASE_URL } from './api/client'
import { listVideoClips, stylePreviewUrl, suggestClipStyle, updateClipStyle } from './api/clips'
import { getHealth } from './api/health'
import { listNotifications, markNotificationsRead, testNotification } from './api/notifications'
import { cancelPublication, confirmPublicationSchedule, disconnectYouTube, getPublicationSettings, getYouTubeAccount, listPublications, previewPublicationSchedule, publishClipNow, savePublicationSettings, scheduleClipPublication, startYouTubeAuth, suggestPublicationTimes, updatePublicationSchedule } from './api/publications'
import { createProject, deleteProject, listProjects } from './api/projects'
import { cancelDownload, importVideoFromUrl, listVideos, pauseVideo, readUrlMetadata, restartVideo, resumeVideo, retryVideoPublicationPlan, startVideo, suggestClipConfig, uploadVideo } from './api/videos'
import type { DownloadProgressItem } from './api/videos'
import type { UploadPublicationPlan } from './api/videos'
import type { Clip } from './types/clip'
import type { Health } from './types/health'
import type { AxisNotification } from './types/notification'
import type { Publication, PublicationSchedulePlan, PublicationSettings, YouTubeAccount } from './types/publication'
import type { Project } from './types/projects'
import type { Video } from './types/video'
import './App.css'

const POLL_MS = Number(import.meta.env.VITE_POLL_INTERVAL || 8000)
const STALE_AFTER_MS = Number(import.meta.env.VITE_STALE_AFTER_MS || 120000)
type Toast = { type: 'success' | 'error' | 'warning' | 'info'; text: string }
type NotificationPrefs = { enabled: boolean; system: boolean; sound: boolean; background: boolean; history: boolean }
type StyleRecommendation = { recommended_style: string; confidence: number; reason: string; editing_direction: string[] }
type ClipDraftConfig = { count: number; duration: number; aiReason?: string; aiConfidence?: number }

const EDITING_STYLES = [
  { id: 'AUTO', name: 'Auto', description: 'A IA escolhe o melhor estilo para cada clip.' },
  { id: 'DRAMATIC', name: 'Dramatico', description: 'Contraste maior, zoom progressivo e captions fortes.' },
  { id: 'HAPPY', name: 'Alegre', description: 'Cores vivas, ritmo leve e captions amigaveis.' },
  { id: 'ENERGETIC', name: 'Energetico', description: 'Ritmo rapido, zooms mais fortes e visual dinamico.' },
  { id: 'CINEMATIC', name: 'Cinematico', description: 'Color grading refinado, zoom lento e transicoes suaves.' },
  { id: 'PODCAST', name: 'Podcast', description: 'Legibilidade alta, poucos efeitos e foco nos participantes.' },
  { id: 'CLEAN', name: 'Clean', description: 'Poucos efeitos, enquadramento estavel e foco no conteudo.' },
]
let openModalCount = 0

function styleName(style?: string | null) {
  return EDITING_STYLES.find(item => item.id === String(style || 'AUTO').toUpperCase())?.name || 'Auto'
}

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
function normalizeUniqueTimes(times: string[]) {
  return Array.from(new Set(times.map(item => item.trim()).filter(Boolean))).sort()
}
function addMinutesToTime(value: string, minutes: number) {
  const [hour, minute] = value.split(':').map(Number)
  const total = Math.min((23 * 60) + 59, Math.max(0, (hour * 60) + minute + minutes))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}
function expandPublicationTimes(times: string[], maxPerDay: number, intervalMinutes = 30) {
  const base = normalizeUniqueTimes(times)
  if (!base.length || maxPerDay <= base.length) return base
  const expanded: string[] = []
  let cycle = 0
  while (expanded.length < maxPerDay && cycle < 48) {
    for (const time of base) {
      const next = addMinutesToTime(time, cycle * intervalMinutes)
      if (!expanded.includes(next)) expanded.push(next)
      if (expanded.length >= maxPerDay) break
    }
    cycle += 1
  }
  return expanded.sort()
}
function nextAvailableTime(times: string[]) {
  const base = normalizeUniqueTimes(times)
  for (const candidate of ['09:00', '13:00', '18:00', '21:00', '09:30', '13:30', '18:30', '21:30']) {
    if (!base.includes(candidate)) return candidate
  }
  return addMinutesToTime(base[base.length - 1] || '09:00', 30)
}
function Modal({ title, subtitle, onClose, footer, children, className = '', closeDisabled = false }: { title: string; subtitle?: string; onClose: () => void; footer?: ReactNode; children: ReactNode; className?: string; closeDisabled?: boolean }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !closeDisabled) onClose()
    }
    openModalCount += 1
    document.body.classList.add('modal-open')
    window.addEventListener('keydown', onKey)
    return () => {
      openModalCount = Math.max(0, openModalCount - 1)
      if (openModalCount === 0) document.body.classList.remove('modal-open')
      window.removeEventListener('keydown', onKey)
    }
  }, [closeDisabled, onClose])
  return <div className="modal" role="presentation" onMouseDown={() => !closeDisabled && onClose()}><section className={`player modal-shell ${className}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={event => event.stopPropagation()}><header className="modal-header"><div><h2>{title}</h2>{subtitle && <p className="muted">{subtitle}</p>}</div><button className="close" aria-label="Fechar" disabled={closeDisabled} onClick={onClose}>×</button></header><div className="modal-body">{children}</div>{footer && <footer className="modal-footer">{footer}</footer>}</section></div>
}
function defaultClipCount(duration?: number | null) {
  if (!duration || duration <= 0) return 1
  return Math.max(1, Math.round(duration / 60))
}
function formatDuration(seconds?: number | null) {
  if (!seconds || seconds <= 0) return '-'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return minutes ? `${minutes}:${String(rest).padStart(2, '0')}` : `0:${String(rest).padStart(2, '0')}`
}
function durationLabel(seconds: number) {
  if (seconds < 60) return `${seconds} segundos`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest ? `${minutes}m${String(rest).padStart(2, '0')}` : `${minutes} minuto${minutes > 1 ? 's' : ''}`
}
function compactName(value?: string | null) {
  if (!value) return 'video'
  try {
    const url = new URL(value)
    return url.hostname.replace(/^www\./, '') || value
  } catch {
    return value.split(/[\\/]/).pop() || value
  }
}
function bytesLabel(value?: number | null) {
  if (!value) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`
}
function etaLabel(value?: number | null) {
  if (!value) return '-'
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`
}
function timeAgo(value?: string | null) {
  if (!value) return 'sem registro'
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 5) return 'agora'
  if (seconds < 60) return `ha ${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `ha ${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `ha ${hours} h`
}
function isVideoStale(video: Video) {
  if (video.status !== 'PROCESSING') return false
  const last = video.last_progress_at || video.last_heartbeat
  if (!last) return true
  return Date.now() - new Date(last).getTime() > STALE_AFTER_MS
}
function clipConfigFromDuration(duration?: number | null): ClipDraftConfig {
  return { count: defaultClipCount(duration), duration: 60 }
}

function StylePicker({ value, onChange, previewClip, onSuggest }: { value: string; onChange: (style: string) => void; previewClip?: Clip; onSuggest?: () => Promise<StyleRecommendation | null> }) {
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [recommendation, setRecommendation] = useState<StyleRecommendation | null>(null)
  const [suggesting, setSuggesting] = useState(false)
  const suggest = async () => {
    if (!onSuggest) return
    setSuggesting(true)
    try {
      setRecommendation(await onSuggest())
    } finally {
      setSuggesting(false)
    }
  }
  return <div className="style-section"><div><span className="eyebrow">Estilo de edicao</span><strong>{styleName(value)}</strong><p className="muted">{EDITING_STYLES.find(item => item.id === value)?.description || 'Preset automatico por clip.'}</p></div><div className="actions"><button onClick={suggest} disabled={!onSuggest || suggesting}>{suggesting ? 'Analisando...' : '✨ Sugerir com IA'}</button><button onClick={() => setGalleryOpen(true)}>Escolher estilo</button></div>{recommendation && <div className="ai-result"><span>✨ Sugestao da IA</span><strong>{styleName(recommendation.recommended_style)}</strong><p>Confianca: {Math.round(recommendation.confidence * 100)}%</p><p>{recommendation.reason}</p><ul>{recommendation.editing_direction.map(item => <li key={item}>{item}</li>)}</ul><div className="actions"><button className="primary" onClick={() => onChange(recommendation.recommended_style)}>Aplicar estilo</button><button onClick={() => setGalleryOpen(true)}>Ver preview</button><button onClick={() => setRecommendation(null)}>Escolher outro</button></div></div>}{galleryOpen && <StyleGalleryModal selected={value} previewClip={previewClip} onClose={() => setGalleryOpen(false)} onSelect={style => { onChange(style); setGalleryOpen(false) }} />}</div>
}

function StyleGalleryModal({ selected, previewClip, onClose, onSelect }: { selected: string; previewClip?: Clip; onClose: () => void; onSelect: (style: string) => void }) {
  const [previewStyle, setPreviewStyle] = useState<string | null>(null)
  return <Modal title="Escolha o estilo de edicao" subtitle="O preview usa o mesmo pipeline de renderizacao sempre que ha clip disponivel." onClose={onClose} className="style-modal" footer={<button onClick={onClose}>Fechar</button>}><div className="style-grid">{EDITING_STYLES.map(style => <article className={`style-card ${selected === style.id ? 'selected' : ''}`} key={style.id}><div className={`style-swatch ${style.id.toLowerCase()}`}>{selected === style.id ? '✓ Selecionado' : style.name}</div><h3>{style.name}</h3><p className="muted">{style.description}</p><div className="actions"><button disabled={!previewClip || style.id === 'AUTO'} onClick={() => setPreviewStyle(style.id)}>Visualizar</button><button className="primary" onClick={() => onSelect(style.id)}>Selecionar</button></div></article>)}</div>{previewStyle && previewClip && <Modal title={`Preview ${styleName(previewStyle)}`} onClose={() => setPreviewStyle(null)} className="style-preview-modal"><div className="segmented"><button className="active">EDITADO</button><button disabled>ORIGINAL</button></div><video src={`${API_BASE_URL}${stylePreviewUrl(previewClip.id, previewStyle)}`} controls /></Modal>}</Modal>
}

function Shell({ health, refresh, notifications, onReadNotifications, onClearNotifications, children }: { health?: Health; refresh: () => void; notifications: AxisNotification[]; onReadNotifications: () => void; onClearNotifications: () => void; children: ReactNode }) {
  const nav = [['/', 'Dashboard'], ['/projects', 'Projetos'], ['/videos', 'Videos'], ['/publications', 'Publicacoes'], ['/settings', 'Configuracoes']]
  const online = health?.status === 'ok'
  return <div className="app"><aside className="sidebar"><div className="brand">AxisClip</div><nav>{nav.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'active' : ''}>{label}</NavLink>)}</nav></aside><section className="workspace"><header className="topbar"><div><strong>AxisClip</strong><span className={online ? 'dot on' : 'dot off'}>{online ? 'ONLINE' : 'OFFLINE'}</span></div><div className="top-actions"><NotificationBell notifications={notifications} onRead={onReadNotifications} onClear={onClearNotifications} /><button onClick={refresh}>Atualizar</button></div></header><main>{children}</main></section><DownloadProgress /></div>
}

function NotificationBell({ notifications, onRead, onClear }: { notifications: AxisNotification[]; onRead: () => void; onClear: () => void }) {
  const [open, setOpen] = useState(false)
  const unread = notifications.filter(n => !n.read).length
  const toggle = () => { const next = !open; setOpen(next); if (next && unread) onRead() }
  return <div className="notification-wrap"><button className="bell" aria-label="Notificacoes" onClick={toggle}>○{unread > 0 && <b>{unread}</b>}</button>{open && <div className="notification-panel"><div className="notification-head"><strong>Notificacoes</strong><span>{notifications.length}</span></div><div className="notification-actions"><button disabled={!unread} onClick={onRead}>Marcar todas como lidas</button><button disabled={!notifications.length} onClick={onClear}>Limpar notificacoes</button></div>{notifications.length === 0 ? <p className="muted">Voce esta em dia.</p> : notifications.map(n => <article className={`notification ${n.type.toLowerCase()}`} key={n.id}><div><strong>{n.title}</strong><span>{fmtDate(n.created_at)}</span></div><p>{n.message}</p>{n.platform && <span className="badge">{platformName(n.platform)}</span>}{n.url && <a href={n.url} target="_blank" rel="noopener noreferrer">Abrir no {platformName(n.platform)}</a>}</article>)}</div>}</div>
}

function DownloadProgress() {
  const [items, setItems] = useState<Record<string, DownloadProgressItem>>({})
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/videos/downloads/events`)
    const update = (event: MessageEvent) => {
      const item = JSON.parse(event.data) as DownloadProgressItem
      setItems(current => ({ ...current, [item.download_id]: item }))
      if (item.status === 'completed' || item.status === 'cancelled') {
        window.setTimeout(() => {
          setItems(current => {
            const next = { ...current }
            delete next[item.download_id]
            return next
          })
        }, 3500)
      }
    }
    source.addEventListener('DOWNLOAD_STARTED', update)
    source.addEventListener('DOWNLOAD_PROGRESS', update)
    source.addEventListener('DOWNLOAD_COMPLETED', update)
    source.addEventListener('DOWNLOAD_ERROR', update)
    source.addEventListener('DOWNLOAD_CANCELLED', update)
    const uploadUpdate = (event: Event) => {
      const item = (event as CustomEvent<DownloadProgressItem>).detail
      setItems(current => ({ ...current, [item.download_id]: item }))
      if (item.status === 'completed') {
        window.setTimeout(() => {
          setItems(current => {
            const next = { ...current }
            delete next[item.download_id]
            return next
          })
        }, 2500)
      }
    }
    window.addEventListener('axisclip-upload-progress', uploadUpdate)
    return () => {
      source.close()
      window.removeEventListener('axisclip-upload-progress', uploadUpdate)
    }
  }, [])
  const downloads = Object.values(items)
  if (!downloads.length) return null
  const active = downloads.filter(item => item.status === 'downloading')
  const primary = active[0] || downloads[0]
  const determined = typeof primary.progress === 'number' && typeof primary.total_bytes === 'number'
  const isUpload = primary.transfer_type === 'upload' || primary.status === 'uploading'
  const label = primary.status === 'completed' ? (isUpload ? 'Upload concluido' : 'Download concluido') : primary.status === 'error' ? 'Falha no download' : primary.status === 'cancelled' ? 'Download cancelado' : isUpload ? 'Enviando video' : active.length > 1 ? `Baixando ${active.length} videos` : 'Baixando video'
  const accessible = determined ? `${isUpload ? 'Enviando' : 'Baixando'} video, ${Math.round(primary.progress || 0)} por cento concluido.` : `${label}. Progresso indeterminado.`
  const cancel = async (id: string) => {
    try {
      await cancelDownload(id)
    } catch {
      return
    }
  }
  return <aside className={`download-progress ${expanded ? 'expanded' : ''}`} aria-live="polite"><div className="download-head"><span className={`download-icon ${primary.status}`}>{primary.status === 'completed' ? '✓' : primary.status === 'error' ? '×' : primary.status === 'cancelled' ? '!' : isUpload ? '↑' : '↓'}</span><div><strong>{label}</strong><p>{compactName(primary.filename)}</p></div>{determined && <b>{Math.round(primary.progress || 0)}%</b>}</div><div className={`download-bar ${determined ? '' : 'indeterminate'}`} role="progressbar" aria-label={accessible} aria-valuemin={determined ? 0 : undefined} aria-valuemax={determined ? 100 : undefined} aria-valuenow={determined ? Math.round(primary.progress || 0) : undefined}><span style={determined ? { width: `${primary.progress}%` } : undefined} /></div><div className="download-meta"><span>{bytesLabel(primary.downloaded_bytes)} / {bytesLabel(primary.total_bytes)}</span><span>{bytesLabel(primary.speed_bytes)}/s</span><span>{etaLabel(primary.eta_seconds)}</span></div>{primary.message && <p className="error-text">{primary.message}</p>}<div className="download-actions"><button onClick={() => setExpanded(!expanded)}>detalhes</button>{primary.status === 'downloading' && <button onClick={() => cancel(primary.download_id)}>Cancelar</button>}</div>{expanded && downloads.length > 1 && <div className="download-list">{downloads.map(item => { const hasProgress = typeof item.progress === 'number' && typeof item.total_bytes === 'number'; return <article key={item.download_id}><div><strong>{compactName(item.filename)}</strong>{hasProgress && <b>{Math.round(item.progress || 0)}%</b>}</div><div className={`download-bar ${hasProgress ? '' : 'indeterminate'}`} role="progressbar" aria-label={hasProgress ? `${Math.round(item.progress || 0)} por cento concluido.` : 'Progresso indeterminado.'} aria-valuemin={hasProgress ? 0 : undefined} aria-valuemax={hasProgress ? 100 : undefined} aria-valuenow={hasProgress ? Math.round(item.progress || 0) : undefined}><span style={hasProgress ? { width: `${item.progress}%` } : undefined} /></div></article> })}</div>}</aside>
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

function ProjectDetail({ project, videos, onVideo, onUpload, onUrl }: { project?: Project; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File, plan?: UploadPublicationPlan | null) => void; onUrl: (id: number, url: string, plan?: UploadPublicationPlan | null) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<'file' | 'url'>('file')
  const [url, setUrl] = useState('')
  const [detectedDuration, setDetectedDuration] = useState<number | null>(null)
  const [detectingUrl, setDetectingUrl] = useState(false)
  const [clipConfig, setClipConfig] = useState<ClipDraftConfig>(clipConfigFromDuration(null))
  const [clipError, setClipError] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)
  const [publicationPlan, setPublicationPlan] = useState<UploadPublicationPlan | null>(null)
  const own = videos.filter(v => v.project_id === project?.id)
  const applyDuration = (duration: number | null) => { setDetectedDuration(duration); setClipConfig(config => ({ ...clipConfigFromDuration(duration), aiReason: config.aiReason, aiConfidence: config.aiConfidence })) }
  const selectedPlan = { ...(publicationPlan || { enabled: false, maxPerDay: 10, startDate: todayInputDate(), times: ['09:00', '13:00', '18:00', '21:00'], timezone: 'America/Sao_Paulo', editingStyle: 'AUTO' }), targetClipCount: clipConfig.count, targetClipDuration: clipConfig.duration }
  const updateFile = (next: File | null) => {
    setFile(next)
    setClipError('')
    if (!next) return applyDuration(null)
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.onloadedmetadata = () => { URL.revokeObjectURL(video.src); applyDuration(video.duration) }
    video.onerror = () => { URL.revokeObjectURL(video.src); setClipError('Nao foi possivel detectar a duracao deste arquivo.') }
    video.src = URL.createObjectURL(next)
  }
  const detectUrl = async (value: string) => {
    const clean = value.trim()
    setUrl(value)
    setClipError('')
    if (!clean.startsWith('http')) return applyDuration(null)
    setDetectingUrl(true)
    try {
      const result = await readUrlMetadata(clean)
      applyDuration(result.duration)
      if (!result.duration) setClipError('Nao foi possivel detectar a duracao da URL.')
    } catch (e) {
      setClipError(e instanceof Error ? e.message : 'Nao foi possivel detectar a duracao da URL.')
    } finally {
      setDetectingUrl(false)
    }
  }
  const setCount = (value: number) => { setClipError(''); setClipConfig(config => ({ ...config, count: Math.max(1, value || 1) })) }
  const setDuration = (value: number) => { setClipError(''); setClipConfig(config => ({ ...config, duration: Math.min(180, Math.max(15, value || 60)) })) }
  const suggest = async () => {
    if (!detectedDuration) return setClipError('Detecte a duracao antes de pedir sugestao da IA.')
    setAiLoading(true)
    try {
      const result = await suggestClipConfig(detectedDuration)
      setClipConfig({ count: result.recommended_count, duration: result.recommended_duration_seconds, aiReason: result.reason, aiConfidence: result.confidence })
    } catch (e) {
      setClipError(e instanceof Error ? e.message : 'Nao foi possivel gerar sugestao com IA.')
    } finally {
      setAiLoading(false)
    }
  }
  const submitFile = () => file && onUpload(project!.id, file, selectedPlan)
  const submitUrl = () => onUrl(project!.id, url, selectedPlan)
  if (!project) return <Empty text="Projeto nao encontrado" />
  return <Page title={project.name} subtitle={`${own.length} videos`}><div className="panel upload simple-upload" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setMode('file'); updateFile(e.dataTransfer.files[0] || null) }}><div className="segmented"><button className={mode === 'file' ? 'active' : ''} onClick={() => setMode('file')}>Arquivo</button><button className={mode === 'url' ? 'active' : ''} onClick={() => setMode('url')}>URL</button></div>{mode === 'file' ? <><label>Adicionar video MP4<input type="file" accept="video/mp4" onChange={e => updateFile(e.target.files?.[0] || null)} /></label>{file && <p>{file.name} - {(file.size / 1024 / 1024).toFixed(1)} MB</p>}</> : <label>URL do video<input value={url} onChange={e => setUrl(e.target.value)} onBlur={e => detectUrl(e.target.value)} placeholder="https://..." /></label>}<div className="clip-config-panel"><div className="planner-metrics"><Info label="Duracao detectada" value={detectingUrl ? 'Detectando...' : formatDuration(detectedDuration)} /><Info label="Clips planejados" value={String(clipConfig.count)} /><Info label="Duracao alvo" value={formatDuration(clipConfig.duration)} /></div>{detectedDuration && <div className="ai-result"><span>Sugestao do Axis Clips</span><strong>{defaultClipCount(detectedDuration)} clips</strong><p>{Math.round(detectedDuration / 60)} minutos - {defaultClipCount(detectedDuration)} clips - ~1 minuto por clip</p></div>}<div className="clip-controls"><label>Quantidade de clips<input type="number" min="1" value={clipConfig.count} onChange={e => setCount(Number(e.target.value))} /></label><label>Duracao dos clips<select value={clipConfig.duration} onChange={e => setDuration(Number(e.target.value))}><option value={30}>30 segundos</option><option value={45}>45 segundos</option><option value={60}>1 minuto</option><option value={90}>1m30</option><option value={120}>2 minutos</option><option value={150}>2m30</option><option value={180}>3 minutos</option></select></label></div><div className="actions"><button onClick={suggest} disabled={!detectedDuration || aiLoading}>{aiLoading ? 'Analisando...' : 'Sugerir com IA'}</button><button onClick={() => setPlanOpen(true)}>Configurar postagem</button></div>{clipConfig.aiReason && <p className="muted">IA recomenda: {clipConfig.count} clips de aproximadamente {durationLabel(clipConfig.duration)}. {clipConfig.aiReason}</p>}{clipError && <p className="error-text">{clipError}</p>}</div><div className="upload-actions"><button disabled={mode === 'file' ? !file : !url.trim()} onClick={mode === 'file' ? submitFile : submitUrl}>{mode === 'file' ? 'Enviar' : 'Processar video'}</button></div>{publicationPlan?.enabled && <p className="muted">Postagem configurada: {publicationPlan.maxPerDay} videos/dia. Clips gerados: {clipConfig.count}. Estilo {styleName(publicationPlan.editingStyle)}.</p>}</div>{planOpen && <PreUploadPlanModal initial={publicationPlan} onClose={() => setPlanOpen(false)} onSave={plan => { setPublicationPlan(plan); setPlanOpen(false) }} />}<VideoList videos={own} onVideo={onVideo} /></Page>
}

function Videos({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <Page title="Videos" subtitle="Processamento"><VideoList videos={videos} onVideo={onVideo} /></Page>
}

function VideoList({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <div className="panel table">{videos.map(v => <button className="row" key={v.id} onClick={() => onVideo(v.id)}><span>Video #{v.id}</span><span>{v.processing_stage || v.status}</span><span>{v.duration ? `${v.duration}s` : '-'}</span><span>{fmtDate(v.created_at)}</span></button>)}</div>
}

function VideoDetail({ video, clips, publicationSettings, onStart, onPause, onResume, onRestart, onRetryPublicationPlan, onRefresh, onPublishNow, onSchedule, onConfirmPlan, onClipStyle }: { video?: Video; clips: Clip[]; publicationSettings?: PublicationSettings; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void; onRetryPublicationPlan: (id: number) => void; onRefresh: () => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfirmPlan: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void>; onClipStyle: (clip: Clip, style: string) => Promise<void> }) {
  const [playing, setPlaying] = useState<Clip | null>(null)
  const [planning, setPlanning] = useState(false)
  const schedulable = clips.filter(c => c.status === 'COMPLETED' && (!c.publication_status || c.publication_status === 'SCHEDULED'))
  const hasScheduled = clips.some(c => c.publication_status === 'SCHEDULED')
  if (!video) return <Empty text="Video nao encontrado" />
  return <Page title={`Video #${video.id}`} subtitle={video.file_path}><div className="panel"><div className="video-actions"><span className={statusClass(video.status)}>{video.status}</span>{video.status === 'PENDING' && <button onClick={() => onStart(video.id)}>Iniciar</button>}{video.status === 'PROCESSING' && <button onClick={() => onPause(video.id)}>Pausar</button>}{video.status === 'PAUSED' && <button onClick={() => onResume(video.id)}>Retomar</button>}{['COMPLETED'].includes(video.status) && <button className="danger" onClick={() => onRestart(video.id)}>Reiniciar</button>}</div><PipelineProgress video={video} onRefresh={onRefresh} onResume={onResume} onRestart={onRestart} onRetryPublicationPlan={onRetryPublicationPlan} /></div>{schedulable.length > 0 && <div className="panel plan-strip"><div><strong>{schedulable.length} clipes prontos</strong><p className="muted">Planeje publicacoes em lote para o YouTube.</p></div><button className="primary" onClick={() => setPlanning(true)}>{hasScheduled ? 'EDITAR AGENDAMENTO' : 'CONFIGURAR PUBLICACOES'}</button></div>}<ClipGallery clips={clips} publicationSettings={publicationSettings} onPlay={setPlaying} onPublishNow={onPublishNow} onSchedule={onSchedule} onConfigurePlan={() => setPlanning(true)} onClipStyle={onClipStyle} />{planning && <PublicationPlannerModal clips={schedulable} settings={publicationSettings} onClose={() => setPlanning(false)} onConfirm={async (clipIds, maxPerDay, startDate, times) => { await onConfirmPlan(clipIds, maxPerDay, startDate, times); setPlanning(false) }} />}{playing && <Player clip={playing} onClose={() => setPlaying(null)} />}</Page>
}

function ClipGallery({ clips, publicationSettings, onPlay, onPublishNow, onSchedule, onConfigurePlan, onClipStyle }: { clips: Clip[]; publicationSettings?: PublicationSettings; onPlay: (clip: Clip) => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfigurePlan: () => void; onClipStyle: (clip: Clip, style: string) => Promise<void> }) {
  const [uploading, setUploading] = useState<Clip | null>(null)
  const [scheduledClip, setScheduledClip] = useState<Clip | null>(null)
  const scheduledOrder = clips.filter(c => c.publication_scheduled_at).sort((a, b) => String(a.publication_scheduled_at).localeCompare(String(b.publication_scheduled_at)))
  const positionFor = (clip: Clip) => Math.max(1, scheduledOrder.findIndex(item => item.id === clip.id) + 1)
  return <><div className="cards clips">{clips.map(c => <article className="clip-card" key={c.id}><div className="thumb"><img loading="lazy" src={`${API_BASE_URL}${c.thumbnail_url}`} alt={clipTitle(c)} /><div className="thumb-badges"><span className={statusClass(c.status)}>{c.status}</span>{c.publication_status && <span className={statusClass(c.publication_status || undefined)}>{c.publication_status === 'SCHEDULED' ? 'AGENDADO' : c.publication_status === 'FAILED' ? 'ERRO' : c.publication_status}</span>}</div></div><div className="clip-body"><h3>{clipTitle(c)}</h3><p className="muted">Trecho #{c.id}</p><div className="meta"><span>{c.duration}s</span><span>{platformName(c.publication_platform || 'YOUTUBE')}</span><span>{styleName(c.applied_preset || c.editing_style)}</span>{c.publication_scheduled_at && <span>{fmtScheduleShort(c.publication_scheduled_at)}</span>}</div><label className="compact-label">Estilo<select value={c.editing_style || 'AUTO'} onChange={e => onClipStyle(c, e.target.value)}>{EDITING_STYLES.map(style => <option key={style.id} value={style.id}>{style.name}</option>)}</select></label>{c.publication_status === 'FAILED' && <p className="error-text">Motivo: {publicationErrorText(c)}</p>}<div className="actions"><button className="primary" aria-label={`Assistir ${clipTitle(c)}`} onClick={() => onPlay(c)}>Assistir</button>{c.publication_status === 'SCHEDULED' ? <button onClick={() => setScheduledClip(c)}>AGENDADO</button> : c.publication_status === 'PUBLISHED' && c.publication_url ? <a href={c.publication_url} target="_blank" rel="noopener noreferrer">Publicado</a> : ['UPLOADING', 'PROCESSING', 'WAITING_RETRY'].includes(String(c.publication_status)) ? <span className={statusClass(c.publication_status || undefined)}>{c.publication_status}</span> : c.publication_status === 'FAILED' ? <button onClick={() => onPublishNow(c)}>Republicar</button> : <><button onClick={onConfigurePlan}>CONFIGURAR</button><button onClick={() => onPublishNow(c)}>Fazer upload</button></>}</div></div></article>)}</div>{uploading && <UploadModal clip={uploading} tiktokEnabled={Boolean(publicationSettings?.tiktok_enabled)} onClose={() => setUploading(null)} onPublishNow={clip => { onPublishNow(clip); setUploading(null) }} onSchedule={(clip, value) => { onSchedule(clip, value); setUploading(null) }} />}{scheduledClip && <ScheduledClipModal clip={scheduledClip} position={positionFor(scheduledClip)} onClose={() => setScheduledClip(null)} />}</>
}

function ScheduledClipModal({ clip, position, onClose }: { clip: Clip; position: number; onClose: () => void }) {
  return <Modal title="Agendado" onClose={onClose} className="scheduled-modal" footer={<button onClick={onClose}>Fechar</button>}><div className="panel grid2"><Info label="Clip" value={`Trecho #${clip.id}`} /><Info label="Plataforma" value={platformName(clip.publication_platform || 'YOUTUBE')} /><Info label="Data e horario" value={fmtDate(clip.publication_scheduled_at || undefined)} /><Info label="Posicao" value={String(position)} /></div>{clip.publication_url && <div className="panel"><a href={clip.publication_url} target="_blank" rel="noopener noreferrer">Abrir publicacao</a></div>}</Modal>
}

function UploadModal({ clip, tiktokEnabled, onClose, onPublishNow, onSchedule }: { clip: Clip; tiktokEnabled: boolean; onClose: () => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void }) {
  const [scheduledAt, setScheduledAt] = useState('')
  return <Modal title={clipTitle(clip)} subtitle={`${clip.duration}s`} onClose={onClose} className="upload-modal" footer={<><button onClick={onClose}>Cancelar</button><button disabled={!scheduledAt} onClick={() => onSchedule(clip, scheduledAt)}>Agendar</button></>}><img src={`${API_BASE_URL}${clip.thumbnail_url}`} alt={clipTitle(clip)} /><div className="panel"><h3>YouTube</h3><div className="actions"><button className="primary" onClick={() => window.confirm('Publicar este clip agora?') && onPublishNow(clip)}>Publicar agora</button></div><label>Agendar<input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} /></label></div><div className="panel"><h3>TikTok</h3><button disabled={!tiktokEnabled}>Indisponivel</button></div></Modal>
}

function PreUploadPlanModal({ initial, onClose, onSave }: { initial?: UploadPublicationPlan | null; onClose: () => void; onSave: (plan: UploadPublicationPlan) => void }) {
  const [maxPerDay, setMaxPerDay] = useState(initial?.maxPerDay || 10)
  const [startDate, setStartDate] = useState(initial?.startDate || todayInputDate())
  const [times, setTimes] = useState(initial?.times?.length ? initial.times : ['09:00', '13:00', '18:00', '21:00'])
  const [timezone, setTimezone] = useState(initial?.timezone || 'America/Sao_Paulo')
  const [editingStyle, setEditingStyle] = useState(initial?.editingStyle || 'AUTO')
  const [error, setError] = useState('')
  const effectiveTimes = useMemo(() => expandPublicationTimes(times, maxPerDay), [times, maxPerDay])
  const needsDistribution = maxPerDay > normalizeUniqueTimes(times).length
  const setTimeAt = (index: number, value: string) => setTimes(items => items.map((item, itemIndex) => itemIndex === index ? value : item))
  const addTime = () => setTimes(items => [...items, nextAvailableTime(items)])
  const distribute = () => setTimes(effectiveTimes)
  const removeTime = (index: number) => setTimes(items => items.length > 1 ? items.filter((_, itemIndex) => itemIndex !== index) : items)
  const suggest = async () => {
    try {
      const result = await suggestPublicationTimes(maxPerDay)
      setTimes(result.times)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nao foi possivel sugerir horarios.')
    }
  }
  const save = () => {
    const cleaned = normalizeUniqueTimes(times)
    if (maxPerDay <= 0) return setError('Videos por dia deve ser maior que zero.')
    if (!startDate) return setError('Informe a data inicial.')
    if (times.some(item => !item)) return setError('Horario invalido.')
    if (cleaned.length !== times.length) return setError('Horarios duplicados nao sao permitidos.')
    onSave({ enabled: true, maxPerDay, startDate, times: effectiveTimes, timezone, editingStyle })
  }
  return <Modal title="Planejamento de publicacoes" subtitle="Configure a publicacao automatica deste envio." onClose={onClose} className="preupload-modal" footer={<><button onClick={onClose}>Cancelar</button><button className="primary" onClick={save}>Salvar configuracao</button></>}><StylePicker value={editingStyle} onChange={setEditingStyle} /><label>Videos por dia<input type="number" min="1" value={maxPerDay} onChange={e => setMaxPerDay(Math.max(1, Number(e.target.value) || 1))} /></label><label>Data inicial<input type="date" min={todayInputDate()} value={startDate} onChange={e => setStartDate(e.target.value)} /></label><label>Fuso horario<input value={timezone} onChange={e => setTimezone(e.target.value)} /></label><div className="time-editor"><span>Horarios principais</span><div>{times.map((item, index) => <label key={`${index}-${item}`}>Horario {index + 1}<input type="time" value={item} onChange={e => setTimeAt(index, e.target.value)} /><button type="button" onClick={() => removeTime(index)}>Remover</button></label>)}</div></div><div className="actions"><button onClick={addTime}>+ Adicionar horario</button><button onClick={suggest}>Sugerir horarios</button></div>{needsDistribution && <div className="planner-notice"><strong>{normalizeUniqueTimes(times).length} horarios principais encontrados.</strong><p>Deseja distribuir os {maxPerDay} videos automaticamente?</p><button onClick={distribute}>Distribuir automaticamente</button></div>}<div className="panel planner-config"><h3>Horarios reais do dia</h3><div className="time-chip-list">{effectiveTimes.map(item => <small key={item}>{item}</small>)}</div></div>{error && <p className="error-text">{error}</p>}</Modal>
}

function PublicationPlannerModal({ clips, settings, onClose, onConfirm }: { clips: Clip[]; settings?: PublicationSettings; onClose: () => void; onConfirm: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void> }) {
  const [maxPerDay, setMaxPerDay] = useState(Math.max(1, settings?.max_uploads_per_day || 10))
  const [startDate, setStartDate] = useState(todayInputDate())
  const [times, setTimes] = useState(settings?.publish_schedule?.length ? settings.publish_schedule : ['09:00', '13:00', '18:00', '21:00'])
  const [editingStyle, setEditingStyle] = useState('AUTO')
  const [plan, setPlan] = useState<PublicationSchedulePlan | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const clipIds = useMemo(() => clips.map(c => c.id), [clips])
  const effectiveTimes = useMemo(() => expandPublicationTimes(times, maxPerDay), [times, maxPerDay])
  const uniqueBaseTimes = useMemo(() => normalizeUniqueTimes(times), [times])
  const needsDistribution = maxPerDay > uniqueBaseTimes.length

  const refreshPlan = useCallback(async () => {
    try {
      setError('')
      setPlan(await previewPublicationSchedule({ clip_ids: clipIds, max_per_day: maxPerDay, start_date: startDate, times: effectiveTimes }))
    } catch (e) {
      setPlan(null)
      setError(e instanceof Error ? e.message : 'Nao foi possivel calcular o planejamento.')
    }
  }, [clipIds, effectiveTimes, maxPerDay, startDate])

  useEffect(() => { refreshPlan() }, [refreshPlan])

  const setTimeAt = (index: number, value: string) => setTimes(items => items.map((item, itemIndex) => itemIndex === index ? value : item))
  const addTime = () => setTimes(items => [...items, nextAvailableTime(items)])
  const distribute = () => setTimes(effectiveTimes)
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
      if (uniqueBaseTimes.length !== times.length) {
        setError('Horarios duplicados nao sao permitidos.')
        return
      }
      setSaving(true)
      if (editingStyle === 'AUTO') {
        for (const clip of clips) {
          const recommendation = await suggestClipStyle(clip.id)
          await updateClipStyle(clip.id, recommendation.recommended_style)
        }
      } else {
        for (const clip of clips) {
          await updateClipStyle(clip.id, editingStyle)
        }
      }
      await onConfirm(clipIds, maxPerDay, startDate, effectiveTimes)
    } finally {
      setSaving(false)
    }
  }

  return <Modal title="Planejamento de publicacoes" subtitle="Configure quando e quantos clips serao publicados." onClose={onClose} closeDisabled={saving} className="planner-modal" footer={<><button disabled={saving} onClick={onClose}>Cancelar</button><button className="primary" disabled={saving || !plan || plan.total_clips === 0} onClick={confirm}>{saving ? 'Renderizando...' : 'Confirmar agendamento'}</button></>}><StylePicker value={editingStyle} onChange={setEditingStyle} previewClip={clips[0]} onSuggest={async () => clips[0] ? suggestClipStyle(clips[0].id) : null} /><section className="planner-layout"><div className="panel planner-config"><h3>Configuracoes de publicacao</h3><Info label="Total de clips" value={String(clips.length)} /><label>Videos por dia<input type="number" min="1" value={maxPerDay} onChange={e => setMaxPerDay(Math.max(1, Number(e.target.value) || 1))} /></label><label>Data inicial<input type="date" min={todayInputDate()} value={startDate} onChange={e => setStartDate(e.target.value)} /></label><Info label="Fuso horario" value={settings?.publish_timezone || 'America/Sao_Paulo'} /><div className="time-editor"><span>Horarios principais</span><div>{times.map((item, index) => <label key={`${index}-${item}`}>Horario {index + 1}<input type="time" value={item} onChange={e => setTimeAt(index, e.target.value)} /><button type="button" onClick={() => removeTime(index)}>Remover</button></label>)}</div></div><div className="actions"><button onClick={addTime}>+ Adicionar horario</button><button onClick={suggest}>Sugerir horarios</button></div>{needsDistribution && <div className="planner-notice"><strong>{uniqueBaseTimes.length} horarios principais encontrados.</strong><p>Deseja distribuir os {maxPerDay} videos automaticamente?</p><button onClick={distribute}>Distribuir automaticamente</button></div>}</div><div className="panel planner-config"><h3>Resumo do planejamento</h3><div className="planner-metrics"><Stat label="Total" value={clips.length} /><Stat label="Por dia" value={maxPerDay} /><Stat label="Dias" value={plan?.estimated_days || 0} /></div><Info label="Horarios reais" value={String(effectiveTimes.length)} /><div className="time-chip-list">{effectiveTimes.map(item => <small key={item}>{item}</small>)}</div>{error && <p className="error-text">{error}</p>}<button onClick={refreshPlan}>Atualizar resumo</button></div></section><h3>Distribuicao dos dias</h3><div className="schedule-summary">{plan?.days.map((day, index) => <article key={day.date}><strong>Dia {index + 1}<br />{new Date(`${day.date}T12:00:00`).toLocaleDateString()}</strong><span>{day.count} clips</span><div>{plan.scheduled.filter(item => item.date === day.date).map((item, itemIndex) => <small key={`${day.date}-${item.clip_id}-${itemIndex}`}>{item.time} - Clip {String(item.clip_id).padStart(2, '0')}</small>)}</div></article>)}</div><h3>Clips gerados</h3><div className="planner-clips">{clips.map(clip => <article key={clip.id}><img src={`${API_BASE_URL}${clip.thumbnail_url}`} alt={clipTitle(clip)} /><div><strong>{clipTitle(clip)}</strong><span>Trecho #{clip.id} - {clip.duration}s - {styleName(clip.applied_preset || clip.editing_style)}</span></div></article>)}</div></Modal>
}

function Player({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  return <Modal title={clip.title} onClose={onClose}><video src={`${API_BASE_URL}${clip.stream_url}`} controls autoPlay /></Modal>
}

function Publications({ publications, onCancel, onEdit }: { publications: Publication[]; onCancel: (id: number) => void; onEdit: (id: number, value: string) => Promise<void> }) {
  const [section, setSection] = useState<'SCHEDULED' | 'PUBLISHED'>('SCHEDULED')
  const [filter, setFilter] = useState<'ALL' | 'SCHEDULED' | 'PUBLISHED' | 'CANCELLED' | 'FAILED'>('ALL')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Publication | null>(null)
  const grouped = section === 'SCHEDULED'
    ? publications.filter(p => p.scheduled_at && p.status !== 'PUBLISHED')
    : publications.filter(p => p.status === 'PUBLISHED')
  const filtered = grouped.filter(p => {
    const matchesFilter = filter === 'ALL' || p.status === filter
    const text = `${p.title || ''} ${p.clip_id} ${p.platform_post_id || ''}`.toLowerCase()
    return matchesFilter && text.includes(search.trim().toLowerCase())
  })
  return <Page title="Publicacoes" subtitle="Central de controle"><div className="publication-tabs"><button className={section === 'SCHEDULED' ? 'active' : ''} onClick={() => setSection('SCHEDULED')}>AGENDADOS</button><button className={section === 'PUBLISHED' ? 'active' : ''} onClick={() => setSection('PUBLISHED')}>PUBLICADOS</button></div><div className="panel publication-tools"><div className="segmented"><button className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>Todos</button><button className={filter === 'SCHEDULED' ? 'active' : ''} onClick={() => setFilter('SCHEDULED')}>Agendados</button><button className={filter === 'PUBLISHED' ? 'active' : ''} onClick={() => setFilter('PUBLISHED')}>Publicados</button><button className={filter === 'CANCELLED' ? 'active' : ''} onClick={() => setFilter('CANCELLED')}>Cancelados</button><button className={filter === 'FAILED' ? 'active' : ''} onClick={() => setFilter('FAILED')}>Erros</button></div><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar por titulo" /></div>{filtered.length === 0 ? <Empty text="Nenhuma publicacao encontrada" /> : <div className="publication-grid">{filtered.map(p => <PublicationCard key={p.id} publication={p} onEdit={() => setEditing(p)} onCancel={() => onCancel(p.id)} />)}</div>}{editing && <EditPublicationScheduleModal publication={editing} onClose={() => setEditing(null)} onSave={async value => { await onEdit(editing.id, value); setEditing(null) }} />}</Page>
}

function statusLabel(status: string) {
  if (status === 'SCHEDULED') return 'AGENDADO'
  if (status === 'PUBLISHED') return 'PUBLICADO'
  if (status === 'CANCELLED') return 'CANCELADO'
  if (status === 'FAILED') return 'ERRO'
  if (status === 'PROCESSING') return 'PROCESSANDO'
  return status
}

function youtubeWatchUrl(publication: Publication) {
  return publication.platform_post_id ? `https://www.youtube.com/watch?v=${publication.platform_post_id}` : publication.publication_url || '#'
}

function localDateInput(value?: string | null) {
  if (!value) return todayInputDate()
  return new Date(value).toLocaleDateString('en-CA')
}

function localTimeInput(value?: string | null) {
  if (!value) return '09:00'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

function PublicationCard({ publication, onEdit, onCancel }: { publication: Publication; onEdit: () => void; onCancel: () => void }) {
  const canEdit = publication.status === 'SCHEDULED'
  const canWatch = publication.status === 'PUBLISHED' && Boolean(publication.platform_post_id || publication.publication_url)
  return <article className="publication-card"><div className="publication-thumb">{publication.thumbnail_url ? <img src={`${API_BASE_URL}${publication.thumbnail_url}`} alt={publication.title || `Trecho #${publication.clip_id}`} /> : <div />}</div><div className="publication-body"><div><h3>{publication.title || `Trecho #${publication.clip_id}`}</h3><p className="muted">Trecho #{publication.clip_id}</p></div><div className="publication-meta"><span>{publication.duration ? `${publication.duration}s` : '-'}</span><span>{platformName(publication.platform)}</span><span className={statusClass(publication.status)}>{statusLabel(publication.status)}</span></div>{publication.status === 'SCHEDULED' && <div className="publication-time"><strong>{fmtScheduleShort(publication.scheduled_at)}</strong><span>{publication.timezone || 'America/Sao_Paulo'}</span></div>}{publication.status === 'PUBLISHED' && <div className="publication-time"><strong>{fmtDate(publication.published_at || undefined)}</strong><span>{publication.platform_post_id || '-'}</span></div>}{publication.status === 'FAILED' && <p className="error-text">{publicationErrorText(publication)}</p>}<div className="actions">{canEdit && <button onClick={onEdit}>Alterar horario</button>}{canEdit && <button className="danger" onClick={onCancel}>Cancelar</button>}{canWatch && <a className="primary" href={youtubeWatchUrl(publication)} target="_blank" rel="noopener noreferrer">Assistir no YouTube</a>}{publication.status === 'PUBLISHED' && <button aria-label="Mais acoes">...</button>}</div></div></article>
}

function EditPublicationScheduleModal({ publication, onClose, onSave }: { publication: Publication; onClose: () => void; onSave: (value: string) => Promise<void> }) {
  const [date, setDate] = useState(localDateInput(publication.scheduled_at))
  const [time, setTime] = useState(localTimeInput(publication.scheduled_at))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const save = async () => {
    const when = new Date(`${date}T${time}:00`)
    if (Number.isNaN(when.getTime()) || when <= new Date()) return setError('Informe data e horario futuros.')
    try {
      setSaving(true)
      await onSave(when.toISOString())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao salvar horario.')
    } finally {
      setSaving(false)
    }
  }
  return <Modal title="Alterar horario da publicacao" subtitle={`Publicacao atual: ${fmtScheduleShort(publication.scheduled_at)}`} onClose={onClose} closeDisabled={saving} className="schedule-edit-modal" footer={<><button disabled={saving} onClick={onClose}>Cancelar</button><button className="primary" disabled={saving} onClick={save}>{saving ? 'Salvando...' : 'Salvar horario'}</button></>}><label>Data<input type="date" min={todayInputDate()} value={date} onChange={e => setDate(e.target.value)} /></label><label>Horario<input type="time" value={time} onChange={e => setTime(e.target.value)} /></label><Info label="Timezone" value={publication.timezone || 'America/Sao_Paulo'} />{error && <p className="error-text">{error}</p>}</Modal>
}

function PublicationRoute({ publications }: { publications: Publication[] }) {
  const id = Number(useParams().id)
  const publication = publications.find(p => p.id === id)
  if (!publication) return <Empty text="Publicacao nao encontrada" />
  return <Page title={`Publicacao #${publication.id}`} subtitle={publication.title || `Clip #${publication.clip_id}`}><div className="panel grid2"><Info label="Plataforma" value={publication.platform} /><Info label="Status" value={publication.status} /><Info label="Video ID" value={publication.platform_post_id || '-'} /><Info label="Tentativas" value={String(publication.attempts || 0)} /><Info label="Criada em" value={fmtDate(publication.created_at)} /><Info label="Publicada em" value={fmtDate(publication.published_at || undefined)} /></div>{publication.status === 'PUBLISHED' && publication.publication_url && <div className="panel"><a href={publication.publication_url} target="_blank" rel="noopener noreferrer">ABRIR PUBLICACAO</a></div>}</Page>
}

function ProjectRoute({ projects, videos, onVideo, onUpload, onUrl }: { projects: Project[]; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File, plan?: UploadPublicationPlan | null) => void; onUrl: (id: number, url: string, plan?: UploadPublicationPlan | null) => void }) {
  const id = Number(useParams().id)
  return <ProjectDetail project={projects.find(p => p.id === id)} videos={videos} onVideo={onVideo} onUpload={onUpload} onUrl={onUrl} />
}

function VideoRoute({ videos, clips, publicationSettings, onStart, onPause, onResume, onRestart, onRetryPublicationPlan, onRefresh, onPublishNow, onSchedule, onConfirmPlan, onClipStyle }: { videos: Video[]; clips: Clip[]; publicationSettings?: PublicationSettings; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void; onRetryPublicationPlan: (id: number) => void; onRefresh: () => void; onPublishNow: (clip: Clip) => void; onSchedule: (clip: Clip, value: string) => void; onConfirmPlan: (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => Promise<void>; onClipStyle: (clip: Clip, style: string) => Promise<void> }) {
  const id = Number(useParams().id)
  return <VideoDetail video={videos.find(v => v.id === id)} clips={clips} publicationSettings={publicationSettings} onStart={onStart} onPause={onPause} onResume={onResume} onRestart={onRestart} onRetryPublicationPlan={onRetryPublicationPlan} onRefresh={onRefresh} onPublishNow={onPublishNow} onSchedule={onSchedule} onConfirmPlan={onConfirmPlan} onClipStyle={onClipStyle} />
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

export function Steps({ stage }: { stage: string }) {
  const steps = ['Upload', 'Transcricao', 'Analise', 'Clips', 'Finalizacao']
  const order = ['PENDING', 'TRANSCRIBING', 'FINDING_CLIPS', 'GENERATING_CLIPS', 'COMPLETED']
  const current = Math.max(order.findIndex(s => s === stage), stage === 'COMPLETED' ? 4 : 0)
  return <div className="steps" aria-label="Status do processamento">{steps.map((s, i) => { const state = stage === 'FAILED' ? 'failed' : i < current || stage === 'COMPLETED' ? 'done' : i === current ? 'run' : 'pending'; return <span key={s} className={state}><i>{state === 'done' ? '✓' : state === 'failed' ? '!' : state === 'run' ? '•' : ''}</i>{s}</span> })}</div>
}

type PipelineStep = {
  key: 'upload' | 'transcription' | 'analysis' | 'selection' | 'clips'
  label: string
  state: 'done' | 'run' | 'pending' | 'stale' | 'failed' | 'paused'
  progress: number | null
}

function stageIndex(stage?: string | null) {
  if (stage === 'COMPLETED') return 5
  if (stage === 'GENERATING_CLIPS') return 4
  if (stage === 'FINDING_CLIPS') return 2
  if (stage === 'TRANSCRIBING') return 1
  return 0
}

function stageLabel(stage?: string | null) {
  if (stage === 'TRANSCRIBING') return 'Transcricao'
  if (stage === 'FINDING_CLIPS') return 'Analise IA'
  if (stage === 'GENERATING_CLIPS') return 'Geracao dos clips'
  if (stage === 'COMPLETED') return 'Concluido'
  if (stage === 'PENDING') return 'Aguardando'
  return stage || 'Aguardando'
}

function generalStatus(video: Video, stale: boolean) {
  if (stale) return 'SEM RESPOSTA'
  if (video.status === 'COMPLETED') return 'CONCLUIDO'
  if (video.status === 'FAILED') return 'FALHOU'
  if (video.status === 'PAUSED') return 'PAUSADO'
  if (video.status === 'WAITING_RETRY') return 'AGUARDANDO RETRY'
  if (video.status === 'PROCESSING') return 'PROCESSANDO'
  return video.status
}

function buildPipelineSteps(video: Video, stale: boolean): PipelineStep[] {
  const current = stageIndex(video.processing_stage || video.status)
  const progress = typeof video.processing_progress === 'number' ? video.processing_progress : null
  const steps: PipelineStep[] = [
    { key: 'upload', label: video.source_type === 'youtube' ? 'Download' : 'Upload', state: 'done', progress: 100 },
    { key: 'transcription', label: 'Transcricao', state: current > 1 ? 'done' : current === 1 ? 'run' : 'pending', progress: current > 1 ? 100 : current === 1 ? progress : 0 },
    { key: 'analysis', label: 'Analise IA', state: current > 2 ? 'done' : current === 2 ? 'run' : 'pending', progress: current > 2 ? 100 : current === 2 ? progress : 0 },
    { key: 'selection', label: 'Selecao', state: current > 2 ? 'done' : current === 2 && progress === 100 ? 'done' : 'pending', progress: current > 2 || progress === 100 ? 100 : 0 },
    { key: 'clips', label: 'Clips', state: current > 4 ? 'done' : current === 4 ? 'run' : 'pending', progress: current > 4 ? 100 : current === 4 ? progress : 0 },
  ]
  const active = steps.find(step => step.state === 'run') || steps[Math.max(0, Math.min(current, steps.length - 1))]
  if (stale) active.state = 'stale'
  if (video.status === 'FAILED' && video.error_type !== 'PUBLICATION_PLAN_ERROR') active.state = 'failed'
  if (video.status === 'PAUSED') active.state = 'paused'
  return steps
}

function PipelineProgress({ video, onRefresh, onResume, onRestart, onRetryPublicationPlan }: { video: Video; onRefresh: () => void; onResume: (id: number) => void; onRestart: (id: number) => void; onRetryPublicationPlan: (id: number) => void }) {
  const stale = isVideoStale(video)
  const steps = buildPipelineSteps(video, stale)
  const active = steps.find(step => ['run', 'stale', 'failed', 'paused'].includes(step.state)) || steps[steps.length - 1]
  const isDeterminate = typeof active.progress === 'number'
  const totalClips = video.target_clip_count || undefined
  const clipDetail = video.processing_stage === 'GENERATING_CLIPS' && totalClips ? `${video.last_completed_clip || 0}/${totalClips} clips` : ''
  const publicationPlanError = video.error_type === 'PUBLICATION_PLAN_ERROR'
  return <section className="pipeline-progress" aria-live="polite"><div className="pipeline-summary"><div><span className={statusClass(stale ? 'stale' : video.status)}>{generalStatus(video, stale)}</span><h2>{stageLabel(video.processing_stage || video.status)}</h2></div><div className="pipeline-times"><Info label="Etapa atual" value={stageLabel(video.processing_stage || video.status)} /><Info label="Ultima atualizacao" value={timeAgo(video.last_progress_at || video.last_heartbeat)} /></div></div><div className="pipeline-steps" aria-label="Progresso do processamento">{steps.map(step => <div className={`pipeline-step ${step.state}`} key={step.key}><i>{step.state === 'done' ? '✓' : step.state === 'failed' ? '✕' : step.state === 'stale' ? '!' : step.state === 'run' ? '●' : '○'}</i><strong>{step.label}</strong><span>{typeof step.progress === 'number' ? `${Math.round(step.progress)}%` : 'processando'}</span></div>)}</div><div className="stage-detail"><div className="stage-detail-head"><div><span className="eyebrow">{active.label}</span><strong>{isDeterminate ? `${Math.round(active.progress || 0)}%` : 'Processando...'}</strong></div>{clipDetail && <b>{clipDetail}</b>}</div><div className={`stage-bar ${isDeterminate ? '' : 'indeterminate'}`} role="progressbar" aria-label={isDeterminate ? `${active.label}, ${Math.round(active.progress || 0)} por cento.` : `${active.label}, progresso indeterminado.`} aria-valuemin={isDeterminate ? 0 : undefined} aria-valuemax={isDeterminate ? 100 : undefined} aria-valuenow={isDeterminate ? Math.round(active.progress || 0) : undefined}><span style={isDeterminate ? { width: `${active.progress || 0}%` } : undefined} /></div><p className={stale ? 'error-text' : 'muted'}>{stale ? 'Processamento sem atualizacao. Nao recebemos novas atualizacoes desta etapa.' : video.processing_message || (isDeterminate ? 'Processando etapa atual.' : 'Processando...')}</p>{publicationPlanError && <div className="planner-notice"><strong>Falha no agendamento</strong><p>Os clips foram gerados. Tente criar as publicacoes novamente sem reprocessar o video.</p><button onClick={() => onRetryPublicationPlan(video.id)}>Tentar agendamento novamente</button></div>}{video.status === 'FAILED' && !publicationPlanError && <details className="error-details"><summary>Detalhes</summary><p>{video.error_type || 'PROCESSING_ERROR'}</p><pre>{video.error_message}</pre></details>}{video.status === 'PAUSED' && <p className="muted">Processo pausado na ultima etapa registrada.</p>}<div className="pipeline-actions"><button onClick={onRefresh}>Atualizar</button>{video.status === 'PAUSED' && <button onClick={() => onResume(video.id)}>Retomar</button>}{(stale || ['PAUSED', 'FAILED'].includes(video.status)) && !publicationPlanError && <button className="danger" onClick={() => onRestart(video.id)}>Reiniciar</button>}</div></div></section>
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
  const [clearedNotificationIds, setClearedNotificationIds] = useState<Set<string>>(() => {
    const saved = window.localStorage.getItem('axisclip.clearedNotificationIds')
    if (!saved) return new Set()
    try {
      return new Set(JSON.parse(saved))
    } catch {
      window.localStorage.removeItem('axisclip.clearedNotificationIds')
      return new Set()
    }
  })
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
      const visibleNotes = notes.filter(n => !clearedNotificationIds.has(n.id))
      setHealth(h); setProjects(p); setVideos(v); setPublications(pubs)
      setPublicationSettings(pubSettings)
      setNotifications(visibleNotes)
      const fresh = visibleNotes.filter(n => !seenNotifications.has(n.id))
      if (fresh.length && notificationPrefs.enabled) {
        const latest = fresh[0]
        setToast({ type: latest.type === 'ERROR' ? 'error' : latest.type === 'RETRY' ? 'warning' : 'success', text: latest.title })
        showNativeNotification(latest)
        playNotificationSound()
      }
      if (fresh.length) setSeenNotifications(prev => new Set([...prev, ...fresh.map(n => n.id)]))
      if (selectedVideo) setClips(await listVideoClips(selectedVideo))
    } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro de conexao' }) }
  }, [clearedNotificationIds, notificationPrefs.enabled, notificationPrefs.history, playNotificationSound, selectedVideo, seenNotifications, showNativeNotification])
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

  const clearNotifications = () => {
    const next = new Set([...clearedNotificationIds, ...notifications.map(item => item.id)])
    setClearedNotificationIds(next)
    window.localStorage.setItem('axisclip.clearedNotificationIds', JSON.stringify([...next]))
    setNotifications([])
  }

  return <BrowserRouter><AppRoutes projects={projects} videos={videos} clips={clips} publications={publications} publicationSettings={publicationSettings} notifications={notifications} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} youtube={youtube} health={health} load={load} setClips={setClips} setToast={setToast} setSelectedVideo={setSelectedVideo} setNotifications={setNotifications} clearNotifications={clearNotifications} updateNotificationPref={updateNotificationPref} showNativeNotification={showNativeNotification} playNotificationSound={playNotificationSound} toast={toast} /></BrowserRouter>
}

function AppRoutes({ projects, videos, clips, publications, publicationSettings, notifications, notificationPrefs, notificationPermission, youtube, health, load, setClips, setToast, setSelectedVideo, setNotifications, clearNotifications, updateNotificationPref, showNativeNotification, playNotificationSound, toast }: { projects: Project[]; videos: Video[]; clips: Clip[]; publications: Publication[]; publicationSettings?: PublicationSettings; notifications: AxisNotification[]; notificationPrefs: NotificationPrefs; notificationPermission: NotificationPermission | 'unsupported'; youtube?: YouTubeAccount; health?: Health; load: () => Promise<void>; setClips: (clips: Clip[]) => void; setToast: (toast: Toast | null) => void; setSelectedVideo: (id: number) => void; setNotifications: (items: AxisNotification[]) => void; clearNotifications: () => void; updateNotificationPref: (key: keyof NotificationPrefs, value: boolean) => Promise<void>; showNativeNotification: (item: AxisNotification) => void; playNotificationSound: () => void; toast: Toast | null }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [youtubeConnecting, setYoutubeConnecting] = useState(false)
  const openVideo = (id: number) => { setSelectedVideo(id); listVideoClips(id).then(setClips); navigate(`/videos/${id}`) }
  const create = async (name: string) => { try { await createProject(name); setToast({ type: 'success', text: 'Projeto criado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro' }) } }
  const upload = async (id: number, file: File, plan?: UploadPublicationPlan | null) => { try { setToast({ type: 'info', text: 'Enviando...' }); const video = await uploadVideo(id, file, plan, item => window.dispatchEvent(new CustomEvent('axisclip-upload-progress', { detail: item }))); setSelectedVideo(video.id); setToast({ type: 'success', text: 'Video enviado com sucesso' }); await load(); navigate(`/videos/${video.id}`) } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha no upload' }) } }
  const uploadUrl = async (id: number, url: string, plan?: UploadPublicationPlan | null) => { try { setToast({ type: 'info', text: 'Baixando video...' }); const video = await importVideoFromUrl(id, url, plan); setSelectedVideo(video.id); setToast({ type: 'success', text: 'Video enviado com sucesso' }); await load(); navigate(`/videos/${video.id}`) } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao processar URL' }) } }
  const removeProject = async (id: number) => { if (!window.confirm('Tem certeza que deseja excluir este projeto?')) return; try { await deleteProject(id); setToast({ type: 'success', text: 'Projeto excluido' }); await load(); navigate('/projects') } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao excluir projeto' }) } }
  const start = async (id: number) => { try { await startVideo(id); setToast({ type: 'success', text: 'Processamento iniciado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao iniciar' }) } }
  const pause = async (id: number) => { try { await pauseVideo(id); setToast({ type: 'success', text: 'Processamento pausado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao pausar' }) } }
  const resume = async (id: number) => { try { await resumeVideo(id); setToast({ type: 'success', text: 'Processamento retomado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao retomar' }) } }
  const restart = async (id: number) => { if (!window.confirm('Tem certeza que deseja reiniciar o processamento? Os clips atuais serao substituidos.')) return; try { await restartVideo(id); setToast({ type: 'success', text: 'Processamento reiniciado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao reiniciar' }) } }
  const retryPublicationPlan = async (id: number) => { try { await retryVideoPublicationPlan(id); setToast({ type: 'success', text: 'Agendamento recriado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao reagendar' }) } }
  const publishNow = async (clip: Clip) => { try { await publishClipNow(clip.id); setToast({ type: 'success', text: 'Clip adicionado a fila de publicacao.' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao publicar' }) } }
  const scheduleClip = async (clip: Clip, value: string) => { try { const when = new Date(value); if (Number.isNaN(when.getTime()) || when <= new Date()) throw new Error('Data de agendamento invalida.'); await scheduleClipPublication(clip.id, when.toISOString()); setToast({ type: 'success', text: `Publicacao agendada para ${when.toLocaleString()}` }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao agendar' }) } }
  const confirmPlan = async (clipIds: number[], maxPerDay: number, startDate: string, times: string[]) => { try { const result = await confirmPublicationSchedule({ clip_ids: clipIds, max_per_day: maxPerDay, start_date: startDate, times }); setToast({ type: 'success', text: `${result.created_publications || 0} clipes agendados` }); await load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao confirmar agendamento' }); throw e } }
  const changeClipStyle = async (clip: Clip, style: string) => {
    try {
      setToast({ type: 'info', text: 'Aplicando estilo...' })
      await updateClipStyle(clip.id, style)
      if (clip.video_id) setClips(await listVideoClips(clip.video_id))
      setToast({ type: 'success', text: `Estilo ${styleName(style)} aplicado` })
    } catch (e) {
      setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao aplicar estilo' })
    }
  }
  const cancelSchedule = async (id: number) => { if (!window.confirm('Cancelar este agendamento?')) return; try { await cancelPublication(id); setToast({ type: 'success', text: 'Agendamento cancelado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao cancelar' }) } }
  const editSchedule = async (id: number, value: string) => { try { const when = new Date(value); if (Number.isNaN(when.getTime()) || when <= new Date()) throw new Error('Data de agendamento invalida.'); await updatePublicationSchedule(id, when.toISOString()); setToast({ type: 'success', text: 'Agendamento atualizado' }); await load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha ao editar' }); throw e } }
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

  return <Shell health={health} refresh={load} notifications={notificationPrefs.history ? notifications : []} onReadNotifications={readNotifications} onClearNotifications={clearNotifications}><Routes><Route path="/" element={<Dashboard health={health} projects={projects} videos={videos} />} /><Route path="/projects" element={<Projects projects={projects} videos={videos} selectProject={id => navigate(`/projects/${id}`)} onCreateProject={create} onDeleteProject={removeProject} />} /><Route path="/projects/:id" element={<ProjectRoute projects={projects} videos={videos} onVideo={openVideo} onUpload={upload} onUrl={uploadUrl} />} /><Route path="/videos" element={<Videos videos={videos} onVideo={openVideo} />} /><Route path="/videos/:id" element={<VideoRoute videos={videos} clips={clips} publicationSettings={publicationSettings} onStart={start} onPause={pause} onResume={resume} onRestart={restart} onRetryPublicationPlan={retryPublicationPlan} onRefresh={load} onPublishNow={publishNow} onSchedule={scheduleClip} onConfirmPlan={confirmPlan} onClipStyle={changeClipStyle} />} /><Route path="/publications" element={<Publications publications={publications} onCancel={cancelSchedule} onEdit={editSchedule} />} /><Route path="/publications/:id" element={<PublicationRoute publications={publications} />} /><Route path="/settings" element={<Settings health={health} youtube={youtube} connecting={youtubeConnecting} publicationSettings={publicationSettings} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} onNotificationPref={updateNotificationPref} onTestNotification={runTestNotification} onConnect={connect} onDisconnect={disconnect} onSavePublicationSettings={savePubSettings} />} /></Routes>{toast && <div className={`toast ${toast.type}`} onAnimationEnd={() => setToast(null)}>{toast.text}</div>}</Shell>
}
export default App
