import { request } from "./http";

export type RunChunkType =
  | "message_delta"
  | "message_final"
  | "tool_started"
  | "tool_delta"
  | "tool_finished"
  | "status"
  | "error";

export interface RunChunk {
  id: string;
  run_id: string;
  user_id: string;
  workspace_id: string;
  session_id: string;
  chunk_index: number;
  chunk_type: RunChunkType;
  role: string | null;
  content: string;
  payload: Record<string, unknown> | null;
  is_final: boolean;
  created_at: string;
}

export interface RunDebugResponse {
  run: Record<string, unknown>;
  messages: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  model_calls: Array<Record<string, unknown>>;
  event_logs: Array<Record<string, unknown>>;
}

export interface WorkspaceResponse {
  id: string;
  user_id: string;
  name: string;
  root_path: string;
  created_at: string;
  updated_at: string;
}

export function listRunChunks(runId: string, after?: number): Promise<RunChunk[]> {
  const params = after === undefined ? "" : `?after=${after}`;
  return request<RunChunk[]>(`/api/runs/${runId}/chunks${params}`);
}

export function getRunDebug(runId: string): Promise<RunDebugResponse> {
  return request<RunDebugResponse>(`/api/runs/${runId}`);
}

export function listWorkspaces(): Promise<WorkspaceResponse[]> {
  return request<WorkspaceResponse[]>("/api/workspaces");
}
