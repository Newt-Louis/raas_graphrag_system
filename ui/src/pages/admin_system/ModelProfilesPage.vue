<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
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
type ProfileCapability = 'llm' | 'embedding'

type EditableField =
  | 'capability'
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
  | 'embedding_dimensions'
  | 'batch_size'
  | 'retrieval_top_k'
  | 'timeout_seconds'
  | 'cost_per_1k_input_tokens'
  | 'cost_per_1k_output_tokens'
  | 'cost_per_1k_tokens'
  | 'extra_parameters'
  | 'status'

interface ApiModelProfile {
  id: string
  capability: ProfileCapability
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
  embedding_dimensions: number | null
  batch_size: number | null
  retrieval_top_k: number | null
  timeout_seconds: number
  cost_per_1k_input_tokens: number | null
  cost_per_1k_output_tokens: number | null
  cost_per_1k_tokens: number | null
  extra_parameters: string
  status: ApiStatus
}

interface BaseModelProfileResponse {
  id: string
  pool_id: string | null
  provider_id: string | null
  api_key_id: string | null
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
  timeout_seconds: number
  extra_parameters: Record<string, unknown>
}

interface LLMModelProfileResponse extends BaseModelProfileResponse {
  temperature: number | null
  top_p: number | null
  top_k: number | null
  max_output_tokens: number | null
  cost_per_1k_input_tokens: number | null
  cost_per_1k_output_tokens: number | null
}

interface EmbeddingModelProfileResponse extends BaseModelProfileResponse {
  embedding_dimensions: number | null
  batch_size: number | null
  retrieval_top_k: number | null
  cost_per_1k_tokens: number | null
}

interface AIProviderResponse {
  id: string
  code: string
  display_name: string
}

interface AIAPIKeyResponse {
  id: string
  provider_id: string
  name: string
  api_key_preview: string
  allowed_capabilities: string[]
  status: string
  is_enabled: boolean
  is_locked: boolean
}

interface AIModelCatalogResponse {
  id: string
  provider_id: string
  capability: ProfileCapability | string
  model_name: string
  display_name: string | null
  is_enabled: boolean
}

interface EditableColumn {
  field: EditableField
  header: string
  width: string
  editor: 'text' | 'number' | 'decimal' | 'select' | 'json'
}

interface SelectOption {
  label: string
  value: string
}

const STORAGE_KEY = 'raas-platform-admin-model-profiles-v3'
const API_BASE = '/api/v1/platform/ai'

const statusOptions: ApiStatus[] = ['active', 'cooldown', 'locked', 'disabled']
const capabilityOptions: SelectOption[] = [
  { label: 'LLM', value: 'llm' },
  { label: 'Embedding', value: 'embedding' },
]

const commonColumns: EditableColumn[] = [
  { field: 'capability', header: 'capability', width: '120px', editor: 'select' },
  { field: 'provider_id', header: 'provider', width: '180px', editor: 'select' },
  { field: 'api_key_id', header: 'api_key_id', width: '220px', editor: 'text' },
  { field: 'model_id', header: 'model_catalog', width: '220px', editor: 'select' },
  { field: 'profile_name', header: 'profile_name', width: '180px', editor: 'text' },
  { field: 'model_name', header: 'model_name', width: '260px', editor: 'text' },
  { field: 'api_base', header: 'api_base', width: '260px', editor: 'text' },
  { field: 'endpoint_id', header: 'endpoint_id', width: '170px', editor: 'text' },
]

const llmPoolColumns: EditableColumn[] = [
  { field: 'pool_id', header: 'pool_id', width: '220px', editor: 'text' },
  { field: 'rotation_order', header: 'rotation_order', width: '130px', editor: 'number' },
  { field: 'weight', header: 'weight', width: '100px', editor: 'number' },
  { field: 'daily_request_count', header: 'daily_request_count', width: '160px', editor: 'number' },
  { field: 'minute_request_count', header: 'minute_request_count', width: '170px', editor: 'number' },
]

const llmColumns: EditableColumn[] = [
  { field: 'temperature', header: 'temperature', width: '130px', editor: 'decimal' },
  { field: 'top_p', header: 'top_p', width: '100px', editor: 'decimal' },
  { field: 'top_k', header: 'top_k', width: '100px', editor: 'number' },
  { field: 'max_output_tokens', header: 'max_output_tokens', width: '160px', editor: 'number' },
  { field: 'timeout_seconds', header: 'timeout_seconds', width: '150px', editor: 'number' },
  { field: 'cost_per_1k_input_tokens', header: 'cost_per_1k_input_tokens', width: '210px', editor: 'decimal' },
  { field: 'cost_per_1k_output_tokens', header: 'cost_per_1k_output_tokens', width: '220px', editor: 'decimal' },
]

const embeddingColumns: EditableColumn[] = [
  { field: 'embedding_dimensions', header: 'embedding_dimensions', width: '180px', editor: 'number' },
  { field: 'batch_size', header: 'batch_size', width: '120px', editor: 'number' },
  { field: 'retrieval_top_k', header: 'retrieval_top_k', width: '140px', editor: 'number' },
  { field: 'timeout_seconds', header: 'timeout_seconds', width: '150px', editor: 'number' },
  { field: 'cost_per_1k_tokens', header: 'cost_per_1k_tokens', width: '180px', editor: 'decimal' },
]

const tailColumns: EditableColumn[] = [
  { field: 'extra_parameters', header: 'extra_parameters', width: '260px', editor: 'json' },
]

const llmStatusColumn: EditableColumn[] = [
  { field: 'status', header: 'status', width: '100px', editor: 'select' },
]

const fallbackEntries: ApiModelProfile[] = [
  {
    id: 'profile-llm-default',
    capability: 'llm',
    pool_id: '',
    provider_id: '',
    api_key_id: '',
    model_id: '',
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
    embedding_dimensions: null,
    batch_size: null,
    retrieval_top_k: null,
    timeout_seconds: 120,
    cost_per_1k_input_tokens: 0,
    cost_per_1k_output_tokens: 0,
    cost_per_1k_tokens: null,
    extra_parameters: '{}',
    status: 'active',
  },
]

const router = useRouter()
const providers = ref<AIProviderResponse[]>([])
const apiKeys = ref<AIAPIKeyResponse[]>([])
const modelCatalog = ref<AIModelCatalogResponse[]>([])
const profiles = ref<ApiModelProfile[]>(loadEntries())
const editingCell = ref<{ rowId: string; field: EditableField } | null>(null)
const editDraft = ref('')
const isLoading = ref(false)
const feedback = ref('')
const rawApiKey = ref('')

const form = reactive<Omit<ApiModelProfile, 'id' | 'status'>>({
  capability: 'llm',
  pool_id: '',
  provider_id: '',
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
  embedding_dimensions: null,
  batch_size: 32,
  retrieval_top_k: 8,
  timeout_seconds: 120,
  cost_per_1k_input_tokens: null,
  cost_per_1k_output_tokens: null,
  cost_per_1k_tokens: null,
  extra_parameters: '{}',
})

const editableColumns = computed(() => [
  ...commonColumns,
  ...(form.capability === 'llm' ? llmPoolColumns : []),
  ...(form.capability === 'llm' ? llmColumns : embeddingColumns),
  ...tailColumns,
  ...(form.capability === 'llm' ? llmStatusColumn : []),
])

const providerOptions = computed<SelectOption[]>(() =>
  providers.value.map((provider) => ({
    label: provider.display_name || provider.code,
    value: provider.id,
  })),
)

const modelOptions = computed<SelectOption[]>(() =>
  compatibleModels(form.provider_id, form.capability).map((model) => ({
    label: model.display_name || model.model_name,
    value: model.id,
  })),
)

const extraParametersPlaceholder = computed(() =>
  form.capability === 'embedding'
    ? '{"mrl_dimensions":[256,512,1024],"mteb_score":64.2}'
    : '{"response_format":"json"}',
)

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

watch(
  () => form.capability,
  () => {
    form.timeout_seconds = form.capability === 'llm' ? 120 : 60
    ensureFormSelections()
    void loadModelProfiles()
  },
)

watch(
  () => form.provider_id,
  () => {
    ensureFormSelections()
  },
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
    const [providerResponse, apiKeyResponse, modelResponse, profileResponse] = await Promise.all([
      axios.get<AIProviderResponse[]>(`${API_BASE}/providers`),
      axios.get<AIAPIKeyResponse[]>(`${API_BASE}/api-keys`),
      axios.get<AIModelCatalogResponse[]>(`${API_BASE}/model-catalog`),
      axios.get<Array<LLMModelProfileResponse | EmbeddingModelProfileResponse>>(profileEndpoint(form.capability)),
    ])

    providers.value = providerResponse.data
    apiKeys.value = apiKeyResponse.data
    modelCatalog.value = modelResponse.data
    ensureFormSelections()
    profiles.value = profileResponse.data.map((profile) => fromApiProfile(profile, form.capability))
  } catch (error) {
    feedback.value = messageFromError(error)
  } finally {
    isLoading.value = false
  }
}

async function addModelProfile() {
  if (!form.provider_id || !rawApiKey.value.trim() || !form.profile_name.trim() || !form.model_name.trim()) {
    feedback.value = 'provider, api_key, profile_name, and model_name are required.'
    return
  }

  feedback.value = ''
  try {
    const apiKey = await createApiKeyForProfile()
    form.api_key_id = apiKey.id

    const response = await axios.post<LLMModelProfileResponse | EmbeddingModelProfileResponse>(
      profileEndpoint(form.capability),
      toApiPayload({
        id: '',
        ...normalizeForm(),
        status: 'active',
      }),
    )

    profiles.value = [fromApiProfile(response.data, form.capability), ...profiles.value]
    apiKeys.value = [apiKey, ...apiKeys.value.filter((entry) => entry.id !== apiKey.id)]
    resetFormAfterSave()
    feedback.value = `Saved ${form.capability} model profile to PostgreSQL.`
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function normalizeForm(): Omit<ApiModelProfile, 'id' | 'status'> {
  return {
    capability: form.capability,
    pool_id: form.pool_id.trim(),
    provider_id: form.provider_id,
    api_key_id: form.api_key_id,
    model_id: form.model_id,
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
    embedding_dimensions: nullableNumber(form.embedding_dimensions),
    batch_size: nullableNumber(form.batch_size),
    retrieval_top_k: nullableNumber(form.retrieval_top_k),
    timeout_seconds: Number(form.timeout_seconds || (form.capability === 'llm' ? 120 : 60)),
    cost_per_1k_input_tokens: nullableNumber(form.cost_per_1k_input_tokens),
    cost_per_1k_output_tokens: nullableNumber(form.cost_per_1k_output_tokens),
    cost_per_1k_tokens: nullableNumber(form.cost_per_1k_tokens),
    extra_parameters: form.extra_parameters.trim() || '{}',
  }
}

function resetFormAfterSave() {
  form.api_key_id = ''
  rawApiKey.value = ''
  form.model_id = ''
  form.profile_name = ''
  form.model_name = ''
  form.api_base = ''
  form.endpoint_id = ''
  form.extra_parameters = '{}'
  ensureFormSelections()
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
  const column = editableColumns.value.find((entry) => entry.field === field)
  if (!row || !column) {
    editingCell.value = null
    return
  }

  ;(row[field] as unknown) = normalizeDraft(column, editDraft.value)
  if (field === 'model_id') syncRowModelName(row)
  if (field === 'provider_id') {
    row.api_key_id = ''
    row.model_id = ''
  }
  editingCell.value = null
  await saveModelProfile(row)
}

function cancelEdit() {
  editingCell.value = null
}

function getNextCell(rowId: string, field: EditableField) {
  const currentColumn = editableColumns.value.findIndex((column) => column.field === field)
  const currentRow = profiles.value.findIndex((entry) => entry.id === rowId)
  if (currentColumn < 0 || currentRow < 0) return null

  let nextColumn = currentColumn + 1
  let nextRow = currentRow
  if (nextColumn >= editableColumns.value.length) {
    nextColumn = 0
    nextRow = Math.min(currentRow + 1, profiles.value.length - 1)
  }

  const nextEntry = profiles.value[nextRow]
  const nextColumnConfig = editableColumns.value[nextColumn]
  if (!nextEntry || !nextColumnConfig) return null
  return { rowId: nextEntry.id, field: nextColumnConfig.field }
}

async function onEditorKeydown(event: KeyboardEvent, rowId: string, field: EditableField) {
  if (event.key === 'Enter') {
    event.preventDefault()
    event.stopPropagation()
    await commitEdit()
    if (event.currentTarget instanceof HTMLElement) event.currentTarget.blur()
    return
  }

  if (event.key === 'Tab') {
    event.preventDefault()
    event.stopPropagation()
    const nextCell = getNextCell(rowId, field)
    await commitEdit()
    if (nextCell) await startEdit(nextCell.rowId, nextCell.field)
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancelEdit()
    if (event.currentTarget instanceof HTMLElement) event.currentTarget.blur()
  }
}

function onEditorBlur(rowId: string, field: EditableField) {
  if (!isEditing(rowId, field)) return
  void commitEdit()
}

function focusEditor(rowId: string, field: EditableField) {
  const key = `${rowId}:${field}`
  const editor = document.querySelector<HTMLInputElement | HTMLSelectElement>(
    `[data-editor-key="${CSS.escape(key)}"]`,
  )
  editor?.focus()
  if (editor instanceof HTMLInputElement) editor.select()
}

function normalizeDraft(column: EditableColumn, value: string) {
  if (column.field === 'status')
    return statusOptions.includes(value as ApiStatus) ? (value as ApiStatus) : 'active'
  if (column.editor === 'number') return value.trim() === '' ? null : Number.parseInt(value, 10)
  if (column.editor === 'decimal') return value.trim() === '' ? null : Number(value)
  if (column.editor === 'json') return value.trim() || '{}'
  return value.trim()
}

function canEdit(field: EditableField) {
  return field !== 'status' && field !== 'capability'
}

function formatCell(row: ApiModelProfile, field: EditableField) {
  const value = row[field]
  if (field === 'capability') return row.capability
  if (field === 'provider_id') return providerLabel(String(value || ''))
  if (field === 'api_key_id') return apiKeyLabel(String(value || ''))
  if (field === 'model_id') return value ? modelLabel(String(value)) : '—'
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function statusSeverity(status: ApiStatus) {
  if (status === 'active') return 'success'
  if (status === 'cooldown') return 'warn'
  if (status === 'locked') return 'contrast'
  return 'danger'
}

function selectOptions(field: EditableField, row?: ApiModelProfile): SelectOption[] {
  if (field === 'provider_id') return providerOptions.value
  if (field === 'model_id') {
    const providerId = row?.provider_id || form.provider_id
    const capability = row?.capability || form.capability
    return compatibleModels(providerId, capability).map((model) => ({
      label: model.display_name || model.model_name,
      value: model.id,
    }))
  }
  if (field === 'status') {
    return statusOptions.map((status) => ({ label: status, value: status }))
  }
  return []
}

async function saveModelProfile(row: ApiModelProfile) {
  if (row.id.startsWith('profile-')) return

  feedback.value = ''
  try {
    const response = await axios.patch<LLMModelProfileResponse | EmbeddingModelProfileResponse>(
      `${profileEndpoint(row.capability)}/${row.id}`,
      toApiPayload(row),
    )
    const updated = fromApiProfile(response.data, row.capability)
    profiles.value = profiles.value.map((entry) => (entry.id === row.id ? updated : entry))
    feedback.value = `Updated ${row.capability} model profile in PostgreSQL.`
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
    const response = await axios.patch<LLMModelProfileResponse | EmbeddingModelProfileResponse>(
      `${profileEndpoint(row.capability)}/${row.id}`,
      toApiPayload(updatedRow),
    )
    const updated = fromApiProfile(response.data, row.capability)
    profiles.value = profiles.value.map((entry) => (entry.id === row.id ? updated : entry))
    feedback.value = `Updated ${row.capability} model profile status in PostgreSQL.`
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
    await axios.delete(`${profileEndpoint(row.capability)}/${row.id}`)
    profiles.value = profiles.value.filter((entry) => entry.id !== row.id)
    feedback.value = `Deleted ${row.capability} model profile from PostgreSQL.`
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function openModelProfileTest(row: ApiModelProfile) {
  if (row.capability !== 'llm') return
  void router.push({
    name: 'api-ai-key-test',
    params: { profileId: row.id },
    query: {
      name: row.profile_name,
      model: row.model_name,
      apiKeyId: row.api_key_id,
    },
  })
}

function statusActionLabel(row: ApiModelProfile) {
  return row.status === 'active' ? 'Disable' : 'Active'
}

function statusActionSeverity(row: ApiModelProfile) {
  return row.status === 'active' ? 'danger' : 'success'
}

function fromApiProfile(
  profile: LLMModelProfileResponse | EmbeddingModelProfileResponse,
  capability: ProfileCapability,
): ApiModelProfile {
  const llmProfile = profile as LLMModelProfileResponse
  const embeddingProfile = profile as EmbeddingModelProfileResponse
  return {
    id: profile.id,
    capability,
    pool_id: profile.pool_id ?? '',
    provider_id: profile.provider_id ?? '',
    api_key_id: profile.api_key_id ?? '',
    model_id: profile.model_id ?? '',
    profile_name: profile.profile_name,
    model_name: profile.model_name,
    api_base: profile.api_base ?? '',
    endpoint_id: profile.endpoint_id ?? '',
    rotation_order: profile.rotation_order,
    weight: profile.weight,
    daily_request_count: profile.daily_request_count,
    minute_request_count: profile.minute_request_count,
    temperature: capability === 'llm' ? llmProfile.temperature : null,
    top_p: capability === 'llm' ? llmProfile.top_p : null,
    top_k: capability === 'llm' ? llmProfile.top_k : null,
    max_output_tokens: capability === 'llm' ? llmProfile.max_output_tokens : null,
    embedding_dimensions: capability === 'embedding' ? embeddingProfile.embedding_dimensions : null,
    batch_size: capability === 'embedding' ? embeddingProfile.batch_size : null,
    retrieval_top_k: capability === 'embedding' ? embeddingProfile.retrieval_top_k : null,
    timeout_seconds: profile.timeout_seconds,
    cost_per_1k_input_tokens: capability === 'llm' ? llmProfile.cost_per_1k_input_tokens : null,
    cost_per_1k_output_tokens: capability === 'llm' ? llmProfile.cost_per_1k_output_tokens : null,
    cost_per_1k_tokens: capability === 'embedding' ? embeddingProfile.cost_per_1k_tokens : null,
    extra_parameters: JSON.stringify(profile.extra_parameters || {}),
    status:
      capability === 'embedding'
        ? 'active'
        : profile.is_locked
          ? 'locked'
          : profile.today_quota_exhausted
            ? 'cooldown'
            : profile.is_enabled
              ? 'active'
              : 'disabled',
  }
}

function toApiPayload(row: Omit<ApiModelProfile, 'id'> | ApiModelProfile) {
  const common = {
    provider_id: row.provider_id || null,
    api_key_id: row.api_key_id || null,
    model_id: row.model_id || null,
    profile_name: row.profile_name,
    model_name: row.model_name,
    api_base: row.api_base || null,
    endpoint_id: row.endpoint_id || null,
    timeout_seconds: row.timeout_seconds,
    extra_parameters: parseJson(row.extra_parameters),
  }

  if (row.capability === 'embedding') {
    return {
      ...common,
      embedding_dimensions: row.embedding_dimensions,
      batch_size: row.batch_size,
      retrieval_top_k: row.retrieval_top_k,
      cost_per_1k_tokens: row.cost_per_1k_tokens,
    }
  }

  return {
    ...common,
    pool_id: row.pool_id || null,
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
    cost_per_1k_input_tokens: row.cost_per_1k_input_tokens,
    cost_per_1k_output_tokens: row.cost_per_1k_output_tokens,
  }
}

function profileEndpoint(capability: ProfileCapability) {
  return `${API_BASE}/${capability}/model-profiles`
}

async function createApiKeyForProfile() {
  const name = `${form.profile_name.trim()} ${form.capability} key`.trim()
  const response = await axios.post<AIAPIKeyResponse>(`${API_BASE}/api-keys`, {
    provider_id: form.provider_id,
    name,
    api_key: rawApiKey.value.trim(),
    api_base: form.api_base.trim() || null,
    endpoint_id: form.endpoint_id.trim() || null,
    allowed_capabilities: [form.capability],
    status: 'active',
    is_enabled: true,
    is_locked: false,
    metadata_json: {},
  })
  return response.data
}

function ensureFormSelections() {
  const providerIds = new Set(providers.value.map((provider) => provider.id))
  if (!form.provider_id || !providerIds.has(form.provider_id)) {
    form.provider_id = providers.value[0]?.id || ''
  }

  const modelIds = new Set(compatibleModels(form.provider_id, form.capability).map((model) => model.id))
  if (form.model_id && !modelIds.has(form.model_id)) {
    form.model_id = ''
  }
}

function compatibleApiKeys(providerId: string, capability: ProfileCapability) {
  return apiKeys.value.filter((apiKey) => {
    const capabilities = apiKey.allowed_capabilities.map((entry) => entry.toLowerCase())
    return (
      apiKey.provider_id === providerId &&
      apiKey.is_enabled &&
      !apiKey.is_locked &&
      apiKey.status !== 'disabled' &&
      (capabilities.length === 0 || capabilities.includes(capability))
    )
  })
}

function compatibleModels(providerId: string, capability: ProfileCapability) {
  return modelCatalog.value.filter(
    (model) => model.provider_id === providerId && model.capability === capability && model.is_enabled,
  )
}

function syncModelNameFromCatalog() {
  const model = modelCatalog.value.find((entry) => entry.id === form.model_id)
  if (model) form.model_name = model.model_name
}

function syncRowModelName(row: ApiModelProfile) {
  const model = modelCatalog.value.find((entry) => entry.id === row.model_id)
  if (model) row.model_name = model.model_name
}

function providerLabel(providerId: string) {
  const provider = providers.value.find((entry) => entry.id === providerId)
  return provider ? provider.display_name || provider.code : providerId || '—'
}

function apiKeyLabel(apiKeyId: string) {
  const apiKey = apiKeys.value.find((entry) => entry.id === apiKeyId)
  if (!apiKey) return apiKeyId || '—'
  return `${apiKey.name}${apiKey.api_key_preview ? ` (${apiKey.api_key_preview})` : ''}`
}

function modelLabel(modelId: string) {
  const model = modelCatalog.value.find((entry) => entry.id === modelId)
  return model ? model.display_name || model.model_name : modelId || '—'
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
          <label class="form-field col-2 col-md-3 col-sm-12">
            <span>capability</span>
            <Select
              v-model="form.capability"
              :options="capabilityOptions"
              option-label="label"
              option-value="value"
            />
          </label>

          <label class="form-field col-3 col-md-4 col-sm-12">
            <span>provider</span>
            <Select
              v-model="form.provider_id"
              :options="providerOptions"
              option-label="label"
              option-value="value"
              placeholder="Select provider"
            />
          </label>

          <label class="form-field col-4 col-md-5 col-sm-12">
            <span>api_key</span>
            <InputText v-model="rawApiKey" type="password" placeholder="Provider API key" />
          </label>

          <label class="form-field col-3 col-md-6 col-sm-12">
            <span>model_catalog</span>
            <Select
              v-model="form.model_id"
              :options="modelOptions"
              option-label="label"
              option-value="value"
              show-clear
              placeholder="Optional"
              @change="syncModelNameFromCatalog"
            />
          </label>

          <label class="form-field col-4 col-md-6 col-sm-12">
            <span>model_name</span>
            <InputText v-model="form.model_name" placeholder="provider/model-name" />
          </label>

          <label class="form-field col-4 col-md-6 col-sm-12">
            <span>profile_name</span>
            <InputText v-model="form.profile_name" placeholder="default-profile" />
          </label>

          <label v-if="form.capability === 'llm'" class="form-field col-4 col-md-6 col-sm-12">
            <span>pool_id</span>
            <InputText v-model="form.pool_id" placeholder="optional UUID" />
          </label>

          <label class="form-field col-5 col-md-7 col-sm-12">
            <span>api_base</span>
            <InputText v-model="form.api_base" placeholder="https://..." />
          </label>

          <label class="form-field col-3 col-md-5 col-sm-12">
            <span>endpoint_id</span>
            <InputText v-model="form.endpoint_id" placeholder="primary" />
          </label>

          <label v-if="form.capability === 'llm'" class="form-field col-2 col-md-3 col-sm-6">
            <span>rotation_order</span>
            <InputNumber v-model="form.rotation_order" :min="0" input-class="full-input" />
          </label>

          <label v-if="form.capability === 'llm'" class="form-field col-2 col-md-3 col-sm-6">
            <span>weight</span>
            <InputNumber v-model="form.weight" :min="1" input-class="full-input" />
          </label>

          <template v-if="form.capability === 'llm'">
            <label class="form-field col-2 col-md-3 col-sm-6">
              <span>top_k</span>
              <InputNumber v-model="form.top_k" :min="0" input-class="full-input" />
            </label>

            <label class="form-field col-2 col-md-3 col-sm-6">
              <span>temperature</span>
              <InputNumber
                v-model="form.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                :min-fraction-digits="1"
                input-class="full-input"
              />
            </label>

            <label class="form-field col-2 col-md-3 col-sm-6">
              <span>top_p</span>
              <InputNumber
                v-model="form.top_p"
                :min="0"
                :max="1"
                :step="0.05"
                :min-fraction-digits="2"
                input-class="full-input"
              />
            </label>

            <label class="form-field col-3 col-md-4 col-sm-12">
              <span>max_output_tokens</span>
              <InputNumber v-model="form.max_output_tokens" :min="1" input-class="full-input" />
            </label>

            <label class="form-field col-3 col-md-4 col-sm-12">
              <span>cost_per_1k_input_tokens</span>
              <InputNumber
                v-model="form.cost_per_1k_input_tokens"
                :min="0"
                :min-fraction-digits="8"
                input-class="full-input"
              />
            </label>

            <label class="form-field col-3 col-md-4 col-sm-12">
              <span>cost_per_1k_output_tokens</span>
              <InputNumber
                v-model="form.cost_per_1k_output_tokens"
                :min="0"
                :min-fraction-digits="8"
                input-class="full-input"
              />
            </label>
          </template>

          <template v-else>
            <label class="form-field col-3 col-md-4 col-sm-12">
              <span>embedding_dimensions</span>
              <InputNumber v-model="form.embedding_dimensions" :min="1" input-class="full-input" />
            </label>

            <label class="form-field col-2 col-md-3 col-sm-6">
              <span>batch_size</span>
              <InputNumber v-model="form.batch_size" :min="1" input-class="full-input" />
            </label>

            <label class="form-field col-2 col-md-3 col-sm-6">
              <span>retrieval_top_k</span>
              <InputNumber v-model="form.retrieval_top_k" :min="1" input-class="full-input" />
            </label>

            <label class="form-field col-3 col-md-4 col-sm-12">
              <span>cost_per_1k_tokens</span>
              <InputNumber
                v-model="form.cost_per_1k_tokens"
                :min="0"
                :min-fraction-digits="8"
                input-class="full-input"
              />
            </label>
          </template>

          <label class="form-field col-2 col-md-3 col-sm-6">
            <span>timeout_seconds</span>
            <InputNumber v-model="form.timeout_seconds" :min="1" input-class="full-input" />
          </label>

          <label v-if="form.capability === 'llm'" class="form-field col-3 col-md-4 col-sm-12">
            <span>minute_request_count</span>
            <InputNumber v-model="form.minute_request_count" :min="0" input-class="full-input" />
          </label>

          <label v-if="form.capability === 'llm'" class="form-field col-3 col-md-4 col-sm-12">
            <span>daily_request_count</span>
            <InputNumber v-model="form.daily_request_count" :min="0" input-class="full-input" />
          </label>

          <label class="form-field col-6 col-md-8 col-sm-12">
            <span>extra_parameters</span>
            <InputText v-model="form.extra_parameters" :placeholder="extraParametersPlaceholder" />
          </label>

          <Button
            class="submit-button form-field col-2 col-md-4 col-sm-12"
            type="submit"
            icon="pi pi-plus"
            label="Add profile"
            :loading="isLoading"
          />
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
          table-style="min-width: 3600px"
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
                :class="{
                  editing: isEditing(data.id, column.field),
                  readonly: !canEdit(column.field),
                }"
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
                    <option
                      v-if="column.field === 'model_id'"
                      value=""
                    >
                      —
                    </option>
                    <option
                      v-for="option in selectOptions(column.field, data)"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                  <input
                    v-else
                    v-model="editDraft"
                    class="cell-editor"
                    :data-editor-key="`${data.id}:${column.field}`"
                    :type="
                      column.editor === 'number' || column.editor === 'decimal' ? 'number' : 'text'
                    "
                    :step="column.editor === 'decimal' ? '0.00000001' : '1'"
                    @blur="onEditorBlur(data.id, column.field)"
                    @click.stop
                    @mousedown.stop
                    @keydown.capture="onEditorKeydown($event, data.id, column.field)"
                  />
                </template>

                <template v-else-if="column.field === 'status'">
                  <Tag
                    :value="formatCell(data, column.field)"
                    :severity="statusSeverity(data.status)"
                  />
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
                  v-if="data.capability === 'llm'"
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
                  v-if="data.capability === 'llm'"
                  label="Test"
                  size="small"
                  severity="info"
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
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
}

.form-field {
  min-width: 0;
  grid-column: span 12;
}

.profile-form label {
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
.profile-form :deep(.p-inputnumber),
.profile-form :deep(.p-password) {
  min-width: 0;
  width: 100%;
}

.profile-form :deep(.full-input) {
  width: 100%;
}

.col-2 {
  grid-column: span 2;
}

.col-3 {
  grid-column: span 3;
}

.col-4 {
  grid-column: span 4;
}

.col-5 {
  grid-column: span 5;
}

.col-6 {
  grid-column: span 6;
}

.col-12 {
  grid-column: span 12;
}

@media (max-width: 1180px) {
  .profile-form {
    grid-template-columns: repeat(8, minmax(0, 1fr));
  }

  .col-md-2 {
    grid-column: span 2;
  }

  .col-md-3 {
    grid-column: span 3;
  }

  .col-md-4 {
    grid-column: span 4;
  }

  .col-md-5 {
    grid-column: span 5;
  }

  .col-md-6 {
    grid-column: span 6;
  }

  .col-md-7 {
    grid-column: span 7;
  }

  .col-md-8 {
    grid-column: span 8;
  }
}

@media (max-width: 760px) {
  .profile-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .col-sm-6 {
    grid-column: span 1;
  }

  .col-sm-12 {
    grid-column: span 2;
  }
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
</style>
