import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { listWorkspaces, WorkspaceResponse } from "@/api/runs";

export const useWorkspaceStore = defineStore("workspace", () => {
  const workspaces = ref<WorkspaceResponse[]>([]);
  const activeWorkspaceId = ref<string | null>(null);
  const loading = ref(false);

  const activeWorkspace = computed(
    () => workspaces.value.find((workspace) => workspace.id === activeWorkspaceId.value) ?? null,
  );

  async function loadWorkspaces(): Promise<void> {
    loading.value = true;
    try {
      workspaces.value = await listWorkspaces();
      if (!activeWorkspaceId.value && workspaces.value.length > 0) {
        activeWorkspaceId.value = workspaces.value[0].id;
      }
    } finally {
      loading.value = false;
    }
  }

  function selectWorkspace(workspaceId: string): void {
    activeWorkspaceId.value = workspaceId;
  }

  return {
    workspaces,
    activeWorkspaceId,
    activeWorkspace,
    loading,
    loadWorkspaces,
    selectWorkspace,
  };
});
