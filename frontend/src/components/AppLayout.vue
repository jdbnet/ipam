<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Menu, Search, X, Home, Server, Grid3x3, SlidersHorizontal, Users, Tag, Layers, FileText, User, Network } from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const sidebarOpen = ref(false);
const searchOpen = ref(false);
const searchQ = ref("");
const searchInput = ref<HTMLInputElement | null>(null);
const searchResults = ref<Record<string, unknown[]>>({});
const searchLoading = ref(false);

const nav = computed(() =>
  [
    { to: "/", label: "Home", icon: Home, perm: "view_index" },
    { to: "/subnets", label: "Subnets", icon: Network, perm: "view_subnet", match: (path: string) => path === "/subnets" || /^\/subnets\/\d+/.test(path) },
    { to: "/devices", label: "Devices", icon: Server, perm: "view_devices" },
    { to: "/racks", label: "Racks", icon: Grid3x3, perm: "view_racks" },
    { to: "/tags", label: "Tags", icon: Tag, perm: "view_tags" },
    { to: "/audit", label: "Audit", icon: FileText, perm: "view_audit" },
    { to: "/users", label: "Users", icon: Users, perm: "view_users" },
    { to: "/settings", label: "Settings", icon: SlidersHorizontal, perm: "view_settings" },
    { to: "/custom-fields", label: "Fields", icon: Layers, perm: "view_custom_fields" },
    { to: "/account", label: "Account", icon: User, perm: null },
  ].filter((n) => !n.perm || auth.can(n.perm)),
);

const hasResults = computed(() =>
  Object.values(searchResults.value).some((items) => items.length > 0),
);

let searchTimer: ReturnType<typeof setTimeout> | null = null;

async function logout() {
  await auth.logout();
  router.push("/login");
}

function openSearch() {
  searchOpen.value = true;
  searchQ.value = "";
  searchResults.value = {};
  nextTick(() => searchInput.value?.focus());
}

function closeSearch() {
  searchOpen.value = false;
}

async function runSearch() {
  const q = searchQ.value.trim();
  if (!q) {
    searchResults.value = {};
    return;
  }
  searchLoading.value = true;
  try {
    searchResults.value = await api.search(q);
  } finally {
    searchLoading.value = false;
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "/" && !["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName)) {
    e.preventDefault();
    openSearch();
  }
  if (e.key === "Escape" && searchOpen.value) {
    closeSearch();
  }
}

watch(searchQ, () => {
  if (!searchOpen.value) return;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 250);
});

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-surface font-sans">
    <!-- Mobile overlay -->
    <div v-if="sidebarOpen" class="fixed inset-0 z-40 bg-black/50 lg:hidden" @click="sidebarOpen = false" />

    <!-- Sidebar -->
    <aside
      class="fixed inset-y-0 left-0 z-50 flex h-full w-64 shrink-0 flex-col border-r border-slate-200 bg-surface-raised transition-transform dark:border-slate-800 lg:static lg:h-screen lg:translate-x-0"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <div class="flex h-14 shrink-0 items-center gap-2.5 border-b border-slate-200 px-4 dark:border-slate-800">
        <img v-if="auth.org.logo" :src="auth.org.logo" alt="" class="h-7 shrink-0 rounded" />
        <div class="min-w-0 flex-1 leading-tight">
          <div class="truncate text-sm font-semibold">{{ auth.org.name }} IPAM</div>
          <div class="text-xs text-slate-500">{{ auth.version }}</div>
        </div>
        <button class="lg:hidden" @click="sidebarOpen = false"><X class="h-5 w-5" /></button>
      </div>
      <nav class="min-h-0 flex-1 overflow-y-auto p-2">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="mb-0.5 flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition"
          :class="(item.match ? item.match(route.path) : route.path === item.to || route.path.startsWith(item.to + '/'))
            ? 'bg-accent/15 text-accent font-medium'
            : 'text-slate-600 hover:bg-surface-overlay dark:text-slate-400'"
          @click="sidebarOpen = false"
        >
          <component :is="item.icon" class="h-4 w-4 shrink-0" />
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="shrink-0 border-t border-slate-200 p-3 dark:border-slate-800">
        <div class="truncate text-xs text-slate-500">{{ auth.user?.name }}</div>
        <button class="mt-2 text-xs text-accent hover:underline" @click="logout">Sign out</button>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <header class="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-surface-raised px-4 dark:border-slate-800">
        <button class="lg:hidden" @click="sidebarOpen = true"><Menu class="h-6 w-6" /></button>
        <span class="font-semibold lg:hidden">{{ auth.org.name }} IPAM</span>
        <button
          class="ml-auto rounded-lg p-2 text-slate-600 transition hover:bg-surface-overlay hover:text-accent dark:text-slate-400"
          title="Search (/)"
          @click="openSearch"
        >
          <Search class="h-5 w-5" />
        </button>
      </header>
      <main class="min-h-0 flex-1 overflow-auto p-4 md:p-6">
        <RouterView />
      </main>
    </div>

    <!-- Search modal -->
    <div v-if="searchOpen" class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[10vh]" @click.self="closeSearch">
      <div class="card flex max-h-[75vh] w-full max-w-xl flex-col">
        <div class="flex items-center gap-2">
          <Search class="h-5 w-5 shrink-0 text-slate-400" />
          <input
            ref="searchInput"
            v-model="searchQ"
            class="input-field flex-1 border-0 bg-transparent px-0 shadow-none focus:ring-0"
            placeholder="Search subnets, IPs, devices…"
            autofocus
            @keydown.esc="closeSearch"
          />
          <button class="rounded-lg p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" @click="closeSearch">
            <X class="h-5 w-5" />
          </button>
        </div>
        <p class="mt-1 text-xs text-slate-500">Press <kbd class="rounded bg-surface-overlay px-1">/</kbd> to open · <kbd class="rounded bg-surface-overlay px-1">Esc</kbd> to close</p>

        <div v-if="searchLoading" class="mt-4 text-sm text-slate-500">Searching…</div>
        <div v-else-if="searchQ.trim() && !hasResults" class="mt-4 text-sm text-slate-500">No results</div>
        <div v-else-if="hasResults" class="mt-4 -mx-1 flex-1 space-y-4 overflow-y-auto px-1">
          <section v-if="searchResults.devices?.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Devices</h2>
            <ul class="mt-1">
              <li v-for="d in searchResults.devices as { id: number; name: string }[]" :key="d.id">
                <RouterLink :to="`/devices/${d.id}`" class="block rounded-lg px-2 py-1.5 text-sm hover:bg-surface-overlay" @click="closeSearch">{{ d.name }}</RouterLink>
              </li>
            </ul>
          </section>
          <section v-if="searchResults.subnets?.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Subnets</h2>
            <ul class="mt-1">
              <li v-for="s in searchResults.subnets as { id: number; name: string; cidr: string }[]" :key="s.id">
                <RouterLink :to="`/subnets/${s.id}`" class="block rounded-lg px-2 py-1.5 text-sm hover:bg-surface-overlay" @click="closeSearch">{{ s.name }} <span class="font-mono text-slate-500">({{ s.cidr }})</span></RouterLink>
              </li>
            </ul>
          </section>
          <section v-if="searchResults.ips?.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">IPs</h2>
            <ul class="mt-1">
              <li v-for="ip in searchResults.ips as { ip: string; subnet_id: number; hostname?: string }[]" :key="ip.ip">
                <RouterLink :to="`/subnets/${ip.subnet_id}`" class="block rounded-lg px-2 py-1.5 font-mono text-sm hover:bg-surface-overlay" @click="closeSearch">
                  {{ ip.ip }}<span v-if="ip.hostname" class="ml-2 font-sans text-slate-500">{{ ip.hostname }}</span>
                </RouterLink>
              </li>
            </ul>
          </section>
          <section v-if="searchResults.racks?.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Racks</h2>
            <ul class="mt-1">
              <li v-for="r in searchResults.racks as { id: number; name: string; site: string }[]" :key="r.id">
                <RouterLink :to="`/racks/${r.id}`" class="block rounded-lg px-2 py-1.5 text-sm hover:bg-surface-overlay" @click="closeSearch">{{ r.name }} <span class="text-slate-500">· {{ r.site }}</span></RouterLink>
              </li>
            </ul>
          </section>
          <section v-if="searchResults.tags?.length">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Tags</h2>
            <ul class="mt-1">
              <li v-for="t in searchResults.tags as { id: number; name: string }[]" :key="t.id">
                <RouterLink to="/tags" class="block rounded-lg px-2 py-1.5 text-sm hover:bg-surface-overlay" @click="closeSearch">{{ t.name }}</RouterLink>
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
