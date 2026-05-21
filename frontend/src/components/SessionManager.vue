<template>
  <section class="manager-panel session-panel">
    <header class="manager-header">
      <span>Sessions</span>
      <button type="button" :disabled="disabled" @click="emit('create')">+</button>
    </header>

    <button
      v-if="sessions.length === 0"
      class="new-chat-button"
      type="button"
      :disabled="disabled"
      @click="emit('create')"
    >
      New Chat
    </button>

    <div class="session-list">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-row"
        :class="{ active: session.id === activeSessionId }"
      >
        <button class="session-item" type="button" @click="emit('select', session.id)">
          <strong>{{ session.title }}</strong>
          <span>{{ formatDate(session.updated_at) }}</span>
        </button>
        <button
          class="manager-delete"
          type="button"
          title="Delete session"
          aria-label="Delete session"
          @click="emit('delete', session.id)"
        >
          x
        </button>
      </div>
      <p v-if="!loading && sessions.length === 0" class="empty-note">No sessions yet</p>
      <p v-if="loading" class="empty-note">Loading...</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { SessionResponse } from "@/api/sessions";

defineProps<{
  sessions: SessionResponse[];
  activeSessionId: string | null;
  loading?: boolean;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  create: [];
  select: [sessionId: string];
  delete: [sessionId: string];
}>();

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString();
}
</script>
