<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, type CustomFieldDef } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const tab = ref<"device" | "subnet">("device");
const fields = ref<CustomFieldDef[]>([]);
const form = ref({ name: "", field_key: "", field_type: "text", required: false, default_value: "", help_text: "" });
const editForm = ref({ id: 0, name: "", field_key: "", field_type: "text", required: false, default_value: "", help_text: "" });
const showAdd = ref(false);
const showEdit = ref(false);
const err = ref("");

const fieldTypes = ["text", "textarea", "number", "select", "checkbox", "date"];

async function load() {
  fields.value = await api.customFields(tab.value);
}

onMounted(load);

async function create() {
  err.value = "";
  try {
    await api.createCustomField({ ...form.value, entity_type: tab.value });
    showAdd.value = false;
    form.value = { name: "", field_key: "", field_type: "text", required: false, default_value: "", help_text: "" };
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

function openEdit(f: CustomFieldDef) {
  editForm.value = {
    id: f.id,
    name: f.name,
    field_key: f.field_key,
    field_type: f.field_type,
    required: !!f.required,
    default_value: "",
    help_text: "",
  };
  showEdit.value = true;
  err.value = "";
}

async function saveEdit() {
  err.value = "";
  try {
    await api.updateCustomField(editForm.value.id, {
      name: editForm.value.name,
      field_type: editForm.value.field_type,
      required: editForm.value.required,
      default_value: editForm.value.default_value || null,
      help_text: editForm.value.help_text || null,
    });
    showEdit.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function del(id: number) {
  if (!confirm("Delete this custom field?")) return;
  await api.deleteCustomField(id);
  await load();
}

async function moveField(index: number, dir: -1 | 1) {
  const target = index + dir;
  if (target < 0 || target >= fields.value.length) return;
  const reordered = [...fields.value];
  const [item] = reordered.splice(index, 1);
  reordered.splice(target, 0, item);
  const orders: Record<number, number> = {};
  reordered.forEach((f, i) => { orders[f.id] = i; });
  await api.reorderCustomFields(tab.value, orders);
  fields.value = reordered;
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Custom fields</h1>
    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button class="rounded-lg px-3 py-1 text-sm" :class="tab === 'device' ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="tab = 'device'; load()">Device</button>
      <button class="rounded-lg px-3 py-1 text-sm" :class="tab === 'subnet' ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="tab = 'subnet'; load()">Subnet</button>
      <button v-if="auth.can('manage_custom_fields')" class="btn-primary ml-auto text-sm" @click="showAdd = true; err = ''">Add field</button>
    </div>
    <ul class="mt-6 space-y-2">
      <li v-for="(f, i) in fields" :key="f.id" class="card flex flex-wrap items-center justify-between gap-2">
        <span>{{ f.name }} <span class="text-slate-500">({{ f.field_type }})</span></span>
        <span class="font-mono text-xs text-slate-500">{{ f.field_key }}</span>
        <div v-if="auth.can('manage_custom_fields')" class="flex gap-2">
          <button class="text-sm text-slate-500 hover:underline" :disabled="i === 0" @click="moveField(i, -1)">↑</button>
          <button class="text-sm text-slate-500 hover:underline" :disabled="i === fields.length - 1" @click="moveField(i, 1)">↓</button>
          <button class="text-sm text-accent hover:underline" @click="openEdit(f)">Edit</button>
          <button class="text-sm text-red-500 hover:underline" @click="del(f.id)">Delete</button>
        </div>
      </li>
    </ul>

    <div v-if="showAdd" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAdd = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="create">
        <h2 class="text-lg font-semibold">Add custom field</h2>
        <input v-model="form.name" class="input-field" placeholder="Display name" required />
        <input v-model="form.field_key" class="input-field font-mono text-sm" placeholder="field_key" required />
        <select v-model="form.field_type" class="input-field">
          <option v-for="t in fieldTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.required" type="checkbox" /> Required</label>
        <input v-model="form.default_value" class="input-field" placeholder="Default value" />
        <input v-model="form.help_text" class="input-field" placeholder="Help text" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Create</button>
          <button type="button" class="btn-secondary" @click="showAdd = false">Cancel</button>
        </div>
      </form>
    </div>

    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showEdit = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="saveEdit">
        <h2 class="text-lg font-semibold">Edit custom field</h2>
        <input v-model="editForm.name" class="input-field" required />
        <input v-model="editForm.field_key" class="input-field font-mono text-sm" disabled />
        <select v-model="editForm.field_type" class="input-field">
          <option v-for="t in fieldTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm"><input v-model="editForm.required" type="checkbox" /> Required</label>
        <input v-model="editForm.default_value" class="input-field" placeholder="Default value" />
        <input v-model="editForm.help_text" class="input-field" placeholder="Help text" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Save</button>
          <button type="button" class="btn-secondary" @click="showEdit = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
