# 数据分析实验与数据应用服务平台

面向指标口径管理、分析实验设计、OLAP查询、数据看板构建与数据API发布的数据应用平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 指标定义 | `metric_def` | 指标 | 指标编号、指标名称、计算公式 |
| 维度管理 | `dimension` | 分析维度 | 维度编号、维度名称、维度类型 |
| 数据集管理 | `dataset` | 分析数据集 | 数据集编号、数据集名称、来源类型 |
| 分析实验 | `experiment` | 实验方案 | 方案编号、实验名称、分析数据集 |
| OLAP查询 | `query_builder` | 查询模板 | 模板编号、模板名称、查询语句 |
| 数据看板 | `dashboard` | 看板配置 | 看板编号、看板名称、包含图表 |
| 图表配置 | `chart` | 图表 | 图表编号、图表名称、图表类型 |
| 数据API发布 | `data_service` | 数据服务 | 服务编号、服务名称、输出数据集 |
| 路段取数 | `segment_timing` | 路段计时样本/覆盖快照 | 路段编号、车辆班次、通过序号、方向、行驶时长 |
| 智能告警 | `alert` | 告警规则 | 规则编号、告警名称、监控指标 |
| 分析用户组 | `user_group` | 用户组 | 组编号、组名称、组描述 |
| 数据快照 | `snapshot` | 快照记录 | 快照编号、数据集名称、快照时间 |
| 任务调度 | `scheduler` | 调度任务 | 任务编号、任务名称、调度类型 |
| 缓存管理 | `cache` | 缓存配置 | 缓存编号、缓存目标、缓存策略 |
| 分析管道 | `pipeline` | 分析节点 | 节点编号、输入数据集、分析算子 |
| 分析模型 | `model` | 模型配置 | 模型编号、模型名称、模型类型 |
| 数据集市 | `data_mart` | 集市表 | 表编号、表名称、主题域 |
| 数据导出 | `export` | 导出任务 | 任务编号、导出对象、导出格式 |
| 数据审计 | `audit` | 审计记录 | 记录编号、操作类型、操作人 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 路段取数与运输时长分位数

围绕「数据API发布缺少可用于计算运输时长分位数的有效样本」新增的取数域，代码位于
`backend/app/segment_seed.py`（示例数据）、`app/services/segment_timing.py`（口径）、
`app/routers/segment_timing.py`（接口），前端页面在「路段取数」菜单。

### 数据来源与口径

- 读取三类上报数据：路段与运营时段（`segment`，含停运/采集中断状态与中断窗口）、
  上下车事件（`segment_event`）、行驶时长上报（`duration_report`）。
- 计时样本按「路段 + 方向 + 车辆班次 + 通过序号」归并：同一班次同序号的重试/补报、
  甚至同时到达的重复抵达事件，只形成 **一个** 有效计时样本（取最早抵达时间）。
- **抵达事件缺失绝不用 0 分钟代替**：行驶时长保持 `null`，样本计入「未完成计时样本」，
  任何缺抵达样本都不进入分位数；可通过 `GET /api/segment_timing/missing_arrivals` 查询原记录。
- 反向经过与返程经过按「方向」字段独立分组，互不合并。
- 分位数采用线性插值（与 `numpy.percentile` 默认口径一致），可比区间取 P25–P75；
  样本未达门槛（每路段 5 个有效样本）的路段输出空态并注明原因：
  暂停运营无车辆经过 / 尖峰采集中断样本不足 / 普通样本不足。

### 补报、重算与同期比较

- `POST /api/segment_timing/backfill_arrival` 补报抵达事件（幂等，重复补报被拒绝），
  补报前自动固化中断前基线快照，补报后生成新快照并逐路段输出同期可比性核对：
  仅补报前后都达标的路段可同期比较；补报后才达标的中断路段只能单独发布。
- 线路发布决策：一段达标、其余停运/中断时采用方案 A（达标路段发布独立分位数，
  空态路段展示原因）；全线无达标路段时采用方案 B（仅预览样本分布，暂缓本期线路发布）。
- 消费端点：`GET /api/data_service/timing_dataset`（发布数据集，只含达标路段）、
  `GET /api/chart/timing_coverage`（图表配置消费，含分位数、可比区间与空态原因）。

### 复验

```bash
python3 -m unittest discover -s tests -v   # 22 个用例，覆盖停运/中断/充足三条线路、
                                           # 超时抵达、重复回报、补报重算与同期核对
```
