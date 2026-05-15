<template>
  <section class="page-header">
    <div>
      <h1>GraphRAG-as-a-Service console</h1>
      <p>
        Manage tenant apps, document ingestion, widget configuration, and embedded chat surfaces
        from separate operational areas.
      </p>
    </div>
    <RouterLink class="button" to="/admin/documents">Open documents</RouterLink>
  </section>

  <section class="section-grid">
    <article class="panel">
      <h2>Platform admin</h2>
      <p>Operate tenants, apps, API keys, model providers, quotas, and app status.</p>
      <span class="metric">12 tenants</span>
    </article>

    <article class="panel">
      <h2>Customer admin</h2>
      <p>Upload, re-index, archive, and monitor documents within the current app scope.</p>
      <span class="metric">384 docs</span>
    </article>

    <article class="panel">
      <h2>Embeddable chat</h2>
      <p>Preview the user-facing chat widget with scoped tenant and app configuration.</p>
      <span class="metric">98.4% ready</span>
    </article>
  </section>
</template>
