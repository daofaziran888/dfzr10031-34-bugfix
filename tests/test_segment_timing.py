"""路段取数与运输时长分位数口径复验。

覆盖任务要求的全部场景：
- 全日停运路线（R3）、中途失败路线（R2）、样本充足路线（R1）；
- 超时抵达拉高高分位、重复回报只算一次、缺抵达绝不补零且不进分位数；
- 反向/返程分组、暂停运营空态、尖峰采集中断空态与未完成样本可查；
- 中断补报幂等、补报后重算、补报前后同期可比性核对；
- 数据API发布数据集与图表覆盖结果的空态说明。

运行：python3 -m unittest discover -s tests -v（在 backend 目录下）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# app 包位于 backend/ 下，测试目录与 backend 平级，先把 backend 加入模块搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.seed import SEED_ROWS
from app.segment_seed import (
    ANALYSIS_DATE,
    DURATION_REPORT_SEED,
    SEGMENT_EVENT_SEED,
    SEGMENT_SEED,
)
from app.services.segment_timing import (
    EMPTY_REASONS,
    STATUS_INTERRUPTED,
    STATUS_PUBLISHABLE,
    STATUS_SUSPENDED,
    STATUS_INSUFFICIENT,
    SegmentTimingService,
    quantile,
)
from app.store import store


def reset_store() -> None:
    """每个用例前重置内存仓库，保证用例相互独立。"""
    store._tables = {
        name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
    }
    store._tables["segment"] = [dict(row) for row in SEGMENT_SEED]
    store._tables["segment_event"] = [dict(row) for row in SEGMENT_EVENT_SEED]
    store._tables["duration_report"] = [dict(row) for row in DURATION_REPORT_SEED]
    store._tables["timing_run"] = []


class QuantileTest(unittest.TestCase):
    def test_linear_interpolation_matches_numpy_convention(self) -> None:
        # numpy.percentile 默认线性插值：P50([1,2,3,4])=2.5，P90=3.7
        self.assertEqual(quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(quantile([1, 2, 3, 4], 0.9), 3.7)
        self.assertEqual(quantile([7], 0.9), 7.0)
        self.assertIsNone(quantile([], 0.9))


class SampleMergeTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        self.svc = SegmentTimingService()

    def test_missing_arrival_never_zero_and_marked_incomplete(self) -> None:
        """抵达缺失：时长为 None 而不是 0，且不进入有效样本。"""
        samples = self.svc.build_samples()
        incomplete = [s for s in samples if not s["是否有效样本"]]
        self.assertEqual(len(incomplete), 3)
        for s in incomplete:
            self.assertIsNone(s["行驶时长分钟"])
            self.assertIn("抵达事件缺失", s["未完成原因"])
        # 原始上报同样不允许出现 0 分钟占位
        for rep in store.rows("duration_report"):
            if rep["抵达时间"] is None:
                self.assertIsNone(rep["行驶时长分钟"])

    def test_duplicate_arrival_same_trip_seq_counts_once(self) -> None:
        """重试补报带同一车辆班次和通过序号时只算一次（R1-0701 有两条抵达事件）。"""
        samples = self.svc.build_samples()
        target = next(
            s for s in samples
            if s["路段编号"] == "SEG-R1-01" and s["车辆班次"] == "R1-0701"
        )
        self.assertEqual(target["抵达事件数"], 2)
        self.assertEqual(target["重复抵达事件数"], 1)
        self.assertTrue(target["是否有效样本"])
        self.assertEqual(target["行驶时长分钟"], 12)  # 07:01 -> 07:13 最早抵达
        # 该路段去程只有 6 个班次 -> 6 个样本，重复事件没有多出样本
        outbound = [s for s in samples if s["路段编号"] == "SEG-R1-01" and s["方向"] == "去程"]
        self.assertEqual(len(outbound), 6)
        self.assertEqual(sum(1 for s in outbound if s["是否有效样本"]), 5)

    def test_simultaneous_arrival_reports_merge_to_one_sample(self) -> None:
        """补报与原抵达同时到达（时间完全相同）时，也只生成一个有效计时样本。"""
        store.rows("segment_event").append({
            "id": 9001, "事件编号": "EVT-9001", "统计日期": ANALYSIS_DATE,
            "路段编号": "SEG-R1-02", "车辆班次": "R1-0701", "通过序号": 1,
            "事件类型": "抵达", "方向": "去程",
            "事件时间": f"{ANALYSIS_DATE} 07:22:00",  # 与 EVT-0020 完全同时
            "采集来源": "中断恢复补报",
        })
        samples = self.svc.build_samples()
        target = [
            s for s in samples
            if s["路段编号"] == "SEG-R1-02" and s["车辆班次"] == "R1-0701"
        ]
        self.assertEqual(len(target), 1)  # 同时到达只生成一个样本
        self.assertTrue(target[0]["是否有效样本"])
        self.assertEqual(target[0]["重复抵达事件数"], 1)
        self.assertEqual(target[0]["行驶时长分钟"], 8)

    def test_reverse_and_return_are_separate_groups(self) -> None:
        """反向经过与返程经过分开统计，互不合并。"""
        samples = self.svc.build_samples()
        ret = [s for s in samples if s["路段编号"] == "SEG-R1-01" and s["方向"] == "返程"]
        rev = [s for s in samples if s["路段编号"] == "SEG-R1-01" and s["方向"] == "反向"]
        self.assertEqual({s["车辆班次"] for s in ret}, {"R1-1005", "R1-1040"})
        self.assertEqual({s["车辆班次"] for s in rev}, {"R1-1110"})
        self.assertEqual(rev[0]["行驶时长分钟"], 14)

    def test_overtime_arrival_enters_high_quantile(self) -> None:
        """超时抵达（32 分钟）进入样本并把 P90 拉高。"""
        run = self.svc.create_run("基线")
        row = next(r for r in run["覆盖结果"] if r["路段编号"] == "SEG-R1-01" and r["方向"] == "去程")
        self.assertEqual(row["超时抵达样本数"], 1)
        self.assertEqual(row["样本分布"], [10, 11, 11, 12, 32])
        # P90 线性插值：12 + (32-12)*0.6 = 24
        self.assertEqual(row["P90"], 24.0)
        self.assertEqual(row["P50"], 11.0)


class CoverageAndEmptyStateTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        self.svc = SegmentTimingService()
        self.run = self.svc.create_run("基线")

    def _row(self, segment: str, direction: str = "去程") -> dict:
        return next(
            r for r in self.run["覆盖结果"]
            if r["路段编号"] == segment and r["方向"] == direction
        )

    def test_suspended_line_full_day_empty_state_with_reason(self) -> None:
        """R3 全日停运：无车辆经过、无样本，空态并说明原因。"""
        for seg in ("SEG-R3-01", "SEG-R3-02"):
            row = self._row(seg)
            self.assertEqual(row["覆盖状态"], STATUS_SUSPENDED)
            self.assertEqual(row["有效样本数"], 0)
            self.assertFalse(row["可发布"])
            self.assertIsNone(row["P50"])
            self.assertEqual(row["空态原因"], EMPTY_REASONS[STATUS_SUSPENDED])
        decision = next(d for d in self.run["线路决策"] if d["线路编号"] == "R3")
        self.assertEqual(decision["线路发布状态"], "全线空态")
        self.assertIn("B", decision["采用方案"])

    def test_interrupted_segment_keeps_incomplete_records_queryable(self) -> None:
        """R2-03 尖峰中断：4 个有效样本未达门槛，2 条缺抵达原记录可查。"""
        row = self._row("SEG-R2-03")
        self.assertEqual(row["覆盖状态"], STATUS_INTERRUPTED)
        self.assertEqual(row["有效样本数"], 4)
        self.assertEqual(row["未完成样本数"], 2)
        self.assertFalse(row["可发布"])
        self.assertIsNone(row["P90"])
        self.assertEqual(row["空态原因"], EMPTY_REASONS[STATUS_INTERRUPTED])
        trips = {item["车辆班次"] for item in row["未完成样本"]}
        self.assertEqual(trips, {"R2-0810", "R2-0835"})
        for item in row["未完成样本"]:
            self.assertTrue(item["上车时间"])  # 原始上车记录仍可查

    def test_suspended_segment_with_no_traffic(self) -> None:
        """R2-02 暂停运营没有车辆经过，单独给出停运空态（与中断空态区分）。"""
        row = self._row("SEG-R2-02")
        self.assertEqual(row["覆盖状态"], STATUS_SUSPENDED)
        self.assertEqual(row["有效样本数"], 0)
        self.assertEqual(row["未完成样本数"], 0)

    def test_partial_line_uses_plan_a_independent_quantile(self) -> None:
        """R2 一段达标、一段停运、一段中断：采用方案A，仅发布达标路段独立分位。"""
        decision = next(d for d in self.run["线路决策"] if d["线路编号"] == "R2")
        self.assertEqual(decision["线路发布状态"], "部分发布")
        self.assertIn("A", decision["采用方案"])
        self.assertEqual(decision["可发布路段"], ["SEG-R2-01（去程）"])
        empty_states = {item["状态"] for item in decision["空态路段"]}
        self.assertEqual(empty_states, {STATUS_SUSPENDED, STATUS_INTERRUPTED})
        row = self._row("SEG-R2-01")
        self.assertEqual(row["覆盖状态"], STATUS_PUBLISHABLE)
        self.assertEqual(row["可比区间"], [17.0, 18.0])

    def test_sufficient_line_publishes_all_qualified_segments(self) -> None:
        """R1 三段去程均达标可发布，返程/反向因样本不足只预览。"""
        decision = next(d for d in self.run["线路决策"] if d["线路编号"] == "R1")
        self.assertEqual(decision["线路发布状态"], "部分发布")
        self.assertEqual(decision["可发布路段数"], 3)
        for seg in ("SEG-R1-01", "SEG-R1-02", "SEG-R1-03"):
            self.assertTrue(self._row(seg)["可发布"])
        rev = self._row("SEG-R1-01", "返程")
        self.assertEqual(rev["覆盖状态"], STATUS_INSUFFICIENT)
        self.assertEqual(rev["空态原因"], EMPTY_REASONS[STATUS_INSUFFICIENT])

    def test_no_incomplete_sample_enters_quantile(self) -> None:
        """任何缺抵达样本都不能进入分位数（参与计算的分布只含有效样本）。"""
        for row in self.run["覆盖结果"]:
            self.assertEqual(len(row["样本分布"]), row["有效样本数"])
            self.assertTrue(all(isinstance(v, int) and v > 0 for v in row["样本分布"]))


class BackfillRecomputeTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        self.svc = SegmentTimingService()
        self.before = self.svc.create_run("中断补报前基线")

    def _r203(self, run: dict) -> dict:
        return next(
            r for r in run["覆盖结果"]
            if r["路段编号"] == "SEG-R2-03" and r["方向"] == "去程"
        )

    def test_backfill_one_arrival_reaches_threshold(self) -> None:
        """补报一条后 4 -> 5 达到门槛，覆盖状态由中断空态转为达标可发布。"""
        run, msg = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:26:00",
        )
        self.assertIsNotNone(run)
        row = self._r203(run)
        self.assertEqual(row["有效样本数"], 5)
        self.assertEqual(row["未完成样本数"], 1)
        self.assertTrue(row["可发布"])
        self.assertEqual(row["覆盖状态"], STATUS_PUBLISHABLE)
        self.assertEqual(row["P50"], 13.0)  # [10,12,13,14,16] 中位数 13
        self.assertIn("16 分钟", msg)
        # 时长由空值变为实际值，全程没有出现 0
        rep = next(
            r for r in store.rows("duration_report")
            if r["车辆班次"] == "R2-0810"
        )
        self.assertEqual(rep["行驶时长分钟"], 16)
        self.assertIsNotNone(rep["抵达时间"])

    def test_duplicate_backfill_is_idempotent(self) -> None:
        """对同一班次+序号重复补报只算一次，第二次被拒绝且不新增样本/事件。"""
        self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:26:00",
        )
        event_count = len(store.rows("segment_event"))
        run2, msg = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:30:00",
        )
        self.assertIsNone(run2)
        self.assertIn("只算一次", msg)
        self.assertEqual(len(store.rows("segment_event")), event_count)

    def test_backfill_both_missing_then_recompute_and_compare(self) -> None:
        """两条缺抵达全部补报后重算：R2-03 达标但只能单独发布，不可与中断前同期比较。"""
        self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:26:00",
        )
        after, _ = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0835", seq=6,
            arrival_time=f"{ANALYSIS_DATE} 08:55:00",
        )
        row = self._r203(after)
        self.assertEqual(row["有效样本数"], 6)
        self.assertEqual(row["未完成样本数"], 0)
        self.assertEqual(row["样本分布"], [10, 12, 13, 14, 16, 20])

        compare = { (c["路段编号"], c["方向"]): c for c in after["同期比较核对"] }
        # 中断路段：补报前不达标、补报后达标 -> 不可同期比较
        self.assertFalse(compare[("SEG-R2-03", "去程")]["可同期比较"])
        self.assertIn("不能与中断前口径同期比较", compare[("SEG-R2-03", "去程")]["说明"])
        # 补报前后都达标的路段 -> 可同期比较
        self.assertTrue(compare[("SEG-R2-01", "去程")]["可同期比较"])
        self.assertTrue(compare[("SEG-R1-02", "去程")]["可同期比较"])
        # 历史快照保留，可追溯中断前口径
        runs = self.svc.list_runs()
        self.assertGreaterEqual(len(runs), 3)

    def test_backfill_without_prior_run_creates_baseline_first(self) -> None:
        """未先生成快照就补报：自动补建中断前基线，同期比较仍锚定补报前口径。"""
        store.rows("timing_run").clear()  # 显式制造无基线场景
        fresh = SegmentTimingService()
        run, msg = fresh.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:26:00",
        )
        self.assertIsNotNone(run, msg)
        compare = {c["路段编号"]: c for c in run["同期比较核对"]}
        # 基线是补报前自动生成的：R2-03 补报前 4 个、补报后 5 个，不可同期比较
        self.assertFalse(compare["SEG-R2-03"]["可同期比较"])
        self.assertEqual(compare["SEG-R2-03"]["补报前有效样本数"], 4)
        self.assertTrue(compare["SEG-R2-01"]["可同期比较"])
        labels = [r["运行标签"] for r in fresh.list_runs()]
        self.assertIn("中断补报前基线", labels)

    def test_backfill_unknown_trip_rejected(self) -> None:
        run, msg = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-9999", seq=99,
            arrival_time=f"{ANALYSIS_DATE} 09:00:00",
        )
        self.assertIsNone(run)
        self.assertIn("未找到", msg)

    def test_backfill_earlier_than_boarding_rejected(self) -> None:
        run, msg = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:00:00",
        )
        self.assertIsNone(run)
        self.assertIn("早于上车时间", msg)

    def test_backfill_bad_time_format_rejected(self) -> None:
        run, msg = self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time="not-a-time",
        )
        self.assertIsNone(run)
        self.assertIn("格式", msg)

    def test_missing_arrivals_remain_queryable(self) -> None:
        """未完成样本明细可独立查询；补报完成后该清单相应减少。"""
        missing = self.svc.list_missing_arrivals()
        self.assertEqual({(m["路段编号"], m["车辆班次"]) for m in missing}, {
            ("SEG-R1-01", "R1-0910"),
            ("SEG-R2-03", "R2-0810"),
            ("SEG-R2-03", "R2-0835"),
        })
        self.svc.backfill_arrival(
            segment="SEG-R2-03", trip="R2-0810", seq=5,
            arrival_time=f"{ANALYSIS_DATE} 08:26:00",
        )
        missing_after = self.svc.list_missing_arrivals()
        self.assertNotIn(("SEG-R2-03", "R2-0810"),
                         {(m["路段编号"], m["车辆班次"]) for m in missing_after})
        self.assertEqual(len(missing_after), 2)


class PublishDatasetTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        self.svc = SegmentTimingService()

    def test_publish_dataset_excludes_empty_and_incomplete(self) -> None:
        dataset = self.svc.publish_dataset()
        published = { (r["路段编号"], r["方向"]) for r in dataset["可发布计时结果"] }
        # 只有 4 个达标行进入发布数据集
        self.assertEqual(len(published), 4)
        self.assertIn(("SEG-R2-01", "去程"), published)
        self.assertNotIn(("SEG-R2-03", "去程"), published)
        self.assertNotIn(("SEG-R3-01", "去程"), published)
        empty = { (r["路段编号"], r["方向"]): r for r in dataset["空态路段"] }
        self.assertEqual(empty[("SEG-R2-02", "去程")]["覆盖状态"], STATUS_SUSPENDED)
        self.assertEqual(empty[("SEG-R2-03", "去程")]["覆盖状态"], STATUS_INTERRUPTED)
        self.assertIn("未以 0 分钟占位", dataset["排除样本说明"])

    def test_chart_coverage_carries_quantile_interval_and_empty_reason(self) -> None:
        chart = self.svc.chart_coverage()
        self.assertEqual(chart["图表名称"], "路段运输时长分位数与计时覆盖")
        by_key = { (r["路段编号"], r["方向"]): r for r in chart["序列"] }
        ok = by_key[("SEG-R1-01", "去程")]
        self.assertEqual(ok["P90"], 24.0)
        self.assertEqual(ok["可比区间"], [11.0, 12.0])
        empty = by_key[("SEG-R3-01", "去程")]
        self.assertIsNone(empty["P50"])
        self.assertTrue(empty["空态原因"])
        # 线路决策随图表结果一并下发
        self.assertEqual(len(chart["线路决策"]), 3)


class ApiEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        from fastapi.testclient import TestClient

        from app.main import app
        self.client = TestClient(app)

    def test_core_endpoints_and_backfill_flow(self) -> None:
        self.assertEqual(self.client.get("/api/health").json()["ok"], True)

        samples = self.client.get("/api/segment_timing/samples").json()
        self.assertEqual(samples["未完成样本数"], 3)

        missing = self.client.get("/api/segment_timing/missing_arrivals").json()
        self.assertEqual(missing["total"], 3)

        coverage = self.client.get("/api/segment_timing/coverage").json()
        self.assertEqual(coverage["汇总"]["有效样本总数"], 27)
        self.assertEqual(coverage["汇总"]["未完成样本总数"], 3)

        published = self.client.get("/api/data_service/timing_dataset").json()
        self.assertEqual(len(published["可发布计时结果"]), 4)

        chart = self.client.get("/api/chart/timing_coverage").json()
        self.assertEqual(len(chart["序列"]), 10)

        # 缺字段被拦下
        bad = self.client.post("/api/segment_timing/backfill_arrival", json={"values": {}})
        self.assertFalse(bad.json()["ok"])

        # 正常补报 -> 重算
        ok = self.client.post("/api/segment_timing/backfill_arrival", json={"values": {
            "segment": "SEG-R2-03", "trip": "R2-0810", "seq": 5,
            "arrival_time": f"{ANALYSIS_DATE} 08:26:00",
        }})
        self.assertTrue(ok.json()["ok"])

        # 重复补报幂等
        dup = self.client.post("/api/segment_timing/backfill_arrival", json={"values": {
            "segment": "SEG-R2-03", "trip": "R2-0810", "seq": 5,
            "arrival_time": f"{ANALYSIS_DATE} 08:30:00",
        }})
        self.assertFalse(dup.json()["ok"])

        runs = self.client.get("/api/segment_timing/runs").json()
        self.assertGreaterEqual(runs["total"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
