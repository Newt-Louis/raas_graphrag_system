<script setup lang="ts">
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'

type ApiStatus = 'active' | 'cooldown' | 'locked' | 'disabled'

type EditableField =
  | 'pool_id'
  | 'provider_id'
  | 'api_key_id'
  | 'model_id'
  | 'profile_name'
  | 'model_name'
  | 'api_base'
  | 'endpoint_id'
  | 'rotation_order'
  | 'weight'
  | 'daily_request_count'
  | 'minute_request_count'
  | 'temperature'
  | 'top_p'
  | 'top_k'
  | 'max_output_tokens'
  | 'timeout_seconds'
  | 'cost_per_1k_input_tokens'
  | 'cost_per_1k_output_tokens'
  | 'extra_parameters'
  | 'status'

interface ApiModelProfile {
  id: string
  pool_id: string
  provider_id: string
  api_key_id: string
  model_id: string
  profile_name: string
  model_name: string
  api_base: string
  endpoint_id: string
  rotation_order: number
  weight: number
  daily_request_count: number
  minute_request_count: number
  temperature: number | null
  top_p: number | null
  top_k: number | null
  max_output_tokens: number | null
  timeout_seconds: number
  cost_per_1k_input_tokens: number | null
  cost_per_1k_output_tokens: number | null
  extra_parameters: string
  status: ApiStatus
}

interface LLMModelProfileResponse {
  id: string
  pool_id: string
  provider_id: string
  api_key_id: string
  model_id: string | null
  profile_name: string
  model_name: string
  api_base: string | null
  endpoint_id: string | null
  rotation_order: number
  weight: number
  is_enabled: boolean
  is_locked: boolean
  today_quota_exhausted: boolean
  daily_request_count: number
  minute_request_count: number
  temperature: number | null
  top_p: number | null
  top_k: number | null
  max_output_tokens: number | null
  timeout_seconds: number
  cost_per_1k_input_tokens: number | null
  cost_per_1k_output_tokens: number | null
  extra_parameters: Record<string, unknown>
}

interface AIProviderResponse {
  id: string
}

interface EditableColumn {
  field: EditableField
  header: string
  width: string
  editor: 'text' | 'number' | 'decimal' | 'select' | 'json'
}

const STORAGE_KEY = 'raas-platform-admin-model-profiles-v2'
const API_BASE = '/api/v1/platform/ai'

const statusOptions: ApiStatus[] = ['active', 'cooldown', 'locked', 'disabled']
const providerOptions = ref(['openai', 'google', 'groq', 'openrouter', 'cohere', 'dashscope', 'zhipuai', 'custom'])

const editableColumns: EditableColumn[] = [
  { field: 'pool_id', header: 'pool_id', width: '220px', editor: 'text' },
  { field: 'provider_id', header: 'provider_id', width: '150px', editor: 'select' },
  { field: 'api_key_id', header: 'api_key_id', width: '220px', editor: 'text' },
  { field: 'model_id', header: 'model_id', width: '180px', editor: 'text' },
  { field: 'profile_name', header: 'profile_name', width: '220px', editor: 'text' },
  { field: 'model_name', header: 'model_name', width: '260px', editor: 'text' },
  { field: 'api_base', header: 'api_base', width: '260px', editor: 'text' },
  { field: 'endpoint_id', header: 'endpoint_id', width: '170px', editor: 'text' },
  { field: 'rotation_order', header: 'rotation_order', width: '130px', editor: 'number' },
  { field: 'weight', header: 'weight', width: '100px', editor: 'number' },
  { field: 'daily_request_count', header: 'daily_request_count', width: '160px', editor: 'number' },
  { field: 'minute_request_count', header: 'minute_request_count', width: '170px', editor: 'number' },
  { field: 'temperature', header: 'temperature', width: '130px', editor: 'decimal' },
  { field: 'top_p', header: 'top_p', width: '100px', editor: 'decimal' },
  { field: 'top_k', header: 'top_k', width: '100px', editor: 'number' },
  { field: 'max_output_tokens', header: 'max_output_tokens', width: '160px', editor: 'number' },
  { field: 'timeout_seconds', header: 'timeout_seconds', width: '150px', editor: 'number' },
  { field: 'cost_per_1k_input_tokens', header: 'cost_per_1k_input_tokens', width: '210px', editor: 'decimal' },
  { field: 'cost_per_1k_output_tokens', header: 'cost_per_1k_output_tokens', width: '220px', editor: 'decimal' },
  { field: 'extra_parameters', header: 'extra_parameters', width: '260px', editor: 'json' },
  { field: 'status', header: 'status', width: '60', editor: 'select' },
]

const fallbackEntries: ApiModelProfile[] = [
  {
    id: 'profile-llm-default',
    pool_id: 'llm-pool-default',
    provider_id: 'google',
    api_key_id: 'gemini-key-primary',
    model_id: 'gemini-flash-catalog-id',
    profile_name: 'llm-default',
    model_name: 'gemini/gemini-2.0-flash',
    api_base: '',
    endpoint_id: 'chat-primary',
    rotation_order: 0,
    weight: 1,
    daily_request_count: 0,
    minute_request_count: 0,
    temperature: 0.3,
    top_p: 0.95,
    top_k: 40,
    max_output_tokens: 8192,
    timeout_seconds: 120,
    cost_per_1k_input_tokens: 0,
    cost_per_1k_output_tokens: 0,
    extra_parameters: '{}',
    status: 'active',
  },
]

const router = useRouter()
const profiles = ref<ApiModelProfile[]>(loadEntries())
const editingCell = ref<{ rowId: string; field: EditableField } | null>(null)
const editDraft = ref('')
const isLoading = ref(false)
const feedback = ref('')

const form = reactive<Omit<ApiModelProfile, 'id' | 'status'>>({
  pool_id: '',
  provider_id: 'openai',
  api_key_id: '',
  model_id: '',
  profile_name: '',
  model_name: '',
  api_base: '',
  endpoint_id: '',
  rotation_order: 0,
  weight: 1,
  daily_request_count: 0,
  minute_request_count: 0,
  temperature: 0.3,
  top_p: 1,
  top_k: null,
  max_output_tokens: 4096,
  timeout_seconds: 120,
  cost_per_1k_input_tokens: null,
  cost_per_1k_output_tokens: null,
  extra_parameters: '{}',
})

onMounted(() => {
  void loadModelProfiles()
})

watch(
  profiles,
  (entries) => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  },
  { deep: true },
)

function loadEntries(): ApiModelProfile[] {
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

async function loadModelProfiles() {
  isLoading.value = true
  feedback.value = ''
  try {
    const [providerResponse, profileResponse] = await Promise.all([
      axios.get<AIProviderResponse[]>(`${API_BASE}/providers`),
      axios.get<LLMModelProfileResponse[]>(`${API_BASE}/llm/model-profiles`),
    ])

    if (providerResponse.data.length) {
      providerOptions.value = providerResponse.data.map((provider) => provider.id)
      const firstProviderId = providerOptions.value[0]
      if (firstProviderId && !providerOptions.value.includes(form.provider_id)) {
        form.provider_id = firstProviderId
      }
    }

    if (profileResponse.data.length) {
      profiles.value = profileResponse.data.map(fromApiProfile)
    }
  } catch (error) {
    feedback.value = messageFromError(error)
  } finally {
    isLoading.value = false
  }
}

async function addModelProfile() {
  if (!form.provider_id.trim() || !form.api_key_id.trim() || !form.profile_name.trim() || !form.model_name.trim()) {
    return
  }

  feedback.value = ''
  try {
    const response = await axios.post<LLMModelProfileResponse>(
      `${API_BASE}/llm/model-profiles`,
      toApiPayload({
        id: '',
        ...normalizeForm(),
        status: 'active',
      }),
    )

    profiles.value = [fromApiProfile(response.data), ...profiles.value]

    form.api_key_id = ''
    form.model_id = ''
    form.profile_name = ''
    form.model_name = ''
    form.api_base = ''
    form.endpoint_id = ''
    form.extra_parameters = '{}'
    feedback.value = 'Saved model profile to PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function normalizeForm(): Omit<ApiModelProfile, 'id' | 'status'> {
  return {
    pool_id: form.pool_id.trim(),
    provider_id: form.provider_id.trim(),
    api_key_id: form.api_key_id.trim(),
    model_id: form.model_id.trim(),
    profile_name: form.profile_name.trim(),
    model_name: form.model_name.trim(),
    api_base: form.api_base.trim(),
    endpoint_id: form.endpoint_id.trim(),
    rotation_order: Number(form.rotation_order || 0),
    weight: Number(form.weight || 1),
    daily_request_count: Number(form.daily_request_count || 0),
    minute_request_count: Number(form.minute_request_count || 0),
    temperature: nullableNumber(form.temperature),
    top_p: nullableNumber(form.top_p),
    top_k: nullableNumber(form.top_k),
    max_output_tokens: nullableNumber(form.max_output_tokens),
    timeout_seconds: Number(form.timeout_seconds || 120),
    cost_per_1k_input_tokens: nullableNumber(form.cost_per_1k_input_tokens),
    cost_per_1k_output_tokens: nullableNumber(form.cost_per_1k_output_tokens),
    extra_parameters: form.extra_parameters.trim() || '{}',
  }
}

function nullableNumber(value: number | null) {
  return value === null || Number.isNaN(value) ? null : Number(value)
}

function isEditing(rowId: string, field: EditableField) {
  return editingCell.value?.rowId === rowId && editingCell.value.field === field
}

async function startEdit(rowId: string, field: EditableField) {
  if (!canEdit(field)) return

  if (editingCell.value && !isEditing(rowId, field)) {
    await commitEdit()
  }

  const row = profiles.value.find((entry) => entry.id === rowId)
  if (!row) return

  editingCell.value = { rowId, field }
  editDraft.value = String(row[field] ?? '')
  await nextTick()
  focusEditor(rowId, field)
}

async function commitEdit() {
  if (!editingCell.value) return

  const { rowId, field } = editingCell.value
  const row = profiles.value.find((entry) => entry.id === rowId)
  const column = editableColumns.find((entry) => entry.field === field)
  if (!row || !column) {
    editingCell.value = null
    return
  }

  ;(row[field] as unknown) = normalizeDraft(column, editDraft.value)
  editingCell.value = null
  await saveModelProfile(row)
}

function cancelEdit() {
  editingCell.value = null
}

function getNextCell(rowId: string, field: EditableField) {
  const currentColumn = editableColumns.findIndex((column) => column.field === field)
  const currentRow = profiles.value.findIndex((entry) => entry.id === rowId)
  if (currentColumn < 0 || currentRow < 0) return null

  let nextColumn = currentColumn + 1
  let nextRow = currentRow
  if (nextColumn >= editableColumns.length) {
    nextColumn = 0
    nextRow = Math.min(currentRow + 1, profiles.value.length - 1)
  }

  const nextEntry = profiles.value[nextRow]
  const nextColumnConfig = editableColumns[nextColumn]
  if (!nextEntry || !nextColumnConfig) return null
  return { rowId: nextEntry.id, field: nextColumnConfig.field }
}

async function onEditorKeydown(event: KeyboardEvent, rowId: string, field: EditableField) {
  if (event.key === 'Enter') {
    event.preventDefault()
    event.stopPropagation()
    await commitEdit()
    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.blur()
    }
    return
  }

  if (event.key === 'Tab') {
    event.preventDefault()
    event.stopPropagation()
    const nextCell = getNextCell(rowId, field)
    await commitEdit()
    if (nextCell) {
      await startEdit(nextCell.rowId, nextCell.field)
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancelEdit()
    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.blur()
    }
  }
}

function onEditorBlur(rowId: string, field: EditableField) {
  if (!isEditing(rowId, field)) return
  void commitEdit()
}

function focusEditor(rowId: string, field: EditableField) {
  const key = `${rowId}:${field}`
  const editor = document.querySelector<HTMLInputElement | HTMLSelectElement>(`[data-editor-key="${CSS.escape(key)}"]`)
  editor?.focus()
  if (editor instanceof HTMLInputElement) editor.select()
}

function normalizeDraft(column: EditableColumn, value: string) {
  if (column.field === 'status') return statusOptions.includes(value as ApiStatus) ? (value as ApiStatus) : 'active'
  if (column.field === 'provider_id') return value || 'custom'
  if (column.editor === 'number') return value.trim() === '' ? null : Number.parseInt(value, 10)
  if (column.editor === 'decimal') return value.trim() === '' ? null : Number(value)
  if (column.editor === 'json') return value.trim() || '{}'
  return value.trim()
}

function canEdit(field: EditableField) {
  return field !== 'status'
}

function formatCell(row: ApiModelProfile, field: EditableField) {
  const value = row[field]
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function statusSeverity(status: ApiStatus) {
  if (status === 'active') return 'success'
  if (status === 'cooldown') return 'warn'
  if (status === 'locked') return 'contrast'
  return 'danger'
}

function selectOptions(field: EditableField) {
  if (field === 'provider_id') return providerOptions.value
  if (field === 'status') return statusOptions
  return []
}

async function saveModelProfile(row: ApiModelProfile) {
  if (row.id.startsWith('profile-')) return

  feedback.value = ''
  try {
    const response = await axios.patch<LLMModelProfileResponse>(
      `${API_BASE}/llm/model-profiles/${row.id}`,
      toApiPayload(row),
    )
    const updated = fromApiProfile(response.data)
    profiles.value = profiles.value.map((entry) => (entry.id === row.id ? updated : entry))
    feedback.value = 'Updated model profile in PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

async function toggleModelProfileStatus(row: ApiModelProfile) {
  const nextStatus: ApiStatus = row.status === 'active' ? 'disabled' : 'active'
  const updatedRow = { ...row, status: nextStatus }

  if (row.id.startsWith('profile-')) {
    profiles.value = profiles.value.map((entry) => (entry.id === row.id ? updatedRow : entry))
    return
  }

  feedback.value = ''
  try {
    const response = await axios.patch<LLMModelProfileResponse>(
      `${API_BASE}/llm/model-profiles/${row.id}`,
      toApiPayload(updatedRow),
    )
    const updated = fromApiProfile(response.data)
    profiles.value = profiles.value.map((entry) => (entry.id === row.id ? updated : entry))
    feedback.value = 'Updated model profile status in PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

async function deleteModelProfile(row: ApiModelProfile) {
  if (!window.confirm(`Delete model profile "${row.profile_name}" permanently?`)) return

  if (row.id.startsWith('profile-')) {
    profiles.value = profiles.value.filter((entry) => entry.id !== row.id)
    return
  }

  feedback.value = ''
  try {
    await axios.delete(`${API_BASE}/llm/model-profiles/${row.id}`)
    profiles.value = profiles.value.filter((entry) => entry.id !== row.id)
    feedback.value = 'Deleted model profile from PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function openModelProfileTest(row: ApiModelProfile) {
  void router.push({
    name: 'api-ai-key-test',
    params: { apiKeyId: row.api_key_id },
    query: {
      name: row.profile_name,
      model: row.model_name,
    },
  })
}

function statusActionLabel(row: ApiModelProfile) {
  return row.status === 'active' ? 'Disable' : 'Active'
}

function statusActionSeverity(row: ApiModelProfile) {
  return row.status === 'active' ? 'danger' : 'success'
}

function fromApiProfile(profile: LLMModelProfileResponse): ApiModelProfile {
  return {
    id: profile.id,
    pool_id: profile.pool_id,
    provider_id: profile.provider_id,
    api_key_id: profile.api_key_id,
    model_id: profile.model_id ?? '',
    profile_name: profile.profile_name,
    model_name: profile.model_name,
    api_base: profile.api_base ?? '',
    endpoint_id: profile.endpoint_id ?? '',
    rotation_order: profile.rotation_order,
    weight: profile.weight,
    daily_request_count: profile.daily_request_count,
    minute_request_count: profile.minute_request_count,
    temperature: profile.temperature,
    top_p: profile.top_p,
    top_k: profile.top_k,
    max_output_tokens: profile.max_output_tokens,
    timeout_seconds: profile.timeout_seconds,
    cost_per_1k_input_tokens: profile.cost_per_1k_input_tokens,
    cost_per_1k_output_tokens: profile.cost_per_1k_output_tokens,
    extra_parameters: JSON.stringify(profile.extra_parameters || {}),
    status: profile.is_locked
      ? 'locked'
      : profile.today_quota_exhausted
        ? 'cooldown'
        : profile.is_enabled
          ? 'active'
          : 'disabled',
  }
}

function toApiPayload(row: Omit<ApiModelProfile, 'id'> | ApiModelProfile) {
  return {
    pool_id: row.pool_id || null,
    provider_id: row.provider_id,
    api_key_id: row.api_key_id,
    model_id: row.model_id || null,
    profile_name: row.profile_name,
    model_name: row.model_name,
    api_base: row.api_base || null,
    endpoint_id: row.endpoint_id || null,
    rotation_order: row.rotation_order,
    weight: row.weight,
    is_enabled: row.status !== 'disabled',
    is_locked: row.status === 'locked',
    today_quota_exhausted: row.status === 'cooldown',
    daily_request_count: row.daily_request_count,
    minute_request_count: row.minute_request_count,
    temperature: row.temperature,
    top_p: row.top_p,
    top_k: row.top_k,
    max_output_tokens: row.max_output_tokens,
    timeout_seconds: row.timeout_seconds,
    cost_per_1k_input_tokens: row.cost_per_1k_input_tokens,
    cost_per_1k_output_tokens: row.cost_per_1k_output_tokens,
    extra_parameters: parseJson(row.extra_parameters),
  }
}

function parseJson(value: string) {
  try {
    return JSON.parse(value || '{}')
  } catch {
    return {}
  }
}

function messageFromError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : error.message
  }
  return error instanceof Error ? error.message : 'Request failed.'
}
</script>

<template>
  <section class="platform-page">
    <p v-if="feedback" class="feedback">{{ feedback }}</p>

    <Card class="profile-form-card">
      <template #title>Add model profile</template>
      <template #content>
        <form class="profile-form" @submit.prevent="addModelProfile">
          <label class="span-2">
            <span>provider_id</span>
            <Select v-model="form.provider_id" :options="providerOptions" />
          </label>

          <label class="span-4">
            <span>model_name</span>
            <InputText v-model="form.model_name" placeholder="provider/model-name" />
          </label>

          <label class="span-4">
            <span>profile_name</span>
            <InputText v-model="form.profile_name" placeholder="llm-default" />
          </label>

          <label class="span-4">
            <span>pool_id</span>
            <InputText v-model="form.pool_id" placeholder="llm-pool-default" />
          </label>

          <label class="span-4">
            <span>api_key_id</span>
            <InputText v-model="form.api_key_id" placeholder="key-id-from-ai-api-keys" />
          </label>

          <label class="span-2">
            <span>model_id</span>
            <InputText v-model="form.model_id" placeholder="optional" />
          </label>

          <label class="span-4">
            <span>api_base</span>
            <InputText v-model="form.api_base" placeholder="https://..." />
          </label>

          <label class="span-3">
            <span>endpoint_id</span>
            <InputText v-model="form.endpoint_id" placeholder="chat-primary" />
          </label>

          <label class="span-1">
            <span>rotation_order</span>
            <InputNumber v-model="form.rotation_order" :min="0" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>weight</span>
            <InputNumber v-model="form.weight" :min="1" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>top_k</span>
            <InputNumber v-model="form.top_k" :min="0" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>temperature</span>
            <InputNumber v-model="form.temperature" :min="0" :max="2" :step="0.1" :min-fraction-digits="1" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>top_p</span>
            <InputNumber v-model="form.top_p" :min="0" :max="1" :step="0.05" :min-fraction-digits="2" input-class="full-input" />
          </label>

          <label class="span-2">
            <span>max_output_tokens</span>
            <InputNumber v-model="form.max_output_tokens" :min="1" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>timeout_seconds</span>
            <InputNumber v-model="form.timeout_seconds" :min="1" input-class="full-input" />
          </label>

          <label class="span-1">
            <span>minute_request_count</span>
            <InputNumber v-model="form.minute_request_count" :min="0" input-class="full-input" />
          </label>

          <label class="span-2">
            <span>daily_request_count</span>
            <InputNumber v-model="form.daily_request_count" :min="0" input-class="full-input" />
          </label>

          <label class="span-2">
            <span>cost_per_1k_input_tokens</span>
            <InputNumber v-model="form.cost_per_1k_input_tokens" :min="0" :min-fraction-digits="8" input-class="full-input" />
          </label>

          <label class="span-2">
            <span>cost_per_1k_output_tokens</span>
            <InputNumber v-model="form.cost_per_1k_output_tokens" :min="0" :min-fraction-digits="8" input-class="full-input" />
          </label>

          <label class="span-4">
            <span>extra_parameters</span>
            <InputText v-model="form.extra_parameters" placeholder='{"response_format":"json"}' />
          </label>

          <Button class="submit-button span-2" type="submit" icon="pi pi-plus" label="Add profile" :loading="isLoading" />
        </form>
      </template>
    </Card>

    <Card class="profile-table-card">
      <template #title>Model profile list</template>
      <template #content>
        <DataTable
          :value="profiles"
          data-key="id"
          scrollable
          scroll-height="620px"
          table-style="min-width: 3860px"
          size="small"
          :loading="isLoading"
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
                :class="{ editing: isEditing(data.id, column.field), readonly: !canEdit(column.field) }"
                :role="canEdit(column.field) ? 'button' : 'cell'"
                @click="startEdit(data.id, column.field)"
                @keydown.enter.prevent="startEdit(data.id, column.field)"
              >
                <template v-if="canEdit(column.field) && isEditing(data.id, column.field)">
                  <select
                    v-if="column.editor === 'select'"
                    v-model="editDraft"
                    class="cell-editor"
                    :data-editor-key="`${data.id}:${column.field}`"
                    @blur="onEditorBlur(data.id, column.field)"
                    @change="commitEdit"
                    @click.stop
                    @mousedown.stop
                    @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                  >
                    <option v-for="option in selectOptions(column.field)" :key="option" :value="option">
                      {{ option }}
                    </option>
                  </select>
                  <input
                    v-else
                    v-model="editDraft"
                    class="cell-editor"
                    :data-editor-key="`${data.id}:${column.field}`"
                    :type="column.editor === 'number' || column.editor === 'decimal' ? 'number' : 'text'"
                    :step="column.editor === 'decimal' ? '0.00000001' : '1'"
                    @blur="onEditorBlur(data.id, column.field)"
                    @click.stop
                    @mousedown.stop
                    @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                  />
                </template>

                <template v-else-if="column.field === 'status'">
                  <Tag :value="formatCell(data, column.field)" :severity="statusSeverity(data.status)" />
                </template>

                <template v-else>
                  <span class="cell-value">{{ formatCell(data, column.field) }}</span>
                </template>
              </div>
            </template>
          </Column>
          <Column header="action" frozen align-frozen="right" style="min-width: 240px">
            <template #body="{ data }">
              <div class="action-row">
                <Button
                  :label="statusActionLabel(data)"
                  :severity="statusActionSeverity(data)"
                  size="small"
                  @click="toggleModelProfileStatus(data)"
                />
                <Button
                  icon="pi pi-trash"
                  severity="danger"
                  size="small"
                  aria-label="Delete model profile"
                  @click="deleteModelProfile(data)"
                />
                <Button
                  label="Test"
                  size="small"
                  @click="openModelProfileTest(data)"
                />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </section>
</template>

<style scoped>
.platform-page {
  display: grid;
  gap: 18px;
}

.feedback {
  margin: 0;
  color: var(--muted-text);
  font-weight: 650;
}

.profile-form {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
}

.profile-form label {
  min-width: 0;
  display: grid;
  gap: 6px;
  color: var(--text-color);
  font-weight: 650;
}

.profile-form label > span {
  overflow: hidden;
  color: var(--muted-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-form :deep(.p-inputtext),
.profile-form :deep(.p-select),
.profile-form :deep(.p-inputnumber) {
  width: 100%;
}

.profile-form :deep(.full-input) {
  width: 100%;
}

.span-1 {
  grid-column: span 1;
}

.span-2 {
  grid-column: span 2;
}

.span-3 {
  grid-column: span 3;
}

.span-4 {
  grid-column: span 4;
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
  width: 100%;
  min-height: 32px;
  display: flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 0 6px;
  background: transparent;
  color: inherit;
  cursor: text;
  text-align: left;
}

.editable-cell:hover {
  border-color: color-mix(in srgb, var(--primary-color) 38%, var(--border-color));
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
}

.editable-cell.readonly {
  cursor: default;
}

.editable-cell.readonly:hover {
  border-color: transparent;
  background: transparent;
}

.editable-cell:focus {
  outline: none;
}

.editable-cell.editing {
  border-color: var(--primary-color);
  background: var(--bg-color);
  padding: 0;
}

.cell-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-editor {
  width: 100%;
  height: 30px;
  border: 0;
  border-radius: 4px;
  outline: 0;
  background: transparent;
  color: var(--text-color);
  font: inherit;
}

.cell-editor:focus {
  border: 0;
  box-shadow: none;
  outline: 0;
}

.profile-table-card :deep(.p-datatable-thead > tr > th) {
  white-space: nowrap;
}

.profile-table-card :deep(.p-datatable-tbody > tr > td) {
  padding: 5px 8px;
}

.action-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

@media (max-width: 1180px) {
  .profile-form {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .span-4,
  .span-3 {
    grid-column: span 3;
  }
}

@media (max-width: 760px) {
  .profile-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .span-1,
  .span-2,
  .span-3,
  .span-4 {
    grid-column: span 2;
  }
}
</style>
