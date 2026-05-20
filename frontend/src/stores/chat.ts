import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { createChatRun } from "@/api/chat";
import { getRunDebug, RunChunk } from "@/api/runs";
import {
  createSession,
  deleteSession as deleteSessionRequest,
  getSessionDetail,
  listSessions,
  SessionResponse,
} from "@/api/sessions";
import { subscribeRunStream, RunStreamSubscription } from "@/api/stream";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  running?: boolean;
}

export interface ToolCard {
  id: string;
  name: string;
  status: "running" | "completed" | "failed";
  content: string;
  payload?: Record<string, unknown> | null;
}

export const useChatStore = defineStore("chat", () => {
  const sessionId = ref<string | null>(null);
  const sessions = ref<SessionResponse[]>([]);
  const activeRunId = ref<string | null>(null);
  const runStatus = ref("idle");
  const messages = ref<ChatMessage[]>([]);
  const tools = ref<ToolCard[]>([]);
  const lastChunkIndex = ref(-1);
  const sending = ref(false);
  const loadingSessions = ref(false);
  const streamError = ref<string | null>(null);
  const sendError = ref<string | null>(null);
  const subscription = ref<RunStreamSubscription | null>(null);

  const assistantMessage = computed(() =>
    [...messages.value].reverse().find((message) => message.role === "assistant" && message.running),
  );

  async function sendMessage(message: string, workspaceId: string | null): Promise<void> {
    const content = message.trim();
    if (!content || sending.value) {
      return;
    }

    sending.value = true;
    streamError.value = null;
    sendError.value = null;
    messages.value.push({
      id: crypto.randomUUID(),
      role: "user",
      content,
    });
    const pendingAssistant: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      running: true,
    };
    messages.value.push(pendingAssistant);

    try {
      const response = await createChatRun({
        workspace_id: workspaceId,
        session_id: sessionId.value,
        message: content,
      });
      sessionId.value = response.session_id;
      activeRunId.value = response.run_id;
      runStatus.value = response.status;
      lastChunkIndex.value = -1;
      upsertSession({
        id: response.session_id,
        user_id: response.user_id,
        workspace_id: response.workspace_id,
        title: summarizeTitle(content),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      startRunStream(response.run_id);
    } catch (error) {
      sendError.value = error instanceof Error ? error.message : "Send failed";
      pendingAssistant.content = sendError.value;
      pendingAssistant.running = false;
      runStatus.value = "failed";
      throw error;
    } finally {
      sending.value = false;
    }
  }

  async function loadWorkspaceSessions(workspaceId: string | null): Promise<void> {
    subscription.value?.close();
    subscription.value = null;
    sessionId.value = null;
    activeRunId.value = null;
    runStatus.value = "idle";
    messages.value = [];
    tools.value = [];
    sessions.value = [];
    if (!workspaceId) {
      return;
    }

    loadingSessions.value = true;
    try {
      sessions.value = await listSessions(workspaceId);
    } finally {
      loadingSessions.value = false;
    }
  }

  async function createBlankSession(workspaceId: string | null): Promise<void> {
    if (!workspaceId) {
      return;
    }

    const session = await createSession(workspaceId);
    upsertSession(session);
    selectBlankSession(session.id);
  }

  async function selectSession(nextSessionId: string): Promise<void> {
    subscription.value?.close();
    subscription.value = null;
    const detail = await getSessionDetail(nextSessionId);
    sessionId.value = detail.session.id;
    activeRunId.value = null;
    runStatus.value = "idle";
    tools.value = [];
    messages.value = detail.messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map((message) => ({
        id: message.id,
        role: message.role as "user" | "assistant",
        content: message.content,
        running: false,
      }));
    upsertSession(detail.session);
  }

  async function deleteSession(sessionIdToDelete: string): Promise<void> {
    await deleteSessionRequest(sessionIdToDelete);
    sessions.value = sessions.value.filter((session) => session.id !== sessionIdToDelete);
    if (sessionId.value === sessionIdToDelete) {
      selectBlankSession(null);
    }
  }

  function selectBlankSession(nextSessionId: string | null): void {
    subscription.value?.close();
    subscription.value = null;
    sessionId.value = nextSessionId;
    activeRunId.value = null;
    runStatus.value = "idle";
    messages.value = [];
    tools.value = [];
    lastChunkIndex.value = -1;
    sending.value = false;
    streamError.value = null;
    sendError.value = null;
  }

  function startRunStream(runId: string): void {
    subscription.value?.close();
    subscription.value = subscribeRunStream(runId, {
      onChunk: handleChunk,
      onDone: async (data) => {
        runStatus.value = data.status;
        markAssistantComplete();
        subscription.value?.close();
        subscription.value = null;
        await refreshRun(data.run_id);
      },
      onError: (error) => {
        streamError.value = error.message;
        markAssistantComplete();
      },
    });
  }

  function handleChunk(chunk: RunChunk): void {
    lastChunkIndex.value = Math.max(lastChunkIndex.value, chunk.chunk_index);

    if (chunk.chunk_type === "message_delta") {
      const target = assistantMessage.value ?? createAssistantMessage(true);
      target.content += chunk.content;
    }

    if (chunk.chunk_type === "message_final") {
      markAssistantComplete();
    }

    if (chunk.chunk_type === "tool_started") {
      tools.value.push({
        id: String(chunk.payload?.tool_call_id ?? chunk.id),
        name: String(chunk.payload?.tool_name ?? "tool"),
        status: "running",
        content: "",
        payload: chunk.payload,
      });
    }

    if (chunk.chunk_type === "tool_delta") {
      const tool = findTool(chunk);
      if (tool) {
        tool.content += chunk.content;
      }
    }

    if (chunk.chunk_type === "tool_finished") {
      const tool = findTool(chunk);
      if (tool) {
        tool.status = chunk.payload?.success === false ? "failed" : "completed";
        if (chunk.content && !tool.content.includes(chunk.content)) {
          tool.content += tool.content ? `\n${chunk.content}` : chunk.content;
        }
      }
    }

    if (chunk.chunk_type === "status") {
      runStatus.value = chunk.content;
    }

    if (chunk.chunk_type === "error") {
      streamError.value = chunk.content;
      runStatus.value = "failed";
      markAssistantComplete();
    }
  }

  async function refreshRun(runId: string): Promise<void> {
    try {
      await getRunDebug(runId);
    } catch (error) {
      streamError.value = error instanceof Error ? error.message : "Refresh failed";
    }
  }

  function createAssistantMessage(running: boolean): ChatMessage {
    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      running,
    };
    messages.value.push(message);
    return message;
  }

  function markAssistantComplete(): void {
    for (const message of messages.value) {
      if (message.role === "assistant") {
        message.running = false;
      }
    }
  }

  function findTool(chunk: RunChunk): ToolCard | undefined {
    const id = String(chunk.payload?.tool_call_id ?? "");
    return tools.value.find((tool) => tool.id === id) ?? tools.value.at(-1);
  }

  function reset(): void {
    subscription.value?.close();
    subscription.value = null;
    sessionId.value = null;
    sessions.value = [];
    activeRunId.value = null;
    runStatus.value = "idle";
    messages.value = [];
    tools.value = [];
    lastChunkIndex.value = -1;
    sending.value = false;
    loadingSessions.value = false;
    streamError.value = null;
    sendError.value = null;
  }

  function upsertSession(session: SessionResponse): void {
    const index = sessions.value.findIndex((item) => item.id === session.id);
    if (index >= 0) {
      sessions.value.splice(index, 1, session);
    } else {
      sessions.value.unshift(session);
    }
  }

  function summarizeTitle(content: string): string {
    const normalized = content.trim().replace(/\s+/g, " ");
    return normalized.slice(0, 48) || "New Session";
  }

  return {
    sessionId,
    sessions,
    activeRunId,
    runStatus,
    messages,
    tools,
    lastChunkIndex,
    sending,
    loadingSessions,
    streamError,
    sendError,
    sendMessage,
    loadWorkspaceSessions,
    createBlankSession,
    selectSession,
    deleteSession,
    selectBlankSession,
    handleChunk,
    refreshRun,
    reset,
  };
});
