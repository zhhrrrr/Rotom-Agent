<template>
  <RotomShell>
    <template #sidebar="{ collapsed }">
      <WorkspaceManager
        v-if="!collapsed"
        v-model="workspace.activeWorkspaceId"
        :workspaces="workspace.workspaces"
        :default-workspace-id="workspace.defaultWorkspaceId"
        :loading="workspace.loading"
        @create="createWorkspace"
        @delete="requestDeleteWorkspace"
      />
      <SessionManager
        v-if="!collapsed"
        :sessions="chat.sessions"
        :active-session-id="chat.sessionId"
        :loading="chat.loadingSessions"
        :disabled="!workspace.activeWorkspaceId"
        @create="createSession"
        @select="selectSession"
        @delete="deleteSession"
      />
      <div class="account-card" :class="{ compact: collapsed }">
        <div class="account-summary">
          <div class="account-avatar" aria-hidden="true">{{ userInitials }}</div>
          <div v-if="!collapsed" class="account-details">
            <strong>{{ auth.user?.display_name ?? "Trainer" }}</strong>
            <span>{{ auth.user?.email ?? "No email" }}</span>
          </div>
        </div>
        <div v-if="!collapsed" class="account-meta">
          <span class="account-status">{{ auth.user?.status ?? "active" }}</span>
          <span>{{ workspace.workspaces.length }} workspace{{ workspace.workspaces.length === 1 ? "" : "s" }}</span>
          <span>{{ chat.sessions.length }} session{{ chat.sessions.length === 1 ? "" : "s" }}</span>
        </div>
        <button v-if="!collapsed" class="ghost-button account-logout" type="button" @click="logout">
          Logout
        </button>
      </div>
    </template>

    <template #topbar>
      <span class="run-id" v-if="chat.activeRunId">{{ chat.activeRunId }}</span>
    </template>

    <ChatWindow
      :messages="chat.messages"
      :tools="chat.tools"
      :status="chat.runStatus"
      :disabled="chat.sending || !workspace.activeWorkspaceId"
      :error="chat.streamError || chat.sendError"
      @send="send"
    />
  </RotomShell>
  <ConfirmDialog
    :open="confirmDialog.open"
    :title="confirmDialog.title"
    :message="confirmDialog.message"
    @cancel="closeConfirmDialog"
    @confirm="confirmDelete"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from "vue";
import { useRouter } from "vue-router";

import ChatWindow from "@/components/ChatWindow.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import RotomShell from "@/components/RotomShell.vue";
import SessionManager from "@/components/SessionManager.vue";
import WorkspaceManager from "@/components/WorkspaceManager.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";

const auth = useAuthStore();
const chat = useChatStore();
const workspace = useWorkspaceStore();
const router = useRouter();
const confirmDialog = reactive<{
  open: boolean;
  title: string;
  message: string;
  action: (() => Promise<void>) | null;
}>({
  open: false,
  title: "",
  message: "",
  action: null,
});

const userInitials = computed(() => {
  const displayName = auth.user?.display_name?.trim();
  const email = auth.user?.email?.trim();
  const source = displayName || email || "Trainer";
  const words = source.split(/\s+/).filter(Boolean);

  if (words.length >= 2) {
    return `${words[0][0]}${words[1][0]}`.toUpperCase();
  }

  return source.slice(0, 2).toUpperCase();
});

onMounted(async () => {
  await auth.loadCurrentUser();
  await workspace.loadWorkspaces();
  await chat.loadWorkspaceSessions(workspace.activeWorkspaceId);
});

watch(
  () => workspace.activeWorkspaceId,
  async (workspaceId) => {
    await chat.loadWorkspaceSessions(workspaceId);
  },
);

async function send(message: string): Promise<void> {
  await chat.sendMessage(message, workspace.activeWorkspaceId);
}

async function createWorkspace(name: string): Promise<void> {
  await workspace.createWorkspace(name);
  await chat.loadWorkspaceSessions(workspace.activeWorkspaceId);
}

async function createSession(): Promise<void> {
  await chat.createBlankSession(workspace.activeWorkspaceId);
}

async function selectSession(nextSessionId: string): Promise<void> {
  await chat.selectSession(nextSessionId);
}

function deleteSession(sessionId: string): void {
  openConfirmDialog({
    title: "Delete Session",
    message: "This will delete the session history, runs, tool traces, model calls, and chunks.",
    action: async () => {
      await chat.deleteSession(sessionId);
    },
  });
}

function requestDeleteWorkspace(workspaceId: string): void {
  const target = workspace.workspaces.find((item) => item.id === workspaceId);
  openConfirmDialog({
    title: "Delete Workspace",
    message: `This will delete ${target?.name ?? "this workspace"} and every session, run, message, trace, and file inside it.`,
    action: async () => {
      await workspace.deleteWorkspace(workspaceId);
      await chat.loadWorkspaceSessions(workspace.activeWorkspaceId);
    },
  });
}

function openConfirmDialog(options: {
  title: string;
  message: string;
  action: () => Promise<void>;
}): void {
  confirmDialog.open = true;
  confirmDialog.title = options.title;
  confirmDialog.message = options.message;
  confirmDialog.action = options.action;
}

function closeConfirmDialog(): void {
  confirmDialog.open = false;
  confirmDialog.action = null;
}

async function confirmDelete(): Promise<void> {
  if (confirmDialog.action) {
    await confirmDialog.action();
  }
  closeConfirmDialog();
}

async function logout(): Promise<void> {
  chat.reset();
  auth.signOut();
  await router.push({ name: "login" });
}
</script>
