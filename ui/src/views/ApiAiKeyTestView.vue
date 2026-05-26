<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  failed?: boolean
}

interface TestResponse {
  success: boolean
  profile_id: string
  profile_name: string
  provider_id: string
  provider_code: string
  api_key_id: string
  model_name: string
  response_text: string
  usage: Record<string, unknown>
  error: string
}

const route = useRoute()
const router = useRouter()
const profileId = computed(() => String(route.params.profileId || ''))
const profileName = ref(String(route.query.name || 'Model profile'))
const modelName = ref(String(route.query.model || ''))
const apiKeyId = ref(String(route.query.apiKeyId || ''))
const providerCode = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const errorMessage = ref('')

const form = reactive({
  message: '',
})

async function sendMessage() {
  const text = form.message.trim()
  if (!text || !profileId.value || loading.value) return

  messages.value.push({ role: 'user', content: text })
  form.message = ''
  loading.value = true
  errorMessage.value = ''

  try {
    const response = await fetch(`/api/v1/test-api-ai-key/llm/model-profiles/${profileId.value}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
      }),
    })

    const payload = (await response.json()) as TestResponse | { detail?: string }
    if (!response.ok) {
      const detail = 'detail' in payload && typeof payload.detail === 'string' ? payload.detail : response.statusText
      throw new Error(detail)
    }

    const result = payload as TestResponse
    profileName.value = result.profile_name
    modelName.value = result.model_name
    apiKeyId.value = result.api_key_id
    providerCode.value = result.provider_code
    messages.value.push({
      role: 'assistant',
      content: result.success ? result.response_text : result.error,
      failed: !result.success,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Test request failed.'
    errorMessage.value = message
    messages.value.push({ role: 'assistant', content: message, failed: true })
  } finally {
    loading.value = false
  }
}

function goBack() {
  void router.push('/platform')
}
</script>

<template>
  <section class="test-page">
    <header class="page-header">
      <div>
        <h1>Test model profile</h1>
        <p>{{ profileName }}</p>
      </div>
      <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="goBack" />
    </header>

    <section class="panel test-layout">
      <div class="profile-summary">
        <div>
          <span>model_name</span>
          <strong>{{ modelName || 'Loaded from PostgreSQL on first test' }}</strong>
        </div>
        <div>
          <span>profile_id</span>
          <strong>{{ profileId }}</strong>
        </div>
        <div>
          <span>api_key_id</span>
          <strong>{{ apiKeyId || 'Loaded from profile' }}</strong>
        </div>
        <div>
          <span>provider</span>
          <strong>{{ providerCode || 'Loaded from profile' }}</strong>
        </div>
      </div>

      <div class="chat-window" aria-live="polite">
        <p v-if="!messages.length" class="empty-state">Send a message to verify this profile with LiteLLM.</p>
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="message"
          :class="[message.role, { failed: message.failed }]"
        >
          {{ message.content }}
        </div>
        <div v-if="loading" class="message assistant loading-dots" aria-label="Loading">
          <span />
          <span />
          <span />
        </div>
      </div>

      <form class="chat-input" @submit.prevent="sendMessage">
        <InputText v-model="form.message" placeholder="Type a quick test message" />
        <Button type="submit" label="Send" icon="pi pi-send" :loading="loading" />
      </form>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </section>
  </section>
</template>

<style scoped>
.test-page {
  display: grid;
  gap: 18px;
}

.test-layout {
  max-width: 900px;
  display: grid;
  gap: 14px;
}

.profile-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.profile-summary div {
  min-width: 0;
  display: grid;
  gap: 4px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-muted);
  padding: 10px 12px;
}

.profile-summary span {
  color: var(--muted-text);
  font-size: 12px;
}

.profile-summary strong {
  overflow: hidden;
  color: var(--text-color);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-window {
  min-height: 420px;
  display: grid;
  align-content: end;
  gap: 10px;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--surface-muted);
  padding: 16px;
}

.empty-state {
  align-self: center;
  justify-self: center;
  margin: 0;
  color: var(--muted-text);
}

.message {
  max-width: 78%;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 10px 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.message.user {
  justify-self: end;
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: #ffffff;
}

.message.assistant {
  justify-self: start;
  background: var(--bg-color);
  color: var(--text-color);
}

.message.failed {
  border-color: color-mix(in srgb, var(--danger-color) 40%, var(--border-color));
  color: var(--danger-color);
}

.loading-dots {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--muted-text);
  animation: pulse 900ms infinite ease-in-out;
}

.loading-dots span:nth-child(2) {
  animation-delay: 120ms;
}

.loading-dots span:nth-child(3) {
  animation-delay: 240ms;
}

.chat-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.error-text {
  margin: 0;
  color: var(--danger-color);
  font-weight: 650;
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
  .profile-summary {
    grid-template-columns: 1fr;
  }

  .chat-input {
    grid-template-columns: 1fr;
  }

  .message {
    max-width: 92%;
  }
}
</style>
