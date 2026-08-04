<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "lucide-vue-next";
import { api } from "@/api";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{
  open: boolean;
  subnetId: number | null;
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

const auth = useAuthStore();
const loading = ref(false);
const saving = ref(false);
const err = ref("");
const msg = ref("");
const hasPool = ref(false);
const form = ref({ start_ip: "", end_ip: "", excluded_ips: "" });

const canEdit = () => auth.can("configure_dhcp");
const canView = () => auth.can("view_dhcp") || auth.can("configure_dhcp");

async function loadPool() {
  if (!props.subnetId) return;
  loading.value = true;
  err.value = "";
  msg.value = "";
  hasPool.value = false;
  form.value = { start_ip: "", end_ip: "", excluded_ips: "" };
  try {
    const d = await api.getDhcp(props.subnetId) as { pools?: { start_ip: string; end_ip: string; excluded_ips?: string }[] };
    if (d.pools?.[0]) {
      hasPool.value = true;
      form.value.start_ip = d.pools[0].start_ip;
      form.value.end_ip = d.pools[0].end_ip;
      form.value.excluded_ips = d.pools[0].excluded_ips || "";
    }
  } catch (e) {
    if (canView()) {
      err.value = e instanceof Error ? e.message : "Failed to load DHCP pool";
    }
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.open, props.subnetId] as const,
  ([open, subnetId]) => {
    if (open && subnetId) loadPool();
  },
  { immediate: true },
);

async function save() {
  if (!props.subnetId || !canEdit()) return;
  saving.value = true;
  err.value = "";
  msg.value = "";
  try {
    await api.setDhcp(props.subnetId, {
      pools: [{
        start_ip: form.value.start_ip,
        end_ip: form.value.end_ip,
        excluded_ips: form.value.excluded_ips.split(",").map((s) => s.trim()).filter(Boolean),
      }],
    });
    hasPool.value = true;
    msg.value = "Saved";
    emit("saved");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to save";
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!props.subnetId || !canEdit() || !confirm("Remove this DHCP pool?")) return;
  saving.value = true;
  err.value = "";
  msg.value = "";
  try {
    await api.setDhcp(props.subnetId, { remove: true });
    hasPool.value = false;
    form.value = { start_ip: "", end_ip: "", excluded_ips: "" };
    msg.value = "Removed";
    emit("saved");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to remove";
  } finally {
    saving.value = false;
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="emit('close')"
      @keydown="onKeydown"
    >
      <form class="card w-full max-w-lg space-y-4 shadow-xl" @submit.prevent="save">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">DHCP pool</h2>
          <button type="button" class="rounded-lg p-1 hover:bg-surface-overlay" aria-label="Close" @click="emit('close')">
            <X class="h-5 w-5" />
          </button>
        </div>
        <p v-if="loading" class="text-sm text-slate-500">Loading…</p>
        <template v-else>
          <input
            v-model="form.start_ip"
            class="input-field"
            placeholder="Start IP"
            required
            :disabled="!canEdit()"
          />
          <input
            v-model="form.end_ip"
            class="input-field"
            placeholder="End IP"
            required
            :disabled="!canEdit()"
          />
          <input
            v-model="form.excluded_ips"
            class="input-field"
            placeholder="Excluded IPs (comma-separated)"
            :disabled="!canEdit()"
          />
          <div v-if="canEdit()" class="flex gap-2">
            <button type="submit" class="btn-primary" :disabled="saving">Save</button>
            <button v-if="hasPool" type="button" class="btn-secondary" :disabled="saving" @click="remove">Remove pool</button>
            <button type="button" class="btn-secondary" @click="emit('close')">Cancel</button>
          </div>
          <div v-else class="flex justify-end">
            <button type="button" class="btn-secondary" @click="emit('close')">Close</button>
          </div>
          <p v-if="msg" class="text-sm text-accent">{{ msg }}</p>
          <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        </template>
      </form>
    </div>
  </Teleport>
</template>
