<template>
  <main class="rotom-shell">
    <aside class="rotom-sidebar">
      <div class="brand-lockup">
        <RotomIcon class="brand-icon" />
        <div>
          <h1>Rotom Agent</h1>
          <p>Electric companion dashboard</p>
        </div>
      </div>
      <slot name="sidebar" />
    </aside>

    <section class="rotom-main">
      <header class="topbar">
        <div>
          <span class="signal-dot" />
          <span>Online</span>
        </div>
        <slot name="topbar" />
      </header>
      <slot />
    </section>
  </main>
</template>

<script setup lang="ts">
import RotomIcon from "./RotomIcon.vue";
</script>
