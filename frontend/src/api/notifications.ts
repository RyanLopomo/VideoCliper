import { request } from "./client";
import type { AxisNotification } from "../types/notification";

export function listNotifications() {
  return request<AxisNotification[]>("/notifications");
}

export function markNotificationsRead() {
  return request<{ ok: boolean }>("/notifications/read-all", { method: "POST" });
}

export function testNotification() {
  return request<AxisNotification>("/notifications/test", { method: "POST" });
}
