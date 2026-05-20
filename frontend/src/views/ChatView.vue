<template>
  <RotomShell>
    <template #sidebar>
      <WorkspaceSelector
        v-model="workspace.activeWorkspaceId"
        :workspaces="workspace.workspaces"
      />
      <div class="sidebar-card">
        <RotomIcon class="sidebar-mascot" variant="small" />
        <p>{{ auth.user?.display_name ?? "Trainer" }}</p>
        <button class="ghost-button" type="button" @click="logout">Logout</button>
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
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";

import ChatWindow from "@/components/ChatWindow.vue";
import RotomIcon from "@/components/RotomIcon.vue";
import RotomShell from "@/components/RotomShell.vue";
import WorkspaceSelector from "@/components/WorkspaceSelector.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";

const auth = useAuthStore();
const chat = useChatStore();
const workspace = useWorkspaceStore();
const router = useRouter();

onMounted(async () => {
  await auth.loadCurrentUser();
  await workspace.loadWorkspaces();
});

async function send(message: string): Promise<void> {
  await chat.sendMessage(message, workspace.activeWorkspaceId);
}

async function logout(): Promise<void> {
  chat.reset();
  auth.signOut();
  await router.push({ name: "login" });
}
</script>
