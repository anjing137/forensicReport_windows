import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '工作台' }
      },
      {
        path: 'cases',
        name: 'CaseList',
        component: () => import('@/views/CaseList.vue'),
        meta: { title: '案件列表' }
      },
      {
        path: 'cases/create',
        name: 'CaseCreate',
        component: () => import('@/views/CaseCreate.vue'),
        meta: { title: '新建案件' }
      },
      {
        path: 'cases/:id',
        name: 'CaseDetail',
        component: () => import('@/views/CaseDetail.vue'),
        meta: { title: '案件详情' }
      },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
