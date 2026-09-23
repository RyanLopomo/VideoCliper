import { API_BASE_URL, request } from "./client";
import type { Video } from "../types/video";

export interface UploadPublicationPlan {
  enabled: boolean;
  maxPerDay: number;
  startDate: string;
  times: string[];
  timezone: string;
  editingStyle?: string;
  targetClipCount?: number;
  targetClipDuration?: number;
}

export interface ClipConfigSuggestion {
  recommended_count: number;
  recommended_duration_seconds: number;
  reason: string;
  confidence: number;
}

export interface DownloadProgressItem {
  download_id: string;
  video_id?: number | null;
  status: "downloading" | "uploading" | "completed" | "error" | "cancelled";
  transfer_type?: "download" | "upload";
  progress?: number | null;
  downloaded_bytes?: number | null;
  total_bytes?: number | null;
  speed_bytes?: number | null;
  eta_seconds?: number | null;
  filename?: string | null;
  message?: string | null;
  updated_at?: string | null;
}

export function listVideos() {
  return request<Video[]>("/videos");
}

export function getVideo(id: number) {
  return request<Video>(`/videos/${id}/status`);
}

export function uploadVideo(projectId: number, file: File, publicationPlan?: UploadPublicationPlan | null, onProgress?: (item: DownloadProgressItem) => void) {
  const body = new FormData();
  body.append("project_id", String(projectId));
  body.append("file", file);
  if (publicationPlan?.enabled) {
    body.append("publication_plan_enabled", "true");
    body.append("publication_max_per_day", String(publicationPlan.maxPerDay));
    body.append("publication_start_date", publicationPlan.startDate);
    body.append("publication_times", JSON.stringify(publicationPlan.times));
    body.append("publication_timezone", publicationPlan.timezone);
  }
  if (publicationPlan?.editingStyle) body.append("editing_style", publicationPlan.editingStyle);
  if (publicationPlan?.targetClipCount) body.append("target_clip_count", String(publicationPlan.targetClipCount));
  if (publicationPlan?.targetClipDuration) body.append("target_clip_duration", String(publicationPlan.targetClipDuration));
  if (!onProgress) return request<Video>("/videos/upload", { method: "POST", body });
  const uploadId = `upload-${Date.now()}`;
  return new Promise<Video>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/videos/upload`);
    xhr.upload.onprogress = event => {
      onProgress({
        download_id: uploadId,
        status: "uploading",
        transfer_type: "upload",
        progress: event.lengthComputable ? (event.loaded / event.total) * 100 : null,
        downloaded_bytes: event.loaded,
        total_bytes: event.lengthComputable ? event.total : null,
        filename: file.name,
      });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress({ download_id: uploadId, status: "completed", transfer_type: "upload", progress: 100, filename: file.name });
        resolve(JSON.parse(xhr.responseText));
        return;
      }
      try {
        const data = JSON.parse(xhr.responseText);
        const message = typeof data.detail === "string" ? data.detail : data.detail?.error || "Falha no upload";
        onProgress({ download_id: uploadId, status: "error", transfer_type: "upload", filename: file.name, message });
        reject(new Error(message));
      } catch {
        onProgress({ download_id: uploadId, status: "error", transfer_type: "upload", filename: file.name, message: "Falha no upload" });
        reject(new Error("Falha no upload"));
      }
    };
    xhr.onerror = () => {
      onProgress({ download_id: uploadId, status: "error", transfer_type: "upload", filename: file.name, message: "Falha no upload" });
      reject(new Error("Falha no upload"));
    };
    xhr.send(body);
  });
}

export function importVideoFromUrl(projectId: number, url: string, publicationPlan?: UploadPublicationPlan | null) {
  return request<Video>("/videos/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      url,
      publication_plan_enabled: Boolean(publicationPlan?.enabled),
      publication_max_per_day: publicationPlan?.enabled ? publicationPlan.maxPerDay : null,
      publication_start_date: publicationPlan?.enabled ? publicationPlan.startDate : null,
      publication_times: publicationPlan?.enabled ? publicationPlan.times : null,
      publication_timezone: publicationPlan?.enabled ? publicationPlan.timezone : null,
      editing_style: publicationPlan?.editingStyle || "AUTO",
      target_clip_count: publicationPlan?.targetClipCount || null,
      target_clip_duration: publicationPlan?.targetClipDuration || null,
    }),
  });
}

export function readUrlMetadata(url: string) {
  return request<{ duration: number | null }>("/videos/url-metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export function suggestClipConfig(duration: number) {
  return request<ClipConfigSuggestion>("/videos/clip-config/suggest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ duration }),
  });
}

export function cancelDownload(downloadId: string) {
  return request<{ ok: boolean; download_id: string; status: string }>(`/videos/downloads/${downloadId}/cancel`, {
    method: "POST",
  });
}

export function pauseVideo(id: number) {
  return request<Video>(`/videos/${id}/pause`, { method: "POST" });
}

export function startVideo(id: number) {
  return request<Video>(`/videos/${id}/start`, { method: "POST" });
}

export function resumeVideo(id: number) {
  return request<Video>(`/videos/${id}/resume`, { method: "POST" });
}

export function retryVideoPublicationPlan(id: number) {
  return request<Video>(`/videos/${id}/publication-plan/retry`, { method: "POST" });
}

export function restartVideo(id: number) {
  return request<Video>(`/videos/${id}/restart`, { method: "POST" });
}
