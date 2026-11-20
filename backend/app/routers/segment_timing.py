"""路段取数接口。

提供原始数据查询（路段/运营时段、上下车事件、行驶时长上报）、计时样本与覆盖结果、
计算快照管理，以及中断恢复后的抵达补报与重算核对。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload
from app.segment_seed import ANALYSIS_DATE
from app.services.segment_timing import service

router = APIRouter(prefix="/api/segment_timing", tags=["路段取数"])


@router.get("/segments")
def list_segments(line: str | None = Query(default=None, description="按线路编号过滤")) -> dict[str, Any]:
    """路段及运营时段清单，含停运与采集中断标记。"""
    items = service.list_segments(line)
    return {"total": len(items), "items": items}


@router.get("/events")
def list_events(
    segment: str | None = Query(default=None, description="按路段编号过滤"),
    direction: str | None = Query(default=None, description="按方向过滤：去程/返程/反向"),
) -> dict[str, Any]:
    """上报的上下车事件；采集中断恢复后仍缺抵达的原始上车记录也在此可查。"""
    items = service.list_events(segment, direction)
    return {"total": len(items), "items": items}


@router.get("/duration_reports")
def list_duration_reports(
    segment: str | None = Query(default=None),
    direction: str | None = Query(default=None),
) -> dict[str, Any]:
    """上报的行驶时长；缺抵达事件时行驶时长为 null，不允许出现 0 分钟占位。"""
    items = service.list_reports(segment, direction)
    return {"total": len(items), "items": items}


@router.get("/samples")
def list_samples(date: str = ANALYSIS_DATE) -> dict[str, Any]:
    """归并后的计时样本：重复抵达只算一次，缺抵达样本标记为未完成且不带时长。"""
    items = service.build_samples(date)
    valid = sum(1 for r in items if r["是否有效样本"])
    return {
        "统计日期": date,
        "total": len(items),
        "有效样本数": valid,
        "未完成样本数": len(items) - valid,
        "items": items,
    }


@router.get("/missing_arrivals")
def list_missing_arrivals(date: str = ANALYSIS_DATE) -> dict[str, Any]:
    """恢复后仍缺抵达事件的原始上车记录（含中断窗口内未补报班次），随时可查。"""
    items = service.list_missing_arrivals(date)
    return {"统计日期": date, "total": len(items), "items": items}


@router.get("/coverage")
def get_coverage(date: str = ANALYSIS_DATE) -> dict[str, Any]:
    """路段计时覆盖结果（图表配置与数据API发布共同消费的主口径）。"""
    run = service.ensure_run("自动计算", date)
    return {
        "统计日期": date,
        "运行编号": run["运行编号"],
        "发布策略": run["发布策略"],
        "汇总": run["汇总"],
        "items": run["覆盖结果"],
        "线路决策": run["线路决策"],
    }


@router.get("/runs")
def list_runs(date: str | None = Query(default=None)) -> dict[str, Any]:
    """计算快照清单：中断补报前后各保留一份，用于同期比较核对。"""
    items = service.list_runs(date)
    return {"total": len(items), "items": items}


@router.get("/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    run = service.get_run(run_id)
    if run is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"计算快照 {run_id} 不存在")
    return run


@router.post("/runs/actions", response_model=ActionResult)
def create_run(payload: EntryPayload) -> ActionResult:
    """按当前原始数据生成一份新的计时覆盖快照。"""
    values = payload.values
    label = str(values.get("label") or "手动计算").strip()
    date = str(values.get("date") or ANALYSIS_DATE).strip()
    run = service.create_run(label, date)
    return ActionResult(ok=True, message=f"计算快照 {run['运行编号']} 已生成", entry=run)


@router.post("/backfill_arrival", response_model=ActionResult)
def backfill_arrival(payload: EntryPayload) -> ActionResult:
    """中断恢复后补报抵达事件：幂等去重、重算覆盖，并输出补报前后同期可比性核对。"""
    values = payload.values
    required = ["segment", "trip", "seq", "arrival_time"]
    missing = [name for name in required if values.get(name) in (None, "")]
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    run, message = service.backfill_arrival(
        segment=str(values["segment"]).strip(),
        trip=str(values["trip"]).strip(),
        seq=int(values["seq"]),
        arrival_time=str(values["arrival_time"]).strip(),
        direction=(str(values["direction"]).strip() if values.get("direction") else None),
    )
    if run is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=run)
