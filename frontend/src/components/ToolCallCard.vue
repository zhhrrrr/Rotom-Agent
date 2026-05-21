<template>
  <article class="tool-card" :class="tool.status">
    <details :open="tool.status === 'running'">
      <summary>
        <span class="tool-bolt">ϟ</span>
        <strong>{{ tool.name }}</strong>
        <small>{{ tool.status }}</small>
      </summary>
      <p class="tool-description">{{ tool.description }}</p>
      <p class="tool-result-description">{{ tool.resultDescription }}</p>
      <div class="tool-meta">
        <span v-if="tool.payload?.runtime_type">Runtime: {{ tool.payload.runtime_type }}</span>
        <span v-if="tool.payload?.risk_level">Risk: {{ tool.payload.risk_level }}</span>
      </div>
      <details
        v-if="tool.payload?.tool_args || tool.content"
        class="tool-technical"
      >
        <summary>Technical details</summary>
        <pre v-if="tool.payload?.tool_args">{{ formatJson(tool.payload.tool_args) }}</pre>
        <pre v-if="tool.content">{{ tool.content }}</pre>
      </details>
    </details>
  </article>
</template>

<script setup lang="ts">
import { ToolCard } from "@/stores/chat";

defineProps<{
  tool: ToolCard;
}>();

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
</script>
