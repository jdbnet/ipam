<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { api, type CustomFieldDef } from "@/api";

const props = defineProps<{
  entityType: "device" | "subnet";
  entityId: number;
  values?: Record<string, unknown>;
  canEdit: boolean;
}>();

const emit = defineEmits<{ saved: [values: Record<string, unknown>] }>();

const fields = ref<CustomFieldDef[]>([]);
const form = ref<Record<string, unknown>>({});
const loading = ref(true);
const saving = ref(false);
const err = ref("");
const msg = ref("");

const visible = computed(() => fields.value.length > 0 || Object.keys(props.values ?? {}).length > 0);

function initForm() {
  const next: Record<string, unknown> = {};
  for (const f of fields.value) {
    const existing = props.values?.[f.field_key];
    if (existing !== undefined && existing !== null) {
      next[f.field_key] = existing;
    } else if (f.default_value) {
      next[f.field_key] = f.field_type === "checkbox" ? f.default_value === "true" : f.default_value;
    } else {
      next[f.field_key] = f.field_type === "checkbox" ? false : "";
    }
  }
  form.value = next;
}

async function loadFields() {
  loading.value = true;
  err.value = "";
  try {
    fields.value = await api.customFields(props.entityType);
    initForm();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to load fields";
    fields.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadFields);

watch(() => props.values, () => {
  if (fields.value.length) initForm();
}, { deep: true });

async function save() {
  if (!props.canEdit) return;
  saving.value = true;
  err.value = "";
  msg.value = "";
  try {
    const payload = { ...form.value };
    if (props.entityType === "device") {
      await api.patchDeviceCustomFields(props.entityId, payload);
    } else {
      await api.patchSubnetCustomFields(props.entityId, payload);
    }
    msg.value = "Saved";
    emit("saved", payload);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to save";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div v-if="visible" class="card">
    <h2 class="font-semibold">Custom fields</h2>
    <p v-if="loading" class="mt-2 text-sm text-slate-500">Loading…</p>
    <form v-else class="mt-3 space-y-3" @submit.prevent="save">
      <div v-for="f in fields" :key="f.id">
        <label class="mb-1 block text-sm font-medium">
          {{ f.name }}<span v-if="f.required" class="text-red-500"> *</span>
        </label>
        <p v-if="f.help_text" class="mb-1 text-xs text-slate-500">{{ f.help_text }}</p>
        <template v-if="canEdit">
          <textarea
            v-if="f.field_type === 'textarea'"
            v-model="form[f.field_key]"
            class="input-field"
            :required="f.required"
          />
          <select
            v-else-if="f.field_type === 'select'"
            v-model="form[f.field_key]"
            class="input-field"
            :required="f.required"
          >
            <option value="">—</option>
            <option v-for="opt in f.validation_rules?.select_options ?? []" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <label v-else-if="f.field_type === 'checkbox'" class="flex items-center gap-2 text-sm">
            <input v-model="form[f.field_key]" type="checkbox" />
            <span>Enabled</span>
          </label>
          <input
            v-else
            v-model="form[f.field_key]"
            class="input-field"
            :type="f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : 'text'"
            :required="f.required"
          />
        </template>
        <p v-else class="text-sm text-slate-600 dark:text-slate-400">
          {{ f.field_type === 'checkbox' ? (form[f.field_key] ? 'Yes' : 'No') : (form[f.field_key] || '—') }}
        </p>
      </div>
      <div v-if="canEdit && fields.length" class="flex gap-2">
        <button type="submit" class="btn-primary text-sm" :disabled="saving">Save fields</button>
      </div>
      <p v-if="msg" class="text-sm text-accent">{{ msg }}</p>
      <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
    </form>
  </div>
</template>
