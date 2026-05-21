import { request } from "./http";

export type RunStreamEventType =
  | "message_delta"
  | "message_final"
  | "tool_started"
  | "tool_delta"
  | "tool_finished"
  | "status"
  | "error";

export interface RunStreamEvent {
  run_id: string;
  user_id: string | null;
  workspace_id: string | null;
  session_id: string | null;
  type: RunStreamEventType;
  role: string | null;
  content: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface RunDebugResponse {
  run: Record<string, unknown>;
  messages: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  model_calls: Array<Record<string, unknown>>;
  event_logs: Array<Record<string, unknown>>;
}

export function getRunDebug(runId: string): Promise<RunDebugResponse> {
  return request<RunDebugResponse>(`/api/runs/${runId}`);
}
