<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { RouterLink } from "vue-router";
import { Network, Wifi, Layers, Server } from "lucide-vue-next";
import { api } from "@/api";

interface DashboardStats {
  total_ips: number;
  used_ips: number;
  available_ips: number;
  utilization_percent: number;
  subnet_count: number;
  device_count: number;
}

interface SubnetOverviewRow {
  id: number;
  name: string;
  cidr: string;
  site: string;
  vlan_id?: number;
  utilization: number;
  available: number;
}

interface ActivityPoint {
  hour: number;
  count: number;
}

const loading = ref(true);
const error = ref("");
const stats = ref<DashboardStats | null>(null);
const subnetOverview = ref<SubnetOverviewRow[]>([]);
const activity = ref<ActivityPoint[]>([]);

const donutStyle = computed(() => {
  const pct = stats.value?.utilization_percent ?? 0;
  return { background: `conic-gradient(rgb(var(--accent)) ${pct}%, rgb(var(--surface-overlay)) ${pct}%)` };
});

const maxActivity = computed(() => Math.max(1, ...activity.value.map((a) => a.count)));

onMounted(async () => {
  try {
    const d = await api.dashboard();
    stats.value = d.stats;
    subnetOverview.value = d.subnet_overview;
    activity.value = d.activity;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load dashboard";
  } finally {
    loading.value = false;
  }
});

function formatHour(h: number) {
  if (h === 0) return "12 AM";
  if (h === 12) return "12 PM";
  return h < 12 ? `${h} AM` : `${h - 12} PM`;
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <p class="mt-1 text-slate-500">Network overview</p>

    <p v-if="loading" class="mt-8 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-8 text-red-500">{{ error }}</p>

    <template v-else-if="stats">
      <div class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div class="card flex items-start gap-4">
          <div class="rounded-lg bg-accent/15 p-3 text-accent"><Network class="h-6 w-6" /></div>
          <div>
            <div class="text-xs font-medium uppercase tracking-wide text-slate-500">Total IPv4 addresses</div>
            <div class="mt-1 text-2xl font-bold text-accent">{{ stats.total_ips.toLocaleString() }}</div>
            <div class="text-sm text-slate-500">{{ stats.utilization_percent }}% utilised</div>
          </div>
        </div>
        <div class="card flex items-start gap-4">
          <div class="rounded-lg bg-surface-overlay p-3 text-slate-500"><Wifi class="h-6 w-6" /></div>
          <div>
            <div class="text-xs font-medium uppercase tracking-wide text-slate-500">Available IPs</div>
            <div class="mt-1 text-2xl font-bold">{{ stats.available_ips.toLocaleString() }}</div>
            <div class="text-sm text-slate-500">{{ 100 - stats.utilization_percent }}% free</div>
          </div>
        </div>
        <div class="card flex items-start gap-4">
          <div class="rounded-lg bg-surface-overlay p-3 text-slate-500"><Layers class="h-6 w-6" /></div>
          <div>
            <div class="text-xs font-medium uppercase tracking-wide text-slate-500">Subnets</div>
            <div class="mt-1 text-2xl font-bold">{{ stats.subnet_count }}</div>
            <div class="text-sm text-slate-500">Total</div>
          </div>
        </div>
        <div class="card flex items-start gap-4">
          <div class="rounded-lg bg-surface-overlay p-3 text-slate-500"><Server class="h-6 w-6" /></div>
          <div>
            <div class="text-xs font-medium uppercase tracking-wide text-slate-500">Devices</div>
            <div class="mt-1 text-2xl font-bold">{{ stats.device_count.toLocaleString() }}</div>
            <div class="text-sm text-slate-500">Managed</div>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="card">
          <h2 class="font-semibold">IPv4 usage distribution</h2>
          <div class="mt-6 flex flex-col items-center gap-6 sm:flex-row sm:justify-center">
            <div class="relative h-44 w-44 shrink-0 rounded-full" :style="donutStyle">
              <div class="absolute inset-5 flex flex-col items-center justify-center rounded-full bg-surface-raised text-center">
                <span class="text-2xl font-bold">{{ stats.total_ips.toLocaleString() }}</span>
                <span class="text-xs uppercase tracking-wide text-slate-500">Total</span>
              </div>
            </div>
            <div class="space-y-3 text-sm">
              <div class="flex items-center gap-2">
                <span class="h-3 w-3 rounded-full bg-accent" />
                <span>{{ stats.utilization_percent }}% Used ({{ stats.used_ips.toLocaleString() }})</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="h-3 w-3 rounded-full bg-surface-overlay ring-1 ring-slate-300 dark:ring-slate-600" />
                <span>{{ 100 - stats.utilization_percent }}% Free ({{ stats.available_ips.toLocaleString() }})</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h2 class="font-semibold">Activity - last 24 hours</h2>
          <p class="mt-1 text-xs text-slate-500">Audit log entries by hour</p>
          <div class="mt-4 flex h-40 items-end gap-0.5">
            <div
              v-for="point in activity"
              :key="point.hour"
              class="flex-1 rounded-t bg-accent/80 transition-all hover:bg-accent"
              :style="{ height: `${Math.max(4, (point.count / maxActivity) * 100)}%` }"
              :title="`${formatHour(point.hour)}: ${point.count}`"
            />
          </div>
          <div class="mt-2 flex justify-between text-[10px] text-slate-500">
            <span>12 AM</span>
            <span>6 AM</span>
            <span>12 PM</span>
            <span>6 PM</span>
          </div>
        </div>
      </div>

      <div class="card mt-6 overflow-x-auto">
        <div class="mb-4 flex items-center justify-between gap-3">
          <h2 class="font-semibold">Subnet overview</h2>
          <RouterLink to="/subnets" class="text-sm text-accent hover:underline">View all subnets</RouterLink>
        </div>
        <table class="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr class="border-b border-slate-200 text-xs font-medium uppercase tracking-wide text-slate-500 dark:border-slate-700">
              <th class="p-2">Subnet</th>
              <th class="p-2">Name</th>
              <th class="p-2">Utilised</th>
              <th class="p-2">Available</th>
              <th class="p-2">Site</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in subnetOverview"
              :key="s.id"
              class="border-b border-slate-100 dark:border-slate-800"
            >
              <td class="p-2">
                <RouterLink :to="`/subnets/${s.id}`" class="font-mono text-accent hover:underline">{{ s.cidr }}</RouterLink>
              </td>
              <td class="p-2">{{ s.name }}</td>
              <td class="p-2">
                <div class="flex items-center gap-2">
                  <div class="h-1.5 w-16 overflow-hidden rounded-full bg-surface-overlay">
                    <div
                      class="h-full rounded-full bg-accent"
                      :style="{ width: `${s.utilization}%` }"
                    />
                  </div>
                  <span>{{ s.utilization }}%</span>
                </div>
              </td>
              <td class="p-2">{{ s.available }}</td>
              <td class="p-2">{{ s.site }}</td>
            </tr>
            <tr v-if="!subnetOverview.length">
              <td colspan="5" class="p-4 text-center text-slate-500">No subnets configured.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
