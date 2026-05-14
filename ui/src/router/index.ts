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
      path: '/builder',
      name: 'builder',
      component: () => import('@/views/BuilderView.vue'),
    },
    {
      path: '/embed/feature1',
      name: 'embed-feature1',
      component: () => import('@/views/Embed1View.vue'),
      meta: { embed: true },
    },
    {
      path: '/embed/feature2',
      name: 'embed-feature2',
      component: () => import('@/views/Embed2View.vue'),
      meta: { embed: true },
    },
  ],
})

export default router