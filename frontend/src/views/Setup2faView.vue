<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api";
import { useAuthStore } from "@/stores/auth";

const step = ref<"generate" | "verify" | "done">("generate");
const qrCode = ref("");
const secret = ref("");
const code = ref("");
const backupCodes = ref<string[]>([]);
const err = ref("");
const router = useRouter();
const auth = useAuthStore();

onMounted(async () => {
  try {
    const r = await api.setup2fa("generate");
    qrCode.value = r.qr_code || "";
    secret.value = r.secret || "";
    step.value = "verify";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to start setup";
  }
});

async function verify() {
  err.value = "";
  try {
    const r = await api.setup2fa("verify", code.value.trim());
    backupCodes.value = r.backup_codes || [];
    step.value = "done";
    await auth.fetchMe();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Invalid code";
  }
}

function finish() {
  router.push("/");
}
</script>
<template>
  <div class="flex min-h-screen items-center justify-center p-6">
    <div class="card w-full max-w-md p-8">
      <h1 class="text-xl font-semibold">Set up 2FA</h1>
      <div v-if="step === 'verify'" class="mt-4 space-y-4">
        <img v-if="qrCode" :src="`data:image/png;base64,${qrCode}`" alt="QR" class="mx-auto rounded-lg" />
        <p class="break-all font-mono text-xs text-slate-500">{{ secret }}</p>
        <input v-model="code" class="input-field text-center font-mono" placeholder="6-digit code" maxlength="6" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <button class="btn-primary w-full" @click="verify">Verify & enable</button>
      </div>
      <div v-else-if="step === 'done'" class="mt-4 space-y-4">
        <p class="text-sm text-slate-500">Save these backup codes securely:</p>
        <ul class="rounded-lg bg-surface-overlay p-3 font-mono text-sm">
          <li v-for="c in backupCodes" :key="c">{{ c }}</li>
        </ul>
        <button class="btn-primary w-full" @click="finish">Continue</button>
      </div>
      <p v-else-if="err" class="mt-4 text-red-500">{{ err }}</p>
      <p v-else class="mt-4 text-slate-500">Loading…</p>
    </div>
  </div>
</template>
