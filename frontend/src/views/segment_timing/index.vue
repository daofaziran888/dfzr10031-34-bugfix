<template>
  <section class="page" data-module="segment_timing">
    <header class="page-head">
      <div>
        <h2>路段取数与运输时长分位数</h2>
        <p class="page-desc">
          读取上报的行驶时长、上下车事件与路段运营时段，归并各路段有效计时记录与未完成样本；
          缺抵达不补零，重复回报按班次+通过序号去重，中断补报后自动重算并核对同期可比性。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="recompute">重新计算快照</button>
        <button class="btn primary" type="button" @click="openBackfill">补报抵达事件</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <p v-if="message" class="page-foot" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</p>

    <!-- 线路发布决策（方案 A / B） -->
    <template v-if="activeTab === 'coverage'">
      <h3 class="block-title">线路发布决策（{{ coveragePayload?.运行编号 }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>线路编号</th><th>线路名称</th><th>发布状态</th><th>采用方式</th>
            <th>可发布路段</th><th>空态路段及原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in lineDecisions" :key="d.线路编号">
            <td>{{ d.线路编号 }}</td>
            <td>{{ d.线路名称 }}</td>
            <td><span class="badge" :class="decisionClass(d.线路发布状态)">{{ d.线路发布状态 }}</span></td>
            <td>{{ d.采用方案 }}</td>
            <td>
              <span v-if="d.可发布路段.length">{{ d.可发布路段.join('、') }}</span>
              <span v-else class="muted">无</span>
            </td>
            <td>
              <div v-for="e in d.空态路段" :key="e.路段" class="empty-reason">
                <strong>{{ e.路段 }}</strong>（{{ e.状态 }}）：{{ e.原因 }}
              </div>
              <span v-if="!d.空态路段.length" class="muted">无</span>
            </td>
          </tr>
        </tbody>
      </table>

      <h3 class="block-title">路段计时覆盖结果（分位数 / 可比区间 / 空态）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>路段</th><th>线路</th><th>方向</th><th>覆盖状态</th>
            <th>有效样本</th><th>未完成</th><th>超时抵达</th>
            <th>P50（分钟）</th><th>P90（分钟）</th><th>可比区间 P25–P75</th>
            <th>样本分布</th><th>空态原因 / 未完成样本</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in coverageRows" :key="`${row.路段编号}-${row.方向}`">
            <td>{{ row.路段编号 }}</td>
            <td>{{ row.线路编号 }}</td>
            <td>{{ row.方向 }}</td>
            <td><span class="badge" :class="statusClass(row.覆盖状态)">{{ row.覆盖状态 }}</span></td>
            <td>{{ row.有效样本数 }} / {{ row.样本门槛 }}</td>
            <td>{{ row.未完成样本数 }}</td>
            <td>{{ row.超时抵达样本数 }}</td>
            <td>{{ row.P50 ?? '—' }}</td>
            <td>{{ row.P90 ?? '—' }}</td>
            <td>{{ row.可比区间 ? `${row.可比区间[0]} ~ ${row.可比区间[1]}` : '—' }}</td>
            <td>{{ row.样本分布.length ? row.样本分布.join(', ') : '—' }}</td>
            <td class="reason-cell">
              <span v-if="row.空态原因" class="empty-reason">{{ row.空态原因 }}</span>
              <div v-for="s in row.未完成样本" :key="`${s.车辆班次}-${s.通过序号}`" class="incomplete-line">
                缺抵达：{{ s.车辆班次 }}#{{ s.通过序号 }}（上车 {{ fmt(s.上车时间) }}）
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="page-foot">口径：任何缺抵达样本均不进入分位数，且不以 0 分钟占位；策略：{{ coveragePayload?.发布策略 }}</p>
    </template>

    <!-- 计时样本 -->
    <template v-if="activeTab === 'samples'">
      <table class="data-table">
        <thead>
          <tr>
            <th>样本编号</th><th>路段</th><th>方向</th><th>车辆班次</th><th>通过序号</th>
            <th>上车时间</th><th>抵达时间</th><th>行驶时长（分钟）</th>
            <th>样本状态</th><th>重复抵达</th><th>未完成原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in samples" :key="s.样本编号">
            <td>{{ s.样本编号 }}</td><td>{{ s.路段编号 }}</td><td>{{ s.方向 }}</td>
            <td>{{ s.车辆班次 }}</td><td>{{ s.通过序号 }}</td>
            <td>{{ fmt(s.上车时间) }}</td><td>{{ fmt(s.抵达时间) }}</td>
            <td>
              <span v-if="s.行驶时长分钟 === null" class="muted">空（禁止补零）</span>
              <span v-else>{{ s.行驶时长分钟 }}</span>
            </td>
            <td><span class="badge" :class="s.是否有效样本 ? 'ok' : 'warn'">{{ s.是否有效样本 ? '有效' : '未完成' }}</span></td>
            <td>{{ s.重复抵达事件数 || '—' }}</td>
            <td>{{ s.未完成原因 || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 行驶时长上报 -->
    <template v-if="activeTab === 'reports'">
      <table class="data-table">
        <thead>
          <tr>
            <th>上报编号</th><th>路段</th><th>方向</th><th>车辆班次</th><th>通过序号</th>
            <th>上车时间</th><th>抵达时间</th><th>行驶时长（分钟）</th><th>备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reports" :key="String(r.上报编号)">
            <td>{{ r.上报编号 }}</td><td>{{ r.路段编号 }}</td><td>{{ r.方向 }}</td>
            <td>{{ r.车辆班次 }}</td><td>{{ r.通过序号 }}</td>
            <td>{{ fmt(r.上车时间) }}</td><td>{{ fmt(r.抵达时间) }}</td>
            <td>
              <span v-if="r.行驶时长分钟 === null" class="muted">null（抵达缺失）</span>
              <span v-else>{{ r.行驶时长分钟 }}</span>
            </td>
            <td>{{ r.备注 || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 上下车事件 -->
    <template v-if="activeTab === 'events'">
      <table class="data-table">
        <thead>
          <tr>
            <th>事件编号</th><th>路段</th><th>方向</th><th>车辆班次</th><th>通过序号</th>
            <th>事件类型</th><th>事件时间</th><th>采集来源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in events" :key="String(e.事件编号)">
            <td>{{ e.事件编号 }}</td><td>{{ e.路段编号 }}</td><td>{{ e.方向 }}</td>
            <td>{{ e.车辆班次 }}</td><td>{{ e.通过序号 }}</td>
            <td>
              <span class="badge" :class="e.事件类型 === '抵达' ? 'ok' : 'info'">{{ e.事件类型 }}</span>
            </td>
            <td>{{ fmt(e.事件时间) || '缺失（可查原上车记录）' }}</td>
            <td>{{ e.采集来源 }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 路段与运营时段 -->
    <template v-if="activeTab === 'segments'">
      <table class="data-table">
        <thead>
          <tr>
            <th>路段编号</th><th>线路</th><th>起讫点</th><th>方向</th>
            <th>运营时段</th><th>路段状态</th><th>中断窗口</th><th>样本门槛</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in segments" :key="String(g.路段编号)">
            <td>{{ g.路段编号 }}</td>
            <td>{{ g.线路编号 }} {{ g.线路名称 }}</td>
            <td>{{ g.起点 }} → {{ g.终点 }}</td>
            <td>{{ g.方向 }}</td>
            <td>{{ g.运营开始 }}–{{ g.运营结束 }}</td>
            <td><span class="badge" :class="statusClass(g.路段状态)">{{ g.路段状态 }}</span></td>
            <td>{{ g.中断开始 ? `${g.中断开始} ~ ${g.中断结束}` : '—' }}</td>
            <td>{{ g.样本门槛 }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 计算快照与同期核对 -->
    <template v-if="activeTab === 'runs'">
      <table class="data-table">
        <thead>
          <tr>
            <th>运行编号</th><th>标签</th><th>创建时间</th><th>可发布行</th><th>空态行</th>
            <th>有效样本</th><th>未完成样本</th><th>同期比较核对</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runs" :key="run.运行编号">
            <td>{{ run.运行编号 }}</td><td>{{ run.运行标签 }}</td><td>{{ run.创建时间 }}</td>
            <td>{{ run.汇总.可发布行数量 }}</td><td>{{ run.汇总.空态行数量 }}</td>
            <td>{{ run.汇总.有效样本总数 }}</td><td>{{ run.汇总.未完成样本总数 }}</td>
            <td>
              <button v-if="run.同期比较核对" class="link" type="button" @click="compareRun = run">
                查看核对（基线 {{ run.基线运行编号 }}）
              </button>
              <span v-else class="muted">基线快照</span>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 补报弹窗 -->
    <Teleport to="body">
      <div v-if="showBackfill" class="modal-overlay" @click.self="showBackfill = false">
        <div class="modal-card">
          <header class="modal-head">
            <h3>中断恢复 · 补报抵达事件</h3>
            <button class="btn ghost" type="button" @click="showBackfill = false">&times;</button>
          </header>
          <form class="modal-body" @submit.prevent="submitBackfill">
            <label class="modal-field">
              <span>路段</span>
              <select v-model="backfill.segment" required @change="onSegmentChange">
                <option value="" disabled>请选择路段</option>
                <option v-for="g in segments" :key="String(g.路段编号)" :value="String(g.路段编号)">
                  {{ g.路段编号 }}（{{ g.路段状态 }}）
                </option>
              </select>
            </label>
            <label class="modal-field">
              <span>缺抵达的车辆班次 / 通过序号</span>
              <select v-model="backfill.tripKey" required>
                <option value="" disabled>请选择班次</option>
                <option v-for="s in backfillableSamples" :key="s.样本编号"
                        :value="`${s.车辆班次}::${s.通过序号}::${s.方向}`">
                  {{ s.车辆班次 }} #{{ s.通过序号 }}（{{ s.方向 }}，上车 {{ fmt(s.上车时间) }}）
                </option>
              </select>
            </label>
            <label class="modal-field">
              <span>补报抵达时间</span>
              <input v-model="backfill.arrivalLocal" type="datetime-local" step="60" required />
            </label>
            <footer class="modal-foot">
              <button class="btn" type="button" @click="showBackfill = false">取消</button>
              <button class="btn primary" type="submit">提交补报并重算</button>
            </footer>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- 同期核对弹窗 -->
    <Teleport to="body">
      <div v-if="compareRun" class="modal-overlay wide" @click.self="compareRun = null">
        <div class="modal-card wide-card">
          <header class="modal-head">
            <h3>同期比较核对：{{ compareRun.运行编号 }} vs {{ compareRun.基线运行编号 }}</h3>
            <button class="btn ghost" type="button" @click="compareRun = null">&times;</button>
          </header>
          <div class="modal-body">
            <table class="data-table">
              <thead>
                <tr>
                  <th>路段</th><th>方向</th><th>补报前有效样本</th><th>补报后有效样本</th>
                  <th>补报前状态</th><th>补报后状态</th><th>可同期比较</th><th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in compareRun.同期比较核对" :key="`${c.路段编号}-${c.方向}`">
                  <td>{{ c.路段编号 }}</td><td>{{ c.方向 }}</td>
                  <td>{{ c.补报前有效样本数 }}</td><td>{{ c.补报后有效样本数 }}</td>
                  <td>{{ c.补报前状态 }}</td><td>{{ c.补报后状态 }}</td>
                  <td><span class="badge" :class="c.可同期比较 ? 'ok' : 'warn'">{{ c.可同期比较 ? '可比较' : '不可比较' }}</span></td>
                  <td>{{ c.说明 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type AnyRow = Record<string, string | number | null>
type IncompleteSample = { 车辆班次: string; 通过序号: number; 上车时间: string | null; 未完成原因: string }
type CoverageRow = AnyRow & {
  路段编号: string
  方向: string
  覆盖状态: string
  有效样本数: number
  未完成样本数: number
  样本门槛: number
  超时抵达样本数: number
  P50: number | null
  P90: number | null
  可比区间: [number, number] | null
  样本分布: number[]
  空态原因: string | null
  未完成样本: IncompleteSample[]
}
type SampleRow = AnyRow & {
  样本编号: string
  路段编号: string
  方向: string
  车辆班次: string
  通过序号: number
  上车时间: string | null
  抵达时间: string | null
  行驶时长分钟: number | null
  是否有效样本: boolean
  重复抵达事件数: number
  未完成原因: string | null
}
type LineDecision = AnyRow & {
  线路编号: string
  线路名称: string
  线路发布状态: string
  采用方案: string
  可发布路段: string[]
  空态路段: Array<{ 路段: string; 状态: string; 原因: string }>
}
type CompareRow = {
  路段编号: string
  方向: string
  补报前有效样本数: number
  补报后有效样本数: number
  补报前状态: string
  补报后状态: string
  可同期比较: boolean
  说明: string
}
type RunRow = AnyRow & {
  运行编号: string
  运行标签: string
  创建时间: string
  基线运行编号?: string
  同期比较核对?: CompareRow[]
  汇总: Record<string, number>
}
type CoveragePayload = {
  运行编号: string
  发布策略: string
  汇总: Record<string, number>
  items: CoverageRow[]
  线路决策: LineDecision[]
}

const API = '/api/segment_timing'
const tabs = [
  { key: 'coverage', label: '计时覆盖' },
  { key: 'samples', label: '计时样本' },
  { key: 'reports', label: '行驶时长上报' },
  { key: 'events', label: '上下车事件' },
  { key: 'segments', label: '路段与运营时段' },
  { key: 'runs', label: '计算快照' },
]
const activeTab = ref('coverage')

const coveragePayload = ref<CoveragePayload | null>(null)
const samples = ref<SampleRow[]>([])
const reports = ref<AnyRow[]>([])
const events = ref<AnyRow[]>([])
const segments = ref<AnyRow[]>([])
const runs = ref<RunRow[]>([])
const compareRun = ref<RunRow | null>(null)
const message = ref('')
const messageOk = ref(true)
const showBackfill = ref(false)
const backfill = ref({ segment: '', tripKey: '', arrivalLocal: '' })

const coverageRows = computed<CoverageRow[]>(() => coveragePayload.value?.items ?? [])
const lineDecisions = computed<LineDecision[]>(() => coveragePayload.value?.线路决策 ?? [])
const backfillableSamples = computed(() =>
  samples.value.filter((s) => s.是否有效样本 === false && (!backfill.value.segment || s.路段编号 === backfill.value.segment)),
)
const stats = computed(() => {
  const sum = coveragePayload.value?.汇总
  return [
    { label: '覆盖行数量', value: sum?.覆盖行数量 ?? 0 },
    { label: '可发布行数量', value: sum?.可发布行数量 ?? 0 },
    { label: '空态行数量', value: sum?.空态行数量 ?? 0 },
    { label: '未完成样本总数', value: sum?.未完成样本总数 ?? 0 },
  ]
})

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  const text = String(value)
  return text.slice(11, 16) || text
}

function statusClass(status: unknown): string {
  const text = String(status ?? '')
  if (text === '达标可发布' || text === '运营中') return 'ok'
  if (text === '采集中断' || text === '采集中断样本不足') return 'danger'
  if (text === '样本不足') return 'warn'
  return 'muted-badge'
}

function decisionClass(status: unknown): string {
  const text = String(status ?? '')
  if (text === '全线可发布') return 'ok'
  if (text === '部分发布') return 'warn'
  return 'muted-badge'
}

function notify(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

async function loadCoverage() {
  coveragePayload.value = await getJson<CoveragePayload>(`${API}/coverage`)
}

async function loadRuns() {
  const data = await getJson<{ items: RunRow[] }>(`${API}/runs`)
  runs.value = data.items
}

async function switchTab(key: string) {
  activeTab.value = key
  try {
    if (key === 'samples' && !samples.value.length) {
      samples.value = (await getJson<{ items: SampleRow[] }>(`${API}/samples`)).items
    } else if (key === 'reports' && !reports.value.length) {
      reports.value = (await getJson<{ items: AnyRow[] }>(`${API}/duration_reports`)).items
    } else if (key === 'events' && !events.value.length) {
      events.value = (await getJson<{ items: AnyRow[] }>(`${API}/events`)).items
    } else if (key === 'segments' && !segments.value.length) {
      segments.value = (await getJson<{ items: AnyRow[] }>(`${API}/segments`)).items
    } else if (key === 'runs') {
      await loadRuns()
    } else if (key === 'coverage') {
      await loadCoverage()
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '数据读取失败', false)
  }
}

async function recompute() {
  try {
    const response = await request(`${API}/runs/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { label: '手动重新计算' } }),
    })
    const data = await response.json()
    if (!data.ok) throw new Error(data.message)
    await Promise.all([loadCoverage(), loadRuns()])
    notify(`快照 ${data.entry.运行编号} 已生成`, true)
  } catch (error) {
    notify(error instanceof Error ? error.message : '重新计算失败', false)
  }
}

function openBackfill() {
  backfill.value = { segment: '', tripKey: '', arrivalLocal: '' }
  showBackfill.value = true
  if (!samples.value.length) {
    void getJson<{ items: SampleRow[] }>(`${API}/samples`).then((d) => { samples.value = d.items })
  }
  if (!segments.value.length) {
    void getJson<{ items: AnyRow[] }>(`${API}/segments`).then((d) => { segments.value = d.items })
  }
}

function onSegmentChange() {
  backfill.value.tripKey = ''
}

async function submitBackfill() {
  const [trip, seqRaw, direction] = backfill.value.tripKey.split('::')
  const arrivalTime = backfill.value.arrivalLocal.replace('T', ' ') + ':00'
  try {
    const response = await request(`${API}/backfill_arrival`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          segment: backfill.value.segment,
          trip,
          seq: Number(seqRaw),
          direction,
          arrival_time: arrivalTime,
        },
      }),
    })
    const data = await response.json()
    if (!data.ok) throw new Error(data.message)
    showBackfill.value = false
    samples.value = []
    reports.value = []
    events.value = []
    await Promise.all([loadCoverage(), loadRuns()])
    notify(`${data.message}；已按补报后口径重算`, true)
  } catch (error) {
    notify(error instanceof Error ? error.message : '补报失败', false)
  }
}

onMounted(async () => {
  try {
    const [segData, covData] = await Promise.all([
      getJson<{ items: AnyRow[] }>(`${API}/segments`),
      getJson<CoveragePayload>(`${API}/coverage`),
    ])
    segments.value = segData.items
    coveragePayload.value = covData
    await loadRuns()
  } catch (error) {
    notify(error instanceof Error ? error.message : '路段取数初始化失败', false)
  }
})
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.tab-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.tab-btn { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.tab-btn.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.block-title { font-size: 14px; margin: 14px 0 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; white-space: nowrap; }
.badge.ok { background: #e7f6ec; color: #1a7f37; }
.badge.warn { background: #fff4e0; color: #b25e09; }
.badge.danger { background: #fde8e8; color: #b42318; }
.badge.info { background: #e8f0fe; color: #1f6feb; }
.badge.muted-badge { background: #eef1f5; color: var(--muted); }
.muted { color: var(--muted); }
.ok-text { color: #1a7f37; }
.reason-cell { min-width: 220px; }
.empty-reason { color: #b25e09; font-size: 12px; margin-bottom: 4px; }
.incomplete-line { color: #b42318; font-size: 12px; }
.modal-overlay.wide .wide-card { width: 880px; }
</style>
