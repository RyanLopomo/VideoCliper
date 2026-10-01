import { request } from "./client";
import type { Video } from "../types/video";

export function listVideos() {
  return request<Video[]>("/videos");
}

export function getVideo(id: number) {
  return request<Video>(`/videos/${id}/status`);
}

export function uploadVideo(projectId: number, file: File) {
  const body = new FormData();
  body.append("project_id", String(projectId));
  body.append("file", file);
  return request<Video>("/videos/upload", { method: "POST", body });
}

export function importVideoFromUrl(projectId: number, url: string) {
  return request<Video>("/videos/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, url }),
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
