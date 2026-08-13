export type PublicationStatus = "PENDING" | "UPLOADING" | "PROCESSING" | "WAITING_RETRY" | "PUBLISHED" | "FAILED";

export interface PublicationSummary {
  status: PublicationStatus;
  total: number;
}
