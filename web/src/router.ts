import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/datasources' },
    {
      path: '/datasources',
      name: 'datasources',
      component: () => import('@/views/DatasourcesView.vue'),
    },
    {
      path: '/datasources/:id',
      name: 'datasource-detail',
      component: () => import('@/views/DatasourceDetailView.vue'),
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: () => import('@/views/AnalysisView.vue'),
    },
    {
      path: '/models',
      name: 'models',
      component: () => import('@/views/ModelsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
  ],
})

export default router
