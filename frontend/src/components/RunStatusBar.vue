<template>
  <div class="run-status" :class="statusClass">
    <span class="status-light" />
    <span>{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  status: string;
}>();

const label = computed(() => props.status.replaceAll("_", " "));
const statusClass = computed(() => ({
  "is-running": ["queued", "running", "model call started", "model_call_started"].includes(label.value),
  "is-done": ["completed", "message final"].includes(label.value),
  "is-error": ["failed", "timeout", "error"].includes(label.value),
}));
</script>
