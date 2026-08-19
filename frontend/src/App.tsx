import { useCallback, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { API_BASE_URL } from './api/client'
import { listVideoClips } from './api/clips'
import { getHealth } from './api/health'
import { disconnectYouTube, getYouTubeAccount, listPublications, startYouTubeAuth } from './api/publications'
import { createProject, listProjects } from './api/projects'
import { listVideos, uploadVideo } from './api/videos'
import type { Clip } from './types/clip'
import type { Health } from './types/health'
import type { Publication, YouTubeAccount } from './types/publication'
import type { Project } from './types/projects'
import type { Video } from './types/video'
import './App.css'

const POLL_MS = Number(import.meta.env.VITE_POLL_INTERVAL || 8000)
type Toast = { type: 'success' | 'error' | 'warning' | 'info'; text: string }

function statusClass(status?: string) {
  return `badge ${String(status || 'UNKNOWN').toLowerCase()}`
}

function fmtDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

function Shell({ health, refresh, children }: { health?: Health; refresh: () => void; children: ReactNode }) {
  const nav = [['/', 'Dashboard'], ['/projects', 'Projetos'], ['/videos', 'Videos'], ['/publications', 'Publicacoes'], ['/settings', 'Configuracoes']]
  const online = health?.status === 'ok'
  return <div className="app"><aside className="sidebar"><div className="brand">AxisClip</div><nav>{nav.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'active' : ''}>{label}</NavLink>)}</nav></aside><section className="workspace"><header className="topbar"><div><strong>AxisClip</strong><span className={online ? 'dot on' : 'dot off'}>{online ? 'ONLINE' : 'OFFLINE'}</span></div><button onClick={refresh}>Atualizar</button></header><main>{children}</main></section></div>
}

function Dashboard({ health, projects, videos }: { health?: Health; projects: Project[]; videos: Video[] }) {
  const metrics = health?.metrics || {}
  const processed = videos.filter(v => v.status === 'COMPLETED').length
  return <Page title="Dashboard" subtitle="Operacao e saude do sistema"><div className="stats"><Stat label="Videos processados" value={processed} /><Stat label="Clips gerados" value={metrics.clips_generated || 0} /><Stat label="Publicacoes" value={metrics.publications || 0} /><Stat label="Publicados" value={metrics.publications_success || health?.published || 0} /><Stat label="Falhas" value={metrics.failures || health?.failed || 0} /></div><div className="panel grid2">{['application', 'database', 'redis', 'worker'].map(key => { const value = String(key === 'worker' ? health?.worker || health?.worker_status || 'UNKNOWN' : health?.[key as keyof Health] || 'OFFLINE'); return <div className="health" key={key}><span>{key}</span><b className={statusClass(value)}>{value}</b></div> })}</div><div className="panel"><h2>Projetos recentes</h2><Table rows={projects.slice(-5).reverse()} columns={['name', 'status', 'created_at']} /></div></Page>
}

function Projects({ projects, videos, selectProject, onCreateProject }: { projects: Project[]; videos: Video[]; selectProject: (id: number) => void; onCreateProject: (name: string) => void }) {
  const [name, setName] = useState('')
  const submit = (e: FormEvent) => { e.preventDefault(); if (name.trim()) { onCreateProject(name); setName('') } }
  return <Page title="Projetos" subtitle="Crie e acompanhe projetos"><form className="form panel" onSubmit={submit}><label>Nome do projeto<input value={name} onChange={e => setName(e.target.value)} placeholder="Novo projeto" /></label><button>Criar projeto</button></form><div className="cards">{projects.map(p => <article className="card" key={p.id}><h3>{p.name}</h3><span className={statusClass(p.status)}>{p.status}</span><p>{fmtDate(p.created_at)}</p><p>{videos.filter(v => v.project_id === p.id).length} videos</p><button onClick={() => selectProject(p.id)}>Abrir projeto</button></article>)}</div></Page>
}

function ProjectDetail({ project, videos, onVideo, onUpload }: { project?: Project; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const own = videos.filter(v => v.project_id === project?.id)
  if (!project) return <Empty text="Projeto nao encontrado" />
  return <Page title={project.name} subtitle={`${own.length} videos`}><div className="panel upload" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFile(e.dataTransfer.files[0]) }}><label>Adicionar video MP4<input type="file" accept="video/mp4" onChange={e => setFile(e.target.files?.[0] || null)} /></label>{file && <p>{file.name} - {(file.size / 1024 / 1024).toFixed(1)} MB</p>}<button disabled={!file} onClick={() => file && onUpload(project.id, file)}>Enviar</button></div><VideoList videos={own} onVideo={onVideo} /></Page>
}

function Videos({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <Page title="Videos" subtitle="Processamento"><VideoList videos={videos} onVideo={onVideo} /></Page>
}

function VideoList({ videos, onVideo }: { videos: Video[]; onVideo: (id: number) => void }) {
  return <div className="panel table">{videos.map(v => <button className="row" key={v.id} onClick={() => onVideo(v.id)}><span>Video #{v.id}</span><span>{v.processing_stage || v.status}</span><span>{v.duration ? `${v.duration}s` : '-'}</span><span>{fmtDate(v.created_at)}</span></button>)}</div>
}

function VideoDetail({ video, clips }: { video?: Video; clips: Clip[] }) {
  const [playing, setPlaying] = useState<Clip | null>(null)
  if (!video) return <Empty text="Video nao encontrado" />
  return <Page title={`Video #${video.id}`} subtitle={video.file_path}><div className="panel"><span className={statusClass(video.status)}>{video.status}</span>{video.error_message && <p className="error">Falha no processamento.</p>}<Steps stage={video.processing_stage || video.status} /></div><ClipGallery clips={clips} onPlay={setPlaying} />{playing && <Player clip={playing} onClose={() => setPlaying(null)} />}</Page>
}

function ClipGallery({ clips, onPlay }: { clips: Clip[]; onPlay: (clip: Clip) => void }) {
  return <div className="cards clips">{clips.map(c => <article className="card" key={c.id}><img src={`${API_BASE_URL}${c.thumbnail_url}`} alt={c.title} /><h3>{c.title}</h3><p>{c.duration}s - {c.status}</p><div className="actions"><button onClick={() => onPlay(c)}>Assistir</button><a href={`${API_BASE_URL}${c.download_url}`}>Baixar</a>{c.publication_url && <a href={c.publication_url} target="_blank" rel="noopener noreferrer">{c.publication_platform || 'Publicacao'}</a>}</div></article>)}</div>
}

function Player({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  return <div className="modal" role="dialog" aria-modal="true"><div className="player"><button className="close" onClick={onClose}>Fechar</button><h2>{clip.title}</h2><video src={`${API_BASE_URL}${clip.stream_url}`} controls autoPlay /></div></div>
}

function Publications({ publications }: { publications: Publication[] }) {
  return <Page title="Publicacoes" subtitle="Fila e historico"><div className="panel table">{publications.map(p => <div className="row" key={p.id}><span>{p.title || `Clip #${p.clip_id}`}</span><span>{p.platform}</span><span className={statusClass(p.status)}>{p.status}</span><span>{p.platform_post_id || '-'}</span>{p.status === 'PUBLISHED' && p.publication_url ? <a href={p.publication_url} target="_blank" rel="noopener noreferrer">Abrir no {p.platform}</a> : <span>-</span>}</div>)}</div></Page>
}

function PublicationRoute({ publications }: { publications: Publication[] }) {
  const id = Number(useParams().id)
  const publication = publications.find(p => p.id === id)
  if (!publication) return <Empty text="Publicacao nao encontrada" />
  return <Page title={`Publicacao #${publication.id}`} subtitle={publication.title || `Clip #${publication.clip_id}`}><div className="panel grid2"><Info label="Plataforma" value={publication.platform} /><Info label="Status" value={publication.status} /><Info label="Video ID" value={publication.platform_post_id || '-'} /><Info label="Tentativas" value={String(publication.attempts || 0)} /><Info label="Criada em" value={fmtDate(publication.created_at)} /><Info label="Publicada em" value={fmtDate(publication.published_at || undefined)} /></div>{publication.status === 'PUBLISHED' && publication.publication_url && <div className="panel"><a href={publication.publication_url} target="_blank" rel="noopener noreferrer">ABRIR PUBLICACAO</a></div>}</Page>
}

function ProjectRoute({ projects, videos, onVideo, onUpload }: { projects: Project[]; videos: Video[]; onVideo: (id: number) => void; onUpload: (id: number, file: File) => void }) {
  const id = Number(useParams().id)
  return <ProjectDetail project={projects.find(p => p.id === id)} videos={videos} onVideo={onVideo} onUpload={onUpload} />
}

function VideoRoute({ videos, clips }: { videos: Video[]; clips: Clip[] }) {
  const id = Number(useParams().id)
  return <VideoDetail video={videos.find(v => v.id === id)} clips={clips} />
}

function Settings({ health, youtube, connecting, onConnect, onDisconnect }: { health?: Health; youtube?: YouTubeAccount; connecting: boolean; onConnect: () => void; onDisconnect: () => void }) {
  const connected = youtube?.connected
  const status = connecting ? 'CONNECTING' : youtube?.status || 'DISCONNECTED'
  const channel = youtube?.channel_title || youtube?.channel_name || 'YouTube'
  return <Page title="Configuracoes" subtitle="Integracoes"><div className="panel grid2"><Info label="Backend URL" value={API_BASE_URL} /><Info label="API status" value={health?.status || 'offline'} /><Info label="Versao" value="0.0.0" /><Info label="TikTok" value="Em breve" /></div><div className="panel"><h2>YouTube</h2><p>{connected ? `Canal: ${channel}` : 'Nenhuma conta conectada'}</p><span className={statusClass(status)}>{status}</span><div className="actions"><button onClick={onConnect} disabled={connecting}>{connecting ? 'CONECTANDO...' : connected ? 'TROCAR CONTA' : 'CONECTAR YOUTUBE'}</button>{connected && <button onClick={onDisconnect}>DESCONECTAR</button>}</div></div></Page>
}

function Steps({ stage }: { stage: string }) {
  const steps = ['UPLOAD', 'TRANSCRICAO', 'ANALISE', 'CLIPS', 'FINALIZACAO']
  const current = ['PENDING', 'TRANSCRIBING', 'FINDING_CLIPS', 'GENERATING_CLIPS', 'COMPLETED'].findIndex(s => s === stage)
  return <div className="steps">{steps.map((s, i) => <span key={s} className={stage === 'FAILED' ? 'failed' : i < current || stage === 'COMPLETED' ? 'done' : i === current ? 'run' : ''}>{s}</span>)}</div>
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

  const load = useCallback(async () => {
    try {
      const yt = await getYouTubeAccount()
      setYoutube(yt)
    } catch {
      setYoutube({ connected: false, status: 'DISCONNECTED' })
    }
    try {
      const [h, p, v, pubs] = await Promise.all([getHealth(), listProjects(), listVideos(), listPublications()])
      setHealth(h); setProjects(p); setVideos(v); setPublications(pubs)
      if (selectedVideo) setClips(await listVideoClips(selectedVideo))
    } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro de conexao' }) }
  }, [selectedVideo])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const active = videos.some(v => !['COMPLETED', 'FAILED'].includes(v.status))
    if (!active) return
    const id = window.setInterval(load, POLL_MS)
    return () => window.clearInterval(id)
  }, [videos, load])

  return <BrowserRouter><AppRoutes projects={projects} videos={videos} clips={clips} publications={publications} youtube={youtube} health={health} load={load} setClips={setClips} setToast={setToast} setSelectedVideo={setSelectedVideo} toast={toast} /></BrowserRouter>
}

function AppRoutes({ projects, videos, clips, publications, youtube, health, load, setClips, setToast, setSelectedVideo, toast }: { projects: Project[]; videos: Video[]; clips: Clip[]; publications: Publication[]; youtube?: YouTubeAccount; health?: Health; load: () => Promise<void>; setClips: (clips: Clip[]) => void; setToast: (toast: Toast | null) => void; setSelectedVideo: (id: number) => void; toast: Toast | null }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [youtubeConnecting, setYoutubeConnecting] = useState(false)
  const openVideo = (id: number) => { setSelectedVideo(id); listVideoClips(id).then(setClips); navigate(`/videos/${id}`) }
  const create = async (name: string) => { try { await createProject(name); setToast({ type: 'success', text: 'Projeto criado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Erro' }) } }
  const upload = async (id: number, file: File) => { try { setToast({ type: 'info', text: 'Enviando...' }); const video = await uploadVideo(id, file); setSelectedVideo(video.id); setToast({ type: 'success', text: 'Video enviado com sucesso' }); await load(); navigate(`/videos/${video.id}`) } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Falha no upload' }) } }
  const disconnect = async () => { try { await disconnectYouTube(); setToast({ type: 'success', text: 'YouTube desconectado' }); load() } catch (e) { setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel desconectar' }) } }
  const connect = async () => { try { setYoutubeConnecting(true); await startYouTubeAuth() } catch (e) { setYoutubeConnecting(false); setToast({ type: 'error', text: e instanceof Error ? e.message : 'Nao foi possivel conectar a conta do YouTube.' }) } }

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

  return <Shell health={health} refresh={load}><Routes><Route path="/" element={<Dashboard health={health} projects={projects} videos={videos} />} /><Route path="/projects" element={<Projects projects={projects} videos={videos} selectProject={id => navigate(`/projects/${id}`)} onCreateProject={create} />} /><Route path="/projects/:id" element={<ProjectRoute projects={projects} videos={videos} onVideo={openVideo} onUpload={upload} />} /><Route path="/videos" element={<Videos videos={videos} onVideo={openVideo} />} /><Route path="/videos/:id" element={<VideoRoute videos={videos} clips={clips} />} /><Route path="/publications" element={<Publications publications={publications} />} /><Route path="/publications/:id" element={<PublicationRoute publications={publications} />} /><Route path="/settings" element={<Settings health={health} youtube={youtube} connecting={youtubeConnecting} onConnect={connect} onDisconnect={disconnect} />} /></Routes>{toast && <div className={`toast ${toast.type}`} onAnimationEnd={() => setToast(null)}>{toast.text}</div>}</Shell>
}
export default App
