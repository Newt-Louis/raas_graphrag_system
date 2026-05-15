<script setup lang="ts">
const colors = ['#2563eb', '#059669', '#7c3aed', '#dc2626']
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Widget builder</h1>
      <p>
        Configure the embeddable chat surface for the current tenant/app, including placement,
        theme, popup behavior, and launch style.
      </p>
    </div>
    <RouterLink class="button" to="/embed/chat">Preview chat</RouterLink>
  </section>

  <section class="builder-layout">
    <form class="panel settings-panel">
      <h2>Appearance</h2>
      <label>
        Position
        <select>
          <option>Bottom right</option>
          <option>Bottom left</option>
          <option>Inline frame</option>
        </select>
      </label>
      <label>
        Frame size
        <select>
          <option>Compact</option>
          <option>Standard</option>
          <option>Large</option>
        </select>
      </label>
      <fieldset>
        <legend>Accent color</legend>
        <button
          v-for="color in colors"
          :key="color"
          class="swatch"
          type="button"
          :style="{ backgroundColor: color }"
          :aria-label="`Use ${color}`"
        />
      </fieldset>
    </form>

    <aside class="panel preview-panel">
      <h2>Current app</h2>
      <p>tenant_id: acme-support</p>
      <p>app_id: help-center</p>
      <p>allowed_origin: https://support.example.com</p>
    </aside>
  </section>
</template>

<style scoped>
.builder-layout {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(0, 1fr);
  gap: 16px;
}

.settings-panel {
  display: grid;
  gap: 16px;
}

label,
fieldset {
  display: grid;
  gap: 8px;
  margin: 0;
  border: 0;
  padding: 0;
  color: var(--muted-text);
  font-weight: 700;
}

select {
  min-height: 38px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-color);
  color: var(--text-color);
  padding: 0 10px;
}

legend {
  padding: 0;
}

.swatch {
  display: inline-block;
  width: 34px;
  height: 34px;
  margin-right: 8px;
  border: 2px solid #ffffff;
  border-radius: 999px;
  box-shadow: 0 0 0 1px var(--border-color);
  cursor: pointer;
}

.preview-panel p + p {
  margin-top: 8px;
}

@media (max-width: 900px) {
  .builder-layout {
    grid-template-columns: 1fr;
  }
}
</style>
