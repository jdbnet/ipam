<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api";

const email = ref("");
const password = ref("");
const err = ref("");
const busy = ref(false);
const ssoEnabled = ref(false);
const ssoLoading = ref(false);
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

onMounted(async () => {
  try {
    const caps = await api.capabilities();
    ssoEnabled.value = caps.sso_enabled;
  } catch (e) {
    // ignore
  }
});

async function startSsoLogin() {
  err.value = "";
  ssoLoading.value = true;
  try {
    const { url } = await api.startSsoLogin();
    window.location.href = url;
  } catch (e) {
    err.value = e instanceof Error ? e.message : "SSO initiation failed";
    ssoLoading.value = false;
  }
}

async function submit() {
  err.value = "";
  busy.value = true;
  try {
    const r = await auth.login(email.value.trim(), password.value);
    if (r.requires_setup) {
      router.push("/setup-2fa");
      return;
    }
    if (r.requires_2fa) {
      router.push("/verify-2fa");
      return;
    }
    await auth.fetchMe();
    router.push((route.query.redirect as string) || "/");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Login failed";
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="flex min-h-screen items-center justify-center bg-surface p-6">
    <div class="card w-full max-w-md p-8">
      <h1 class="text-2xl font-semibold">Sign in</h1>
      <p class="mt-1 text-sm text-slate-500">Access your IP address management workspace.</p>
      <form class="mt-8 space-y-4" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Email</label>
          <input v-model="email" type="email" class="input-field" required autocomplete="username" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Password</label>
          <input v-model="password" type="password" class="input-field" required autocomplete="current-password" />
        </div>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <button type="submit" class="btn-primary w-full" :disabled="busy || ssoLoading">{{ busy ? "Signing in…" : "Sign in" }}</button>
        <div v-if="ssoEnabled" class="pt-4 border-t border-slate-200 dark:border-slate-800">
          <button type="button" class="btn-secondary w-full" :disabled="ssoLoading || busy" @click="startSsoLogin">
            {{ ssoLoading ? 'Redirecting…' : 'Sign in with Single Sign-On' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
