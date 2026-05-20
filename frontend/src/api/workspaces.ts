import { request } from "./http";

export interface WorkspaceResponse {
  id: string;
  user_id: string;
  name: string;
  root_path: string;
  created_at: string;
  updated_at: string;
}

export interface CreateWorkspaceRequest {
  name: string;
}

export function listWorkspaces(): Promise<WorkspaceResponse[]> {
  return request<WorkspaceResponse[]>("/api/workspaces");
}

export function createWorkspace(payload: CreateWorkspaceRequest): Promise<WorkspaceResponse> {
  return request<WorkspaceResponse>("/api/workspaces", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspace(workspaceId: string): Promise<void> {
  return request<void>(`/api/workspaces/${workspaceId}`, {
    method: "DELETE",
  });
}
