import { request } from "./http";

export interface SessionResponse {
  id: string;
  user_id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SessionMessageResponse {
  id: string;
  user_id: string;
  workspace_id: string;
  session_id: string;
  run_id: string | null;
  role: string;
  content: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface SessionDetailResponse {
  session: SessionResponse;
  messages: SessionMessageResponse[];
}

export function listSessions(workspaceId: string): Promise<SessionResponse[]> {
  return request<SessionResponse[]>(`/api/sessions?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function createSession(workspaceId: string, title = "New Session"): Promise<SessionResponse> {
  return request<SessionResponse>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      workspace_id: workspaceId,
      title,
    }),
  });
}

export function getSessionDetail(sessionId: string): Promise<SessionDetailResponse> {
  return request<SessionDetailResponse>(`/api/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}
