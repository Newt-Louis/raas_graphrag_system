<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useThemePreference } from './composables/useThemePreference'

const route = useRoute()
useThemePreference()
const isEmbedRoute = computed(() => route.meta.embed === true)
</script>

<template>
  <RouterView v-if="isEmbedRoute" />

  <div v-else class="app-shell">
    <aside class="side-nav" aria-label="Primary navigation">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">R</span>
        <span>
          <strong>GraphRAG Service</strong>
          <small>Multi-tenant console</small>
        </span>
      </RouterLink>

      <nav class="nav-links">
        <RouterLink to="/">Overview</RouterLink>
        <RouterLink to="/platform">System admin</RouterLink>
        <RouterLink to="/admin/documents">Documents</RouterLink>
        <RouterLink to="/admin/widget">Widget builder</RouterLink>
        <RouterLink to="/embed/chat">Embed chat</RouterLink>
      </nav>
    </aside>

    <main class="main-panel">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  background: var(--surface-muted);
  color: var(--text-color);
}

.side-nav {
  padding: 20px 16px;
  border-right: 1px solid var(--border-color);
  background: var(--bg-color);
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px;
  color: var(--text-color);
  text-decoration: none;
}

.brand-mark {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: var(--border-radius);
  background: var(--primary-color);
  color: #ffffff;
  font-weight: 700;
}

.brand strong,
.brand small {
  display: block;
}

.brand small {
  margin-top: 2px;
  color: var(--secondary-color);
  font-size: 12px;
}

.nav-links {
  display: grid;
  gap: 4px;
  margin-top: 28px;
}

.nav-links a {
  padding: 10px 12px;
  border-radius: var(--border-radius);
  color: var(--secondary-color);
  text-decoration: none;
  font-weight: 600;
}

.nav-links a.router-link-active {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.main-panel {
  min-width: 0;
  padding: 28px;
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .side-nav {
    border-right: 0;
    border-bottom: 1px solid var(--border-color);
  }

  .nav-links {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .main-panel {
    padding: 18px;
  }
}
</style>
