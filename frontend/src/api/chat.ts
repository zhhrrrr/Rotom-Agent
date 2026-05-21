import { request } from "./http";

export interface ChatRequest {
  workspace_id?: string | null;
  session_id?: string | null;
  message: string;
}

export interface ChatResponse {
  user_id: string;
  workspace_id: string;
  session_id: string;
  run_id: string;
  status: string;
}

export function createChatRun(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
