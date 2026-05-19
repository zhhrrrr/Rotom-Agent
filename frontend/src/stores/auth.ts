import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { getMe, login, UserResponse } from "@/api/auth";
import { getAccessToken, setAccessToken } from "@/api/http";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(getAccessToken());
  const user = ref<UserResponse | null>(null);
  const loading = ref(false);

  const isAuthenticated = computed(() => Boolean(token.value));

  async function signIn(email: string, password: string): Promise<void> {
    loading.value = true;
    try {
      const response = await login({ email, password });
      token.value = response.access_token;
      setAccessToken(response.access_token);
      user.value = await getMe();
    } finally {
      loading.value = false;
    }
  }

  async function loadCurrentUser(): Promise<void> {
    if (!token.value) {
      return;
    }
    user.value = await getMe();
  }

  function signOut(): void {
    token.value = null;
    user.value = null;
    setAccessToken(null);
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    signIn,
    loadCurrentUser,
    signOut,
  };
});
