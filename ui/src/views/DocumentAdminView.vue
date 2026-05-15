<template>
  <section class="page-header">
    <div>
      <h1>Document admin</h1>
      <p>
        Customer admins manage document lifecycle for their scoped tenant/app. Pipeline state stays
        visible from upload through GraphRAG indexing.
      </p>
    </div>
    <button class="button" type="button">Upload document</button>
  </section>

  <section class="panel document-panel">
    <div class="status-row">
      <strong>refund-policy.pdf</strong>
      <span class="badge">ready</span>
    </div>
    <div class="status-row">
      <strong>onboarding-handbook.docx</strong>
      <span class="badge">indexing</span>
    </div>
    <div class="status-row">
      <strong>release-notes-q2.md</strong>
      <span class="badge">parsing</span>
    </div>
    <div class="status-row">
      <strong>legacy-faq.csv</strong>
      <span class="badge">failed</span>
    </div>
  </section>
</template>

<style scoped>
.document-panel {
  max-width: 900px;
}
</style>
