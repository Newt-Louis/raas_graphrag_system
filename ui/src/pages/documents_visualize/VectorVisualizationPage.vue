<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'

interface GraphElementContext {
  element_id: string
  element_type: string
  text: string
  order_index: number
  metadata: Record<string, unknown>
}

interface GraphChunkContext {
  chunk_id: string
  document_id: string
  text: string
  chunk_index: number
  source_elements: GraphElementContext[]
  previous_chunk_id: string | null
  next_chunk_id: string | null
  parent_chunk_id: string | null
  metadata: Record<string, unknown>
}

interface VectorSearchMatch {
  rank: number
  vector_id: string
  document_id: string
  chunk_id: string
  chunk_text: string
  similarity: number
  distance: number
  metadata: Record<string, unknown>
  graph_context: GraphChunkContext | null
}

interface VectorSearchResponse {
  query: string
  tenant_id: string
  app_id: string
  collection_id: string | null
  vector_table: string
  embedding_profile_id: string | null
  embedding_model: string | null
  top_k: number
  min_similarity: number
  matches: VectorSearchMatch[]
  usage: Record<string, unknown>
}

interface VectorHealthItem {
  document_id: string
  collection_id: string | null
  embedding_profile_id: string | null
  embedding_profile_name: string | null
  embedding_model: string | null
  expected_dimension: number | null
  vector_dimension: number | null
  dimension_status: 'ok' | 'mismatch' | 'unknown' | string
  embedded_chunk_count: number
  graph_chunk_count: number | null
  graph_embeddable_chunk_count: number | null
  missing_embedding_count: number | null
  source_metadata: Record<string, unknown>
  last_indexed_at: string | null
}

interface VectorHealthResponse {
  tenant_id: string
  app_id: string
  collection_id: string | null
  vector_table: string
  checked_at: string
  total_embedded_chunks: number
  documents: VectorHealthItem[]
}

const API_BASE = '/api/v1/visualize/vector'
const DEFAULT_SCOPE = {
  tenant_id: 'tenant-a',
  app_id: 'app-a',
  collection_id: null as string | null,
}

const queryText = ref('')
const searchResult = ref<VectorSearchResponse | null>(null)
const healthResult = ref<VectorHealthResponse | null>(null)
const selectedHealthItem = ref<VectorHealthItem | null>(null)
const isSearching = ref(false)
const isLoadingHealth = ref(false)
const searchError = ref('')
const healthError = ref('')

const canSearch = computed(() => Boolean(queryText.value.trim()))
const matchCount = computed(() => searchResult.value?.matches.length ?? 0)
const healthDocuments = computed(() => healthResult.value?.documents ?? [])

onMounted(() => {
  refreshHealth()
})

async function runVectorSearch() {
  if (!canSearch.value) {
    searchError.value = 'Query is required.'
    return
  }

  isSearching.value = true
  searchError.value = ''

  try {
    const response = await fetch(`${API_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...DEFAULT_SCOPE,
        query: queryText.value.trim(),
        top_k: 5,
        min_similarity: 0.4,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(errorDetail(payload, response.statusText))
    }
    searchResult.value = payload as VectorSearchResponse
  } catch (error) {
    searchError.value = error instanceof Error ? error.message : 'Vector search failed.'
  } finally {
    isSearching.value = false
  }
}

async function refreshHealth() {
  isLoadingHealth.value = true
  healthError.value = ''

  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(DEFAULT_SCOPE),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(errorDetail(payload, response.statusText))
    }
    healthResult.value = payload as VectorHealthResponse
    selectedHealthItem.value = healthResult.value.documents[0] ?? null
  } catch (error) {
    healthError.value = error instanceof Error ? error.message : 'Vector health check failed.'
  } finally {
    isLoadingHealth.value = false
  }
}

function errorDetail(payload: unknown, fallback: string) {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return fallback
}

function formatScore(value: number) {
  if (!Number.isFinite(value)) {
    return '0.000'
  }
  return value.toFixed(3)
}

function formatDate(value: string | null) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function statusSeverity(status: string) {
  if (status === 'ok') {
    return 'success'
  }
  if (status === 'mismatch') {
    return 'danger'
  }
  return 'warn'
}

function missingSeverity(count: number | null) {
  return count ? 'danger' : 'success'
}

function compactJson(value: Record<string, unknown>) {
  return Object.keys(value || {}).length ? JSON.stringify(value, null, 2) : '{}'
}

function metadataValue(metadata: Record<string, unknown>, key: string) {
  const value = metadata?.[key]
  if (value === undefined || value === null || value === '') {
    return ''
  }
  return String(value)
}

function scoreWidth(value: number) {
  return `${Math.max(2, Math.min(100, value * 100))}%`
}
</script>

<template>
  <section class="visualization-page" aria-label="Vector visualization">
    <form class="query-bar" @submit.prevent="runVectorSearch">
      <label class="query-field">
        <span>Test query</span>
        <InputText
          v-model="queryText"
          autocomplete="off"
          placeholder="Nhập câu hỏi để kiểm tra context trong vector index"
        />
      </label>
      <Button
        type="submit"
        label="Search"
        icon="pi pi-search"
        :loading="isSearching"
        :disabled="!canSearch"
      />
      <Button
        type="button"
        icon="pi pi-refresh"
        severity="secondary"
        text
        rounded
        aria-label="Refresh health"
        :loading="isLoadingHealth"
        @click="refreshHealth"
      />
    </form>

    <p v-if="searchError" class="error-text">{{ searchError }}</p>
    <p v-if="healthError" class="error-text">{{ healthError }}</p>

    <section v-if="searchResult" class="result-section" aria-label="Vector search results">
      <div class="section-head">
        <div>
          <h3>Search debugger</h3>
          <div class="meta-line">
            <span>{{ searchResult.vector_table }}</span>
            <span>{{ searchResult.embedding_model || '-' }}</span>
            <span>{{ matchCount }} matches</span>
            <span>min {{ formatScore(searchResult.min_similarity) }}</span>
          </div>
        </div>
        <Tag :value="searchResult.embedding_profile_id || 'runtime profile'" severity="info" />
      </div>

      <div v-if="searchResult.matches.length" class="match-list">
        <article v-for="match in searchResult.matches" :key="match.vector_id" class="match-row">
          <div class="rank-cell">
            <span class="rank">#{{ match.rank }}</span>
            <div class="score-block">
              <span>{{ formatScore(match.similarity) }}</span>
              <div class="score-track">
                <i :style="{ width: scoreWidth(match.similarity) }"></i>
              </div>
            </div>
            <small>distance {{ formatScore(match.distance) }}</small>
          </div>

          <div class="match-main">
            <div class="match-title">
              <strong>{{ match.document_id }}</strong>
              <span>{{ match.chunk_id }}</span>
            </div>
            <p class="chunk-text">{{ match.chunk_text }}</p>

            <div class="source-strip">
              <span v-if="metadataValue(match.metadata, 'filename')">
                {{ metadataValue(match.metadata, 'filename') }}
              </span>
              <span v-if="metadataValue(match.metadata, 'chunk_role')">
                {{ metadataValue(match.metadata, 'chunk_role') }}
              </span>
              <span v-if="metadataValue(match.metadata, 'parent_chunk_id')">
                parent {{ metadataValue(match.metadata, 'parent_chunk_id') }}
              </span>
            </div>

            <details class="detail-block">
              <summary>metadata</summary>
              <pre>{{ compactJson(match.metadata) }}</pre>
            </details>

            <details v-if="match.graph_context" class="detail-block graph-detail" open>
              <summary>graph context</summary>
              <div class="graph-context">
                <div class="graph-links">
                  <Tag
                    v-if="match.graph_context.previous_chunk_id"
                    :value="`prev ${match.graph_context.previous_chunk_id}`"
                    severity="secondary"
                  />
                  <Tag
                    v-if="match.graph_context.next_chunk_id"
                    :value="`next ${match.graph_context.next_chunk_id}`"
                    severity="secondary"
                  />
                  <Tag
                    v-if="match.graph_context.parent_chunk_id"
                    :value="`parent ${match.graph_context.parent_chunk_id}`"
                    severity="secondary"
                  />
                </div>
                <div v-if="match.graph_context.source_elements.length" class="element-list">
                  <div
                    v-for="element in match.graph_context.source_elements"
                    :key="element.element_id"
                    class="element-row"
                  >
                    <Tag :value="element.element_type" severity="info" />
                    <span>{{ element.text }}</span>
                  </div>
                </div>
              </div>
            </details>
          </div>
        </article>
      </div>

      <div v-else class="empty-state">
        <strong>No matches</strong>
      </div>
    </section>

    <section class="result-section" aria-label="Embedding profile health">
      <div class="section-head">
        <div>
          <h3>Embedding profile health</h3>
          <div class="meta-line">
            <span>{{ healthResult?.vector_table || '-' }}</span>
            <span>{{ healthResult ? `${healthResult.total_embedded_chunks} embedded chunks` : '0 embedded chunks' }}</span>
            <span>{{ healthResult ? formatDate(healthResult.checked_at) : '-' }}</span>
          </div>
        </div>
      </div>

      <DataTable
        v-model:selection="selectedHealthItem"
        :value="healthDocuments"
        data-key="document_id"
        selection-mode="single"
        size="small"
        scrollable
        scroll-height="360px"
        class="health-table"
      >
        <Column field="document_id" header="document_id" frozen style="min-width: 220px" />
        <Column header="profile" style="min-width: 220px">
          <template #body="{ data }">
            <div class="profile-cell">
              <strong>{{ data.embedding_profile_name || '-' }}</strong>
              <span>{{ data.embedding_profile_id || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column field="embedding_model" header="model" style="min-width: 220px" />
        <Column header="dimension" style="min-width: 170px">
          <template #body="{ data }">
            <div class="dimension-cell">
              <Tag :value="data.dimension_status" :severity="statusSeverity(data.dimension_status)" />
              <span>{{ data.vector_dimension || '-' }} / {{ data.expected_dimension || '-' }}</span>
            </div>
          </template>
        </Column>
        <Column header="chunks" style="min-width: 180px">
          <template #body="{ data }">
            <span>{{ data.embedded_chunk_count }} / {{ data.graph_embeddable_chunk_count ?? '-' }}</span>
          </template>
        </Column>
        <Column header="missing" style="min-width: 130px">
          <template #body="{ data }">
            <Tag
              :value="String(data.missing_embedding_count ?? 0)"
              :severity="missingSeverity(data.missing_embedding_count)"
            />
          </template>
        </Column>
        <Column header="last_indexed_at" style="min-width: 190px">
          <template #body="{ data }">
            {{ formatDate(data.last_indexed_at) }}
          </template>
        </Column>
      </DataTable>

      <div v-if="selectedHealthItem" class="health-detail">
        <div class="health-metrics">
          <div>
            <span>embedded</span>
            <strong>{{ selectedHealthItem.embedded_chunk_count }}</strong>
          </div>
          <div>
            <span>graph chunks</span>
            <strong>{{ selectedHealthItem.graph_chunk_count ?? '-' }}</strong>
          </div>
          <div>
            <span>embeddable</span>
            <strong>{{ selectedHealthItem.graph_embeddable_chunk_count ?? '-' }}</strong>
          </div>
          <div>
            <span>missing</span>
            <strong>{{ selectedHealthItem.missing_embedding_count ?? 0 }}</strong>
          </div>
        </div>
        <details class="detail-block">
          <summary>source metadata</summary>
          <pre>{{ compactJson(selectedHealthItem.source_metadata) }}</pre>
        </details>
      </div>

      <div v-else-if="!isLoadingHealth" class="empty-state">
        <strong>No vector health rows</strong>
      </div>
    </section>
  </section>
</template>

<style scoped>
.visualization-page {
  display: grid;
  gap: 18px;
  min-height: 240px;
}

.query-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: end;
}

.query-field {
  display: grid;
  min-width: 0;
  gap: 6px;
  margin-right: 12px;
  margin-top: 12px;
}

.query-field span {
  color: var(--muted-text);
  font-size: 12px;
  font-weight: 700;
}

.query-field :deep(.p-inputtext) {
  width: 100%;
}

.error-text {
  margin: 0;
  color: var(--danger-color);
  font-weight: 700;
}

.result-section {
  display: grid;
  gap: 14px;
  border-top: 1px solid var(--border-color);
  padding-top: 18px;
}

.section-head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  justify-content: space-between;
}

.section-head h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--muted-text);
  font-size: 12px;
}

.match-list {
  display: grid;
  gap: 12px;
}

.match-row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 14px;
}

.rank-cell {
  display: grid;
  align-content: start;
  gap: 8px;
}

.rank {
  color: var(--primary-color);
  font-size: 20px;
  font-weight: 800;
}

.score-block {
  display: grid;
  gap: 6px;
  font-weight: 800;
}

.score-track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border-color);
}

.score-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--success-color);
}

.rank-cell small,
.match-title span,
.source-strip,
.profile-cell span,
.dimension-cell span,
.health-metrics span {
  color: var(--muted-text);
  font-size: 12px;
}

.match-main {
  display: grid;
  min-width: 0;
  gap: 10px;
}

.match-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}

.match-title strong,
.match-title span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.chunk-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
}

.source-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-strip span {
  min-height: 24px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  padding: 3px 8px;
}

.detail-block {
  min-width: 0;
}

.detail-block summary {
  color: var(--muted-text);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.detail-block pre {
  overflow: auto;
  max-height: 260px;
  margin: 10px 0 0;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-muted);
  color: var(--text-color);
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
}

.graph-context,
.element-list {
  display: grid;
  gap: 10px;
}

.graph-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.element-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}

.element-row span:last-child {
  overflow-wrap: anywhere;
  line-height: 1.5;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 120px;
  color: var(--muted-text);
}

.profile-cell,
.dimension-cell {
  display: grid;
  gap: 4px;
}

.profile-cell span {
  overflow-wrap: anywhere;
}

.health-table {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  overflow: hidden;
}

.health-detail {
  display: grid;
  gap: 12px;
}

.health-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.health-metrics div {
  display: grid;
  gap: 4px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 12px;
}

.health-metrics strong {
  font-size: 22px;
}

@media (max-width: 980px) {
  .match-row {
    grid-template-columns: 1fr;
  }

  .rank-cell {
    grid-template-columns: auto minmax(160px, 1fr) auto;
    align-items: center;
  }

  .health-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .query-bar,
  .section-head,
  .rank-cell {
    display: grid;
    grid-template-columns: 1fr;
  }

  .health-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
