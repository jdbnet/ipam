<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { api, type AuditEntry } from "@/api";
import { formatLocalTime } from "@/utils/datetime";

const logs = ref<AuditEntry[]>([]);
const actions = ref<string[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
const limit = 50;
const offset = ref(0);

const filters = ref({ user: "", action: "", from: "", to: "" });
const applied = ref({ user: "", action: "", from: "", to: "" });

const exportUrl = computed(() => api.auditExportUrl({
  user: applied.value.user || undefined,
  action: applied.value.action || undefined,
  from: applied.value.from || undefined,
  to: applied.value.to || undefined,
}));

const page = computed(() => Math.floor(offset.value / limit) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const d = await api.audit({
      limit,
      offset: offset.value,
      user: applied.value.user || undefined,
      action: applied.value.action || undefined,
      from: applied.value.from || undefined,
      to: applied.value.to || undefined,
    });
    logs.value = d.items;
    total.value = d.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load audit log";
    logs.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    actions.value = await api.auditActions();
  } catch {
    actions.value = [];
  }
  await load();
});

function applyFilters() {
  applied.value = { ...filters.value };
  offset.value = 0;
  load();
}

function clearFilters() {
  filters.value = { user: "", action: "", from: "", to: "" };
  applied.value = { user: "", action: "", from: "", to: "" };
  offset.value = 0;
  load();
}

function prevPage() {
  if (offset.value >= limit) {
    offset.value -= limit;
    load();
  }
}

function nextPage() {
  if (offset.value + limit < total.value) {
    offset.value += limit;
    load();
  }
}
</script>
<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-bold">Audit log</h1>
      <a :href="exportUrl" class="btn-secondary text-sm">Export CSV</a>
    </div>

    <form class="card mt-6 flex flex-wrap items-end gap-3" @submit.prevent="applyFilters">
      <div>
        <label class="mb-1 block text-xs text-slate-500">User</label>
        <input v-model="filters.user" class="input-field py-1.5 text-sm" placeholder="Name contains…" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-slate-500">Action</label>
        <select v-model="filters.action" class="input-field py-1.5 text-sm">
          <option value="">All actions</option>
          <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-slate-500">From</label>
        <input v-model="filters.from" type="date" class="input-field py-1.5 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-slate-500">To</label>
        <input v-model="filters.to" type="date" class="input-field py-1.5 text-sm" />
      </div>
      <button type="submit" class="btn-primary text-sm">Apply</button>
      <button type="button" class="btn-secondary text-sm" @click="clearFilters">Clear</button>
    </form>

    <p v-if="loading" class="mt-6 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-6 text-red-500">{{ error }}</p>
    <div v-else class="card mt-6 overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="border-b dark:border-slate-700">
            <th class="p-2">Time</th>
            <th class="p-2">User</th>
            <th class="p-2">Action</th>
            <th class="p-2">Details</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in logs" :key="l.id" class="border-b dark:border-slate-800">
            <td class="p-2 whitespace-nowrap text-xs text-slate-500">{{ formatLocalTime(l.timestamp) }}</td>
            <td class="p-2">{{ l.user_name || "—" }}</td>
            <td class="p-2 font-mono text-xs">{{ l.action }}</td>
            <td class="p-2 max-w-md truncate">{{ l.details }}</td>
          </tr>
          <tr v-if="!logs.length">
            <td colspan="4" class="p-4 text-center text-slate-500">No audit entries match your filters.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!loading && !error && total > 0" class="mt-4 flex items-center justify-between text-sm text-slate-500">
      <span>{{ total }} entries · page {{ page }} of {{ totalPages }}</span>
      <div class="flex gap-2">
        <button type="button" class="btn-secondary text-sm" :disabled="offset === 0" @click="prevPage">Previous</button>
        <button type="button" class="btn-secondary text-sm" :disabled="offset + limit >= total" @click="nextPage">Next</button>
      </div>
    </div>
  </div>
</template>
