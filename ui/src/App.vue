<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useThemePreference } from './composables/useThemePreference'

const route = useRoute()
useThemePreference()
const isEmbedRoute = computed(() => route.meta.embed === true)
const SIDEBAR_KEY = 'raas-platform-sidebar-collapsed'
const isSidebarCollapsed = ref(
  typeof window !== 'undefined' && window.localStorage.getItem(SIDEBAR_KEY) === 'true',
)
const navItems = [
  { to: '/', label: 'Overview', icon: 'pi pi-home' },
  { to: '/platform', label: 'System admin', icon: 'pi pi-server' },
  { to: '/admin/documents', label: 'Documents', icon: 'pi pi-folder-open' },
  { to: '/admin/widget', label: 'Widget builder', icon: 'pi pi-objects-column' },
  { to: '/embed/chat', label: 'Embed chat', icon: 'pi pi-comments' },
]

watch(isSidebarCollapsed, (value) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(SIDEBAR_KEY, String(value))
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': isSidebarCollapsed }">
    <aside class="side-nav" aria-label="Primary navigation">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">R</span>
        <span class="brand-copy">
          <strong>GraphRAG Service</strong>
          <small>Multi-tenant console</small>
        </span>
      </RouterLink>

      <button
        class="sidebar-toggle"
        type="button"
        :aria-label="isSidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'"
        @click="isSidebarCollapsed = !isSidebarCollapsed"
      >
        <span>{{ isSidebarCollapsed ? '>' : '<' }}</span>
      </button>

      <nav class="nav-links">
        <RouterLink v-for="item in navItems" :key="item.to" class="nav-link" :to="item.to">
          <i class="nav-icon" :class="item.icon" aria-hidden="true"></i>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-tooltip">{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <main class="main-panel" :class="{ 'main-panel-full-bleed': isEmbedRoute }">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  --sidebar-width: 260px;
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  background: var(--surface-muted);
  color: var(--text-color);
  transition: grid-template-columns 180ms ease;
}

.app-shell.sidebar-collapsed {
  --sidebar-width: 74px;
}

.side-nav {
  position: relative;
  min-width: 0;
  padding: 20px 16px;
  border-right: 1px solid var(--border-color);
  background: var(--bg-color);
  transition:
    padding 180ms ease,
    width 180ms ease;
}

.sidebar-collapsed .side-nav {
  padding-right: 12px;
  padding-left: 12px;
}

.brand {
  min-height: 52px;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px;
  color: var(--text-color);
  text-decoration: none;
}

.brand-mark {
  flex: 0 0 auto;
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: var(--border-radius);
  background: var(--primary-color);
  color: #ffffff;
  font-weight: 700;
}

.brand-copy {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  transition:
    opacity 160ms ease,
    transform 180ms ease,
    width 180ms ease;
}

.sidebar-collapsed .brand-copy {
  width: 0;
  opacity: 0;
  transform: translateX(-8px);
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

.sidebar-toggle {
  position: absolute;
  top: 68px;
  right: -13px;
  z-index: 3;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--bg-color);
  color: var(--text-color);
  cursor: pointer;
  box-shadow: 0 6px 16px #0f172a18;
}

.sidebar-toggle span {
  display: block;
  line-height: 1;
}

.nav-links {
  display: grid;
  gap: 4px;
  margin-top: 28px;
}

.nav-link {
  position: relative;
  min-height: 42px;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--border-radius);
  color: var(--secondary-color);
  text-decoration: none;
  font-weight: 600;
  transition:
    background 160ms ease,
    color 160ms ease,
    padding 180ms ease;
}

.nav-link.router-link-active {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.nav-icon {
  flex: 0 0 24px;
  color: currentColor;
  font-size: 16px;
  text-align: center;
}

.nav-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition:
    opacity 140ms ease,
    transform 180ms ease,
    width 180ms ease;
}

.nav-tooltip {
  pointer-events: none;
  position: absolute;
  top: 50%;
  left: calc(100% + 10px);
  z-index: 20;
  padding: 7px 9px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--text-color);
  color: var(--bg-color);
  font-size: 12px;
  white-space: nowrap;
  opacity: 0;
  transform: translate(-6px, -50%);
  transition:
    opacity 140ms ease,
    transform 160ms ease;
}

.sidebar-collapsed .nav-link {
  justify-content: center;
  padding-right: 8px;
  padding-left: 8px;
}

.sidebar-collapsed .nav-label {
  width: 0;
  opacity: 0;
  transform: translateX(-8px);
}

.sidebar-collapsed .nav-link:hover .nav-tooltip,
.sidebar-collapsed .nav-link:focus-visible .nav-tooltip {
  opacity: 1;
  transform: translate(0, -50%);
}

.main-panel {
  min-width: 0;
  padding: 28px;
  transition: padding 180ms ease;
}

.main-panel-full-bleed {
  padding: 0;
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

  .main-panel-full-bleed {
    padding: 0;
  }
}
</style>
