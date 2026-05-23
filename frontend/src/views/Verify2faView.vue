<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api";
import { useAuthStore } from "@/stores/auth";

const code = ref("");
const useBackup = ref(false);
const err = ref("");
const busy = ref(false);
const router = useRouter();
const auth = useAuthStore();

async function submit() {
  err.value = "";
  busy.value = true;
  try {
    await api.verify2fa(code.value.trim(), useBackup.value);
    await auth.fetchMe();
    router.push("/");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Verification failed";
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="flex min-h-screen items-center justify-center p-6">
    <div class="card w-full max-w-md p-8">
      <h1 class="text-xl font-semibold">Two-factor authentication</h1>
      <form class="mt-6 space-y-4" @submit.prevent="submit">
        <input v-model="code" class="input-field text-center font-mono text-lg tracking-widest" :placeholder="useBackup ? 'Backup code' : '000000'" />
        <label class="flex items-center gap-2 text-sm">
          <input v-model="useBackup" type="checkbox" /> Use backup code
        </label>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <button class="btn-primary w-full" :disabled="busy">Verify</button>
      </form>
    </div>
  </div>
</template>
