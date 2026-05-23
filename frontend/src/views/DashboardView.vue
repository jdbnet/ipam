<script setup lang="ts">
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { api, type Subnet } from "@/api";

const sites = ref<Record<string, Subnet[]>>({});
const loading = ref(true);

onMounted(async () => {
  try {
    const d = await api.dashboard();
    sites.value = d.sites;
  } finally {
    loading.value = false;
  }
});
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <p class="mt-1 text-slate-500">Subnets grouped by site</p>
    <div v-if="loading" class="mt-8 text-slate-500">Loading…</div>
    <div v-else class="mt-6 space-y-8">
      <section v-for="(subnets, site) in sites" :key="site">
        <h2 class="mb-3 text-lg font-semibold text-accent">{{ site }}</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <RouterLink
            v-for="s in subnets"
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
                <div class="h-full rounded-full bg-accent transition-all" :style="{ width: `${s.utilization ?? 0}%` }" />
              </div>
              <div class="mt-1 text-xs text-slate-500">{{ s.utilization ?? 0 }}% used</div>
            </div>
          </RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
