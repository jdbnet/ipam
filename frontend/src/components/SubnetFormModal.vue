<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "lucide-vue-next";
import { api, type Subnet } from "@/api";

const props = defineProps<{
  open: boolean;
  mode: "add" | "edit";
  subnet?: Subnet | null;
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

const form = ref({
  name: "",
  cidr: "",
  site: "",
  vlan_id: "" as string | number,
  vlan_description: "",
  vlan_notes: "",
});
const saving = ref(false);
const err = ref("");

function resetForm() {
  form.value = {
    name: "",
    cidr: "",
    site: "",
    vlan_id: "",
    vlan_description: "",
    vlan_notes: "",
  };
}

watch(
  () => [props.open, props.mode, props.subnet?.id] as const,
  ([open]) => {
    if (!open) return;
    err.value = "";
    if (props.mode === "edit" && props.subnet) {
      form.value = {
        name: props.subnet.name,
        cidr: props.subnet.cidr,
        site: props.subnet.site || "",
        vlan_id: props.subnet.vlan_id ?? "",
        vlan_description: props.subnet.vlan_description || "",
        vlan_notes: props.subnet.vlan_notes || "",
      };
    } else {
      resetForm();
    }
  },
  { immediate: true },
);

async function save() {
  saving.value = true;
  err.value = "";
  try {
    const body: Partial<Subnet> = {
      name: form.value.name,
      cidr: form.value.cidr,
      site: form.value.site,
      vlan_description: form.value.vlan_description || undefined,
      vlan_notes: form.value.vlan_notes || undefined,
    };
    if (form.value.vlan_id) body.vlan_id = Number(form.value.vlan_id);

    if (props.mode === "edit" && props.subnet) {
      await api.updateSubnet(props.subnet.id, {
        ...body,
        vlan_description: form.value.vlan_description || null,
        vlan_notes: form.value.vlan_notes || null,
        vlan_id: form.value.vlan_id ? Number(form.value.vlan_id) : null,
      });
    } else {
      await api.createSubnet(body);
    }
    emit("saved");
    emit("close");
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to save";
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
      <form class="card w-full max-w-lg space-y-3 shadow-xl" @submit.prevent="save">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">{{ mode === "add" ? "Add subnet" : "Edit subnet" }}</h2>
          <button type="button" class="rounded-lg p-1 hover:bg-surface-overlay" aria-label="Close" @click="emit('close')">
            <X class="h-5 w-5" />
          </button>
        </div>
        <input v-model="form.name" class="input-field" placeholder="Name" required />
        <input v-model="form.cidr" class="input-field font-mono" placeholder="192.168.1.0/24" required />
        <input v-model="form.site" class="input-field" placeholder="Site" />
        <input v-model="form.vlan_id" type="number" class="input-field" placeholder="VLAN ID" min="1" max="4094" />
        <input v-model="form.vlan_description" class="input-field" placeholder="VLAN description" />
        <input v-model="form.vlan_notes" class="input-field" placeholder="VLAN notes" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary" :disabled="saving">
            {{ mode === "add" ? "Create" : "Save" }}
          </button>
          <button type="button" class="btn-secondary" @click="emit('close')">Cancel</button>
        </div>
      </form>
    </div>
  </Teleport>
</template>
