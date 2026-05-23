<script setup lang="ts">
import { ref } from 'vue'
import SelectButton from 'primevue/selectbutton'

import { type ThemeMode, useThemePreference } from '@/composables/useThemePreference'
import ModelProfilesPage from '@/pages/admin_system/ModelProfilesPage.vue'
import ProvidersPage from '@/pages/admin_system/ProvidersPage.vue'

type PlatformTab = 'model-profiles' | 'providers'

const tabs: { label: string; value: PlatformTab }[] = [
  { label: 'Model Profiles', value: 'model-profiles' },
  { label: 'Providers', value: 'providers' },
]

const themeOptions: { label: string; value: ThemeMode; icon: string }[] = [
  { label: 'Light', value: 'light', icon: 'pi pi-sun' },
  { label: 'Dark', value: 'dark', icon: 'pi pi-moon' },
  { label: 'System', value: 'system', icon: 'pi pi-desktop' },
]

const { themeMode, setThemeMode } = useThemePreference()
const activeTab = ref<PlatformTab>('model-profiles')

function setTheme(value: ThemeMode) {
  setThemeMode(value)
}
</script>

<template>
  <section class="platform-dashboard">
    <header class="dashboard-header">
      <div>
        <span class="eyebrow">System Admin</span>
        <h1>AI model rotation profiles</h1>
        <p>Quản lý thông tin model profile dùng cho lõi xoay vòng LLM của hệ thống.</p>
      </div>

      <SelectButton
        :model-value="themeMode"
        :options="themeOptions"
        option-label="label"
        option-value="value"
        aria-label="Theme mode"
        @update:model-value="setTheme($event as ThemeMode)"
      >
        <template #option="{ option }">
          <span class="theme-option">
            <i :class="option.icon" />
            <span>{{ option.label }}</span>
          </span>
        </template>
      </SelectButton>
    </header>

    <nav class="tab-nav" aria-label="Platform admin sections">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        class="tab-button"
        :class="{ active: activeTab === tab.value }"
        type="button"
        @click="activeTab = tab.value"
      >
        {{ tab.label }}
      </button>
    </nav>

    <ModelProfilesPage v-if="activeTab === 'model-profiles'" />
    <ProvidersPage v-else />
  </section>
</template>

<style scoped>
.platform-dashboard {
  display: grid;
  gap: 18px;
}

.dashboard-header {
  display: flex;
  gap: 18px;
  align-items: flex-start;
  justify-content: space-between;
}

.eyebrow {
  display: block;
  color: var(--muted-text);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.dashboard-header h1 {
  margin: 4px 0 8px;
  color: var(--text-color);
  font-size: 28px;
  line-height: 1.15;
}

.dashboard-header p {
  max-width: 780px;
  margin: 0;
  color: var(--muted-text);
  line-height: 1.55;
}

.theme-option {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.tab-nav {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--border-color);
}

.tab-button {
  min-height: 38px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted-text);
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}

.tab-button.active {
  border-bottom-color: var(--primary-color);
  color: var(--primary-color);
}

@media (max-width: 760px) {
  .dashboard-header {
    display: grid;
  }
}
</style>
