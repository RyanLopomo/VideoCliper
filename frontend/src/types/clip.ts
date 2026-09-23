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
  publication_id?: number | null;
  publication_platform?: string | null;
  publication_status?: string | null;
  publication_scheduled_at?: string | null;
  publication_error_type?: string | null;
  publication_error_details?: string | null;
  editing_style?: string;
  applied_preset?: string | null;
  ai_style_recommendation?: string | null;
  ai_style_confidence?: number | null;
  ai_style_reason?: string | null;
}
