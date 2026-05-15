<script setup lang="ts">
import { useEmbedConfig } from '@/composables/useEmbedConfig'

useEmbedConfig()
</script>

<template>
  <main class="embed-shell" aria-label="Embedded chat preview">
    <section class="chat-frame">
      <header class="chat-header">
        <div>
          <strong>Support assistant</strong>
          <span>Scoped to acme-support / help-center</span>
        </div>
      </header>

      <div class="chat-body">
        <p class="message assistant">Ask a question about the indexed documents for this app.</p>
        <p class="message user">What is the refund window?</p>
        <p class="message assistant">
          The current policy allows refunds within 30 days when the order has an eligible status.
        </p>
      </div>

      <form class="chat-input">
        <input aria-label="Message" placeholder="Ask about this app's documents" />
        <button class="button" type="button">Send</button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.embed-shell {
  min-height: 100vh;
  display: grid;
  place-items: end;
  padding: 18px;
  background: transparent;
  color: var(--text-color);
}

.chat-frame {
  width: min(420px, 100%);
  height: min(680px, calc(100vh - 36px));
  display: grid;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-color);
  box-shadow: 0 16px 40px rgb(15 23 42 / 18%);
}

.chat-header {
  padding: 16px;
  background: var(--primary-color);
  color: #ffffff;
}

.chat-header strong,
.chat-header span {
  display: block;
}

.chat-header span {
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.9;
}

.chat-body {
  display: grid;
  align-content: end;
  gap: 10px;
  padding: 16px;
  overflow: auto;
  background: var(--surface-muted);
}

.message {
  max-width: 82%;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--border-radius);
  line-height: 1.45;
}

.message.assistant {
  background: var(--bg-color);
  border: 1px solid var(--border-color);
}

.message.user {
  justify-self: end;
  background: var(--primary-color);
  color: #ffffff;
}

.chat-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--border-color);
}

.chat-input input {
  min-width: 0;
  min-height: 38px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 0 12px;
}
</style>
