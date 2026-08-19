import { request } from "./client";
import type { Publication, YouTubeAccount } from "../types/publication";

export function listPublications() {
  return request<Publication[]>("/publications");
}

export function getYouTubeAccount() {
  return request<YouTubeAccount>("/youtube/account");
}

export async function startYouTubeAuth() {
  const data = await request<{ auth_url: string }>("/youtube/auth");
  window.location.href = data.auth_url;
}

export function disconnectYouTube() {
  return request<YouTubeAccount>("/youtube/disconnect", { method: "POST" });
}
