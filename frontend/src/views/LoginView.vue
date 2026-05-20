<template>
  <main class="login-view">
    <section class="login-panel">
      <RotomIcon class="login-mascot" variant="pixel" />
      <RotomIcon class="login-float" variant="official" />
      <h1>Rotom Agent</h1>
      <p class="login-subtitle">{{ isRegisterMode ? "New Trainer" : "Trainer Login" }}</p>

      <div class="mode-tabs" role="tablist" aria-label="Auth mode">
        <button
          type="button"
          :class="{ active: !isRegisterMode }"
          @click="isRegisterMode = false"
        >
          Login
        </button>
        <button
          type="button"
          :class="{ active: isRegisterMode }"
          @click="isRegisterMode = true"
        >
          Register
        </button>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <label v-if="isRegisterMode">
          <span>Name</span>
          <input v-model="displayName" type="text" autocomplete="name" required />
        </label>
        <label>
          <span>Email</span>
          <input v-model="email" type="email" autocomplete="email" required />
        </label>
        <label>
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            :autocomplete="isRegisterMode ? 'new-password' : 'current-password'"
            minlength="8"
            required
          />
        </label>
        <button type="submit" :disabled="auth.loading">
          {{ auth.loading ? "Loading..." : isRegisterMode ? "Register" : "Login" }}
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
const isRegisterMode = ref(false);
const displayName = ref("");
const email = ref("");
const password = ref("");
const error = ref<string | null>(null);

async function submit(): Promise<void> {
  error.value = null;
  try {
    if (isRegisterMode.value) {
      await auth.signUp(email.value, password.value, displayName.value);
    } else {
      await auth.signIn(email.value, password.value);
    }
    await router.push({ name: "chat" });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Auth failed";
  }
}
</script>
