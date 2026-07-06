<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const err = ref("");

onMounted(async () => {
  const urlParams = new URLSearchParams(window.location.search);
  const code = (route.query.code as string) || urlParams.get("code");
  const state = (route.query.state as string) || urlParams.get("state");

  const ssoError = (route.query.error as string) || urlParams.get("error");
  const ssoErrorDesc = (route.query.error_description as string) || urlParams.get("error_description");

  if (ssoError) {
    err.value = `SSO Error: ${ssoError} - ${ssoErrorDesc || "No description provided"}`;
    return;
  }

  if (!code || !state) {
    err.value = `Missing callback parameters. URL: ${window.location.search}`;
    return;
  }

  try {
    const res = await api.ssoCallback(code, state);
    if (res.requires_setup) {
      router.push("/setup-2fa");
      return;
    }
    if (res.requires_2fa) {
      router.push("/verify-2fa");
      return;
    }
    await auth.fetchMe();
    router.push("/");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "SSO Login failed";
  }
});
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-surface p-6">
    <div class="card w-full max-w-md p-8 text-center">
      <h1 class="text-2xl font-semibold">Single Sign-On</h1>
      <p v-if="err" class="mt-4 text-red-500">{{ err }}</p>
      <p v-else class="mt-4 text-slate-500">Completing sign-in…</p>
      <div v-if="err" class="mt-6">
        <RouterLink to="/login" class="btn-primary inline-block w-full text-center">Back to login</RouterLink>
      </div>
    </div>
  </div>
</template>
