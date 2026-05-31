<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import { useEmbedConfig } from '@/composables/useEmbedConfig'

interface Citation {
  reference: number
  source: string
  document_id: string
  chunk_id: string
  filename: string | null
  similarity: number | null
  excerpt: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  failed?: boolean
}

interface ChatCompletionResponse {
  answer: string
  strategy: string
  citations: Citation[]
}

const route = useRoute()
useEmbedConfig()

const messages = ref<ChatMessage[]>([])
const prompt = ref('')
const loading = ref(false)
const errorMessage = ref('')
const sidebarOpen = ref(true)
const conversationRef = ref<HTMLElement | null>(null)
const sessionId = ref(createId())

const scope = computed(() => ({
  tenant_id: String(route.query.tenant_id || 'tenant-a'),
  app_id: String(route.query.app_id || 'app-a'),
  collection_id: route.query.collection_id ? String(route.query.collection_id) : null,
}))
const conversationTitle = computed(() => {
  const firstQuestion = messages.value.find((message) => message.role === 'user')
  return firstQuestion?.content || 'New conversation'
})

async function sendMessage() {
  const text = prompt.value.trim()
  if (!text || loading.value) {
    return
  }

  const history = messages.value
    .filter((message) => !message.failed)
    .slice(-12)
    .map(({ role, content }) => ({ role, content }))

  messages.value.push({ id: createId(), role: 'user', content: text })
  prompt.value = ''
  loading.value = true
  errorMessage.value = ''
  await scrollToBottom()

  try {
    const response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...scope.value,
        session_id: sessionId.value,
        message: text,
        history,
        top_k: 5,
        min_similarity: 0.4,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(errorDetail(payload, response.statusText))
    }

    const result = payload as ChatCompletionResponse
    messages.value.push({
      id: createId(),
      role: 'assistant',
      content: result.answer,
      citations: result.citations,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Chat request failed.'
    errorMessage.value = message
    messages.value.push({
      id: createId(),
      role: 'assistant',
      content: message,
      failed: true,
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

function newConversation() {
  messages.value = []
  prompt.value = ''
  errorMessage.value = ''
  sessionId.value = createId()
}

async function scrollToBottom() {
  await nextTick()
  if (conversationRef.value) {
    conversationRef.value.scrollTop = conversationRef.value.scrollHeight
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

function createId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}
</script>

<template>
  <main class="chat-page">
    <aside class="conversation-sidebar" :class="{ hidden: !sidebarOpen }">
      <div class="sidebar-head">
        <Button
          type="button"
          icon="pi pi-plus"
          label="New chat"
          severity="secondary"
          outlined
          class="new-chat-button"
          @click="newConversation"
        />
        <Button
          type="button"
          icon="pi pi-times"
          text
          rounded
          severity="secondary"
          aria-label="Close sidebar"
          class="mobile-close"
          @click="sidebarOpen = false"
        />
      </div>

      <nav class="conversation-list" aria-label="Conversations">
        <button class="conversation-item active" type="button">
          <i class="pi pi-comment" aria-hidden="true"></i>
          <span>{{ conversationTitle }}</span>
        </button>
      </nav>

      <footer class="sidebar-footer">
        <span>{{ scope.tenant_id }}</span>
        <strong>{{ scope.app_id }}</strong>
      </footer>
    </aside>

    <section class="chat-workspace">
      <header class="chat-topbar">
        <Button
          type="button"
          icon="pi pi-bars"
          text
          rounded
          severity="secondary"
          aria-label="Open sidebar"
          @click="sidebarOpen = !sidebarOpen"
        />
        <strong>GraphRAG Assistant</strong>
        <span class="scope-label">{{ scope.collection_id || 'All documents' }}</span>
      </header>

      <div ref="conversationRef" class="conversation-stream" aria-live="polite">
        <section v-if="!messages.length" class="empty-conversation">
          <span class="assistant-mark">R</span>
          <h1>How can I help?</h1>
        </section>

        <article
          v-for="message in messages"
          :key="message.id"
          class="message-row"
          :class="message.role"
        >
          <div v-if="message.role === 'assistant'" class="message-avatar">R</div>
          <div class="message-content" :class="{ failed: message.failed }">
            <p>{{ message.content }}</p>
            <details v-if="message.citations?.length" class="citations">
              <summary>{{ message.citations.length }} sources</summary>
              <ol>
                <li v-for="citation in message.citations" :key="`${message.id}-${citation.reference}`">
                  <strong>[{{ citation.reference }}] {{ citation.filename || citation.document_id }}</strong>
                  <span v-if="citation.similarity !== null">
                    similarity {{ citation.similarity.toFixed(3) }}
                  </span>
                  <p>{{ citation.excerpt }}</p>
                </li>
              </ol>
            </details>
          </div>
        </article>

        <article v-if="loading" class="message-row assistant">
          <div class="message-avatar">R</div>
          <div class="loading-dots" aria-label="Loading">
            <span />
            <span />
            <span />
          </div>
        </article>
      </div>

      <footer class="composer-area">
        <form class="composer" @submit.prevent="sendMessage">
          <Textarea
            v-model="prompt"
            auto-resize
            rows="1"
            placeholder="Message GraphRAG Assistant"
            aria-label="Message"
            @keydown="handleComposerKeydown"
          />
          <Button
            type="submit"
            icon="pi pi-arrow-up"
            rounded
            aria-label="Send message"
            :disabled="!prompt.trim() || loading"
            :loading="loading"
          />
        </form>
        <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.chat-page {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  background: var(--bg-color);
  color: var(--text-color);
}

.conversation-sidebar {
  min-width: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 14px;
  border-right: 1px solid var(--border-color);
  background: var(--surface-muted);
  padding: 12px;
  transition:
    width 180ms ease,
    padding 180ms ease,
    transform 180ms ease;
}

.conversation-sidebar.hidden {
  width: 0;
  padding-right: 0;
  padding-left: 0;
  overflow: hidden;
}

.sidebar-head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.new-chat-button {
  flex: 1 1 auto;
  justify-content: start;
}

.mobile-close {
  display: none;
}

.conversation-list {
  min-width: 0;
}

.conversation-item {
  width: 100%;
  min-height: 40px;
  display: flex;
  gap: 9px;
  align-items: center;
  border: 0;
  border-radius: var(--border-radius);
  background: transparent;
  color: var(--text-color);
  padding: 9px 10px;
  text-align: left;
  cursor: pointer;
}

.conversation-item.active,
.conversation-item:hover {
  background: color-mix(in srgb, var(--primary-color) 10%, var(--bg-color));
}

.conversation-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-footer {
  display: grid;
  gap: 3px;
  overflow: hidden;
  border-top: 1px solid var(--border-color);
  padding: 12px 8px 0;
}

.sidebar-footer span,
.scope-label {
  overflow: hidden;
  color: var(--muted-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-workspace {
  min-width: 0;
  height: 100dvh;
  display: grid;
  grid-template-rows: 56px minmax(0, 1fr) auto;
  background: var(--bg-color);
}

.chat-topbar {
  display: flex;
  gap: 10px;
  align-items: center;
  border-bottom: 1px solid var(--border-color);
  padding: 0 16px;
}

.scope-label {
  margin-left: auto;
}

.conversation-stream {
  overflow: auto;
  padding: 22px 16px 16px;
}

.empty-conversation {
  min-height: 100%;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 14px;
  padding-bottom: 90px;
}

.empty-conversation h1 {
  margin: 0;
  font-size: 28px;
  letter-spacing: 0;
}

.assistant-mark,
.message-avatar {
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--primary-color);
  color: #ffffff;
  font-weight: 700;
}

.assistant-mark {
  width: 50px;
  height: 50px;
  font-size: 20px;
}

.message-row {
  width: min(820px, 100%);
  display: grid;
  gap: 12px;
  margin: 0 auto 22px;
}

.message-row.assistant {
  grid-template-columns: 30px minmax(0, 1fr);
}

.message-row.user {
  justify-items: end;
}

.message-avatar {
  width: 30px;
  height: 30px;
  font-size: 12px;
}

.message-content {
  min-width: 0;
  line-height: 1.65;
}

.message-content p {
  margin: 0;
  white-space: pre-wrap;
}

.message-row.user .message-content {
  max-width: min(680px, 86%);
  border-radius: 18px;
  background: var(--surface-muted);
  padding: 10px 15px;
}

.message-content.failed,
.error-text {
  color: var(--danger-color);
}

.citations {
  margin-top: 14px;
  color: var(--muted-text);
  font-size: 13px;
}

.citations summary {
  cursor: pointer;
  font-weight: 700;
}

.citations ol {
  display: grid;
  gap: 10px;
  margin: 10px 0 0;
  padding-left: 20px;
}

.citations li span {
  display: block;
  margin-top: 2px;
}

.citations p {
  margin-top: 4px;
  color: var(--text-color);
  line-height: 1.45;
}

.loading-dots {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  min-height: 30px;
}

.loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted-text);
  animation: pulse 900ms infinite ease-in-out;
}

.loading-dots span:nth-child(2) {
  animation-delay: 120ms;
}

.loading-dots span:nth-child(3) {
  animation-delay: 240ms;
}

.composer-area {
  padding: 12px 16px 18px;
}

.composer {
  width: min(820px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  margin: 0 auto;
  border: 1px solid var(--border-color);
  border-radius: 20px;
  background: var(--bg-color);
  padding: 8px 9px 8px 14px;
  box-shadow: 0 8px 22px rgb(15 23 42 / 8%);
}

.composer textarea {
  max-height: 180px;
  resize: none;
  border: 0;
  box-shadow: none;
  padding: 7px 0;
}

.composer textarea:focus {
  box-shadow: none;
}

.error-text {
  width: min(820px, 100%);
  margin: 8px auto 0;
  font-size: 13px;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  50% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

@media (max-width: 760px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .conversation-sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 5;
    width: min(290px, 86vw);
    box-shadow: 12px 0 28px rgb(15 23 42 / 16%);
  }

  .conversation-sidebar.hidden {
    width: min(290px, 86vw);
    padding: 12px;
    transform: translateX(-100%);
  }

  .mobile-close {
    display: inline-flex;
  }

  .conversation-stream {
    padding-right: 12px;
    padding-left: 12px;
  }

  .composer-area {
    padding-right: 10px;
    padding-left: 10px;
  }

  .message-row.user .message-content {
    max-width: 92%;
  }
}
</style>
