<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "lucide-vue-next";
import { api } from "@/api";
import { formatLocalTime } from "@/utils/datetime";

export interface IpHistoryEntry {
  ip: string;
  action: "assigned" | "removed";
  device_name: string;
  subnet_name?: string;
  subnet_cidr?: string;
  user_name?: string;
  timestamp?: string;
}

const props = defineProps<{
  ip: string | null;
}>();

const emit = defineEmits<{ close: [] }>();

const loading = ref(false);
const error = ref("");
const history = ref<IpHistoryEntry[]>([]);

watch(
  () => props.ip,
  async (ip) => {
    if (!ip) {
      history.value = [];
      error.value = "";
      return;
    }
    loading.value = true;
    error.value = "";
    try {
      history.value = (await api.ipHistory(ip)) as IpHistoryEntry[];
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to load history";
      history.value = [];
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

function formatTime(ts?: string) {
  return formatLocalTime(ts, "Unknown");
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="ip"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center"
      @click.self="emit('close')"
      @keydown="onKeydown"
    >
      <div class="card max-h-[80vh] w-full max-w-lg overflow-hidden p-0 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <h2 class="font-semibold">IP history · <span class="font-mono text-accent">{{ ip }}</span></h2>
          <button type="button" class="rounded-lg p-1 hover:bg-surface-overlay" aria-label="Close" @click="emit('close')">
            <X class="h-5 w-5" />
          </button>
        </div>
        <div class="max-h-[60vh] overflow-y-auto p-4">
          <p v-if="loading" class="text-center text-sm text-slate-500">Loading…</p>
          <p v-else-if="error" class="text-center text-sm text-red-500">{{ error }}</p>
          <p v-else-if="history.length === 0" class="text-center text-sm text-slate-500">No assignment history for this address.</p>
          <ul v-else class="space-y-3">
            <li
              v-for="(entry, i) in history"
              :key="i"
              class="flex gap-3 border-b border-slate-100 pb-3 last:border-0 dark:border-slate-800"
            >
              <span
                class="mt-0.5 shrink-0 text-xs font-semibold uppercase"
                :class="entry.action === 'assigned' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'"
              >
                {{ entry.action === "assigned" ? "Assigned" : "Removed" }}
              </span>
              <div class="min-w-0 flex-1 text-sm">
                <div>
                  <span class="font-medium">{{ entry.device_name }}</span>
                  <span v-if="entry.subnet_name" class="text-slate-500">
                    · {{ entry.subnet_name }}<span v-if="entry.subnet_cidr"> ({{ entry.subnet_cidr }})</span>
                  </span>
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ entry.user_name || "Unknown" }} · {{ formatTime(entry.timestamp) }}
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </Teleport>
</template>
