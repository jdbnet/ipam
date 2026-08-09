<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { GripVertical, Pencil, Trash2 } from "lucide-vue-next";
import { api, type Subnet } from "@/api";
import { useAuthStore } from "@/stores/auth";
import SubnetFormModal from "@/components/SubnetFormModal.vue";

type DropTarget =
  | { kind: "site"; beforeSite: string }
  | { kind: "subnet"; site: string; visualIndex: number; insertIndex: number };

const auth = useAuthStore();
const subnets = ref<Subnet[]>([]);
const siteOrder = ref<string[]>([]);
const loading = ref(true);
const error = ref("");
const layoutErr = ref("");
const showAdd = ref(false);
const editSubnet = ref<Subnet | null>(null);
const dragKind = ref<"site" | "subnet" | null>(null);
const dragSite = ref<string | null>(null);
const dragSubnetId = ref<number | null>(null);
const dropTarget = ref<DropTarget | null>(null);

const canEdit = () => auth.can("edit_subnet");

function siteLabel(site?: string | null) {
  return site?.trim() ? site : "Unassigned";
}

function siteToDb(site: string) {
  return site === "Unassigned" ? "" : site;
}

function subnetsInSite(site: string) {
  return subnets.value
    .filter((s) => siteLabel(s.site) === site)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.name.localeCompare(b.name));
}

const orderedSites = computed(() => {
  const present = new Set(subnets.value.map((s) => siteLabel(s.site)));
  const ordered = siteOrder.value.filter((s) => present.has(s));
  const remaining = [...present]
    .filter((s) => !ordered.includes(s))
    .sort((a, b) => {
      if (a === "Unassigned") return -1;
      if (b === "Unassigned") return 1;
      return a.localeCompare(b);
    });
  return [...ordered, ...remaining];
});

function buildLayoutPayload() {
  const entries: { id: number; site: string; sort_order: number }[] = [];
  for (const site of orderedSites.value) {
    for (const [i, s] of subnetsInSite(site).entries()) {
      entries.push({ id: s.id, site, sort_order: i });
    }
  }
  return { site_order: orderedSites.value, subnets: entries };
}

function snapshotState() {
  return {
    subnets: subnets.value.map((s) => ({ ...s })),
    siteOrder: [...siteOrder.value],
  };
}

async function loadSubnets() {
  loading.value = true;
  error.value = "";
  try {
    const data = await api.subnets(true);
    subnets.value = data.items;
    siteOrder.value = data.site_order;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load subnets";
    subnets.value = [];
    siteOrder.value = [];
  } finally {
    loading.value = false;
  }
}

async function persistLayout(previous = snapshotState()) {
  layoutErr.value = "";
  try {
    await api.reorderSubnetsLayout(buildLayoutPayload());
  } catch (e) {
    layoutErr.value = e instanceof Error ? e.message : "Failed to save order";
    subnets.value = previous.subnets;
    siteOrder.value = previous.siteOrder;
  }
}

function moveSubnet(subnetId: number, toSite: string, toIndex: number) {
  const subnet = subnets.value.find((s) => s.id === subnetId);
  if (!subnet) return;
  const fromSite = siteLabel(subnet.site);
  subnet.site = siteToDb(toSite);

  const others = subnets.value.filter((s) => s.id !== subnetId);
  const targetList = others
    .filter((s) => siteLabel(s.site) === toSite)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  targetList.splice(toIndex, 0, subnet);
  targetList.forEach((s, i) => {
    s.sort_order = i;
  });

  if (fromSite !== toSite) {
    others
      .filter((s) => siteLabel(s.site) === fromSite)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .forEach((s, i) => {
        s.sort_order = i;
      });
    if (!siteOrder.value.includes(toSite)) {
      siteOrder.value = [...orderedSites.value, toSite];
    }
  }
}

function moveSite(fromSite: string, beforeSite: string) {
  const order = orderedSites.value.filter((s) => s !== fromSite);
  if (beforeSite === "__end__") {
    order.push(fromSite);
  } else {
    const targetIndex = order.indexOf(beforeSite);
    if (targetIndex === -1) {
      order.push(fromSite);
    } else {
      order.splice(targetIndex, 0, fromSite);
    }
  }
  siteOrder.value = order;
}

function clearDrag() {
  dragKind.value = null;
  dragSite.value = null;
  dragSubnetId.value = null;
  dropTarget.value = null;
}

function setSiteDropTarget(beforeSite: string, e: DragEvent) {
  if (!canEdit() || dragKind.value !== "site" || !dragSite.value || dragSite.value === beforeSite) return false;
  e.preventDefault();
  e.dataTransfer!.dropEffect = "move";
  dropTarget.value = { kind: "site", beforeSite };
  return true;
}

function pointerInsertsAfter(e: DragEvent, el: HTMLElement) {
  const rect = el.getBoundingClientRect();
  if (rect.width >= rect.height) {
    return e.clientX > rect.left + rect.width / 2;
  }
  return e.clientY > rect.top + rect.height / 2;
}

function computeSubnetInsert(list: Subnet[], dragId: number, visualIndex: number, sameSite: boolean): number | null {
  if (!sameSite) return visualIndex;
  const fromIndex = list.findIndex((s) => s.id === dragId);
  if (fromIndex === -1) return visualIndex;
  const insertIndex = fromIndex < visualIndex ? visualIndex - 1 : visualIndex;
  if (insertIndex === fromIndex) return null;
  return insertIndex;
}

function resolveSubnetDrop(site: string, visualIndex: number, e: DragEvent) {
  if (!canEdit() || dragKind.value !== "subnet" || !dragSubnetId.value) return false;

  const list = subnetsInSite(site);
  const dragged = subnets.value.find((s) => s.id === dragSubnetId.value);
  const sameSite = siteLabel(dragged?.site) === site;
  const insertIndex = computeSubnetInsert(list, dragSubnetId.value, visualIndex, sameSite);

  e.preventDefault();
  e.stopPropagation();
  e.dataTransfer!.dropEffect = "move";
  if (insertIndex === null) {
    dropTarget.value = null;
    return true;
  }

  dropTarget.value = { kind: "subnet", site, visualIndex, insertIndex };
  return true;
}

function visualIndexFromGridPointer(grid: HTMLElement, site: string, e: DragEvent): number {
  const list = subnetsInSite(site);
  const cards = [...grid.querySelectorAll<HTMLElement>("[data-subnet-card]")];
  if (!cards.length) return 0;

  for (const el of cards) {
    const index = Number(el.dataset.index);
    if (Number.isNaN(index)) continue;
    const rect = el.getBoundingClientRect();
    if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
      return pointerInsertsAfter(e, el) ? index + 1 : index;
    }
  }

  const sorted = cards
    .map((el) => ({ index: Number(el.dataset.index), rect: el.getBoundingClientRect() }))
    .filter((c) => !Number.isNaN(c.index))
    .sort((a, b) => {
      const rowA = Math.round(a.rect.top);
      const rowB = Math.round(b.rect.top);
      if (rowA !== rowB) return rowA - rowB;
      return a.rect.left - b.rect.left;
    });

  const { clientX: x, clientY: y } = e;
  for (const { index, rect } of sorted) {
    if (y < rect.top + rect.height / 2) return index;
    if (y <= rect.bottom && x < rect.left + rect.width / 2) return index;
  }
  return list.length;
}

function onGridDragOver(site: string, e: DragEvent) {
  if (dragKind.value === "subnet") {
    const grid = e.currentTarget as HTMLElement;
    resolveSubnetDrop(site, visualIndexFromGridPointer(grid, site, e), e);
    return;
  }
  if (dragKind.value === "site") {
    setSiteDropTarget(site, e);
  }
}

async function onGridDrop(site: string, e: DragEvent) {
  if (dragKind.value === "site") {
    await onSiteDrop(site, e);
    return;
  }
  await onSubnetDrop(site, subnetsInSite(site).length, e);
}

function isSiteDropBefore(site: string) {
  return dropTarget.value?.kind === "site" && dropTarget.value.beforeSite === site;
}

function isSubnetDropAt(site: string, index: number) {
  return dropTarget.value?.kind === "subnet" && dropTarget.value.site === site && dropTarget.value.visualIndex === index;
}

function onSiteDragStart(site: string, e: DragEvent) {
  if (!canEdit()) return;
  dragKind.value = "site";
  dragSite.value = site;
  e.dataTransfer!.effectAllowed = "move";
  e.dataTransfer!.setData("text/plain", `site:${site}`);
}

function onSiteDragOver(beforeSite: string, e: DragEvent) {
  setSiteDropTarget(beforeSite, e);
}

async function onSiteDrop(beforeSite: string, e: DragEvent) {
  e.preventDefault();
  e.stopPropagation();
  if (!canEdit() || dragKind.value !== "site" || !dragSite.value) {
    clearDrag();
    return;
  }
  if (beforeSite !== "__end__" && dragSite.value === beforeSite) {
    clearDrag();
    return;
  }
  const previous = snapshotState();
  moveSite(dragSite.value, beforeSite);
  clearDrag();
  await persistLayout(previous);
}

function onSubnetDragStart(subnetId: number, e: DragEvent) {
  if (!canEdit()) return;
  dragKind.value = "subnet";
  dragSubnetId.value = subnetId;
  e.dataTransfer!.effectAllowed = "move";
  e.dataTransfer!.setData("text/plain", `subnet:${subnetId}`);
}

function onSectionDragOver(site: string, e: DragEvent) {
  if (dragKind.value === "site") {
    setSiteDropTarget(site, e);
  }
}

async function onSectionDrop(site: string, e: DragEvent) {
  if (dragKind.value === "site") {
    await onSiteDrop(site, e);
  }
}

async function onSubnetDrop(site: string, index: number, e: DragEvent) {
  e.preventDefault();
  e.stopPropagation();
  if (dragKind.value === "site") {
    await onSiteDrop(site, e);
    return;
  }
  if (!canEdit() || dragKind.value !== "subnet" || !dragSubnetId.value) {
    clearDrag();
    return;
  }
  const insertIndex = dropTarget.value?.kind === "subnet" && dropTarget.value.site === site
    ? dropTarget.value.insertIndex
    : computeSubnetInsert(subnetsInSite(site), dragSubnetId.value, index, siteLabel(subnets.value.find((s) => s.id === dragSubnetId.value)?.site) === site);
  if (insertIndex === null) {
    clearDrag();
    return;
  }
  const previous = snapshotState();
  moveSubnet(dragSubnetId.value, site, insertIndex);
  clearDrag();
  await persistLayout(previous);
}

async function del(id: number) {
  if (!confirm("Delete subnet and all IPs?")) return;
  error.value = "";
  try {
    await api.deleteSubnet(id);
    await loadSubnets();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to delete subnet";
  }
}

onMounted(loadSubnets);
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">Subnets</h1>
        <p class="mt-1 text-slate-500">Browse subnets grouped by site</p>
      </div>
      <button
        v-if="auth.can('add_subnet')"
        type="button"
        class="btn-primary text-sm"
        @click="showAdd = true"
      >
        Add subnet
      </button>
    </div>

    <p v-if="loading" class="mt-8 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-8 text-red-500">{{ error }}</p>
    <p v-else-if="!subnets.length" class="mt-8 text-slate-500">No subnets yet.</p>
    <div v-else class="mt-6 space-y-2">
      <p v-if="layoutErr" class="mb-4 text-sm text-red-500">{{ layoutErr }}</p>

      <template v-for="site in orderedSites" :key="site">
        <div
          v-if="isSiteDropBefore(site)"
          class="flex items-center gap-2 py-1"
          aria-hidden="true"
        >
          <div class="h-1 flex-1 rounded-full bg-accent shadow-[0_0_8px] shadow-accent/50" />
          <span class="shrink-0 text-xs font-medium text-accent">Drop site here</span>
          <div class="h-1 flex-1 rounded-full bg-accent shadow-[0_0_8px] shadow-accent/50" />
        </div>

        <section
          class="rounded-xl transition-opacity"
          :class="dragKind === 'site' && dragSite === site ? 'opacity-40' : ''"
          @dragover="onSectionDragOver(site, $event)"
          @drop="onSectionDrop(site, $event)"
        >
          <h2
            class="mb-3 flex items-center gap-2 text-lg font-semibold text-accent"
            :class="canEdit() ? 'cursor-grab active:cursor-grabbing' : ''"
            :draggable="canEdit()"
            @dragstart="onSiteDragStart(site, $event)"
            @dragend="clearDrag"
            @dragover.stop="onSiteDragOver(site, $event)"
            @drop.stop="onSiteDrop(site, $event)"
          >
            <GripVertical v-if="canEdit()" class="h-4 w-4 shrink-0 text-slate-400" />
            {{ site }}
          </h2>

          <div
            class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
            @dragover="onGridDragOver(site, $event)"
            @drop="onGridDrop(site, $event)"
          >
            <template v-for="(s, index) in subnetsInSite(site)" :key="s.id">
              <div
                v-if="isSubnetDropAt(site, index)"
                class="card flex min-h-[8.5rem] flex-col items-center justify-center border-2 border-dashed border-accent bg-accent/10"
                aria-hidden="true"
              >
                <GripVertical class="mb-1 h-4 w-4 text-accent/60" />
                <span class="text-sm font-medium text-accent">Drop here</span>
              </div>

              <div
                data-subnet-card
                :data-index="index"
                class="card relative flex transition-opacity"
                :class="dragKind === 'subnet' && dragSubnetId === s.id ? 'opacity-40' : ''"
              >
                <button
                  v-if="canEdit()"
                  type="button"
                  class="mr-2 shrink-0 self-start cursor-grab p-1 text-slate-400 hover:text-slate-600 active:cursor-grabbing"
                  aria-label="Drag subnet"
                  draggable="true"
                  @click.stop
                  @dragstart="onSubnetDragStart(s.id, $event)"
                  @dragend="clearDrag"
                >
                  <GripVertical class="h-4 w-4" />
                </button>
                <RouterLink :to="`/subnets/${s.id}`" class="min-w-0 flex-1 transition hover:opacity-90">
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
                <div
                  v-if="auth.can('edit_subnet') || auth.can('delete_subnet')"
                  class="absolute right-2 top-2 flex gap-1"
                >
                  <button
                    v-if="auth.can('edit_subnet')"
                    type="button"
                    class="rounded-lg p-1.5 text-slate-500 hover:bg-surface-overlay hover:text-accent"
                    aria-label="Edit subnet"
                    @click.stop="editSubnet = s"
                  >
                    <Pencil class="h-4 w-4" />
                  </button>
                  <button
                    v-if="auth.can('delete_subnet')"
                    type="button"
                    class="rounded-lg p-1.5 text-slate-500 hover:bg-surface-overlay hover:text-red-500"
                    aria-label="Delete subnet"
                    @click.stop="del(s.id)"
                  >
                    <Trash2 class="h-4 w-4" />
                  </button>
                </div>
              </div>
            </template>

            <div
              v-if="isSubnetDropAt(site, subnetsInSite(site).length)"
              class="card flex min-h-[8.5rem] flex-col items-center justify-center border-2 border-dashed border-accent bg-accent/10"
              aria-hidden="true"
            >
              <GripVertical class="mb-1 h-4 w-4 text-accent/60" />
              <span class="text-sm font-medium text-accent">Drop here</span>
            </div>
          </div>
        </section>
      </template>

      <div
        v-if="canEdit() && dragKind === 'site'"
        class="rounded-xl border-2 border-dashed border-transparent py-4 transition"
        :class="isSiteDropBefore('__end__') ? 'border-accent bg-accent/5' : ''"
        @dragover="onSiteDragOver('__end__', $event)"
        @drop="onSiteDrop('__end__', $event)"
      >
        <div
          v-if="isSiteDropBefore('__end__')"
          class="flex items-center gap-2 px-2"
          aria-hidden="true"
        >
          <div class="h-1 flex-1 rounded-full bg-accent shadow-[0_0_8px] shadow-accent/50" />
          <span class="shrink-0 text-xs font-medium text-accent">Drop site at end</span>
          <div class="h-1 flex-1 rounded-full bg-accent shadow-[0_0_8px] shadow-accent/50" />
        </div>
      </div>
    </div>

    <SubnetFormModal
      :open="showAdd"
      mode="add"
      @close="showAdd = false"
      @saved="loadSubnets"
    />
    <SubnetFormModal
      :open="!!editSubnet"
      mode="edit"
      :subnet="editSubnet"
      @close="editSubnet = null"
      @saved="loadSubnets"
    />
  </div>
</template>
