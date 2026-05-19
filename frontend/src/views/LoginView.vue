<template>
  <main class="login-view">
    <section class="login-panel">
      <RotomIcon class="login-mascot" />
      <h1>Rotom Agent</h1>
      <p class="login-subtitle">Sign in to your electric companion workspace.</p>

      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>Email</span>
          <input v-model="email" type="email" autocomplete="email" required />
        </label>
        <label>
          <span>Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <button type="submit" :disabled="auth.loading">
          {{ auth.loading ? "Charging..." : "Login" }}
        </button>
        <p v-if="error" class="form-error">{{ error }}</p>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import RotomIcon from "@/components/RotomIcon.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const email = ref("");
const password = ref("");
const error = ref<string | null>(null);

async function submit(): Promise<void> {
  error.value = null;
  try {
    await auth.signIn(email.value, password.value);
    await router.push({ name: "chat" });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Login failed";
  }
}
</script>
