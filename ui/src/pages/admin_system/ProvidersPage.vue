<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'

type ApiStatus = 'active' | 'cooldown' | 'locked' | 'disabled'

interface AIProviderResponse {
  id: string
  code: string
  display_name: string
  provider_kind: string
  base_url: string | null
  auth_type: string
  is_enabled: boolean
  is_locked: boolean
  lock_reason: string | null
  default_headers: Record<string, unknown>
  provider_config: Record<string, unknown>
  created_at: string
  updated_at: string
}

type ProviderEditableField =
  | 'code'
  | 'display_name'
  | 'provider_kind'
  | 'base_url'
  | 'auth_type'
  | 'lock_reason'
  | 'default_headers'
  | 'provider_config'

interface ProviderEditableColumn {
  field: ProviderEditableField
  header: string
  width: string
  editor: 'text' | 'json'
}

const API_BASE = '/api/v1/platform/ai'

const providerEditableColumns: ProviderEditableColumn[] = [
  { field: 'code', header: 'code', width: '140px', editor: 'text' },
  { field: 'display_name', header: 'display_name', width: '200px', editor: 'text' },
  { field: 'provider_kind', header: 'provider_kind', width: '150px', editor: 'text' },
  { field: 'base_url', header: 'base_url', width: '260px', editor: 'text' },
  { field: 'auth_type', header: 'auth_type', width: '120px', editor: 'text' },
  { field: 'lock_reason', header: 'lock_reason', width: '220px', editor: 'text' },
  { field: 'default_headers', header: 'default_headers', width: '260px', editor: 'json' },
  { field: 'provider_config', header: 'provider_config', width: '260px', editor: 'json' },
]

const providers = ref<AIProviderResponse[]>([])
const providerEditingCell = ref<{ rowId: string; field: ProviderEditableField } | null>(null)
const providerEditDraft = ref('')
const isLoading = ref(false)
const feedback = ref('')

const providerForm = reactive({
  code: '',
  display_name: '',
  provider_kind: 'litellm',
  base_url: '',
  auth_type: 'api_key',
  is_enabled: true,
  is_locked: false,
  lock_reason: '',
  default_headers: '{}',
  provider_config: '{}',
})

onMounted(() => {
  void loadProviders()
})

async function loadProviders() {
  isLoading.value = true
  feedback.value = ''
  try {
    const response = await axios.get<AIProviderResponse[]>(`${API_BASE}/providers`)
    providers.value = response.data
  } catch (error) {
    feedback.value = messageFromError(error)
  } finally {
    isLoading.value = false
  }
}

async function addProvider() {
  if (!providerForm.code.trim() || !providerForm.display_name.trim()) return

  feedback.value = ''
  try {
    const response = await axios.post<AIProviderResponse>(`${API_BASE}/providers`, providerPayload())
    providers.value = [...providers.value, response.data].sort((left, right) => left.code.localeCompare(right.code))
    resetProviderForm()
    feedback.value = 'Saved provider to PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

async function toggleProviderStatus(provider: AIProviderResponse) {
  feedback.value = ''
  try {
    const response = await axios.patch<AIProviderResponse>(
      `${API_BASE}/providers/${provider.id}`,
      {
        is_enabled: !provider.is_enabled,
        is_locked: provider.is_locked && !provider.is_enabled ? false : provider.is_locked,
      },
    )
    providers.value = providers.value.map((entry) => (entry.id === provider.id ? response.data : entry))
    feedback.value = 'Updated provider status in PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

async function deleteProvider(provider: AIProviderResponse) {
  if (!window.confirm(`Delete provider "${provider.display_name}" permanently?`)) return

  feedback.value = ''
  try {
    await axios.delete(`${API_BASE}/providers/${provider.id}`)
    providers.value = providers.value.filter((entry) => entry.id !== provider.id)
    feedback.value = 'Deleted provider from PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function providerPayload() {
  return {
    code: providerForm.code.trim(),
    display_name: providerForm.display_name.trim(),
    provider_kind: providerForm.provider_kind.trim() || 'litellm',
    base_url: providerForm.base_url.trim() || null,
    auth_type: providerForm.auth_type.trim() || 'api_key',
    is_enabled: providerForm.is_enabled,
    is_locked: providerForm.is_locked,
    lock_reason: providerForm.lock_reason.trim() || null,
    default_headers: parseJson(providerForm.default_headers),
    provider_config: parseJson(providerForm.provider_config),
  }
}

function resetProviderForm() {
  providerForm.code = ''
  providerForm.display_name = ''
  providerForm.provider_kind = 'litellm'
  providerForm.base_url = ''
  providerForm.auth_type = 'api_key'
  providerForm.is_enabled = true
  providerForm.is_locked = false
  providerForm.lock_reason = ''
  providerForm.default_headers = '{}'
  providerForm.provider_config = '{}'
}

function providerStatus(provider: AIProviderResponse): ApiStatus {
  if (provider.is_locked) return 'locked'
  return provider.is_enabled ? 'active' : 'disabled'
}

function providerStatusActionLabel(provider: AIProviderResponse) {
  return provider.is_enabled ? 'Disable' : 'Active'
}

function providerStatusActionSeverity(provider: AIProviderResponse) {
  return provider.is_enabled ? 'danger' : 'success'
}

function statusSeverity(status: ApiStatus) {
  if (status === 'active') return 'success'
  if (status === 'cooldown') return 'warn'
  if (status === 'locked') return 'contrast'
  return 'danger'
}

function isProviderEditing(rowId: string, field: ProviderEditableField) {
  return providerEditingCell.value?.rowId === rowId && providerEditingCell.value.field === field
}

async function startProviderEdit(rowId: string, field: ProviderEditableField) {
  if (providerEditingCell.value && !isProviderEditing(rowId, field)) {
    await commitProviderEdit()
  }

  const row = providers.value.find((entry) => entry.id === rowId)
  if (!row) return

  providerEditingCell.value = { rowId, field }
  providerEditDraft.value = formatProviderCell(row, field)
  await nextTick()
  focusProviderEditor(rowId, field)
}

async function commitProviderEdit() {
  if (!providerEditingCell.value) return

  const { rowId, field } = providerEditingCell.value
  const row = providers.value.find((entry) => entry.id === rowId)
  const column = providerEditableColumns.find((entry) => entry.field === field)
  if (!row || !column) {
    providerEditingCell.value = null
    return
  }

  const updated = applyProviderDraft(row, column, providerEditDraft.value)
  providerEditingCell.value = null
  await saveProvider(updated)
}

function cancelProviderEdit() {
  providerEditingCell.value = null
}

function getNextProviderCell(rowId: string, field: ProviderEditableField) {
  const currentColumn = providerEditableColumns.findIndex((column) => column.field === field)
  const currentRow = providers.value.findIndex((entry) => entry.id === rowId)
  if (currentColumn < 0 || currentRow < 0) return null

  let nextColumn = currentColumn + 1
  let nextRow = currentRow
  if (nextColumn >= providerEditableColumns.length) {
    nextColumn = 0
    nextRow = Math.min(currentRow + 1, providers.value.length - 1)
  }

  const nextEntry = providers.value[nextRow]
  const nextColumnConfig = providerEditableColumns[nextColumn]
  if (!nextEntry || !nextColumnConfig) return null
  return { rowId: nextEntry.id, field: nextColumnConfig.field }
}

async function onProviderEditorKeydown(event: KeyboardEvent, rowId: string, field: ProviderEditableField) {
  if (event.key === 'Enter') {
    event.preventDefault()
    event.stopPropagation()
    await commitProviderEdit()
    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.blur()
    }
    return
  }

  if (event.key === 'Tab') {
    event.preventDefault()
    event.stopPropagation()
    const nextCell = getNextProviderCell(rowId, field)
    await commitProviderEdit()
    if (nextCell) {
      await startProviderEdit(nextCell.rowId, nextCell.field)
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancelProviderEdit()
    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.blur()
    }
  }
}

function onProviderEditorBlur(rowId: string, field: ProviderEditableField) {
  if (!isProviderEditing(rowId, field)) return
  void commitProviderEdit()
}

function focusProviderEditor(rowId: string, field: ProviderEditableField) {
  const key = `${rowId}:${field}`
  const editor = document.querySelector<HTMLInputElement>(`[data-provider-editor-key="${CSS.escape(key)}"]`)
  editor?.focus()
  editor?.select()
}

function formatProviderCell(row: AIProviderResponse, field: ProviderEditableField) {
  const value = row[field]
  if (field === 'default_headers' || field === 'provider_config') {
    return JSON.stringify(value || {})
  }
  if (value === null || value === undefined || value === '') return ''
  return String(value)
}

function displayProviderCell(row: AIProviderResponse, field: ProviderEditableField) {
  const value = formatProviderCell(row, field)
  return value || '—'
}

function applyProviderDraft(
  row: AIProviderResponse,
  column: ProviderEditableColumn,
  draft: string,
): AIProviderResponse {
  const value = column.editor === 'json' ? parseJson(draft) : draft.trim()
  const normalized = {
    ...row,
    [column.field]: value === '' && (column.field === 'base_url' || column.field === 'lock_reason')
      ? null
      : value,
  }
  providers.value = providers.value.map((entry) => (entry.id === row.id ? normalized : entry))
  return normalized
}

async function saveProvider(provider: AIProviderResponse) {
  feedback.value = ''
  try {
    const response = await axios.patch<AIProviderResponse>(
      `${API_BASE}/providers/${provider.id}`,
      providerToPayload(provider),
    )
    providers.value = providers.value.map((entry) => (entry.id === provider.id ? response.data : entry))
    feedback.value = 'Updated provider in PostgreSQL.'
  } catch (error) {
    feedback.value = messageFromError(error)
  }
}

function providerToPayload(provider: AIProviderResponse) {
  return {
    code: provider.code,
    display_name: provider.display_name,
    provider_kind: provider.provider_kind,
    base_url: provider.base_url || null,
    auth_type: provider.auth_type,
    is_enabled: provider.is_enabled,
    is_locked: provider.is_locked,
    lock_reason: provider.lock_reason || null,
    default_headers: provider.default_headers || {},
    provider_config: provider.provider_config || {},
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
      <template #title>Add provider</template>
      <template #content>
        <form class="profile-form" @submit.prevent="addProvider">
          <label class="span-2">
            <span>code</span>
            <InputText v-model="providerForm.code" placeholder="openai" />
          </label>

          <label class="span-3">
            <span>display_name</span>
            <InputText v-model="providerForm.display_name" placeholder="OpenAI" />
          </label>

          <label class="span-2">
            <span>provider_kind</span>
            <InputText v-model="providerForm.provider_kind" placeholder="litellm" />
          </label>

          <label class="span-2">
            <span>auth_type</span>
            <InputText v-model="providerForm.auth_type" placeholder="api_key" />
          </label>

          <label class="span-4">
            <span>base_url</span>
            <InputText v-model="providerForm.base_url" placeholder="https://..." />
          </label>

          <label class="span-2 provider-toggle">
            <input v-model="providerForm.is_enabled" type="checkbox" />
            <span>is_enabled</span>
          </label>

          <label class="span-2 provider-toggle">
            <input v-model="providerForm.is_locked" type="checkbox" />
            <span>is_locked</span>
          </label>

          <label class="span-4">
            <span>lock_reason</span>
            <InputText v-model="providerForm.lock_reason" placeholder="optional" />
          </label>

          <label class="span-4">
            <span>default_headers</span>
            <InputText v-model="providerForm.default_headers" placeholder='{"x-header":"value"}' />
          </label>

          <label class="span-4">
            <span>provider_config</span>
            <InputText v-model="providerForm.provider_config" placeholder='{"region":"us"}' />
          </label>

          <Button class="submit-button span-2" type="submit" icon="pi pi-plus" label="Add provider" :loading="isLoading" />
        </form>
      </template>
    </Card>

    <Card class="profile-table-card">
      <template #title>Provider list</template>
      <template #content>
        <DataTable
          :value="providers"
          data-key="id"
          scrollable
          scroll-height="620px"
          table-style="min-width: 1600px"
          size="small"
          :loading="isLoading"
        >
          <Column
            v-for="column in providerEditableColumns"
            :key="column.field"
            :field="column.field"
            :header="column.header"
            :style="{ minWidth: column.width }"
          >
            <template #body="{ data }">
              <div
                class="editable-cell"
                :class="{ editing: isProviderEditing(data.id, column.field) }"
                role="button"
                @click="startProviderEdit(data.id, column.field)"
                @keydown.enter.prevent="startProviderEdit(data.id, column.field)"
              >
                <template v-if="isProviderEditing(data.id, column.field)">
                  <input
                    v-model="providerEditDraft"
                    class="cell-editor"
                    :data-provider-editor-key="`${data.id}:${column.field}`"
                    type="text"
                    @blur="onProviderEditorBlur(data.id, column.field)"
                    @click.stop
                    @mousedown.stop
                    @keydown.capture="onProviderEditorKeydown($event, data.id, column.field)"
                  />
                </template>

                <template v-else>
                  <span class="cell-value">{{ displayProviderCell(data, column.field) }}</span>
                </template>
              </div>
            </template>
          </Column>
          <Column header="status" style="min-width: 120px">
            <template #body="{ data }">
              <Tag :value="providerStatus(data)" :severity="statusSeverity(providerStatus(data))" />
            </template>
          </Column>
          <Column header="action" frozen align-frozen="right" style="min-width: 170px">
            <template #body="{ data }">
              <div class="action-row">
                <Button
                  :label="providerStatusActionLabel(data)"
                  :severity="providerStatusActionSeverity(data)"
                  size="small"
                  @click="toggleProviderStatus(data)"
                />
                <Button
                  icon="pi pi-trash"
                  severity="danger"
                  size="small"
                  aria-label="Delete provider"
                  @click="deleteProvider(data)"
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
.profile-form :deep(.p-inputnumber) {
  width: 100%;
}

.provider-toggle {
  grid-template-columns: auto 1fr;
  align-items: center;
  min-height: 38px;
}

.provider-toggle input {
  width: 16px;
  height: 16px;
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
