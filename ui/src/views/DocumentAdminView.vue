<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import FileUpload from 'primevue/fileupload'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import GraphVisualizationPage from '@/pages/documents_visualize/GraphVisualizationPage.vue'
import VectorVisualizationPage from '@/pages/documents_visualize/VectorVisualizationPage.vue'
import type {
  FileUploadRemoveEvent,
  FileUploadSelectEvent,
  FileUploadUploaderEvent,
} from 'primevue/fileupload'

type UploadStatus = 'pending' | 'uploading' | 'ready' | 'failed'
type VisualizationTab = 'vector' | 'graph'

interface ChunkStrategyOption {
  label: string
  value: string
}

interface UploadRecord {
  id: string
  filename: string
  size: number
  status: UploadStatus
  progress: number
  document_id?: string
  chunks?: number
  vector_stored_count?: number
  error?: string
}

interface IngestResponse {
  status: string
  document_id: string
  filename: string
  stats: Record<string, number>
  vector_stored_count: number
  warnings?: string[]
}

interface DocumentRecord {
  id: string
  filename: string
  extension: string
  content_type: string | null
  byte_size: number
  sha256: string
  status: string
  chunk_count: number
  vector_record_count: number
  graph_record_count: number
  last_indexed_at: string | null
  created_at: string
}

const uploadDialogVisible = ref(false)
const selectedFiles = ref<File[]>([])
const uploadRecords = ref<UploadRecord[]>([])
const documents = ref<DocumentRecord[]>([])
const activeUploads = ref(0)
const deletingDocumentIds = ref(new Set<string>())
const isLoadingDocuments = ref(false)
const lastError = ref('')
const activeVisualizationTab = ref<VisualizationTab>('vector')

const form = reactive({
  tenant_id: 'tenant-a',
  app_id: 'app-a',
  collection_id: '',
  chunk_strategy: 'parent_child',
  max_tokens: 700,
  overlap_tokens: 80,
  parent_max_tokens: 1800,
  semantic_similarity_threshold: 0.72,
})

const chunkStrategyOptions: ChunkStrategyOption[] = [
  { label: 'Parent child', value: 'parent_child' },
  { label: 'Semantic', value: 'semantic' },
  { label: 'Sliding window', value: 'sliding_window' },
]

const visualizationTabs: { label: string; value: VisualizationTab }[] = [
  { label: 'Vector', value: 'vector' },
  { label: 'Graph', value: 'graph' },
]

const acceptedFileTypes = [
  '.txt',
  '.csv',
  '.json',
  '.jsonl',
  '.pdf',
  '.xls',
  '.xlsx',
  '.doc',
  '.docx',
  '.ppt',
  '.pptx',
  '.jpg',
  '.jpeg',
  '.png',
].join(',')

const canUpload = computed(() => Boolean(form.tenant_id.trim() && form.app_id.trim()))
const isUploading = computed(() => activeUploads.value > 0)

onMounted(loadDocuments)

function openUploadDialog() {
  uploadDialogVisible.value = true
  lastError.value = ''
}

function onSelect(event: FileUploadSelectEvent) {
  selectedFiles.value = normalizeFiles(event.files)
  seedPendingRecords(selectedFiles.value)
}

function onRemove(event: FileUploadRemoveEvent) {
  const removed = normalizeFiles(event.file)
  if (!removed.length) {
    return
  }
  const removedKeys = new Set(removed.map(fileKey))
  selectedFiles.value = selectedFiles.value.filter((file) => !removedKeys.has(fileKey(file)))
  uploadRecords.value = uploadRecords.value.filter((record) => !removedKeys.has(record.id))
}

function onClear() {
  selectedFiles.value = []
  uploadRecords.value = []
  lastError.value = ''
}

async function uploadSelected(event: FileUploadUploaderEvent) {
  if (!canUpload.value) {
    lastError.value = 'tenant_id and app_id are required.'
    return
  }

  const files = normalizeFiles(event.files)
  if (!files.length) {
    return
  }

  lastError.value = ''
  activeUploads.value = files.length

  for (const file of files) {
    const id = fileKey(file)
    upsertRecord(file, { status: 'uploading', progress: 35, error: '' })

    try {
      const response = await fetch('/api/v1/ingest', {
        method: 'POST',
        body: buildFormData(file),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = typeof payload.detail === 'string' ? payload.detail : response.statusText
        throw new Error(detail)
      }

      const result = payload as IngestResponse
      updateRecord(id, {
        status: 'ready',
        progress: 100,
        document_id: result.document_id,
        chunks: result.stats?.chunks ?? 0,
        vector_stored_count: result.vector_stored_count,
        error: result.warnings?.join(' '),
      })
      await loadDocuments()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed.'
      updateRecord(id, { status: 'failed', progress: 100, error: message })
      lastError.value = message
      await loadDocuments()
    } finally {
      activeUploads.value -= 1
    }
  }
}

async function loadDocuments() {
  isLoadingDocuments.value = true
  try {
    const response = await fetch('/api/v1/documents')
    const payload = await response.json().catch(() => [])
    if (!response.ok) {
      const detail = typeof payload.detail === 'string' ? payload.detail : response.statusText
      throw new Error(detail)
    }
    documents.value = Array.isArray(payload) ? payload as DocumentRecord[] : []
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : 'Document list could not be loaded.'
  } finally {
    isLoadingDocuments.value = false
  }
}

async function deleteDocument(document: DocumentRecord) {
  if (!window.confirm(`Delete ${document.filename}?`)) {
    return
  }
  deletingDocumentIds.value.add(document.id)
  try {
    const response = await fetch(`/api/v1/documents/${document.id}`, { method: 'DELETE' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof payload.detail === 'string' ? payload.detail : response.statusText
      throw new Error(detail)
    }
    await loadDocuments()
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : 'Document could not be deleted.'
  } finally {
    deletingDocumentIds.value.delete(document.id)
  }
}

function buildFormData(file: File) {
  const data = new FormData()
  data.append('tenant_id', form.tenant_id.trim())
  data.append('app_id', form.app_id.trim())
  if (form.collection_id.trim()) {
    data.append('collection_id', form.collection_id.trim())
  }
  data.append('chunk_strategy', form.chunk_strategy)
  data.append('max_tokens', String(form.max_tokens))
  data.append('overlap_tokens', String(form.overlap_tokens))
  data.append('parent_max_tokens', String(form.parent_max_tokens))
  data.append('semantic_similarity_threshold', String(form.semantic_similarity_threshold))
  data.append('extract_semantic_graph', 'true')
  data.append('file', file)
  return data
}

function seedPendingRecords(files: File[]) {
  const existingById = new Map(uploadRecords.value.map((record) => [record.id, record]))
  uploadRecords.value = files.map((file) => {
    const id = fileKey(file)
    return existingById.get(id) ?? {
      id,
      filename: file.name,
      size: file.size,
      status: 'pending',
      progress: 0,
    }
  })
}

function upsertRecord(file: File, patch: Partial<UploadRecord>) {
  const id = fileKey(file)
  const existing = uploadRecords.value.find((record) => record.id === id)
  if (existing) {
    Object.assign(existing, patch)
    return
  }
  uploadRecords.value.push({
    id,
    filename: file.name,
    size: file.size,
    status: 'pending',
    progress: 0,
    ...patch,
  })
}

function updateRecord(id: string, patch: Partial<UploadRecord>) {
  const record = uploadRecords.value.find((item) => item.id === id)
  if (record) {
    Object.assign(record, patch)
  }
}

function normalizeFiles(files: File | File[] | unknown): File[] {
  if (Array.isArray(files)) {
    return files
  }
  if (files instanceof File) {
    return [files]
  }
  return []
}

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function statusSeverity(status: string) {
  if (status === 'ready') {
    return 'success'
  }
  if (status === 'failed') {
    return 'danger'
  }
  if (status === 'uploading') {
    return 'info'
  }
  return 'secondary'
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B'
  }
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const unit = units[exponent] ?? 'B'
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 1)} ${unit}`
}

function formatDate(value: string | null) {
  if (!value) {
    return '-'
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Document admin</h1>
      <p>Customer document lifecycle and GraphRAG indexing status by tenant/app scope.</p>
    </div>
    <Button type="button" icon="pi pi-upload" label="Upload document" @click="openUploadDialog" />
  </section>

  <section class="panel document-panel">
    <div class="panel-title">
      <h2>Uploaded documents</h2>
      <Tag :value="`${documents.length} files`" severity="secondary" />
    </div>

    <DataTable
      v-if="documents.length"
      :value="documents"
      data-key="id"
      :loading="isLoadingDocuments"
      striped-rows
      scrollable
      table-style="min-width: 980px"
    >
      <Column field="filename" header="filename" frozen style="min-width: 240px" />
      <Column header="size" style="width: 110px">
        <template #body="{ data }">{{ formatBytes(data.byte_size) }}</template>
      </Column>
      <Column field="chunk_count" header="chunks" style="width: 90px" />
      <Column field="vector_record_count" header="vectors" style="width: 90px" />
      <Column field="graph_record_count" header="graph records" style="width: 130px" />
      <Column header="indexed at" style="min-width: 180px">
        <template #body="{ data }">{{ formatDate(data.last_indexed_at) }}</template>
      </Column>
      <Column header="status" style="width: 110px">
        <template #body="{ data }">
          <Tag :value="data.status" :severity="statusSeverity(data.status)" />
        </template>
      </Column>
      <Column header="action" style="width: 80px">
        <template #body="{ data }">
          <Button
            type="button"
            icon="pi pi-trash"
            severity="danger"
            text
            rounded
            title="Delete document"
            aria-label="Delete document"
            :loading="deletingDocumentIds.has(data.id)"
            @click="deleteDocument(data)"
          />
        </template>
      </Column>
    </DataTable>

    <div v-else class="empty-state">
      <span class="empty-icon pi pi-file-arrow-up"></span>
      <strong>No uploaded documents</strong>
    </div>
  </section>

  <section class="panel visualization-panel" aria-labelledby="visualization-title">
    <div class="panel-title">
      <h2 id="visualization-title">Visualization</h2>
    </div>

    <nav class="visualization-tabs" aria-label="Document visualization sections">
      <button
        v-for="tab in visualizationTabs"
        :key="tab.value"
        class="visualization-tab-button"
        :class="{ active: activeVisualizationTab === tab.value }"
        type="button"
        @click="activeVisualizationTab = tab.value"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="visualization-body">
      <VectorVisualizationPage v-if="activeVisualizationTab === 'vector'" />
      <GraphVisualizationPage v-else />
    </div>
  </section>

  <Dialog
    v-model:visible="uploadDialogVisible"
    modal
    header="Upload documents"
    class="upload-dialog"
    :style="{ width: 'min(920px, calc(100vw - 32px))' }"
  >
    <form class="ingest-form" @submit.prevent>
      <label class="form-field col-3 col-md-4 col-sm-12">
        <span>tenant_id</span>
        <InputText v-model="form.tenant_id" autocomplete="off" />
      </label>
      <label class="form-field col-3 col-md-4 col-sm-12">
        <span>app_id</span>
        <InputText v-model="form.app_id" autocomplete="off" />
      </label>
      <label class="form-field col-3 col-md-4 col-sm-12">
        <span>collection_id</span>
        <InputText v-model="form.collection_id" autocomplete="off" />
      </label>
      <label class="form-field col-3 col-md-4 col-sm-12">
        <span>chunk_strategy</span>
        <Select
          v-model="form.chunk_strategy"
          :options="chunkStrategyOptions"
          option-label="label"
          option-value="value"
        />
      </label>
      <label class="form-field col-3 col-md-4 col-sm-6">
        <span>max_tokens</span>
        <InputNumber v-model="form.max_tokens" :min="100" show-buttons input-class="full-input" />
      </label>
      <label class="form-field col-3 col-md-4 col-sm-6">
        <span>overlap_tokens</span>
        <InputNumber v-model="form.overlap_tokens" :min="0" :max="1000" show-buttons input-class="full-input" />
      </label>
      <label v-if="form.chunk_strategy === 'parent_child'" class="form-field col-3 col-md-4 col-sm-6">
        <span>parent_max_tokens</span>
        <InputNumber v-model="form.parent_max_tokens" :min="100" show-buttons input-class="full-input" />
      </label>
      <label v-if="form.chunk_strategy === 'semantic'" class="form-field col-3 col-md-4 col-sm-6">
        <span>semantic_similarity_threshold</span>
        <InputNumber
          v-model="form.semantic_similarity_threshold"
          :min="0"
          :max="1"
          :step="0.01"
          :min-fraction-digits="2"
          :max-fraction-digits="2"
          show-buttons
          input-class="full-input"
        />
      </label>
    </form>

    <FileUpload
      name="file"
      mode="advanced"
      custom-upload
      multiple
      :accept="acceptedFileTypes"
      :max-file-size="52428800"
      choose-label="Choose"
      upload-label="Upload"
      cancel-label="Clear"
      :disabled="isUploading"
      @select="onSelect"
      @remove="onRemove"
      @clear="onClear"
      @uploader="uploadSelected"
    >
      <template #empty>
        <div class="drop-empty">
          <i class="pi pi-cloud-upload"></i>
          <span>Drop files here</span>
        </div>
      </template>
    </FileUpload>

    <p v-if="lastError" class="error-text">{{ lastError }}</p>

    <section v-if="uploadRecords.length" class="upload-progress-panel">
      <div class="panel-title">
        <h3>Upload progress</h3>
        <Tag :value="`${uploadRecords.length} files`" severity="secondary" />
      </div>
      <div class="document-list">
        <div v-for="record in uploadRecords" :key="record.id" class="document-row">
          <div class="document-main">
            <strong>{{ record.filename }}</strong>
            <span>{{ formatBytes(record.size) }}</span>
          </div>
          <div class="document-progress">
            <ProgressBar :value="record.progress" :show-value="false" />
            <small v-if="record.document_id">{{ record.document_id }}</small>
            <small v-else-if="record.error">{{ record.error }}</small>
          </div>
          <div class="document-meta">
            <span v-if="record.chunks !== undefined">{{ record.chunks }} chunks</span>
            <span v-if="record.vector_stored_count !== undefined">{{ record.vector_stored_count }} vectors</span>
            <Tag :value="record.status" :severity="statusSeverity(record.status)" />
          </div>
        </div>
      </div>
    </section>

    <template #footer>
      <Button
        type="button"
        label="Close"
        severity="secondary"
        icon="pi pi-times"
        @click="uploadDialogVisible = false"
      />
      <span v-if="!canUpload" class="footer-hint">tenant_id and app_id required</span>
    </template>
  </Dialog>
</template>

<style scoped>
.document-panel {
  max-width: 1100px;
}

.visualization-panel {
  max-width: 1100px;
  margin-top: 24px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title h2 {
  margin: 0;
}

.visualization-tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--border-color);
}

.visualization-tab-button {
  min-height: 38px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted-text);
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}

.visualization-tab-button.active {
  border-bottom-color: var(--primary-color);
  color: var(--primary-color);
}

.visualization-body {
  min-height: 240px;
}

.document-list {
  display: grid;
  gap: 10px;
}

.upload-progress-panel {
  margin-top: 16px;
}

.upload-progress-panel h3 {
  margin: 0;
  font-size: 15px;
}

.document-row {
  display: grid;
  grid-template-columns: minmax(180px, 1.2fr) minmax(180px, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);
}

.document-row:last-child {
  border-bottom: 0;
}

.document-main,
.document-progress,
.document-meta {
  min-width: 0;
}

.document-main {
  display: grid;
  gap: 4px;
}

.document-main strong,
.document-progress small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-main span,
.document-progress small,
.document-meta span,
.footer-hint {
  color: var(--muted-text);
  font-size: 12px;
}

.document-progress {
  display: grid;
  gap: 6px;
}

.document-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  white-space: nowrap;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 180px;
  gap: 8px;
  color: var(--muted-text);
  text-align: center;
}

.empty-icon {
  color: #0f766e;
  font-size: 30px;
}

.ingest-form {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
  margin-bottom: 16px;
}

.form-field {
  min-width: 0;
  grid-column: span 12;
}

.ingest-form label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.ingest-form label span {
  color: var(--muted-text);
  font-size: 12px;
  font-weight: 700;
}

.ingest-form :deep(.p-inputtext),
.ingest-form :deep(.p-select),
.ingest-form :deep(.p-inputnumber) {
  min-width: 0;
  width: 100%;
}

.ingest-form :deep(.full-input) {
  width: 100%;
}

.col-3 {
  grid-column: span 3;
}

.col-12 {
  grid-column: span 12;
}

.drop-empty {
  display: grid;
  place-items: center;
  min-height: 160px;
  gap: 10px;
  color: var(--muted-text);
}

.drop-empty i {
  color: #0f766e;
  font-size: 34px;
}

.error-text {
  margin: 12px 0 0;
  color: var(--danger-color);
  font-weight: 700;
}

.footer-hint {
  margin-right: auto;
}

:deep(.upload-dialog .p-dialog-content) {
  padding-top: 6px;
}

:deep(.p-fileupload) {
  border-radius: var(--border-radius);
}

:deep(.p-fileupload-content) {
  border-color: var(--border-color);
}

@media (max-width: 980px) {
  .document-row {
    grid-template-columns: 1fr;
  }

  .ingest-form {
    grid-template-columns: repeat(8, minmax(0, 1fr));
  }

  .document-meta {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .col-md-4 {
    grid-column: span 4;
  }
}

@media (max-width: 760px) {
  .ingest-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .col-sm-6 {
    grid-column: span 1;
  }

  .col-sm-12 {
    grid-column: span 2;
  }
}
</style>
