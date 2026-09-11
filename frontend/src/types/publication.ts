export type PublicationStatus = "SCHEDULED" | "PENDING" | "UPLOADING" | "PROCESSING" | "WAITING_RETRY" | "PUBLISHED" | "FAILED" | "CANCELLED";

export interface PublicationSummary {
  status: PublicationStatus;
  total: number;
}

export interface PublicationAccount {
  id: number;
  platform: string;
  account_name: string;
  platform_account_id: string;
  enabled: boolean;
  is_default: boolean;
}

export interface Publication {
  id: number;
  clip_id: number;
  title?: string | null;
  duration?: number | null;
  thumbnail_url?: string | null;
  platform: string;
  account?: PublicationAccount | null;
  status: PublicationStatus;
  error_type?: string | null;
  error_details?: string | null;
  created_at?: string;
  updated_at?: string;
  published_at?: string | null;
  scheduled_at?: string | null;
  next_retry?: string | null;
  manual?: boolean;
  platform_post_id?: string | null;
  publication_url?: string | null;
  timezone?: string | null;
  attempts?: number;
}

export interface PublicationSettings {
  youtube_auto_publish: boolean;
  max_uploads_per_day: number;
  publish_schedule: string[];
  publish_timezone: string;
  manual_upload_counts_toward_daily_limit: boolean;
  tiktok_enabled: boolean;
}

export interface PublicationScheduleDay {
  date: string;
  count: number;
  times: string[];
  clip_ids: number[];
}

export interface PublicationSchedulePlan {
  total_clips: number;
  max_per_day: number;
  start_date: string;
  times: string[];
  estimated_days: number;
  days: PublicationScheduleDay[];
  scheduled: { clip_id: number; date: string; time: string; scheduled_at: string }[];
  created_publications?: number;
  publication_ids?: number[];
}

export interface PublicationSchedulePayload {
  clip_ids: number[];
  platform?: string;
  max_per_day: number;
  start_date: string;
  times: string[];
}

export interface YouTubeAccount {
  connected: boolean;
  status: "CONNECTED" | "DISCONNECTED" | "INVALID" | "CONNECTING" | "ERROR";
  channel_name?: string;
  channel_title?: string;
  channel_thumbnail?: string | null;
  channel_id?: string;
  account?: PublicationAccount;
}
