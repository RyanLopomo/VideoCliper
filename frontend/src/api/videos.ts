import { request } from "./client";
import type { Video } from "../types/video";

export interface UploadPublicationPlan {
  enabled: boolean;
  maxPerDay: number;
  startDate: string;
  times: string[];
  timezone: string;
}

export function listVideos() {
  return request<Video[]>("/videos");
}

export function getVideo(id: number) {
  return request<Video>(`/videos/${id}/status`);
}

export function uploadVideo(projectId: number, file: File, publicationPlan?: UploadPublicationPlan | null) {
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
  return request<Video>("/videos/upload", { method: "POST", body });
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
    }),
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

export function restartVideo(id: number) {
  return request<Video>(`/videos/${id}/restart`, { method: "POST" });
}
