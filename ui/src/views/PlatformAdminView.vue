<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'

import { type ThemeMode, useThemePreference } from '@/composables/useThemePreference'

type Capability = 'embedding' | 'llm'
type ApiStatus = 'active' | 'cooldown' | 'locked' | 'disabled'

type EditableField =
  | 'profileName'
  | 'provider'
  | 'capability'
  | 'modelName'
  | 'apiKeyPreview'
  | 'apiBase'
  | 'endpointId'
  | 'status'
  | 'embeddingDimensions'
  | 'maxBatchSize'
  | 'contextWindow'
  | 'maxOutputTokens'
  | 'temperature'
  | 'timeoutSeconds'
  | 'minuteQuota'
  | 'dailyQuota'
  | 'defaultProfile'

interface ApiEntry {
  id: string
  profileName: string
  provider: string
  capability: Capability
  modelName: string
  apiKeyPreview: string
  apiBase: string
  endpointId: string
  status: ApiStatus
  embeddingDimensions: number | null
  maxBatchSize: number | null
  contextWindow: number | null
  maxOutputTokens: number | null
  temperature: number | null
  timeoutSeconds: number
  minuteQuota: number | null
  dailyQuota: number | null
  defaultProfile: boolean
}

interface EditableColumn {
  field: EditableField
  header: string
  width: string
  editor: 'text' | 'password' | 'number' | 'decimal' | 'select' | 'switch'
}

const STORAGE_KEY = 'raas-platform-admin-api-profiles'

const providerOptions = ['OpenAI', 'Google Gemini', 'Groq', 'OpenRouter', 'Cohere', 'DashScope', 'ZhipuAI', 'Custom']
const capabilityOptions = [
  { label: 'Embedding', value: 'embedding' },
  { label: 'LLM', value: 'llm' },
]
const statusOptions = [
  { label: 'Active', value: 'active' },
  { label: 'Cooldown', value: 'cooldown' },
  { label: 'Locked', value: 'locked' },
  { label: 'Disabled', value: 'disabled' },
]
const themeOptions: { label: string; value: ThemeMode; icon: string }[] = [
  { label: 'Light', value: 'light', icon: 'pi pi-sun' },
  { label: 'Dark', value: 'dark', icon: 'pi pi-moon' },
  { label: 'System', value: 'system', icon: 'pi pi-desktop' },
]

const editableColumns: EditableColumn[] = [
  { field: 'profileName', header: 'Profile', width: '180px', editor: 'text' },
  { field: 'provider', header: 'Provider', width: '160px', editor: 'select' },
  { field: 'capability', header: 'Type', width: '130px', editor: 'select' },
  { field: 'modelName', header: 'Model', width: '220px', editor: 'text' },
  { field: 'apiKeyPreview', header: 'API key', width: '150px', editor: 'password' },
  { field: 'apiBase', header: 'API base', width: '220px', editor: 'text' },
  { field: 'endpointId', header: 'Endpoint', width: '160px', editor: 'text' },
  { field: 'status', header: 'Status', width: '130px', editor: 'select' },
  { field: 'embeddingDimensions', header: 'Dim', width: '110px', editor: 'number' },
  { field: 'maxBatchSize', header: 'Batch', width: '110px', editor: 'number' },
  { field: 'contextWindow', header: 'Context', width: '120px', editor: 'number' },
  { field: 'maxOutputTokens', header: 'Output', width: '120px', editor: 'number' },
  { field: 'temperature', header: 'Temp', width: '110px', editor: 'decimal' },
  { field: 'timeoutSeconds', header: 'Timeout', width: '120px', editor: 'number' },
  { field: 'minuteQuota', header: 'RPM', width: '110px', editor: 'number' },
  { field: 'dailyQuota', header: 'RPD', width: '110px', editor: 'number' },
  { field: 'defaultProfile', header: 'Default', width: '110px', editor: 'switch' },
]

const fallbackEntries: ApiEntry[] = [
  {
    id: 'profile-embedding-default',
    profileName: 'embedding-default',
    provider: 'OpenAI',
    capability: 'embedding',
    modelName: 'text-embedding-3-small',
    apiKeyPreview: 'sk-...n/a',
    apiBase: '',
    endpointId: 'embeddings-primary',
    status: 'active',
    embeddingDimensions: 1536,
    maxBatchSize: 96,
    contextWindow: null,
    maxOutputTokens: null,
    temperature: null,
    timeoutSeconds: 60,
    minuteQuota: 3000,
    dailyQuota: 200000,
    defaultProfile: true,
  },
  {
    id: 'profile-llm-default',
    profileName: 'llm-default',
    provider: 'Google Gemini',
    capability: 'llm',
    modelName: 'gemini/gemini-2.0-flash',
    apiKeyPreview: 'AIza...n/a',
    apiBase: '',
    endpointId: 'chat-primary',
    status: 'active',
    embeddingDimensions: null,
    maxBatchSize: null,
    contextWindow: 1048576,
    maxOutputTokens: 8192,
    temperature: 0.3,
    timeoutSeconds: 120,
    minuteQuota: 60,
    dailyQuota: 1500,
    defaultProfile: true,
  },
]

const { themeMode, setThemeMode } = useThemePreference()
const apiEntries = ref<ApiEntry[]>(loadEntries())
const editingCell = ref<{ rowId: string; field: EditableField } | null>(null)
const editTextDraft = ref('')
const editNumberDraft = ref<number | null>(null)
const editBooleanDraft = ref(false)

const form = reactive({
  profileName: '',
  provider: 'OpenAI',
  capability: 'embedding' as Capability,
  modelName: '',
  apiKey: '',
  apiBase: '',
  endpointId: '',
  embeddingDimensions: 1536 as number | null,
  maxBatchSize: 96 as number | null,
  contextWindow: 128000 as number | null,
  maxOutputTokens: 4096 as number | null,
  temperature: 0.3 as number | null,
  timeoutSeconds: 60,
  minuteQuota: null as number | null,
  dailyQuota: null as number | null,
  defaultProfile: false,
})

const totalProfiles = computed(() => apiEntries.value.length)
const embeddingProfiles = computed(() => apiEntries.value.filter((entry) => entry.capability === 'embedding').length)
const llmProfiles = computed(() => apiEntries.value.filter((entry) => entry.capability === 'llm').length)
const activeProfiles = computed(() => apiEntries.value.filter((entry) => entry.status === 'active').length)

watch(
  apiEntries,
  (entries) => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  },
  { deep: true },
)

function loadEntries(): ApiEntry[] {
  if (typeof window === 'undefined') return fallbackEntries

  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (!stored) return fallbackEntries

  try {
    const parsed = JSON.parse(stored)
    return Array.isArray(parsed) ? parsed : fallbackEntries
  } catch {
    return fallbackEntries
  }
}

function addApiProfile() {
  if (!form.profileName.trim() || !form.modelName.trim()) return

  const isEmbedding = form.capability === 'embedding'
  apiEntries.value = [
    {
      id: crypto.randomUUID(),
      profileName: form.profileName.trim(),
      provider: form.provider,
      capability: form.capability,
      modelName: form.modelName.trim(),
      apiKeyPreview: maskSecret(form.apiKey),
      apiBase: form.apiBase.trim(),
      endpointId: form.endpointId.trim(),
      status: 'active',
      embeddingDimensions: isEmbedding ? form.embeddingDimensions : null,
      maxBatchSize: isEmbedding ? form.maxBatchSize : null,
      contextWindow: isEmbedding ? null : form.contextWindow,
      maxOutputTokens: isEmbedding ? null : form.maxOutputTokens,
      temperature: isEmbedding ? null : form.temperature,
      timeoutSeconds: form.timeoutSeconds,
      minuteQuota: form.minuteQuota,
      dailyQuota: form.dailyQuota,
      defaultProfile: form.defaultProfile,
    },
    ...apiEntries.value,
  ]

  form.profileName = ''
  form.modelName = ''
  form.apiKey = ''
  form.endpointId = ''
  form.apiBase = ''
  form.defaultProfile = false
}

function isEditing(rowId: string, field: EditableField) {
  return editingCell.value?.rowId === rowId && editingCell.value.field === field
}

async function startEdit(rowId: string, field: EditableField) {
  if (editingCell.value && !isEditing(rowId, field)) {
    commitEdit()
  }

  const row = apiEntries.value.find((entry) => entry.id === rowId)
  if (!row) return

  editingCell.value = { rowId, field }
  const value = row[field]
  editTextDraft.value = field === 'apiKeyPreview' ? '' : String(value ?? '')
  editNumberDraft.value = typeof value === 'number' ? value : null
  editBooleanDraft.value = Boolean(value)
  await nextTick()
  focusEditor(rowId, field)
}

function commitEdit() {
  if (!editingCell.value) return

  const { rowId, field } = editingCell.value
  const row = apiEntries.value.find((entry) => entry.id === rowId)
  if (!row) {
    editingCell.value = null
    return
  }

  const column = editableColumns.find((item) => item.field === field)
  const rawValue =
    column?.editor === 'number' || column?.editor === 'decimal'
      ? editNumberDraft.value
      : column?.editor === 'switch'
        ? editBooleanDraft.value
        : editTextDraft.value

  if (field === 'apiKeyPreview') {
    const value = String(rawValue || '').trim()
    if (value) row.apiKeyPreview = maskSecret(value)
  } else {
    ;(row[field] as unknown) = normalizeDraft(field, rawValue)
  }
  editingCell.value = null
}

function cancelEdit() {
  editingCell.value = null
}

async function moveToNextCell(rowId: string, field: EditableField) {
  const currentColumn = editableColumns.findIndex((column) => column.field === field)
  const currentRow = apiEntries.value.findIndex((entry) => entry.id === rowId)
  if (currentColumn < 0 || currentRow < 0) return

  let nextColumn = currentColumn + 1
  let nextRow = currentRow
  if (nextColumn >= editableColumns.length) {
    nextColumn = 0
    nextRow = Math.min(currentRow + 1, apiEntries.value.length - 1)
  }

  const nextEntry = apiEntries.value[nextRow]
  const nextColumnConfig = editableColumns[nextColumn]
  if (!nextEntry || !nextColumnConfig) return
  const nextField = nextColumnConfig.field
  await startEdit(nextEntry.id, nextField)
}

function onEditorKeydown(event: KeyboardEvent, rowId: string, field: EditableField) {
  if (event.key === 'Enter') {
    event.preventDefault()
    commitEdit()
    return
  }

  if (event.key === 'Tab') {
    event.preventDefault()
    commitEdit()
    void moveToNextCell(rowId, field)
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    cancelEdit()
  }
}

function focusEditor(rowId: string, field: EditableField) {
  const key = `${rowId}:${field}`
  const host = document.querySelector<HTMLElement>(`[data-editor-key="${CSS.escape(key)}"]`)
  const input = host?.querySelector<HTMLElement>('input, select, button')
  input?.focus()
  if (input instanceof HTMLInputElement) input.select()
}

function normalizeDraft(field: EditableField, value: unknown) {
  if (field === 'defaultProfile') return Boolean(value)
  if (field === 'capability') return value === 'llm' ? 'llm' : 'embedding'
  if (field === 'status') return String(value || 'active') as ApiStatus
  if (field === 'provider') return String(value || 'Custom')
  if (['embeddingDimensions', 'maxBatchSize', 'contextWindow', 'maxOutputTokens', 'timeoutSeconds', 'minuteQuota', 'dailyQuota'].includes(field)) {
    return value === '' || value === undefined ? null : Number(value)
  }
  if (field === 'temperature') {
    return value === '' || value === undefined ? null : Number(value)
  }
  return String(value ?? '').trim()
}

function fieldOptions(field: EditableField) {
  if (field === 'provider') return providerOptions
  if (field === 'capability') return capabilityOptions
  if (field === 'status') return statusOptions
  return []
}

function formatCell(row: ApiEntry, field: EditableField) {
  const value = row[field]
  if (field === 'capability') return row.capability === 'embedding' ? 'Embedding' : 'LLM'
  if (field === 'defaultProfile') return row.defaultProfile ? 'Yes' : 'No'
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function statusSeverity(status: ApiStatus) {
  if (status === 'active') return 'success'
  if (status === 'cooldown') return 'warn'
  if (status === 'locked') return 'contrast'
  return 'danger'
}

function maskSecret(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return 'Not set'
  if (trimmed.length <= 8) return '••••' + trimmed.slice(-2)
  return `${trimmed.slice(0, 4)}...${trimmed.slice(-4)}`
}

function setTheme(value: ThemeMode) {
  setThemeMode(value)
}
</script>

<template>
  <section class="platform-dashboard">
    <header class="dashboard-header">
      <div>
        <span class="eyebrow">Platform Admin</span>
        <h1>System AI Gateway Dashboard</h1>
        <p>Quản lý provider, API key, model profile, quota và thông số runtime cho lõi xoay vòng model của hệ thống.</p>
      </div>

      <div class="theme-control">
        <SelectButton
          :model-value="themeMode"
          :options="themeOptions"
          option-label="label"
          option-value="value"
          aria-label="Theme mode"
          @update:model-value="setTheme($event as ThemeMode)"
        >
          <template #option="{ option }">
            <span class="theme-option">
              <i :class="option.icon" />
              <span>{{ option.label }}</span>
            </span>
          </template>
        </SelectButton>
      </div>
    </header>

    <section class="metric-strip" aria-label="AI gateway metrics">
      <Card>
        <template #content>
          <span class="metric-label">Profiles</span>
          <strong>{{ totalProfiles }}</strong>
        </template>
      </Card>
      <Card>
        <template #content>
          <span class="metric-label">Embedding</span>
          <strong>{{ embeddingProfiles }}</strong>
        </template>
      </Card>
      <Card>
        <template #content>
          <span class="metric-label">LLM</span>
          <strong>{{ llmProfiles }}</strong>
        </template>
      </Card>
      <Card>
        <template #content>
          <span class="metric-label">Active</span>
          <strong>{{ activeProfiles }}</strong>
        </template>
      </Card>
    </section>

    <section class="admin-layout">
      <Card class="profile-form-card">
        <template #title>Add AI API profile</template>
        <template #content>
          <form class="profile-form" @submit.prevent="addApiProfile">
            <label>
              <span>Profile name</span>
              <InputText v-model="form.profileName" placeholder="embedding-default" />
            </label>

            <label>
              <span>Provider</span>
              <Select v-model="form.provider" :options="providerOptions" />
            </label>

            <label>
              <span>Capability</span>
              <Select v-model="form.capability" :options="capabilityOptions" option-label="label" option-value="value" />
            </label>

            <label>
              <span>Model name</span>
              <InputText v-model="form.modelName" placeholder="provider/model-name" />
            </label>

            <label>
              <span>API key</span>
              <Password v-model="form.apiKey" toggle-mask :feedback="false" input-class="full-input" />
            </label>

            <label>
              <span>API base</span>
              <InputText v-model="form.apiBase" placeholder="https://..." />
            </label>

            <label>
              <span>Endpoint ID</span>
              <InputText v-model="form.endpointId" placeholder="chat-primary" />
            </label>

            <template v-if="form.capability === 'embedding'">
              <label>
                <span>Dimensions</span>
                <InputNumber v-model="form.embeddingDimensions" :min="1" input-class="full-input" />
              </label>
              <label>
                <span>Batch size</span>
                <InputNumber v-model="form.maxBatchSize" :min="1" input-class="full-input" />
              </label>
            </template>

            <template v-else>
              <label>
                <span>Context window</span>
                <InputNumber v-model="form.contextWindow" :min="1" input-class="full-input" />
              </label>
              <label>
                <span>Max output</span>
                <InputNumber v-model="form.maxOutputTokens" :min="1" input-class="full-input" />
              </label>
              <label>
                <span>Temperature</span>
                <InputNumber v-model="form.temperature" :min="0" :max="2" :step="0.1" :min-fraction-digits="1" input-class="full-input" />
              </label>
            </template>

            <label>
              <span>Timeout seconds</span>
              <InputNumber v-model="form.timeoutSeconds" :min="1" input-class="full-input" />
            </label>

            <label>
              <span>RPM quota</span>
              <InputNumber v-model="form.minuteQuota" :min="0" input-class="full-input" />
            </label>

            <label>
              <span>RPD quota</span>
              <InputNumber v-model="form.dailyQuota" :min="0" input-class="full-input" />
            </label>

            <label class="switch-row">
              <span>Default profile</span>
              <ToggleSwitch v-model="form.defaultProfile" />
            </label>

            <Button class="submit-button" type="submit" icon="pi pi-plus" label="Add profile" />
          </form>
        </template>
      </Card>

      <Card class="profile-table-card">
        <template #title>AI API profiles</template>
        <template #content>
          <DataTable
            :value="apiEntries"
            data-key="id"
            scrollable
            scroll-height="640px"
            table-style="min-width: 2280px"
            size="small"
          >
            <Column
              v-for="column in editableColumns"
              :key="column.field"
              :field="column.field"
              :header="column.header"
              :style="{ minWidth: column.width }"
            >
              <template #body="{ data }">
                <div
                  class="editable-cell"
                  :class="{ editing: isEditing(data.id, column.field) }"
                  role="button"
                  tabindex="0"
                  @click="startEdit(data.id, column.field)"
                  @keydown.enter.prevent="startEdit(data.id, column.field)"
                >
                  <template v-if="isEditing(data.id, column.field)">
                    <div class="editor-host" :data-editor-key="`${data.id}:${column.field}`">
                      <Select
                        v-if="column.editor === 'select'"
                        v-model="editTextDraft"
                        class="cell-editor"
                        :options="fieldOptions(column.field)"
                        :option-label="column.field === 'capability' || column.field === 'status' ? 'label' : undefined"
                        :option-value="column.field === 'capability' || column.field === 'status' ? 'value' : undefined"
                        @blur="commitEdit"
                        @change="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                      <Password
                        v-else-if="column.editor === 'password'"
                        v-model="editTextDraft"
                        class="cell-editor"
                        :feedback="false"
                        toggle-mask
                        input-class="cell-input"
                        @blur="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                      <InputNumber
                        v-else-if="column.editor === 'number'"
                        v-model="editNumberDraft"
                        class="cell-editor"
                        input-class="cell-input"
                        :min="0"
                        @blur="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                      <InputNumber
                        v-else-if="column.editor === 'decimal'"
                        v-model="editNumberDraft"
                        class="cell-editor"
                        input-class="cell-input"
                        :min="0"
                        :max="2"
                        :step="0.1"
                        :min-fraction-digits="1"
                        @blur="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                      <ToggleSwitch
                        v-else-if="column.editor === 'switch'"
                        v-model="editBooleanDraft"
                        @blur="commitEdit"
                        @change="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                      <InputText
                        v-else
                        v-model="editTextDraft"
                        class="cell-editor"
                        @blur="commitEdit"
                        @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                      />
                    </div>
                  </template>

                  <template v-else-if="column.field === 'status'">
                    <Tag :value="formatCell(data, column.field)" :severity="statusSeverity(data.status)" />
                  </template>

                  <template v-else-if="column.field === 'capability'">
                    <Tag :value="formatCell(data, column.field)" :severity="data.capability === 'embedding' ? 'info' : 'secondary'" />
                  </template>

                  <template v-else>
                    <span class="cell-value">{{ formatCell(data, column.field) }}</span>
                  </template>
                </div>
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>
    </section>
  </section>
</template>

<style scoped>
.platform-dashboard {
  display: grid;
  gap: 18px;
}

.dashboard-header {
  display: flex;
  gap: 18px;
  align-items: flex-start;
  justify-content: space-between;
}

.eyebrow,
.metric-label {
  display: block;
  color: var(--muted-text);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.dashboard-header h1 {
  margin: 4px 0 8px;
  color: var(--text-color);
  font-size: 30px;
  line-height: 1.15;
}

.dashboard-header p {
  max-width: 780px;
  margin: 0;
  color: var(--muted-text);
  line-height: 1.55;
}

.theme-control {
  flex: 0 0 auto;
}

.theme-option {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-strip :deep(.p-card-body) {
  padding: 16px;
}

.metric-strip strong {
  display: block;
  margin-top: 6px;
  color: var(--text-color);
  font-size: 28px;
}

.admin-layout {
  display: grid;
  grid-template-columns: minmax(320px, 390px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.profile-form {
  display: grid;
  gap: 13px;
}

.profile-form label {
  display: grid;
  gap: 6px;
  color: var(--text-color);
  font-weight: 650;
}

.profile-form label > span {
  color: var(--muted-text);
  font-size: 12px;
}

.profile-form :deep(.p-inputtext),
.profile-form :deep(.p-select),
.profile-form :deep(.p-password),
.profile-form :deep(.p-inputnumber) {
  width: 100%;
}

.profile-form :deep(.full-input) {
  width: 100%;
}

.switch-row {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.submit-button {
  width: 100%;
}

.profile-table-card {
  min-width: 0;
}

.profile-table-card :deep(.p-card-content) {
  padding: 0;
}

.editable-cell {
  min-height: 34px;
  display: flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 3px 6px;
  cursor: text;
}

.editable-cell:hover {
  border-color: var(--border-color);
  background: color-mix(in srgb, var(--primary-color) 7%, transparent);
}

.editable-cell.editing {
  border-color: var(--primary-color);
  background: var(--bg-color);
  cursor: default;
}

.cell-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-host,
.cell-editor,
.cell-editor :deep(.p-inputtext),
.cell-editor :deep(.p-select),
.cell-editor :deep(.p-password),
.cell-editor :deep(.cell-input) {
  width: 100%;
}

.profile-table-card :deep(.p-datatable-thead > tr > th) {
  white-space: nowrap;
}

.profile-table-card :deep(.p-datatable-tbody > tr > td) {
  padding: 6px 8px;
}

@media (max-width: 1180px) {
  .admin-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .dashboard-header {
    display: grid;
  }

  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
