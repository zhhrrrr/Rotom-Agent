<template>
  <main class="login-view">
    <section class="login-panel">
      <RotomIcon class="login-float" variant="official" />
      <div class="login-title-row">
        <RotomIcon class="login-title-icon" variant="pixel" />
        <h1>Rotom Agent</h1>
      </div>
      <p class="login-subtitle">
        {{ isRegisterMode ? "New Trainer" : "Trainer Login" }}
      </p>

      <div class="mode-tabs" role="tablist" aria-label="Auth mode">
        <button
          type="button"
          :class="{ active: !isRegisterMode }"
          @click="setRegisterMode(false)"
        >
          Login
        </button>
        <button
          type="button"
          :class="{ active: isRegisterMode }"
          @click="setRegisterMode(true)"
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
        <label v-if="isRegisterMode">
          <span>Confirm Password</span>
          <input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
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
const confirmPassword = ref("");
const error = ref<string | null>(null);

function setRegisterMode(nextMode: boolean): void {
  isRegisterMode.value = nextMode;
  confirmPassword.value = "";
  error.value = null;
}

async function submit(): Promise<void> {
  error.value = null;
  if (isRegisterMode.value && password.value !== confirmPassword.value) {
    error.value = "Passwords do not match";
    return;
  }

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
