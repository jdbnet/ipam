<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const form = ref({ org_name: "", org_logo: "" });
const msg = ref("");
const err = ref("");
const busy = ref(false);

async function load() {
  const data = await api.settings();
  form.value = { org_name: data.org_name, org_logo: data.org_logo };
}

onMounted(load);

async function save() {
  err.value = "";
  msg.value = "";
  busy.value = true;
  try {
    const data = await api.updateSettings(form.value);
    form.value = { org_name: data.org_name, org_logo: data.org_logo };
    if (data.org) auth.org = data.org;
    else await auth.fetchMe();
    msg.value = "Settings saved";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold">Settings</h1>
    <p class="mt-1 text-sm text-slate-500">Configure organisation branding shown in the header and browser tab.</p>

    <form class="card mt-6 max-w-lg space-y-4" @submit.prevent="save">
      <div>
        <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Organisation name</label>
        <input v-model="form.org_name" class="input-field" placeholder="Your Organisation" />
        <p class="mt-1 text-xs text-slate-500">Shown as “{{ form.org_name || "Organisation" }} IPAM” in the sidebar.</p>
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Logo URL</label>
        <input v-model="form.org_logo" class="input-field font-mono text-sm" placeholder="https://example.com/logo.png" />
        <p class="mt-1 text-xs text-slate-500">URL or path to a PNG logo. Also used as the favicon.</p>
      </div>

      <div v-if="form.org_logo" class="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
        <p class="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Preview</p>
        <img :src="form.org_logo" alt="" class="h-10 rounded" @error="($event.target as HTMLImageElement).style.display = 'none'" />
      </div>

      <div v-if="auth.can('manage_settings')" class="flex flex-wrap items-center gap-3">
        <button type="submit" class="btn-primary" :disabled="busy">{{ busy ? "Saving…" : "Save" }}</button>
        <p v-if="msg" class="text-sm text-accent">{{ msg }}</p>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
      </div>
      <p v-else class="text-sm text-slate-500">You can view settings but do not have permission to change them.</p>
    </form>
  </div>
</template>
