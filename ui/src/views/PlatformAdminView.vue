<template>
  <section class="page-header">
    <div>
      <h1>Platform admin</h1>
      <p>
        Internal controls for tenant onboarding, app lifecycle, API keys, model settings, and
        platform quotas.
      </p>
    </div>
    <button class="button" type="button">Create tenant</button>
  </section>

  <section class="section-grid">
    <article class="panel">
      <h2>Tenant status</h2>
      <ul class="status-list">
        <li class="status-row">
          <span>acme-support</span>
          <span class="badge">active</span>
        </li>
        <li class="status-row">
          <span>northwind-ops</span>
          <span class="badge">trial</span>
        </li>
        <li class="status-row">
          <span>contoso-helpdesk</span>
          <span class="badge">paused</span>
        </li>
      </ul>
    </article>

    <article class="panel">
      <h2>Model providers</h2>
      <p>Configure LLM and embedding defaults per app without leaking provider secrets to clients.</p>
      <span class="metric">3 providers</span>
    </article>

    <article class="panel">
      <h2>Quota window</h2>
      <p>Track chat, ingestion, and indexing usage before enforcing tenant-level limits.</p>
      <span class="metric">74%</span>
    </article>
  </section>
</template>
