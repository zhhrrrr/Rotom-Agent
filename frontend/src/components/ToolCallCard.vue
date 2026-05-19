<template>
  <article class="tool-card" :class="tool.status">
    <header>
      <span class="tool-bolt">ϟ</span>
      <strong>{{ tool.name }}</strong>
      <small>{{ tool.status }}</small>
    </header>
    <pre v-if="tool.content">{{ tool.content }}</pre>
  </article>
</template>

<script setup lang="ts">
import { ToolCard } from "@/stores/chat";

defineProps<{
  tool: ToolCard;
}>();
</script>
