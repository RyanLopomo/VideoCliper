export interface Clip {
  id: number;
  video_id: number;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  status: string;
  thumbnail_url: string;
  stream_url: string;
  download_url: string;
  publication_url?: string | null;
  publication_platform?: string | null;
  publication_status?: string | null;
}
