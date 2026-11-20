<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">数据分析实验与数据应用服务平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向指标口径管理、分析实验设计、OLAP查询、数据看板构建与数据API发布的数据应用平台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "指标定义", path: "/metric_def" }, { label: "维度管理", path: "/dimension" }, { label: "数据集管理", path: "/dataset" }, { label: "分析实验", path: "/experiment" }, { label: "OLAP查询", path: "/query_builder" }, { label: "数据看板", path: "/dashboard" }, { label: "图表配置", path: "/chart" }, { label: "数据API发布", path: "/data_service" }, { label: "路段取数", path: "/segment_timing" }, { label: "智能告警", path: "/alert" }, { label: "分析用户组", path: "/user_group" }, { label: "数据快照", path: "/snapshot" }, { label: "任务调度", path: "/scheduler" }, { label: "缓存管理", path: "/cache" }, { label: "分析管道", path: "/pipeline" }, { label: "分析模型", path: "/model" }, { label: "数据集市", path: "/data_mart" }, { label: "数据导出", path: "/export" }, { label: "数据审计", path: "/audit" }]
</script>
