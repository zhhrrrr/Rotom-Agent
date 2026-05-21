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
  runs: SessionRunResponse[];
  tool_calls: SessionToolCallResponse[];
  has_more: boolean;
  next_before: string | null;
}

export interface SessionRunResponse {
  id: string;
  user_id: string;
  workspace_id: string;
  session_id: string;
  user_input: string;
  status: string;
  current_step: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface SessionToolCallResponse {
  id: string;
  user_id: string;
  workspace_id: string;
  run_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  tool_result: Record<string, unknown> | null;
  status: "running" | "completed" | "failed" | string;
  runtime_type: string | null;
  risk_level: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
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

export interface SessionDetailOptions {
  before?: string | null;
  limit?: number;
}

export function getSessionDetail(
  sessionId: string,
  options: SessionDetailOptions = {},
): Promise<SessionDetailResponse> {
  const params = new URLSearchParams();
  if (options.before) {
    params.set("before", options.before);
  }
  if (options.limit) {
    params.set("limit", String(options.limit));
  }
  const query = params.toString();
  return request<SessionDetailResponse>(`/api/sessions/${sessionId}${query ? `?${query}` : ""}`);
}

export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}
