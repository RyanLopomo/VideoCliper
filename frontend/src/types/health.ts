export interface Health {
  status: string;
  application?: string;
  database?: string;
  redis?: string;
  worker?: string;
  worker_status?: string;
  pending?: number;
  uploading?: number;
  processing?: number;
  waiting_retry?: number;
  failed?: number;
  published?: number;
  metrics?: {
    clips_generated?: number;
    publications?: number;
    publications_success?: number;
    failures?: number;
    retries?: number;
    avg_publication_seconds?: number | null;
  };
}
