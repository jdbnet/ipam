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
  const code = route.query.code as string;
  const state = route.query.state as string;

  if (!code || !state) {
    err.value = "Missing callback parameters.";
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
