<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { RouterLink } from "vue-router";
import { api, type Subnet } from "@/api";

const subnets = ref<Subnet[]>([]);
const loading = ref(true);
const error = ref("");

const bySite = computed(() => {
  const m: Record<string, Subnet[]> = {};
  for (const s of subnets.value) {
    const site = s.site || "Unassigned";
    if (!m[site]) m[site] = [];
    m[site].push(s);
  }
  return m;
});

const siteOrder = computed(() =>
  Object.keys(bySite.value).sort((a, b) => {
    if (a === "Unassigned") return -1;
    if (b === "Unassigned") return 1;
    return a.localeCompare(b);
  }),
);

onMounted(async () => {
  try {
    subnets.value = await api.subnets(true);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load subnets";
  } finally {
    loading.value = false;
  }
});
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Subnets</h1>
    <p class="mt-1 text-slate-500">Browse subnets grouped by site</p>
    <p v-if="loading" class="mt-8 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-8 text-red-500">{{ error }}</p>
    <p v-else-if="!subnets.length" class="mt-8 text-slate-500">No subnets yet.</p>
    <div v-else class="mt-6 space-y-8">
      <section v-for="site in siteOrder" :key="site">
        <h2 class="mb-3 text-lg font-semibold text-accent">{{ site }}</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <RouterLink
            v-for="s in bySite[site]"
            :key="s.id"
            :to="`/subnets/${s.id}`"
            class="card block transition hover:border-accent/50"
          >
            <div class="font-medium">{{ s.name }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-2">
              <span class="font-mono text-sm text-slate-500">{{ s.cidr }}</span>
              <span
                v-if="s.vlan_id"
                class="rounded-full bg-surface-overlay px-2 py-0.5 text-xs font-semibold text-slate-600 dark:text-slate-300"
              >VLAN {{ s.vlan_id }}</span>
            </div>
            <div class="mt-3">
              <div class="h-2 overflow-hidden rounded-full bg-surface-overlay">
                <div
                  class="h-full rounded-full transition-all"
                  :class="(s.utilization ?? 0) >= 90 ? 'bg-red-500' : 'bg-accent'"
                  :style="{ width: `${s.utilization ?? 0}%` }"
                />
              </div>
              <div class="mt-1 text-xs text-slate-500">{{ s.utilization ?? 0 }}% used</div>
            </div>
          </RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
