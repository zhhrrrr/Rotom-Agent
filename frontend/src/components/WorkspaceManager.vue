<template>
  <section class="manager-panel">
    <header class="manager-header">
      <span>Workspaces</span>
      <button type="button" @click="showCreate = !showCreate">+</button>
    </header>

    <form v-if="showCreate" class="manager-form" @submit.prevent="create">
      <input v-model="draftName" type="text" placeholder="Workspace name" />
      <button type="submit" :disabled="loading || !draftName.trim()">Create</button>
    </form>

    <div class="workspace-list">
      <div
        v-for="workspace in workspaces"
        :key="workspace.id"
        class="workspace-row"
        :class="{ active: workspace.id === modelValue }"
      >
        <button class="workspace-item" type="button" @click="emit('update:modelValue', workspace.id)">
          <strong>
            {{ workspace.name }}
            <span v-if="workspace.id === defaultWorkspaceId" class="default-label">Default</span>
          </strong>
          <span>{{ shortId(workspace.id) }}</span>
        </button>
        <button
          v-if="workspace.id !== defaultWorkspaceId"
          class="manager-delete"
          type="button"
          title="Delete workspace"
          aria-label="Delete workspace"
          @click="emit('delete', workspace.id)"
        >
          x
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";

import { WorkspaceResponse } from "@/api/workspaces";

defineProps<{
  modelValue: string | null;
  workspaces: WorkspaceResponse[];
  defaultWorkspaceId: string | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  create: [name: string];
  delete: [workspaceId: string];
}>();

const showCreate = ref(false);
const draftName = ref("");

function create(): void {
  const name = draftName.value.trim();
  if (!name) {
    return;
  }
  emit("create", name);
  draftName.value = "";
  showCreate.value = false;
}

function shortId(id: string): string {
  return id.slice(0, 12);
}
</script>
