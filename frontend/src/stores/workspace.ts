import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  createWorkspace as createWorkspaceRequest,
  deleteWorkspace as deleteWorkspaceRequest,
  listWorkspaces,
  WorkspaceResponse,
} from "@/api/workspaces";

export const useWorkspaceStore = defineStore("workspace", () => {
  const workspaces = ref<WorkspaceResponse[]>([]);
  const activeWorkspaceId = ref<string | null>(null);
  const loading = ref(false);

  const activeWorkspace = computed(
    () => workspaces.value.find((workspace) => workspace.id === activeWorkspaceId.value) ?? null,
  );
  const defaultWorkspaceId = computed(() => workspaces.value[0]?.id ?? null);

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

  async function createWorkspace(name: string): Promise<WorkspaceResponse> {
    loading.value = true;
    try {
      const workspace = await createWorkspaceRequest({ name });
      workspaces.value.push(workspace);
      activeWorkspaceId.value = workspace.id;
      return workspace;
    } finally {
      loading.value = false;
    }
  }

  async function deleteWorkspace(workspaceId: string): Promise<void> {
    loading.value = true;
    try {
      await deleteWorkspaceRequest(workspaceId);
      workspaces.value = workspaces.value.filter((workspace) => workspace.id !== workspaceId);
      if (activeWorkspaceId.value === workspaceId) {
        activeWorkspaceId.value = workspaces.value[0]?.id ?? null;
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
    defaultWorkspaceId,
    loading,
    loadWorkspaces,
    createWorkspace,
    deleteWorkspace,
    selectWorkspace,
  };
});
