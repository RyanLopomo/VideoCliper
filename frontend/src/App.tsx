import { useCallback, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { API_BASE_URL } from './api/client'
import { listVideoClips } from './api/clips'
import { getHealth } from './api/health'
import { listNotifications, markNotificationsRead, testNotification } from './api/notifications'
import { disconnectYouTube, getYouTubeAccount, listPublications, startYouTubeAuth } from './api/publications'
import { createProject, deleteProject, listProjects } from './api/projects'
import { importVideoFromUrl, listVideos, pauseVideo, restartVideo, resumeVideo, startVideo, uploadVideo } from './api/videos'
import type { Clip } from './types/clip'
import type { Health } from './types/health'
import type { AxisNotification } from './types/notification'
import type { Publication, YouTubeAccount } from './types/publication'
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
function platformName(value?: string | null) {
  return String(value || '').toUpperCase() === 'TIKTOK' ? 'TikTok' : 'YouTube'
}
function clipTitle(clip: Clip) {
  return clip.title?.trim() || `Clip #${clip.id}`
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

function VideoDetail({ video, clips, onStart, onPause, onResume, onRestart }: { video?: Video; clips: Clip[]; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void }) {
  const [playing, setPlaying] = useState<Clip | null>(null)
  if (!video) return <Empty text="Video nao encontrado" />
  return <Page title={`Video #${video.id}`} subtitle={video.file_path}><div className="panel"><div className="video-actions"><span className={statusClass(video.status)}>{video.status}</span>{video.status === 'PENDING' && <button onClick={() => onStart(video.id)}>Iniciar</button>}{video.status === 'PROCESSING' && <button onClick={() => onPause(video.id)}>Pausar</button>}{video.status === 'PAUSED' && <button onClick={() => onResume(video.id)}>Retomar</button>}{['PAUSED', 'FAILED', 'COMPLETED'].includes(video.status) && <button className="danger" onClick={() => onRestart(video.id)}>Reiniciar</button>}</div>{video.error_message && <p className="error">Falha no processamento.</p>}<Steps stage={video.status === 'PAUSED' ? 'PAUSED' : video.processing_stage || video.status} /></div><ClipGallery clips={clips} onPlay={setPlaying} />{playing && <Player clip={playing} onClose={() => setPlaying(null)} />}</Page>
}

function ClipGallery({ clips, onPlay }: { clips: Clip[]; onPlay: (clip: Clip) => void }) {
  return <div className="cards clips">{clips.map(c => <article className="clip-card" key={c.id}><div className="thumb"><img loading="lazy" src={`${API_BASE_URL}${c.thumbnail_url}`} alt={clipTitle(c)} /><div className="thumb-badges"><span className={statusClass(c.status)}>{c.status}</span>{c.publication_status && <span className={statusClass(c.publication_status)}>{c.publication_status}</span>}</div></div><div className="clip-body"><h3>{clipTitle(c)}</h3><p className="muted">Trecho #{c.id}</p><div className="meta"><span>{c.duration}s</span>{c.publication_platform && <span>{platformName(c.publication_platform)}</span>}</div><div className="actions"><button className="primary" aria-label={`Assistir ${clipTitle(c)}`} onClick={() => onPlay(c)}>Assistir</button><a href={`${API_BASE_URL}${c.download_url}`} aria-label={`Baixar ${clipTitle(c)}`}>Baixar</a>{c.publication_url && <a href={c.publication_url} target="_blank" rel="noopener noreferrer">Abrir no {platformName(c.publication_platform)}</a>}</div></div></article>)}</div>
}

function Player({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  return <div className="modal" role="dialog" aria-modal="true"><div className="player"><button className="close" onClick={onClose}>Fechar</button><h2>{clip.title}</h2><video src={`${API_BASE_URL}${clip.stream_url}`} controls autoPlay /></div></div>
}

function Publications({ publications }: { publications: Publication[] }) {
  return <Page title="Publicacoes" subtitle="Fila e historico"><div className="pub-table"><div className="pub-row head"><span>Clip</span><span>Platform</span><span>Status</span><span>Attempts</span><span>Created</span><span>Published</span><span>Action</span></div>{publications.map(p => <div className="pub-row" key={p.id}><span>{p.title || `Clip #${p.clip_id}`}</span><span>{platformName(p.platform)}</span><span className={statusClass(p.status)}>{p.status}</span><span>{p.attempts || 0}</span><span>{fmtDate(p.created_at)}</span><span>{fmtDate(p.published_at || undefined)}</span>{p.status === 'PUBLISHED' && p.publication_url ? <a href={p.publication_url} target="_blank" rel="noopener noreferrer">Abrir</a> : p.status === 'FAILED' ? <span className="muted">Ver erro</span> : <span className="muted">-</span>}</div>)}</div></Page>
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

function VideoRoute({ videos, clips, onStart, onPause, onResume, onRestart }: { videos: Video[]; clips: Clip[]; onStart: (id: number) => void; onPause: (id: number) => void; onResume: (id: number) => void; onRestart: (id: number) => void }) {
  const id = Number(useParams().id)
  return <VideoDetail video={videos.find(v => v.id === id)} clips={clips} onStart={onStart} onPause={onPause} onResume={onResume} onRestart={onRestart} />
}

function Settings({ health, youtube, connecting, notificationPrefs, notificationPermission, onNotificationPref, onTestNotification, onConnect, onDisconnect }: { health?: Health; youtube?: YouTubeAccount; connecting: boolean; notificationPrefs: NotificationPrefs; notificationPermission: NotificationPermission | 'unsupported'; onNotificationPref: (key: keyof NotificationPrefs, value: boolean) => void; onTestNotification: () => void; onConnect: () => void; onDisconnect: () => void }) {
  const connected = youtube?.connected
  const status = connecting ? 'CONNECTING' : youtube?.status || 'DISCONNECTED'
  const channel = youtube?.channel_title || youtube?.channel_name || 'YouTube'
  return <Page title="Configuracoes" subtitle="Integracoes"><div className="panel grid2"><Info label="Backend URL" value={API_BASE_URL} /><Info label="API status" value={health?.status || 'offline'} /><Info label="Versao" value="0.0.0" /><Info label="TikTok" value="Em breve" /></div><div className="panel"><h2>YouTube</h2><p>{connected ? `Canal: ${channel}` : 'Nenhuma conta conectada'}</p><span className={statusClass(status)}>{status}</span><div className="actions"><button onClick={onConnect} disabled={connecting}>{connecting ? 'CONECTANDO...' : connected ? 'TROCAR CONTA' : 'CONECTAR YOUTUBE'}</button>{connected && <button onClick={onDisconnect}>DESCONECTAR</button>}</div></div><div className="panel settings-panel"><h2>Notificacoes</h2><Toggle label="Ativar notificacoes" checked={notificationPrefs.enabled} onChange={v => onNotificationPref('enabled', v)} /><Toggle label="Notificacoes do sistema" checked={notificationPrefs.system} onChange={v => onNotificationPref('system', v)} /><Toggle label="Som" checked={notificationPrefs.sound} onChange={v => onNotificationPref('sound', v)} /><Toggle label="Notificacoes em segundo plano" checked={notificationPrefs.background} onChange={v => onNotificationPref('background', v)} /><Toggle label="Historico" checked={notificationPrefs.history} onChange={v => onNotificationPref('history', v)} /><p className="muted">Permissao: {notificationPermission.toUpperCase()}</p>{notificationPermission === 'denied' && <p className="error-text">As notificacoes do navegador estao bloqueadas.</p>}<button onClick={onTestNotification}>Testar notificacao</button></div></Page>
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
      const [h, p, v, pubs, notes] = await Promise.all([getHealth(), listProjects(), listVideos(), listPublications(), notificationPrefs.history ? listNotifications() : Promise.resolve([])])
      setHealth(h); setProjects(p); setVideos(v); setPublications(pubs)
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

  return <BrowserRouter><AppRoutes projects={projects} videos={videos} clips={clips} publications={publications} notifications={notifications} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} youtube={youtube} health={health} load={load} setClips={setClips} setToast={setToast} setSelectedVideo={setSelectedVideo} setNotifications={setNotifications} updateNotificationPref={updateNotificationPref} showNativeNotification={showNativeNotification} playNotificationSound={playNotificationSound} toast={toast} /></BrowserRouter>
}

function AppRoutes({ projects, videos, clips, publications, notifications, notificationPrefs, notificationPermission, youtube, health, load, setClips, setToast, setSelectedVideo, setNotifications, updateNotificationPref, showNativeNotification, playNotificationSound, toast }: { projects: Project[]; videos: Video[]; clips: Clip[]; publications: Publication[]; notifications: AxisNotification[]; notificationPrefs: NotificationPrefs; notificationPermission: NotificationPermission | 'unsupported'; youtube?: YouTubeAccount; health?: Health; load: () => Promise<void>; setClips: (clips: Clip[]) => void; setToast: (toast: Toast | null) => void; setSelectedVideo: (id: number) => void; setNotifications: (items: AxisNotification[]) => void; updateNotificationPref: (key: keyof NotificationPrefs, value: boolean) => Promise<void>; showNativeNotification: (item: AxisNotification) => void; playNotificationSound: () => void; toast: Toast | null }) {
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
  const disconnect = async () => { try { await disconnectYouTube(); setToast({ type: 'success', text: 'YouTube desconectado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel desconectar' }) } }
  const connect = async () => { try { setYoutubeConnecting(true); await startYouTubeAuth() } catch (e) { setYoutubeConnecting(false); setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel conectar a conta do YouTube.' }) } }
  const readNotifications = async () => { await markNotificationsRead(); setNotifications(notifications.map(n => ({ ...n, read: true }))) }
  const runTestNotification = async () => { const item = await testNotification(); setNotifications([item, ...notifications.filter(n => n.id !== item.id)]); setToast({ type: 'success', text: item.title }); showNativeNotification(item); playNotificationSound() }

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

  return <Shell health={health} refresh={load} notifications={notificationPrefs.history ? notifications : []} onReadNotifications={readNotifications}><Routes><Route path="/" element={<Dashboard health={health} projects={projects} videos={videos} />} /><Route path="/projects" element={<Projects projects={projects} videos={videos} selectProject={id => navigate(`/projects/${id}`)} onCreateProject={create} onDeleteProject={removeProject} />} /><Route path="/projects/:id" element={<ProjectRoute projects={projects} videos={videos} onVideo={openVideo} onUpload={upload} onUrl={uploadUrl} />} /><Route path="/videos" element={<Videos videos={videos} onVideo={openVideo} />} /><Route path="/videos/:id" element={<VideoRoute videos={videos} clips={clips} onStart={start} onPause={pause} onResume={resume} onRestart={restart} />} /><Route path="/publications" element={<Publications publications={publications} />} /><Route path="/publications/:id" element={<PublicationRoute publications={publications} />} /><Route path="/settings" element={<Settings health={health} youtube={youtube} connecting={youtubeConnecting} notificationPrefs={notificationPrefs} notificationPermission={notificationPermission} onNotificationPref={updateNotificationPref} onTestNotification={runTestNotification} onConnect={connect} onDisconnect={disconnect} />} /></Routes>{toast && <div className={`toast ${toast.type}`} onAnimationEnd={() => setToast(null)}>{toast.text}</div>}</Shell>
}
export default App
