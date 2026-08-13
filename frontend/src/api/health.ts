import { request } from "./client";
import type { Health } from "../types/health";

export function getHealth() {
  return request<Health>("/health");
}
