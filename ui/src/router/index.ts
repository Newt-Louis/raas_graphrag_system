import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/platform',
      name: 'platform-admin',
      component: () => import('@/views/PlatformAdminView.vue'),
    },
    {
      path: '/platform/api-ai-keys/:apiKeyId/test',
      name: 'api-ai-key-test',
      component: () => import('@/views/ApiAiKeyTestView.vue'),
    },
    {
      path: '/admin/documents',
      name: 'customer-documents',
      component: () => import('@/views/DocumentAdminView.vue'),
    },
    {
      path: '/admin/widget',
      name: 'widget-builder',
      component: () => import('@/views/WidgetBuilderView.vue'),
    },
    {
      path: '/embed/chat',
      name: 'embed-chat',
      component: () => import('@/views/EmbedChatView.vue'),
      meta: { embed: true },
    },
    {
      path: '/builder',
      redirect: '/admin/widget',
    },
    {
      path: '/embed/feature1',
      redirect: '/embed/chat',
    },
    {
      path: '/embed/feature2',
      redirect: '/embed/chat',
    },
  ],
})

export default router
