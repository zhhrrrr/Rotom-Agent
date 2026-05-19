<template>
  <section class="chat-window">
    <RunStatusBar :status="status" />
    <div class="message-list">
      <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
      <ToolCallCard v-for="tool in tools" :key="tool.id" :tool="tool" />
    </div>
    <p v-if="error" class="stream-error">{{ error }}</p>
    <form class="composer" @submit.prevent="submit">
      <textarea v-model="draft" rows="3" placeholder="Ask Rotom Agent..." />
      <button type="submit" :disabled="disabled || !draft.trim()">Send</button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";

import { ChatMessage, ToolCard } from "@/stores/chat";
import MessageBubble from "./MessageBubble.vue";
import RunStatusBar from "./RunStatusBar.vue";
import ToolCallCard from "./ToolCallCard.vue";

defineProps<{
  messages: ChatMessage[];
  tools: ToolCard[];
  status: string;
  disabled?: boolean;
  error?: string | null;
}>();

const emit = defineEmits<{
  send: [message: string];
}>();

const draft = ref("");

function submit(): void {
  const message = draft.value.trim();
  if (!message) {
    return;
  }
  emit("send", message);
  draft.value = "";
}
</script>
