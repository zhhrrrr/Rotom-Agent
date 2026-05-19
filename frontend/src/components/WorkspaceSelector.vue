<template>
  <label class="workspace-selector">
    <span>Workspace</span>
    <select :value="modelValue" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option v-for="workspace in workspaces" :key="workspace.id" :value="workspace.id">
        {{ workspace.name }}
      </option>
    </select>
  </label>
</template>

<script setup lang="ts">
import { WorkspaceResponse } from "@/api/runs";

defineProps<{
  modelValue: string | null;
  workspaces: WorkspaceResponse[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();
</script>
