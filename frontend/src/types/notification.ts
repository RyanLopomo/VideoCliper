export type NotificationType =
  | "PROCESSING_STARTED"
  | "PROCESSING_COMPLETED"
  | "DOWNLOAD_STARTED"
  | "DOWNLOAD_COMPLETED"
  | "DOWNLOAD_ERROR"
  | "DOWNLOAD_CANCELLED"
  | "UPLOAD_STARTED"
  | "UPLOAD_COMPLETED"
  | "PUBLISHED"
  | "ERROR"
  | "RETRY"
  | "RECOVERY";

export interface AxisNotification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  video_id?: number | null;
  clip_id?: number | null;
  publication_id?: number | null;
  platform?: string | null;
  url?: string | null;
  read: boolean;
  created_at: string;
}
