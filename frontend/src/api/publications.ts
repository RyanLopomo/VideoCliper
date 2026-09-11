import { request } from "./client";
import type { Publication, PublicationSchedulePayload, PublicationSchedulePlan, PublicationSettings, YouTubeAccount } from "../types/publication";

export function listPublications() {
  return request<Publication[]>("/publications");
}

export function getYouTubeAccount() {
  return request<YouTubeAccount>("/youtube/account");
}

export function getPublicationSettings() {
  return request<PublicationSettings>("/publication-settings");
}

export function savePublicationSettings(settings: PublicationSettings) {
  return request<PublicationSettings>("/publication-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function publishClipNow(clipId: number, platform = "YOUTUBE") {
  return request<Publication>("/publications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clip_id: clipId, platform }),
  });
}

export function scheduleClipPublication(clipId: number, scheduledAt: string, platform = "YOUTUBE") {
  return request<Publication>("/publications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clip_id: clipId, platform, scheduled_at: scheduledAt }),
  });
}

export function updatePublicationSchedule(publicationId: number, scheduledAt: string) {
  return request<Publication>(`/publications/${publicationId}/schedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scheduled_at: scheduledAt }),
  });
}

export function suggestPublicationTimes(maxPerDay: number) {
  return request<{ times: string[] }>("/publications/schedule/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_per_day: maxPerDay }),
  });
}

export function previewPublicationSchedule(payload: PublicationSchedulePayload) {
  return request<PublicationSchedulePlan>("/publications/schedule/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function confirmPublicationSchedule(payload: PublicationSchedulePayload) {
  return request<PublicationSchedulePlan>("/publications/schedule/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function cancelPublication(publicationId: number) {
  return request<Publication>(`/publications/${publicationId}/cancel`, { method: "POST" });
}

export async function startYouTubeAuth() {
  const data = await request<{ auth_url: string }>("/youtube/auth");
  window.location.href = data.auth_url;
}

export function disconnectYouTube() {
  return request<YouTubeAccount>("/youtube/disconnect", { method: "POST" });
}
