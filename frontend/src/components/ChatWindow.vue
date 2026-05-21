<template>
  <section class="chat-window">
    <RunStatusBar :status="status" />
    <div ref="messageList" class="message-list" @scroll="onScroll">
      <button
        v-if="hasOlder"
        class="history-loader"
        type="button"
        :disabled="loadingOlder"
        @click="requestOlderHistory"
      >
        {{ loadingOlder ? "Loading..." : "Load earlier runs" }}
      </button>
      <section v-for="record in runRecords" :key="record.runId" class="run-record">
        <MessageBubble :message="record.userMessage" />
        <details class="run-process-card" :open="record.status === 'running' || record.tools.length > 0">
          <summary>
            <span class="tool-bolt">ϟ</span>
            <strong>Run Process</strong>
            <small>{{ record.tools.length }} tools · {{ record.status }}</small>
          </summary>
          <div class="run-process-body">
            <ToolCallCard v-for="tool in record.tools" :key="tool.id" :tool="tool" />
            <p v-if="record.tools.length === 0" class="process-empty">No tool calls for this run.</p>
          </div>
        </details>
        <MessageBubble
          v-if="record.assistantMessage"
          :message="record.assistantMessage"
        />
      </section>
    </div>
    <p v-if="error" class="stream-error">{{ error }}</p>
    <form class="composer" @submit.prevent="submit">
      <textarea v-model="draft" rows="3" placeholder="Ask Rotom Agent..." />
      <button type="submit" :disabled="disabled || !draft.trim()">Send</button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";

import { ChatRunRecord } from "@/stores/chat";
import MessageBubble from "./MessageBubble.vue";
import RunStatusBar from "./RunStatusBar.vue";
import ToolCallCard from "./ToolCallCard.vue";

const props = defineProps<{
  runRecords: ChatRunRecord[];
  status: string;
  disabled?: boolean;
  error?: string | null;
  hasOlder?: boolean;
  loadingOlder?: boolean;
}>();

const emit = defineEmits<{
  send: [message: string];
  loadOlder: [];
}>();

const draft = ref("");
const messageList = ref<HTMLElement | null>(null);
const stickToBottom = ref(true);
const pendingHistoryScroll = ref<{ height: number; top: number } | null>(null);

function submit(): void {
  const message = draft.value.trim();
  if (!message) {
    return;
  }
  emit("send", message);
  draft.value = "";
}

function onScroll(): void {
  const element = messageList.value;
  if (!element) {
    return;
  }

  const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
  stickToBottom.value = distanceToBottom < 90;

  if (element.scrollTop <= 32) {
    requestOlderHistory();
  }
}

function requestOlderHistory(): void {
  const element = messageList.value;
  if (!element || !props.hasOlder || props.loadingOlder) {
    return;
  }

  pendingHistoryScroll.value = {
    height: element.scrollHeight,
    top: element.scrollTop,
  };
  emit("loadOlder");
}

function scrollToBottom(): void {
  const element = messageList.value;
  if (element) {
    element.scrollTop = element.scrollHeight;
  }
}

watch(
  () => props.runRecords.length,
  async () => {
    await nextTick();
    const element = messageList.value;
    if (!element) {
      return;
    }

    if (pendingHistoryScroll.value) {
      element.scrollTop =
        element.scrollHeight - pendingHistoryScroll.value.height + pendingHistoryScroll.value.top;
      pendingHistoryScroll.value = null;
      return;
    }

    if (stickToBottom.value) {
      scrollToBottom();
    }
  },
  { flush: "post" },
);

watch(
  () =>
    props.runRecords
      .map((record) => `${record.runId}:${record.assistantMessage?.content.length ?? 0}:${record.tools.length}`)
      .join("|"),
  async () => {
    if (!stickToBottom.value) {
      return;
    }
    await nextTick();
    scrollToBottom();
  },
  { flush: "post" },
);
</script>
