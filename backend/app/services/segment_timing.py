"""路段取数业务规则。

口径要点（与任务描述逐条对应）：

1. 同一「车辆班次 + 通过序号 + 方向 + 路段」的重试/补报事件只归并为一个计时样本；
   重复抵达事件只认一次（取最早一条），并保留重复次数用于核对。
2. 抵达事件缺失时绝不以 0 分钟代替：行驶时长保持空值，样本计入「未完成计时样本」，
   且任何缺抵达样本都不进入分位数计算。
3. 反向经过与返程经过按「方向」字段分成不同分组，互不合并。
4. 暂停运营且无车辆经过的路段输出空态并注明原因；尖峰采集中断的路段同样空态，
   但其中缺抵达的原始上车记录仍可通过未完成样本明细查询。
5. 补报抵达后重新计算：生成新的计算快照，旧快照保留；只有补报前后都达标的路段
   才标记为「可同期比较」，补报后才达标的路段只能单独发布，不能与中断前口径对比。
6. 分位数采用线性插值（与 numpy/PERCENTILE 同口径），可比区间取 P25–P75。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.segment_seed import ANALYSIS_DATE, SAMPLE_THRESHOLD
from app.store import store

# 覆盖状态枚举（同时用于图表空态文案）。
STATUS_PUBLISHABLE = "达标可发布"
STATUS_INSUFFICIENT = "样本不足"
STATUS_SUSPENDED = "暂停运营无车辆经过"
STATUS_INTERRUPTED = "采集中断样本不足"

EMPTY_REASONS = {
    STATUS_SUSPENDED: "路段暂停运营，统计日内无车辆经过，无任何计时样本",
    STATUS_INTERRUPTED: "尖峰时段采集中断，恢复后仍有班次缺抵达事件，有效样本未达门槛",
    STATUS_INSUFFICIENT: "有效计时样本未达发布门槛，仅可预览样本分布",
}

# 发布策略：达标路段独立发布分位数（方案A）；未达标路段空态展示原因。
PUBLISH_STRATEGY = "达标路段独立分位发布，未达标路段空态并说明原因"

EVENT_MODULE = "segment_event"
REPORT_MODULE = "duration_report"
SEGMENT_MODULE = "segment"
RUN_MODULE = "timing_run"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def quantile(values: list[int], pct: float) -> float | None:
    """线性插值分位数，与 numpy.percentile 默认口径一致。"""
    if not values:
        return None
    data = sorted(values)
    if len(data) == 1:
        return float(data[0])
    pos = (len(data) - 1) * pct
    low = int(pos)
    high = min(low + 1, len(data) - 1)
    frac = pos - low
    return round(data[low] + (data[high] - data[low]) * frac, 2)


class SegmentTimingService:
    """路段计时覆盖计算与补报重算。"""

    # ------------------------------------------------------------------
    # 原始数据读取
    # ------------------------------------------------------------------
    def list_segments(self, line: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(SEGMENT_MODULE)
        if line:
            rows = [r for r in rows if r.get("线路编号") == line]
        return [dict(r) for r in rows]

    def list_events(self, segment: str | None = None, direction: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(EVENT_MODULE)
        if segment:
            rows = [r for r in rows if r.get("路段编号") == segment]
        if direction:
            rows = [r for r in rows if r.get("方向") == direction]
        return [dict(r) for r in rows]

    def list_reports(self, segment: str | None = None, direction: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(REPORT_MODULE)
        if segment:
            rows = [r for r in rows if r.get("路段编号") == segment]
        if direction:
            rows = [r for r in rows if r.get("方向") == direction]
        return [dict(r) for r in rows]

    def list_missing_arrivals(self, target_date: str = ANALYSIS_DATE) -> list[dict[str, Any]]:
        """采集中断恢复后仍缺抵达事件的原始记录：始终可查，不依赖是否已补报。"""
        samples = self.build_samples(target_date)
        return [
            {
                "路段编号": s["路段编号"], "方向": s["方向"],
                "车辆班次": s["车辆班次"], "通过序号": s["通过序号"],
                "上车时间": s["上车时间"], "未完成原因": s["未完成原因"],
            }
            for s in samples if not s["是否有效样本"]
        ]

    # ------------------------------------------------------------------
    # 样本归并：事件 + 时长上报 -> 计时样本
    # ------------------------------------------------------------------
    def build_samples(self, target_date: str = ANALYSIS_DATE) -> list[dict[str, Any]]:
        events = [e for e in store.rows(EVENT_MODULE) if e.get("统计日期") == target_date]
        reports = [r for r in store.rows(REPORT_MODULE) if r.get("统计日期") == target_date]

        report_index: dict[tuple, dict[str, Any]] = {}
        for rep in reports:
            key = (rep["路段编号"], rep["方向"], rep["车辆班次"], rep["通过序号"])
            # 同键重复上报时保留信息更全的一条（有抵达的优先）。
            old = report_index.get(key)
            if old is None or (old.get("抵达时间") is None and rep.get("抵达时间") is not None):
                report_index[key] = rep

        grouped: dict[tuple, dict[str, Any]] = {}
        for evt in events:
            key = (evt["路段编号"], evt["方向"], evt["车辆班次"], evt["通过序号"])
            bucket = grouped.setdefault(key, {
                "路段编号": evt["路段编号"], "方向": evt["方向"],
                "车辆班次": evt["车辆班次"], "通过序号": evt["通过序号"],
                "上车候选": [], "抵达候选": [], "上车事件数": 0,
                "抵达事件数": 0, "重复抵达事件数": 0,
            })
            if evt["事件类型"] == "上车":
                bucket["上车事件数"] += 1
                if evt.get("事件时间"):
                    bucket["上车候选"].append(evt["事件时间"])
            else:
                bucket["抵达事件数"] += 1
                if evt.get("事件时间"):
                    bucket["抵达候选"].append(evt["事件时间"])

        samples: list[dict[str, Any]] = []
        for key, bucket in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][3])):
            board_ts = min(bucket["上车候选"]) if bucket["上车候选"] else None
            arrive_ts = min(bucket["抵达候选"]) if bucket["抵达候选"] else None
            # 同一班次+序号的多次抵达，最早一条生效，其余计入重复次数。
            bucket["重复抵达事件数"] = max(bucket["抵达事件数"] - 1, 0)

            report = report_index.get(key)
            report_minutes = report.get("行驶时长分钟") if report else None

            event_minutes: int | None = None
            board_dt, arrive_dt = _parse_ts(board_ts), _parse_ts(arrive_ts)
            if board_dt is not None and arrive_dt is not None and arrive_dt >= board_dt:
                event_minutes = int((arrive_dt - board_dt).total_seconds() // 60)

            has_arrival = arrive_ts is not None
            # 以事件链算出的时长为准；上报时长仅用于交叉核对。
            duration = event_minutes if has_arrival else None
            cross_check: dict[str, Any] = {"上报时长分钟": report_minutes}
            if has_arrival and report_minutes is not None:
                cross_check["时长一致"] = (report_minutes == event_minutes)
                cross_check["事件时长分钟"] = event_minutes
            elif not has_arrival:
                # 缺抵达的上报也必须是空值，防止上游把缺失写成 0。
                cross_check["上报缺失已置空"] = report_minutes is None

            samples.append({
                "样本编号": f"S-{key[0]}-{key[2]}-{key[3]}",
                "统计日期": target_date,
                "路段编号": key[0], "方向": key[1],
                "车辆班次": key[2], "通过序号": key[3],
                "上车时间": board_ts, "抵达时间": arrive_ts,
                "行驶时长分钟": duration,  # 缺抵达时为 None，绝不补 0
                "是否有效样本": has_arrival,
                "未完成原因": None if has_arrival else "抵达事件缺失（采集中断后仍未恢复，待补报）",
                "重复抵达事件数": bucket["重复抵达事件数"],
                "上车事件数": bucket["上车事件数"],
                "抵达事件数": bucket["抵达事件数"],
                "超时抵达": bool(has_arrival and duration is not None and duration >= 25),
                "交叉核对": cross_check,
            })
        return samples

    # ------------------------------------------------------------------
    # 覆盖结果：按 路段 × 方向 聚合
    # ------------------------------------------------------------------
    def build_coverage(self, target_date: str = ANALYSIS_DATE) -> list[dict[str, Any]]:
        samples = self.build_samples(target_date)
        segments = {s["路段编号"]: s for s in self.list_segments()}

        keys = sorted({(s["路段编号"], s["方向"]) for s in samples})
        # 没有任何样本的路段也要出空态行（停运线路）。
        for seg_id in segments:
            if not any(k[0] == seg_id for k in keys):
                keys.append((seg_id, "去程"))  # 停运路段无方向数据，占位一行

        coverage: list[dict[str, Any]] = []
        for seg_id, direction in sorted(set(keys)):
            seg = segments.get(seg_id, {})
            group = [s for s in samples if s["路段编号"] == seg_id and s["方向"] == direction]
            valid = [s for s in group if s["是否有效样本"]]
            incomplete = [s for s in group if not s["是否有效样本"]]
            durations = [s["行驶时长分钟"] for s in valid]
            threshold = int(seg.get("样本门槛", SAMPLE_THRESHOLD))

            suspended = seg.get("路段状态") == "暂停运营"
            interrupted = seg.get("路段状态") == "采集中断"
            if suspended and not group:
                status = STATUS_SUSPENDED
            elif interrupted and len(durations) < threshold:
                status = STATUS_INTERRUPTED
            elif len(durations) >= threshold:
                status = STATUS_PUBLISHABLE
            else:
                status = STATUS_INSUFFICIENT

            row = {
                "路段编号": seg_id,
                "线路编号": seg.get("线路编号"),
                "线路名称": seg.get("线路名称"),
                "方向": direction,
                "起点": seg.get("起点"),
                "终点": seg.get("终点"),
                "运营时段": f"{seg.get('运营开始', '')}–{seg.get('运营结束', '')}",
                "路段状态": seg.get("路段状态"),
                "中断窗口": (f"{seg.get('中断开始')} ~ {seg.get('中断结束')}"
                          if seg.get("中断开始") else None),
                "样本门槛": threshold,
                "有效样本数": len(durations),
                "未完成样本数": len(incomplete),
                "未完成样本": [
                    {"车辆班次": s["车辆班次"], "通过序号": s["通过序号"],
                     "上车时间": s["上车时间"], "未完成原因": s["未完成原因"]}
                    for s in incomplete
                ],
                "超时抵达样本数": sum(1 for s in valid if s["超时抵达"]),
                "重复抵达事件数": sum(s["重复抵达事件数"] for s in group),
                "覆盖状态": status,
                "空态原因": EMPTY_REASONS.get(status),
                "可发布": status == STATUS_PUBLISHABLE,
                # 分位数仅在达标时给出；任何缺抵达样本都不在 durations 内。
                "P25": quantile(durations, 0.25) if status == STATUS_PUBLISHABLE else None,
                "P50": quantile(durations, 0.50) if status == STATUS_PUBLISHABLE else None,
                "P90": quantile(durations, 0.90) if status == STATUS_PUBLISHABLE else None,
                "可比区间": (
                    [quantile(durations, 0.25), quantile(durations, 0.75)]
                    if status == STATUS_PUBLISHABLE else None
                ),
                "样本分布": sorted(durations),
            }
            coverage.append(row)
        return coverage

    # ------------------------------------------------------------------
    # 线路发布决策（方案A：达标路段独立发布；方案B：仅预览暂缓发布）
    # ------------------------------------------------------------------
    def build_line_decisions(self, coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        lines = sorted({row["线路编号"] for row in coverage if row.get("线路编号")})
        for line in lines:
            rows = [r for r in coverage if r["线路编号"] == line]
            publishable = [r for r in rows if r["可发布"]]
            empty = [r for r in rows if not r["可发布"]]
            if not rows or not any(r["有效样本数"] or r["未完成样本数"] for r in rows):
                line_status = "全线空态"
            elif len(publishable) == len(rows):
                line_status = "全线可发布"
            elif publishable:
                line_status = "部分发布"
            else:
                line_status = "暂缓发布"
            decisions.append({
                "线路编号": line,
                "线路名称": rows[0].get("线路名称"),
                "线路发布状态": line_status,
                "可发布路段数": len(publishable),
                "空态路段数": len(empty),
                "采用方案": "A：达标路段独立分位发布" if publishable else "B：仅预览样本分布，暂缓本期线路发布",
                "可发布路段": [f"{r['路段编号']}（{r['方向']}）" for r in publishable],
                "空态路段": [
                    {"路段": f"{r['路段编号']}（{r['方向']}）", "状态": r["覆盖状态"], "原因": r["空态原因"]}
                    for r in empty
                ],
            })
        return decisions

    # ------------------------------------------------------------------
    # 计算快照（中断补报前 / 补报后各一份）
    # ------------------------------------------------------------------
    def create_run(self, label: str, target_date: str = ANALYSIS_DATE) -> dict[str, Any]:
        coverage = self.build_coverage(target_date)
        decisions = self.build_line_decisions(coverage)
        run_rows = store.rows(RUN_MODULE)
        run = {
            "id": max((int(r.get("id", 0)) for r in run_rows), default=0) + 1,
            "运行编号": f"RUN-{target_date.replace('-', '')}-{len(run_rows) + 1:02d}",
            "统计日期": target_date,
            "运行标签": label,
            "创建时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "发布策略": PUBLISH_STRATEGY,
            "覆盖结果": coverage,
            "线路决策": decisions,
            "汇总": {
                "覆盖行数量": len(coverage),
                "可发布行数量": sum(1 for r in coverage if r["可发布"]),
                "空态行数量": sum(1 for r in coverage if not r["可发布"]),
                "有效样本总数": sum(r["有效样本数"] for r in coverage),
                "未完成样本总数": sum(r["未完成样本数"] for r in coverage),
            },
        }
        run_rows.append(run)
        return run

    def list_runs(self, target_date: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(RUN_MODULE)
        if target_date:
            rows = [r for r in rows if r.get("统计日期") == target_date]
        return [dict(r) for r in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        return store.find(RUN_MODULE, run_id)

    def latest_run(self, target_date: str = ANALYSIS_DATE) -> dict[str, Any] | None:
        rows = self.list_runs(target_date)
        return rows[-1] if rows else None

    def ensure_run(self, label: str, target_date: str = ANALYSIS_DATE) -> dict[str, Any]:
        """覆盖查询入口：没有快照时先按当前数据补算一份，保证图表始终有结果可消费。"""
        run = self.latest_run(target_date)
        if run is None:
            run = self.create_run(label, target_date)
        return run

    # ------------------------------------------------------------------
    # 补报抵达 -> 重算并与上一份快照核对同期可比性
    # ------------------------------------------------------------------
    def backfill_arrival(
        self,
        *,
        segment: str,
        trip: str,
        seq: int,
        arrival_time: str,
        target_date: str = ANALYSIS_DATE,
        direction: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        events = store.rows(EVENT_MODULE)
        matched = [
            e for e in events
            if e["路段编号"] == segment and e["车辆班次"] == trip
            and e["通过序号"] == seq and e["事件类型"] == "上车"
            and (direction is None or e["方向"] == direction)
        ]
        if not matched:
            return None, f"未找到路段 {segment} 班次 {trip} 通过序号 {seq} 的上车记录，无法补报"
        target = matched[0]
        dir_value = direction or target["方向"]

        # 已有抵达事件时按幂等处理：同一班次+序号重复补报只算一次，不重复生成样本。
        existing = [
            e for e in events
            if e["路段编号"] == segment and e["车辆班次"] == trip
            and e["通过序号"] == seq and e["事件类型"] == "抵达" and e.get("事件时间")
        ]
        if existing:
            return None, (
                f"班次 {trip} 通过序号 {seq} 已存在抵达事件 {min(e['事件时间'] for e in existing)}，"
                "重复补报已忽略（同一班次+序号只算一次）"
            )

        board_dt = _parse_ts(target.get("事件时间"))
        arrive_dt = _parse_ts(arrival_time)
        if arrive_dt is None:
            return None, f"补报抵达时间格式应为 YYYY-MM-DD HH:MM:SS，收到：{arrival_time}"
        if board_dt is not None and arrive_dt < board_dt:
            return None, (
                f"补报抵达时间 {arrival_time} 早于上车时间 {target.get('事件时间')}，"
                "不能生成计时样本"
            )

        # 补报前先固化一份基线快照；若此前没有任何快照，先按当前（缺抵达）数据补算，
        # 保证同期比较的锚点一定是中断补报前口径，而不是补报后的快照自身。
        if self.latest_run(target_date) is None:
            self.create_run("中断补报前基线", target_date)

        next_id = max((int(e.get("id", 0)) for e in events), default=0) + 1
        events.append({
            "id": next_id,
            "事件编号": f"EVT-BF{next_id:04d}",
            "统计日期": target_date,
            "路段编号": segment,
            "车辆班次": trip,
            "通过序号": seq,
            "事件类型": "抵达",
            "方向": dir_value,
            "事件时间": arrival_time,
            "采集来源": "中断恢复补报",
        })

        # 同步补全行驶时长上报（缺失值由 None 变为实际分钟数，全程不出现 0 分钟占位）。
        reports = store.rows(REPORT_MODULE)
        rep = next((
            r for r in reports
            if r["路段编号"] == segment and r["车辆班次"] == trip
            and r["通过序号"] == seq and r["方向"] == dir_value
        ), None)
        minutes = int((arrive_dt - board_dt).total_seconds() // 60) if board_dt else None
        if rep is not None:
            rep["抵达时间"] = arrival_time
            rep["行驶时长分钟"] = minutes
            rep["备注"] = (rep.get("备注") or "") + "；抵达事件已补报"
        else:
            reports.append({
                "id": max((int(r.get("id", 0)) for r in reports), default=0) + 1,
                "上报编号": f"DUR-BF{len(reports) + 1:04d}",
                "统计日期": target_date, "路段编号": segment,
                "车辆班次": trip, "通过序号": seq, "方向": dir_value,
                "上车时间": target.get("事件时间"), "抵达时间": arrival_time,
                "行驶时长分钟": minutes, "备注": "中断恢复补报后生成",
            })

        after = self.create_run("中断补报后重算", target_date)
        # 同期比较始终锚定当日中断补报前的第一份基线快照，而不是上一次补报快照。
        baseline = self.list_runs(target_date)[0]
        after["基线运行编号"] = baseline["运行编号"]
        after["同期比较核对"] = self._compare_runs(baseline, after)
        return after, f"班次 {trip} 通过序号 {seq} 的抵达事件已补报（{arrival_time}，{minutes} 分钟），覆盖结果已重算"

    def _compare_runs(self, before: dict[str, Any] | None, after: dict[str, Any]) -> list[dict[str, Any]]:
        """逐路段核对补报前后哪些结果可用于同期比较。"""
        if before is None:
            return []
        before_map = {(r["路段编号"], r["方向"]): r for r in before["覆盖结果"]}
        result = []
        for row in after["覆盖结果"]:
            key = (row["路段编号"], row["方向"])
            old = before_map.get(key)
            if old is None:
                continue
            comparable = bool(old["可发布"] and row["可发布"])
            note = "补报前后均达标，可同期比较" if comparable else (
                "补报后才达标，仅可单独发布，不能与中断前口径同期比较"
                if row["可发布"] else "补报后仍未达标，继续空态")
            result.append({
                "路段编号": key[0], "方向": key[1],
                "补报前有效样本数": old["有效样本数"],
                "补报后有效样本数": row["有效样本数"],
                "补报前状态": old["覆盖状态"],
                "补报后状态": row["覆盖状态"],
                "可同期比较": comparable,
                "说明": note,
            })
        return result

    # ------------------------------------------------------------------
    # 给数据API发布 / 图表配置消费的成品数据
    # ------------------------------------------------------------------
    def publish_dataset(self, target_date: str = ANALYSIS_DATE) -> dict[str, Any]:
        run = self.ensure_run("发布前计算", target_date)
        publishable = [r for r in run["覆盖结果"] if r["可发布"]]
        return {
            "统计日期": target_date,
            "运行编号": run["运行编号"],
            "发布策略": PUBLISH_STRATEGY,
            "样本门槛": SAMPLE_THRESHOLD,
            "可发布计时结果": [
                {
                    "路段编号": r["路段编号"], "线路编号": r["线路编号"], "方向": r["方向"],
                    "有效样本数": r["有效样本数"],
                    "P25": r["P25"], "P50": r["P50"], "P90": r["P90"],
                    "可比区间": r["可比区间"], "超时抵达样本数": r["超时抵达样本数"],
                }
                for r in publishable
            ],
            "空态路段": [
                {"路段编号": r["路段编号"], "方向": r["方向"],
                 "覆盖状态": r["覆盖状态"], "空态原因": r["空态原因"]}
                for r in run["覆盖结果"] if not r["可发布"]
            ],
            "排除样本说明": "所有缺抵达事件的未完成样本均未进入分位数，且未以 0 分钟占位",
            "线路决策": run["线路决策"],
            "汇总": run["汇总"],
        }

    def chart_coverage(self, target_date: str = ANALYSIS_DATE) -> dict[str, Any]:
        """图表配置消费的路段计时覆盖结果：分位数 + 可比区间 + 空态原因。"""
        run = self.ensure_run("图表消费计算", target_date)
        return {
            "图表名称": "路段运输时长分位数与计时覆盖",
            "统计日期": target_date,
            "运行编号": run["运行编号"],
            "发布策略": PUBLISH_STRATEGY,
            "序列": [
                {
                    "路段编号": r["路段编号"], "线路编号": r["线路编号"], "方向": r["方向"],
                    "覆盖状态": r["覆盖状态"],
                    "有效样本数": r["有效样本数"], "未完成样本数": r["未完成样本数"],
                    "P50": r["P50"], "P90": r["P90"],
                    "可比区间": r["可比区间"],
                    "空态原因": r["空态原因"],
                    "样本分布": r["样本分布"],
                }
                for r in run["覆盖结果"]
            ],
            "线路决策": run["线路决策"],
        }


service = SegmentTimingService()
