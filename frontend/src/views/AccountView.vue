<script setup lang="ts">
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { api } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const profile = ref<{
  totp_enabled?: boolean;
  role_requires_2fa?: boolean;
  backup_codes?: string[];
} | null>(null);
const pw = ref({ current: "", newPw: "" });
const mfaPw = ref("");
const msg = ref("");
const err = ref("");
const newBackupCodes = ref<string[]>([]);

onMounted(async () => { profile.value = await api.account() as typeof profile.value; });

async function changePw() {
  err.value = "";
  try {
    await api.changePassword(pw.value.current, pw.value.newPw);
    msg.value = "Password updated";
    pw.value = { current: "", newPw: "" };
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function disable2fa() {
  if (!mfaPw.value || !confirm("Disable two-factor authentication?")) return;
  err.value = "";
  try {
    await api.disable2fa(mfaPw.value);
    mfaPw.value = "";
    profile.value = await api.account() as typeof profile.value;
    msg.value = "2FA disabled";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function regenCodes() {
  if (!mfaPw.value || !confirm("Regenerate backup codes? Old codes will stop working.")) return;
  err.value = "";
  try {
    const r = await api.regenerateBackupCodes(mfaPw.value);
    newBackupCodes.value = r.backup_codes;
    mfaPw.value = "";
    profile.value = await api.account() as typeof profile.value;
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Account</h1>
    <div class="card mt-6 max-w-md space-y-2">
      <p><strong>{{ auth.user?.name }}</strong></p>
      <p class="text-slate-500">{{ auth.user?.email }}</p>
      <p class="text-sm">2FA: {{ profile?.totp_enabled ? "Enabled" : "Disabled" }}</p>
    </div>

    <div class="card mt-6 max-w-md space-y-4">
      <h2 class="font-semibold">Two-factor authentication</h2>
      <template v-if="profile?.totp_enabled">
        <div v-if="profile.backup_codes?.length">
          <p class="text-sm text-slate-500">Backup codes:</p>
          <ul class="mt-2 rounded-lg bg-surface-overlay p-3 font-mono text-sm">
            <li v-for="c in profile.backup_codes" :key="c">{{ c }}</li>
          </ul>
        </div>
        <div v-if="newBackupCodes.length">
          <p class="text-sm font-medium text-accent">New backup codes - save these now:</p>
          <ul class="mt-2 rounded-lg bg-surface-overlay p-3 font-mono text-sm">
            <li v-for="c in newBackupCodes" :key="c">{{ c }}</li>
          </ul>
        </div>
        <input v-model="mfaPw" type="password" class="input-field" placeholder="Password to confirm" />
        <div class="flex flex-wrap gap-2">
          <button class="btn-secondary text-sm" @click="regenCodes">Regenerate backup codes</button>
          <button
            v-if="!profile.role_requires_2fa"
            class="text-sm text-red-500 hover:underline"
            @click="disable2fa"
          >Disable 2FA</button>
          <p v-else class="text-sm text-slate-500">Your role requires 2FA - it cannot be disabled.</p>
        </div>
      </template>
      <template v-else>
        <p class="text-sm text-slate-500">Protect your account with an authenticator app.</p>
        <RouterLink to="/setup-2fa" class="btn-primary inline-block text-sm">Enable 2FA</RouterLink>
      </template>
    </div>

    <form class="card mt-6 max-w-md space-y-3" @submit.prevent="changePw">
      <h2 class="font-semibold">Change password</h2>
      <input v-model="pw.current" type="password" class="input-field" placeholder="Current password" />
      <input v-model="pw.newPw" type="password" class="input-field" placeholder="New password" />
      <button class="btn-primary">Update</button>
      <p v-if="msg" class="text-sm text-accent">{{ msg }}</p>
      <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
    </form>
  </div>
</template>
