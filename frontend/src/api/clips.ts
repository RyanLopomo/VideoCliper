import { request } from "./client";
import type { Clip } from "../types/clip";

export function listVideoClips(videoId: number) {
  return request<Clip[]>(`/clips/video/${videoId}`);
}
