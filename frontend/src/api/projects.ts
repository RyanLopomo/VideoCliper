import { request } from "./client";
import type { Project } from "../types/projects";

export function listProjects() {
  return request<Project[]>("/projects");
}

export function getProject(id: number) {
  return request<Project>(`/projects/${id}`);
}

export function createProject(name: string) {
  return request<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}
