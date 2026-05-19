import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { createChatRun } from "@/api/chat";
import { getRunDebug, RunChunk } from "@/api/runs";
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
  const activeRunId = ref<string | null>(null);
  const runStatus = ref("idle");
  const messages = ref<ChatMessage[]>([]);
  const tools = ref<ToolCard[]>([]);
  const lastChunkIndex = ref(-1);
  const sending = ref(false);
  const streamError = ref<string | null>(null);
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
      startRunStream(response.run_id);
    } finally {
      sending.value = false;
    }
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
    await getRunDebug(runId);
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

  return {
    sessionId,
    activeRunId,
    runStatus,
    messages,
    tools,
    lastChunkIndex,
    sending,
    streamError,
    sendMessage,
    handleChunk,
    refreshRun,
  };
});
