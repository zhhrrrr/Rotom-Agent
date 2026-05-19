<template>
  <article class="message-bubble" :class="message.role">
    <RotomIcon v-if="message.role === 'assistant'" class="bubble-avatar" />
    <div class="bubble-content">
      <p>{{ message.content || "..." }}</p>
      <span v-if="message.running" class="typing-spark">Streaming</span>
    </div>
  </article>
</template>

<script setup lang="ts">
import { ChatMessage } from "@/stores/chat";
import RotomIcon from "./RotomIcon.vue";

defineProps<{
  message: ChatMessage;
}>();
</script>
