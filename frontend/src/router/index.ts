import { createRouter, createWebHistory } from 'vue-router'

import HomeDashboard from '@/views/Dashboard.vue'
const MetricDef = () => import('@/views/metric_def/index.vue')
const Dimension = () => import('@/views/dimension/index.vue')
const Dataset = () => import('@/views/dataset/index.vue')
const Experiment = () => import('@/views/experiment/index.vue')
const QueryBuilder = () => import('@/views/query_builder/index.vue')
const Dashboard = () => import('@/views/dashboard/index.vue')
const Chart = () => import('@/views/chart/index.vue')
const DataService = () => import('@/views/data_service/index.vue')
const SegmentTiming = () => import('@/views/segment_timing/index.vue')
const Alert = () => import('@/views/alert/index.vue')
const UserGroup = () => import('@/views/user_group/index.vue')
const Snapshot = () => import('@/views/snapshot/index.vue')
const Scheduler = () => import('@/views/scheduler/index.vue')
const Cache = () => import('@/views/cache/index.vue')
const Pipeline = () => import('@/views/pipeline/index.vue')
const Model = () => import('@/views/model/index.vue')
const DataMart = () => import('@/views/data_mart/index.vue')
const Export = () => import('@/views/export/index.vue')
const Audit = () => import('@/views/audit/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeDashboard },
    { path: '/metric_def', name: 'metric_def', component: MetricDef },
    { path: '/dimension', name: 'dimension', component: Dimension },
    { path: '/dataset', name: 'dataset', component: Dataset },
    { path: '/experiment', name: 'experiment', component: Experiment },
    { path: '/query_builder', name: 'query_builder', component: QueryBuilder },
    { path: '/dashboard', name: 'dashboard', component: Dashboard },
    { path: '/chart', name: 'chart', component: Chart },
    { path: '/data_service', name: 'data_service', component: DataService },
    { path: '/segment_timing', name: 'segment_timing', component: SegmentTiming },
    { path: '/alert', name: 'alert', component: Alert },
    { path: '/user_group', name: 'user_group', component: UserGroup },
    { path: '/snapshot', name: 'snapshot', component: Snapshot },
    { path: '/scheduler', name: 'scheduler', component: Scheduler },
    { path: '/cache', name: 'cache', component: Cache },
    { path: '/pipeline', name: 'pipeline', component: Pipeline },
    { path: '/model', name: 'model', component: Model },
    { path: '/data_mart', name: 'data_mart', component: DataMart },
    { path: '/export', name: 'export', component: Export },
    { path: '/audit', name: 'audit', component: Audit },
  ],
})

export default router
