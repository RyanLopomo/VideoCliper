import { request } from "./client";
import type { Clip } from "../types/clip";

export function listVideoClips(videoId: number) {
  return request<Clip[]>(`/clips/video/${videoId}`);
}

export function stylePreviewUrl(clipId: number, style: string) {
  return `/clips/${clipId}/style-preview/${style}`;
}

export function suggestClipStyle(clipId: number) {
  return request<{ recommended_style: string; confidence: number; reason: string; editing_direction: string[] }>(`/clips/${clipId}/style/suggest`, { method: "POST" });
}

export function updateClipStyle(clipId: number, style: string) {
  return request<{ id: number; editing_style: string; applied_preset?: string | null }>(`/clips/${clipId}/style`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ style }),
  });
}
