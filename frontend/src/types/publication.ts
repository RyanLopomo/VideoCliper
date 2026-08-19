export type PublicationStatus = "PENDING" | "UPLOADING" | "PROCESSING" | "WAITING_RETRY" | "PUBLISHED" | "FAILED";

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
  thumbnail_url?: string | null;
  platform: string;
  account?: PublicationAccount | null;
  status: PublicationStatus;
  created_at?: string;
  updated_at?: string;
  published_at?: string | null;
  platform_post_id?: string | null;
  publication_url?: string | null;
  attempts?: number;
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
