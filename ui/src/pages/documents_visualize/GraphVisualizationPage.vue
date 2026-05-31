<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import cytoscape from 'cytoscape'
import type {
  Core,
  EdgeSingular,
  ElementDefinition,
  EventObject,
  LayoutOptions,
  NodeSingular,
} from 'cytoscape'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'

interface GraphNode {
  id: string
  node_type: string
  label: string
  properties: Record<string, unknown>
}

interface GraphEdge {
  id: string
  source: string
  target: string
  relation_type: string
  properties: Record<string, unknown>
}

interface GraphStats {
  node_count: number
  edge_count: number
  nodes_by_type: Record<string, number>
  edges_by_type: Record<string, number>
}

interface GraphResponse {
  tenant_id: string
  app_id: string
  collection_id: string | null
  document_id: string | null
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: GraphStats
}

type SelectedItem =
  | { kind: 'node'; data: GraphNode }
  | { kind: 'edge'; data: GraphEdge }
  | null

type LayoutKey = 'cose' | 'breadthfirst' | 'concentric' | 'grid' | 'circle'

const API_ENDPOINT = '/api/v1/visualize/graph'
const DEFAULT_SCOPE = {
  tenant_id: 'tenant-a',
  app_id: 'app-a',
  collection_id: null as string | null,
}

const NODE_COLORS: Record<string, string> = {
  Document: '#2563eb',
  Element: '#0891b2',
  Chunk: '#0f766e',
  Entity: '#d97706',
}

const EDGE_COLORS: Record<string, string> = {
  HAS_ELEMENT: '#94a3b8',
  HAS_CHUNK: '#64748b',
  DERIVED_FROM: '#0ea5e9',
  NEXT_CHUNK: '#10b981',
  PARENT_CHUNK: '#a855f7',
  MENTIONED_IN: '#f59e0b',
  SEMANTIC_RELATION: '#ef4444',
}

const containerRef = ref<HTMLDivElement | null>(null)
const cy = shallowRef<Core | null>(null)
const graphResult = ref<GraphResponse | null>(null)
const selected = ref<SelectedItem>(null)
const isLoading = ref(false)
const loadError = ref('')

const layoutOptions: { label: string; value: LayoutKey }[] = [
  { label: 'Force (cose)', value: 'cose' },
  { label: 'Breadthfirst', value: 'breadthfirst' },
  { label: 'Concentric', value: 'concentric' },
  { label: 'Circle', value: 'circle' },
  { label: 'Grid', value: 'grid' },
]

const filters = ref({
  document_id: '',
  include_structure: true,
  include_semantic: true,
  limit: 2000,
  layout: 'cose' as LayoutKey,
})

const stats = computed(() => graphResult.value?.stats)
const hasGraph = computed(
  () => Boolean(graphResult.value && (graphResult.value.nodes.length || graphResult.value.edges.length)),
)
const nodeTypeEntries = computed(() =>
  Object.entries(stats.value?.nodes_by_type ?? {}).sort((a, b) => b[1] - a[1]),
)
const edgeTypeEntries = computed(() =>
  Object.entries(stats.value?.edges_by_type ?? {}).sort((a, b) => b[1] - a[1]),
)

onMounted(() => {
  initCytoscape()
  loadGraph()
})

onBeforeUnmount(() => {
  cy.value?.destroy()
  cy.value = null
})

watch(
  () => filters.value.layout,
  (next) => {
    runLayout(next)
  },
)

function initCytoscape() {
  if (!containerRef.value || cy.value) {
    return
  }
  cy.value = cytoscape({
    container: containerRef.value,
    elements: [],
    wheelSensitivity: 0.2,
    minZoom: 0.1,
    maxZoom: 4,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': (node: NodeSingular) =>
            NODE_COLORS[node.data('node_type') as string] ?? '#64748b',
          label: 'data(label)',
          color: '#0f172a',
          'font-size': 11,
          'font-weight': 600,
          'text-valign': 'bottom',
          'text-halign': 'center',
          'text-margin-y': 6,
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.85,
          'text-background-padding': '2px',
          'text-background-shape': 'roundrectangle',
          'text-max-width': '140px',
          'text-wrap': 'ellipsis',
          width: (node: NodeSingular) => nodeSize(node.data('node_type') as string),
          height: (node: NodeSingular) => nodeSize(node.data('node_type') as string),
          'border-width': 1.5,
          'border-color': '#ffffff',
          'overlay-opacity': 0,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-color': '#0f172a',
          'border-width': 3,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1.4,
          'line-color': (edge: EdgeSingular) =>
            EDGE_COLORS[edge.data('relation_type') as string] ?? '#94a3b8',
          'target-arrow-color': (edge: EdgeSingular) =>
            EDGE_COLORS[edge.data('relation_type') as string] ?? '#94a3b8',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'arrow-scale': 0.8,
          label: 'data(relation_type)',
          'font-size': 9,
          color: '#475569',
          'text-rotation': 'autorotate',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.85,
          'text-background-padding': '1px',
          'text-background-shape': 'roundrectangle',
          'text-margin-y': -4,
        },
      },
      {
        selector: 'edge:selected',
        style: {
          width: 3,
          'line-color': '#0f172a',
          'target-arrow-color': '#0f172a',
        },
      },
      {
        selector: '.faded',
        style: {
          opacity: 0.15,
          'text-opacity': 0.1,
        },
      },
    ],
  })

  cy.value.on('tap', 'node', (event: EventObject) => {
    const node = event.target as NodeSingular
    selected.value = {
      kind: 'node',
      data: {
        id: node.id(),
        node_type: node.data('node_type'),
        label: node.data('full_label') ?? node.data('label'),
        properties: node.data('properties') ?? {},
      },
    }
    highlightNeighborhood(node)
  })

  cy.value.on('tap', 'edge', (event: EventObject) => {
    const edge = event.target
    selected.value = {
      kind: 'edge',
      data: {
        id: edge.id(),
        source: edge.data('source'),
        target: edge.data('target'),
        relation_type: edge.data('relation_type'),
        properties: edge.data('properties') ?? {},
      },
    }
    clearHighlight()
  })

  cy.value.on('tap', (event: EventObject) => {
    if (event.target === cy.value) {
      selected.value = null
      clearHighlight()
    }
  })
}

function highlightNeighborhood(node: NodeSingular) {
  if (!cy.value) {
    return
  }
  const neighborhood = node.closedNeighborhood()
  cy.value.elements().addClass('faded')
  neighborhood.removeClass('faded')
}

function clearHighlight() {
  cy.value?.elements().removeClass('faded')
}

function nodeSize(type: string): number {
  switch (type) {
    case 'Document':
      return 46
    case 'Entity':
      return 36
    case 'Chunk':
      return 28
    case 'Element':
      return 22
    default:
      return 24
  }
}

async function loadGraph() {
  isLoading.value = true
  loadError.value = ''
  try {
    const response = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...DEFAULT_SCOPE,
        document_id: filters.value.document_id.trim() || null,
        include_structure: filters.value.include_structure,
        include_semantic: filters.value.include_semantic,
        limit: filters.value.limit,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(errorDetail(payload, response.statusText))
    }
    graphResult.value = payload as GraphResponse
    renderGraph(graphResult.value)
  } catch (error) {
    graphResult.value = null
    clearGraph()
    loadError.value = error instanceof Error ? error.message : 'Graph request failed.'
  } finally {
    isLoading.value = false
  }
}

function renderGraph(payload: GraphResponse) {
  if (!cy.value) {
    return
  }
  const elements: ElementDefinition[] = []
  for (const node of payload.nodes) {
    elements.push({
      data: {
        id: node.id,
        label: truncateLabel(node.label),
        full_label: node.label,
        node_type: node.node_type,
        properties: node.properties,
      },
    })
  }
  for (const edge of payload.edges) {
    elements.push({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        relation_type: edge.relation_type,
        properties: edge.properties,
      },
    })
  }
  cy.value.batch(() => {
    cy.value?.elements().remove()
    cy.value?.add(elements)
  })
  selected.value = null
  clearHighlight()
  runLayout(filters.value.layout)
}

function clearGraph() {
  cy.value?.elements().remove()
  selected.value = null
}

function runLayout(layoutKey: LayoutKey) {
  if (!cy.value || cy.value.elements().length === 0) {
    return
  }
  const layoutConfig: Record<LayoutKey, LayoutOptions> = {
    cose: {
      name: 'cose',
      animate: false,
      idealEdgeLength: () => 90,
      nodeRepulsion: () => 8000,
      edgeElasticity: () => 100,
      gravity: 0.15,
      padding: 30,
    },
    breadthfirst: {
      name: 'breadthfirst',
      animate: false,
      directed: true,
      padding: 30,
      spacingFactor: 1.1,
    },
    concentric: {
      name: 'concentric',
      animate: false,
      padding: 30,
      minNodeSpacing: 30,
      concentric: (node: NodeSingular) =>
        node.data('node_type') === 'Document' ? 3 : node.degree(false),
      levelWidth: () => 1,
    },
    circle: { name: 'circle', animate: false, padding: 30 },
    grid: { name: 'grid', animate: false, padding: 30 },
  }
  cy.value.layout(layoutConfig[layoutKey]).run()
}

function resetView() {
  cy.value?.fit(undefined, 40)
}

function truncateLabel(label: string): string {
  if (!label) {
    return ''
  }
  return label.length > 48 ? `${label.slice(0, 45)}…` : label
}

function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? '#64748b'
}

function edgeColor(type: string): string {
  return EDGE_COLORS[type] ?? '#94a3b8'
}

function compactJson(value: Record<string, unknown> | undefined) {
  return value && Object.keys(value).length ? JSON.stringify(value, null, 2) : '{}'
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
</script>

<template>
  <section class="visualization-page" aria-label="Graph visualization">
    <form class="control-bar" @submit.prevent="loadGraph">
      <label class="control-field control-field--wide">
        <span>document_id (optional)</span>
        <InputText
          v-model="filters.document_id"
          autocomplete="off"
          placeholder="Để trống để lấy toàn bộ tenant/app scope"
        />
      </label>
      <label class="control-field">
        <span>limit</span>
        <InputNumber
          v-model="filters.limit"
          :min="50"
          :max="10000"
          :step="100"
          show-buttons
          input-class="full-input"
        />
      </label>
      <label class="control-field">
        <span>layout</span>
        <Select
          v-model="filters.layout"
          :options="layoutOptions"
          option-label="label"
          option-value="value"
        />
      </label>
      <div class="toggle-group">
        <label class="toggle-field">
          <Checkbox v-model="filters.include_structure" :binary="true" input-id="include-structure" />
          <span>structure</span>
        </label>
        <label class="toggle-field">
          <Checkbox v-model="filters.include_semantic" :binary="true" input-id="include-semantic" />
          <span>semantic</span>
        </label>
      </div>
      <div class="control-actions">
        <Button
          type="submit"
          label="Load"
          icon="pi pi-play"
          :loading="isLoading"
        />
        <Button
          type="button"
          icon="pi pi-arrows-alt"
          severity="secondary"
          text
          rounded
          aria-label="Fit graph"
          :disabled="!hasGraph"
          @click="resetView"
        />
      </div>
    </form>

    <p v-if="loadError" class="error-text">{{ loadError }}</p>

    <div class="legend">
      <div class="legend-group">
        <span class="legend-title">Nodes</span>
        <span
          v-for="[type, count] in nodeTypeEntries"
          :key="`n-${type}`"
          class="legend-chip"
        >
          <i class="legend-swatch" :style="{ background: nodeColor(type) }"></i>
          {{ type }} · {{ count }}
        </span>
      </div>
      <div class="legend-group">
        <span class="legend-title">Edges</span>
        <span
          v-for="[type, count] in edgeTypeEntries"
          :key="`e-${type}`"
          class="legend-chip"
        >
          <i class="legend-swatch legend-swatch--line" :style="{ background: edgeColor(type) }"></i>
          {{ type }} · {{ count }}
        </span>
      </div>
      <div class="legend-totals">
        <Tag :value="`${stats?.node_count ?? 0} nodes`" severity="info" />
        <Tag :value="`${stats?.edge_count ?? 0} edges`" severity="secondary" />
      </div>
    </div>

    <div class="graph-area">
      <div ref="containerRef" class="graph-canvas" role="presentation"></div>

      <aside class="detail-panel" aria-label="Selected element details">
        <template v-if="selected?.kind === 'node'">
          <header class="detail-head">
            <Tag :value="selected.data.node_type" :style="{ background: nodeColor(selected.data.node_type), color: '#fff' }" />
            <strong class="detail-label">{{ selected.data.label }}</strong>
          </header>
          <dl class="detail-list">
            <div>
              <dt>id</dt>
              <dd>{{ selected.data.id }}</dd>
            </div>
          </dl>
          <details class="detail-block" open>
            <summary>properties</summary>
            <pre>{{ compactJson(selected.data.properties) }}</pre>
          </details>
        </template>

        <template v-else-if="selected?.kind === 'edge'">
          <header class="detail-head">
            <Tag
              :value="selected.data.relation_type"
              :style="{ background: edgeColor(selected.data.relation_type), color: '#fff' }"
            />
          </header>
          <dl class="detail-list">
            <div>
              <dt>source</dt>
              <dd>{{ selected.data.source }}</dd>
            </div>
            <div>
              <dt>target</dt>
              <dd>{{ selected.data.target }}</dd>
            </div>
            <div>
              <dt>id</dt>
              <dd>{{ selected.data.id }}</dd>
            </div>
          </dl>
          <details class="detail-block" open>
            <summary>properties</summary>
            <pre>{{ compactJson(selected.data.properties) }}</pre>
          </details>
        </template>

        <template v-else>
          <div class="detail-empty">
            <i class="pi pi-pointer"></i>
            <span>Click node hoặc edge để xem chi tiết</span>
          </div>
        </template>
      </aside>
    </div>

    <div v-if="!hasGraph && !isLoading && !loadError" class="empty-state">
      <strong>No graph data</strong>
      <span>Ingest tài liệu (kèm extract semantic graph nếu cần) rồi bấm Load.</span>
    </div>
  </section>
</template>

<style scoped>
.visualization-page {
  display: grid;
  gap: 16px;
  min-height: 240px;
}

.control-bar {
  display: grid;
  grid-template-columns: minmax(220px, 1.6fr) 130px 170px auto auto;
  gap: 12px;
  align-items: end;
}

.control-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.control-field--wide {
  min-width: 0;
}

.control-field span {
  color: var(--muted-text);
  font-size: 12px;
  font-weight: 700;
}

.control-field :deep(.p-inputtext),
.control-field :deep(.p-select),
.control-field :deep(.p-inputnumber) {
  min-width: 0;
  width: 100%;
}

.control-field :deep(.full-input) {
  width: 100%;
}

.toggle-group {
  display: grid;
  gap: 6px;
  align-content: end;
  padding-bottom: 4px;
}

.toggle-field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.control-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.error-text {
  margin: 0;
  color: var(--danger-color);
  font-weight: 700;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-muted);
}

.legend-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.legend-title {
  color: var(--muted-text);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--surface-color, #ffffff);
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
}

.legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.legend-swatch--line {
  width: 16px;
  height: 3px;
  border-radius: 2px;
}

.legend-totals {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.graph-area {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
  gap: 14px;
  min-height: 520px;
}

.graph-canvas {
  position: relative;
  min-height: 520px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
  overflow: hidden;
}

.detail-panel {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-color, #ffffff);
  min-height: 520px;
}

.detail-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.detail-label {
  overflow-wrap: anywhere;
  font-size: 14px;
}

.detail-list {
  display: grid;
  gap: 6px;
  margin: 0;
}

.detail-list div {
  display: grid;
  gap: 2px;
}

.detail-list dt {
  color: var(--muted-text);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.detail-list dd {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.detail-block summary {
  color: var(--muted-text);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.detail-block pre {
  overflow: auto;
  max-height: 280px;
  margin: 10px 0 0;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-muted);
  color: var(--text-color);
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
}

.detail-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  height: 100%;
  min-height: 200px;
  color: var(--muted-text);
  text-align: center;
}

.detail-empty i {
  font-size: 28px;
}

.empty-state {
  display: grid;
  place-items: center;
  gap: 6px;
  min-height: 100px;
  color: var(--muted-text);
}

@media (max-width: 980px) {
  .control-bar {
    grid-template-columns: 1fr 1fr;
  }

  .control-actions {
    grid-column: span 2;
    justify-content: flex-end;
  }

  .graph-area {
    grid-template-columns: 1fr;
  }

  .detail-panel {
    min-height: 240px;
  }
}

@media (max-width: 640px) {
  .control-bar {
    grid-template-columns: 1fr;
  }

  .control-actions {
    grid-column: auto;
  }
}
</style>
