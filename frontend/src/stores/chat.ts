import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { createChatRun } from "@/api/chat";
import { getRunDebug, RunStreamEvent } from "@/api/runs";
import {
  createSession,
  deleteSession as deleteSessionRequest,
  getSessionDetail,
  listSessions,
  SessionDetailResponse,
  SessionMessageResponse,
  SessionRunResponse,
  SessionResponse,
  SessionToolCallResponse,
} from "@/api/sessions";
import { subscribeRunStream, RunStreamSubscription } from "@/api/stream";

const HISTORY_PAGE_SIZE = 12;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  running?: boolean;
}

export interface ToolCard {
  id: string;
  name: string;
  description: string;
  resultDescription: string;
  status: "running" | "completed" | "failed";
  content: string;
  payload?: Record<string, unknown> | null;
}

export interface ChatRunRecord {
  runId: string;
  status: string;
  userMessage: ChatMessage;
  assistantMessage?: ChatMessage;
  tools: ToolCard[];
}

export const useChatStore = defineStore("chat", () => {
  const sessionId = ref<string | null>(null);
  const sessions = ref<SessionResponse[]>([]);
  const activeRunId = ref<string | null>(null);
  const runStatus = ref("idle");
  const messages = ref<ChatMessage[]>([]);
  const tools = ref<ToolCard[]>([]);
  const runRecords = ref<ChatRunRecord[]>([]);
  const sending = ref(false);
  const loadingSessions = ref(false);
  const loadingOlderHistory = ref(false);
  const hasOlderHistory = ref(false);
  const historyBefore = ref<string | null>(null);
  const streamError = ref<string | null>(null);
  const sendError = ref<string | null>(null);
  const subscription = ref<RunStreamSubscription | null>(null);

  const assistantMessage = computed(() =>
    [...messages.value].reverse().find((message) => message.role === "assistant" && message.running),
  );

  const activeRunRecord = computed(() =>
    activeRunId.value
      ? runRecords.value.find((record) => record.runId === activeRunId.value) ?? null
      : null,
  );

  async function sendMessage(message: string, workspaceId: string | null): Promise<void> {
    const content = message.trim();
    if (!content || sending.value) {
      return;
    }

    sending.value = true;
    streamError.value = null;
    sendError.value = null;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
    };
    messages.value.push(userMessage);
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
      upsertSessionTitleOnce({
        id: response.session_id,
        user_id: response.user_id,
        workspace_id: response.workspace_id,
        title: summarizeTitle(content),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      runRecords.value.push({
        runId: response.run_id,
        status: response.status,
        userMessage,
        assistantMessage: pendingAssistant,
        tools: [],
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
    runRecords.value = [];
    resetHistoryCursor();
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
    const detail = await getSessionDetail(nextSessionId, { limit: HISTORY_PAGE_SIZE });
    sessionId.value = detail.session.id;
    activeRunId.value = null;
    runStatus.value = "idle";
    tools.value = [];
    applySessionDetail(detail, "replace");
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
    runRecords.value = [];
    resetHistoryCursor();
    sending.value = false;
    streamError.value = null;
    sendError.value = null;
  }

  function startRunStream(runId: string): void {
    subscription.value?.close();
    subscription.value = subscribeRunStream(runId, {
      onEvent: handleRunEvent,
      onDone: async (data) => {
        runStatus.value = data.status;
        markAssistantComplete();
        subscription.value?.close();
        subscription.value = null;
        await refreshRun(data.run_id);
      },
      onError: (error) => {
        streamError.value = error.message;
        runStatus.value = "failed";
        markAssistantComplete();
      },
    });
  }

  function handleRunEvent(event: RunStreamEvent): void {
    if (event.type === "message_delta") {
      const target = activeRunRecord.value?.assistantMessage ?? assistantMessage.value ?? createAssistantMessage(true);
      if (activeRunRecord.value && !activeRunRecord.value.assistantMessage) {
        activeRunRecord.value.assistantMessage = target;
      }
      target.content += event.content;
    }

    if (event.type === "message_final") {
      markAssistantComplete();
    }

    if (event.type === "tool_started") {
      const tool = {
        id: String(event.payload?.tool_call_id ?? crypto.randomUUID()),
        name: String(event.payload?.tool_name ?? "tool"),
        description: describeToolEvent("tool_started", event.payload),
        resultDescription: "工具正在执行，Rotom 会在完成后补充结果说明。",
        status: "running",
        content: "",
        payload: event.payload,
      } satisfies ToolCard;
      tools.value.push(tool);
      activeRunRecord.value?.tools.push(tool);
    }

    if (event.type === "tool_delta") {
      const tool = findTool(event);
      if (tool) {
        tool.content += event.content;
        tool.resultDescription = describeLiveToolOutput(tool.name, tool.content);
      }
    }

    if (event.type === "tool_finished") {
      const tool = findTool(event);
      if (tool) {
        tool.status = event.payload?.success === false ? "failed" : "completed";
        tool.description = describeToolEvent("tool_finished", event.payload);
        tool.resultDescription = describeToolResult(
          tool.name,
          event.payload,
          tool.content || event.content,
          asRecord(event.payload?.tool_args),
        );
      }
    }

    if (event.type === "status") {
      runStatus.value = event.content;
      if (activeRunRecord.value) {
        activeRunRecord.value.status = event.content;
      }
    }

    if (event.type === "error") {
      streamError.value = event.content;
      runStatus.value = "failed";
      markAssistantComplete();
      if (activeRunRecord.value) {
        activeRunRecord.value.status = "failed";
      }
    }
  }

  async function refreshRun(runId: string): Promise<void> {
    try {
      const detail = await getRunDebug(runId);
      mergeRunDebug(runId, detail);
      if (sessionId.value) {
        const sessionDetail = await getSessionDetail(sessionId.value, { limit: HISTORY_PAGE_SIZE });
        applySessionDetail(sessionDetail, "replace");
        upsertSession(sessionDetail.session);
      }
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

  function findTool(event: RunStreamEvent): ToolCard | undefined {
    const id = String(event.payload?.tool_call_id ?? "");
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
    runRecords.value = [];
    resetHistoryCursor();
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

  function upsertSessionTitleOnce(session: SessionResponse): void {
    const existing = sessions.value.find((item) => item.id === session.id);
    if (existing && existing.title !== "New Session") {
      sessions.value.splice(sessions.value.indexOf(existing), 1, {
        ...existing,
        updated_at: session.updated_at,
      });
      return;
    }
    upsertSession(session);
  }

  async function loadOlderHistory(): Promise<void> {
    if (!sessionId.value || !hasOlderHistory.value || loadingOlderHistory.value) {
      return;
    }

    loadingOlderHistory.value = true;
    try {
      const detail = await getSessionDetail(sessionId.value, {
        before: historyBefore.value,
        limit: HISTORY_PAGE_SIZE,
      });
      applySessionDetail(detail, "prepend");
    } catch (error) {
      streamError.value = error instanceof Error ? error.message : "Load history failed";
    } finally {
      loadingOlderHistory.value = false;
    }
  }

  function applySessionDetail(detail: SessionDetailResponse, mode: "replace" | "prepend"): void {
    const records = buildRunRecords(detail.runs, detail.messages, detail.tool_calls);
    if (mode === "prepend") {
      const existingIds = new Set(runRecords.value.map((record) => record.runId));
      runRecords.value = [
        ...records.filter((record) => !existingIds.has(record.runId)),
        ...runRecords.value,
      ];
    } else {
      runRecords.value = records;
    }
    syncFlatState();
    hasOlderHistory.value = detail.has_more;
    historyBefore.value = detail.next_before;
  }

  function syncFlatState(): void {
    messages.value = runRecords.value.flatMap((record) =>
      record.assistantMessage ? [record.userMessage, record.assistantMessage] : [record.userMessage],
    );
    tools.value = runRecords.value.flatMap((record) => record.tools);
  }

  function resetHistoryCursor(): void {
    hasOlderHistory.value = false;
    historyBefore.value = null;
    loadingOlderHistory.value = false;
  }

  function buildRunRecords(
    runs: SessionRunResponse[],
    sessionMessages: SessionMessageResponse[],
    toolCalls: SessionToolCallResponse[],
  ): ChatRunRecord[] {
    const sortedRuns = [...runs].sort((left, right) => left.created_at.localeCompare(right.created_at));
    const messagesByRun = new Map<string, SessionMessageResponse[]>();
    for (const message of sessionMessages) {
      if (!message.run_id) {
        continue;
      }
      const group = messagesByRun.get(message.run_id) ?? [];
      group.push(message);
      messagesByRun.set(message.run_id, group);
    }

    return sortedRuns.map((run) => {
      const runMessages = messagesByRun.get(run.id) ?? [];
      const user = runMessages.find((message) => message.role === "user");
      const assistant = [...runMessages].reverse().find((message) => message.role === "assistant");
      return {
        runId: run.id,
        status: run.status,
        userMessage: toChatMessage(user, "user", run.user_input),
        assistantMessage: assistant ? toChatMessage(assistant, "assistant", assistant.content) : undefined,
        tools: toolCalls
          .filter((toolCall) => toolCall.run_id === run.id)
          .map(toToolCard),
      };
    });
  }

  function toChatMessage(
    message: SessionMessageResponse | undefined,
    role: "user" | "assistant",
    fallback: string,
  ): ChatMessage {
    return {
      id: message?.id ?? crypto.randomUUID(),
      role,
      content: message?.content ?? fallback,
      running: false,
    };
  }

  function toToolCard(toolCall: SessionToolCallResponse): ToolCard {
    return {
      id: toolCall.id,
      name: toolCall.tool_name,
      description: describeToolCall(toolCall),
      resultDescription: describePersistedToolResult(toolCall),
      status: toolCall.status === "completed" ? "completed" : toolCall.status === "running" ? "running" : "failed",
      content: formatToolResult(toolCall),
      payload: {
        tool_call_id: toolCall.id,
        tool_name: toolCall.tool_name,
        tool_args: toolCall.tool_args,
        runtime_type: toolCall.runtime_type,
        risk_level: toolCall.risk_level,
        success: toolCall.status === "completed",
        error: toolCall.error,
      },
    };
  }

  function formatToolResult(toolCall: SessionToolCallResponse): string {
    if (toolCall.error) {
      return toolCall.error;
    }
    if (!toolCall.tool_result) {
      return "";
    }
    return JSON.stringify(toolCall.tool_result, null, 2);
  }

  function describeToolCall(toolCall: SessionToolCallResponse): string {
    if (toolCall.status === "running") {
      return describeToolAction(toolCall.tool_name, toolCall.tool_args, "started");
    }
    if (toolCall.status === "completed") {
      return describeToolAction(toolCall.tool_name, toolCall.tool_args, "completed");
    }
    return describeToolAction(toolCall.tool_name, toolCall.tool_args, "failed", toolCall.error);
  }

  function describeToolEvent(
    eventType: "tool_started" | "tool_finished",
    payload: Record<string, unknown> | null | undefined,
  ): string {
    const toolName = String(payload?.tool_name ?? "tool");
    const args = asRecord(payload?.tool_args);
    if (eventType === "tool_started") {
      return describeToolAction(toolName, args, "started");
    }

    const success = payload?.success !== false;
    return describeToolAction(
      toolName,
      args,
      success ? "completed" : "failed",
      typeof payload?.error === "string" ? payload.error : undefined,
    );
  }

  function describeToolAction(
    toolName: string,
    args: Record<string, unknown>,
    phase: "started" | "completed" | "failed",
    error?: string | null,
  ): string {
    const prefix =
      phase === "started"
        ? "Rotom 正在"
        : phase === "completed"
          ? "Rotom 已经"
          : "Rotom 没能";

    if (phase === "failed") {
      return `${prefix}${toolVerb(toolName, args)}。${error ? `原因：${error}` : ""}`;
    }
    return `${prefix}${toolVerb(toolName, args)}。`;
  }

  function toolVerb(toolName: string, args: Record<string, unknown>): string {
    if (toolName === "list_dir") {
      return `查看目录 ${formatPath(args.path)}`;
    }
    if (toolName === "read_file") {
      return `读取文件 ${formatPath(args.path)}`;
    }
    if (toolName === "write_file") {
      return `写入文件 ${formatPath(args.path)}`;
    }
    if (toolName === "run_shell") {
      return `在隔离 Docker 环境中执行命令 ${formatInline(args.command)}`;
    }
    return `调用工具 ${toolName}`;
  }

  function describeToolResult(
    toolName: string,
    payload: Record<string, unknown> | null | undefined,
    fallback: string,
    args: Record<string, unknown> = {},
  ): string {
    if (payload?.success === false) {
      const error = typeof payload.error === "string" ? payload.error : fallback;
      return error ? `工具执行失败：${error}` : "工具执行失败。";
    }
    if (toolName === "list_dir") {
      return describeListDirText(fallback, args);
    }
    if (toolName === "read_file") {
      return describeReadFileText(fallback, args);
    }
    if (toolName === "write_file") {
      return describeWriteFileText(fallback, args);
    }
    if (toolName === "run_shell") {
      return describeShellText(fallback);
    }
    return fallback ? `工具返回结果：${previewText(fallback)}` : "工具调用完成。";
  }

  function describePersistedToolResult(toolCall: SessionToolCallResponse): string {
    if (toolCall.status === "running") {
      return "工具正在执行，Rotom 会在完成后补充结果说明。";
    }
    if (toolCall.error) {
      return `工具执行失败：${toolCall.error}`;
    }
    const result = asRecord(toolCall.tool_result);
    if (result.success === false) {
      const error = typeof result.error === "string" ? result.error : "未知错误";
      return `工具执行失败：${error}`;
    }

    const data = asRecord(result.data);
    if (toolCall.tool_name === "list_dir") {
      return describeListDirData(data, toolCall.tool_args);
    }
    if (toolCall.tool_name === "read_file") {
      return describeReadFileData(data, toolCall.tool_args);
    }
    if (toolCall.tool_name === "write_file") {
      return describeWriteFileData(data, toolCall.tool_args);
    }
    if (toolCall.tool_name === "run_shell") {
      return describeShellData(data);
    }
    return "工具调用完成，结果已记录在技术细节中。";
  }

  function describeLiveToolOutput(toolName: string, content: string): string {
    if (!content.trim()) {
      return "工具正在执行，暂时还没有返回内容。";
    }
    if (toolName === "list_dir") {
      return describeListDirText(content, {});
    }
    if (toolName === "read_file") {
      return describeReadFileText(content, {});
    }
    if (toolName === "write_file") {
      return describeWriteFileText(content, {});
    }
    if (toolName === "run_shell") {
      return describeShellText(content);
    }
    return `工具已经返回部分结果：${previewText(content)}`;
  }

  function describeListDirData(data: Record<string, unknown>, args: Record<string, unknown>): string {
    const entries = Array.isArray(data.entries) ? data.entries : [];
    const path = formatPath(args.path);
    if (entries.length === 0) {
      return `目录 ${path} 是空的，没有发现文件或子目录。`;
    }

    const names = entries
      .map((entry) => asRecord(entry).name)
      .filter((name): name is string => typeof name === "string")
      .slice(0, 5);
    const suffix = entries.length > names.length ? ` 等 ${entries.length} 个项目` : `${entries.length} 个项目`;
    return `目录 ${path} 中发现 ${suffix}${names.length ? `：${names.join("、")}` : ""}。`;
  }

  function describeReadFileData(data: Record<string, unknown>, args: Record<string, unknown>): string {
    const content = typeof data.content === "string" ? data.content : "";
    return describeReadFileText(content, args);
  }

  function describeWriteFileData(data: Record<string, unknown>, args: Record<string, unknown>): string {
    const path = typeof data.path === "string" ? data.path : typeof args.path === "string" ? args.path : ".";
    const bytes = typeof data.bytes === "number" ? data.bytes : null;
    return bytes === null
      ? `文件 ${formatPath(path)} 已写入完成。`
      : `文件 ${formatPath(path)} 已写入完成，共写入 ${bytes} 字节。`;
  }

  function describeShellData(data: Record<string, unknown>): string {
    const exitCode = typeof data.exit_code === "number" ? data.exit_code : data.exit_code === null ? "null" : "未知";
    const timedOut = data.timed_out === true;
    const stdout = typeof data.stdout === "string" ? data.stdout.trim() : "";
    const stderr = typeof data.stderr === "string" ? data.stderr.trim() : "";
    if (timedOut) {
      return `命令执行超时，已停止运行。${stderr ? `错误输出：${previewText(stderr)}` : ""}`;
    }
    if (stderr && !stdout) {
      return `命令执行结束，退出码 ${exitCode}，返回错误输出：${previewText(stderr)}`;
    }
    if (stdout) {
      return `命令执行结束，退出码 ${exitCode}，输出预览：${previewText(stdout)}`;
    }
    return `命令执行结束，退出码 ${exitCode}，没有输出内容。`;
  }

  function describeListDirText(content: string, args: Record<string, unknown>): string {
    const parsed = tryParseJson(content);
    if (parsed) {
      const data = Array.isArray(parsed)
        ? { entries: parsed }
        : asRecord(parsed).entries
          ? asRecord(parsed)
          : asRecord(asRecord(parsed).data);
      return describeListDirData(asRecord(data), args);
    }
    return content.trim()
      ? `目录内容已经读取完成，结果预览：${previewText(content)}`
      : "目录内容已经读取完成。";
  }

  function describeReadFileText(content: string, args: Record<string, unknown>): string {
    const path = typeof args.path === "string" ? ` ${formatPath(args.path)}` : "";
    const text = content.trim();
    if (!text) {
      return `文件${path} 已读取完成，内容为空。`;
    }
    return `文件${path} 已读取完成，共 ${content.length} 个字符。预览：${previewText(text)}`;
  }

  function describeWriteFileText(content: string, args: Record<string, unknown>): string {
    const parsed = tryParseJson(content);
    if (parsed) {
      return describeWriteFileData(asRecord(parsed), args);
    }
    const path = typeof args.path === "string" ? ` ${formatPath(args.path)}` : "";
    return `文件${path} 已写入完成。`;
  }

  function describeShellText(content: string): string {
    const parsed = tryParseJson(content);
    if (parsed) {
      return describeShellData(asRecord(parsed));
    }
    const text = content.trim();
    return text ? `命令已经执行完成，输出预览：${previewText(text)}` : "命令已经执行完成，没有输出内容。";
  }

  function tryParseJson(content: string): unknown | null {
    try {
      return JSON.parse(content);
    } catch {
      return null;
    }
  }

  function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  }

  function formatPath(value: unknown): string {
    return formatInline(typeof value === "string" && value ? value : ".");
  }

  function formatInline(value: unknown): string {
    return `“${String(value ?? "")}”`;
  }

  function previewText(value: string, limit = 120): string {
    const normalized = value.replace(/\s+/g, " ").trim();
    if (normalized.length <= limit) {
      return normalized;
    }
    return `${normalized.slice(0, limit)}...`;
  }

  function mergeRunDebug(runId: string, detail: Awaited<ReturnType<typeof getRunDebug>>): void {
    const record = runRecords.value.find((item) => item.runId === runId);
    if (!record) {
      return;
    }

    record.status = String(detail.run.status ?? record.status);
    const assistant = [...detail.messages].reverse().find((message) => message.role === "assistant");
    if (assistant) {
      const assistantMessage: ChatMessage = {
        id: String(assistant.id),
        role: "assistant",
        content: String(assistant.content ?? ""),
        running: false,
      };
      record.assistantMessage = assistantMessage;
      const index = messages.value.findIndex((message) => message.id === record.assistantMessage?.id);
      if (index < 0) {
        const pendingIndex = messages.value.findIndex(
          (message) => message.role === "assistant" && message.running,
        );
        if (pendingIndex >= 0) {
          messages.value.splice(pendingIndex, 1, assistantMessage);
        }
      }
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
    runRecords,
    sending,
    loadingSessions,
    loadingOlderHistory,
    hasOlderHistory,
    streamError,
    sendError,
    sendMessage,
    loadWorkspaceSessions,
    createBlankSession,
    selectSession,
    deleteSession,
    loadOlderHistory,
    selectBlankSession,
    handleRunEvent,
    refreshRun,
    reset,
  };
});
