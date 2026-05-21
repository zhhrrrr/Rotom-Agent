<template>
  <main class="rotom-shell" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
    <aside class="rotom-sidebar">
      <div class="brand-lockup">
        <RotomIcon class="brand-icon" variant="pixel" />
        <div class="brand-copy">
          <h1>Rotom Agent</h1>
        </div>
      </div>
      <slot name="sidebar" :collapsed="sidebarCollapsed" />
    </aside>

    <section class="rotom-main">
      <header class="topbar">
        <div class="topbar-left">
          <button
            class="sidebar-toggle"
            type="button"
            :aria-label="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            {{ sidebarCollapsed ? ">" : "<" }}
          </button>
          <div class="connection-status">
            <span class="signal-dot" />
            <span>Online</span>
          </div>
        </div>
        <slot name="topbar" />
      </header>
      <slot />
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from "vue";

import RotomIcon from "./RotomIcon.vue";

const sidebarCollapsed = ref(false);
</script>
