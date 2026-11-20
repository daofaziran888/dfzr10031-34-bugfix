"""路段取数示例数据。

围绕「运输时长分位数」口径准备三类原始数据，均按真实业务字段组织：

- ``segment``：路段及运营时段，包含停运、尖峰采集中断等状态；
- ``segment_event``：上报的上车/抵达事件，带车辆班次、通过序号、方向；
- ``duration_report``：上报的行驶时长，抵达事件缺失时为 null，且绝不用 0 分钟代替。

样本统计日固定为 2026-11-19，保证任何环境起服务后都能复现同一组核对结果。
"""
from __future__ import annotations

from typing import Any

ANALYSIS_DATE = "2026-11-19"
# 分位数发布的最小有效计时样本门槛（任务口径：达到样本门槛才允许发布分位数）。
SAMPLE_THRESHOLD = 5

# ---------------------------------------------------------------------------
# 路段（含运营时段）
# ---------------------------------------------------------------------------
SEGMENT_SEED: list[dict[str, Any]] = [
    # R1：样本充足线路
    {"id": 1, "路段编号": "SEG-R1-01", "线路编号": "R1", "线路名称": "1路 火车站—大学城",
     "起点": "火车站", "终点": "文化宫", "方向": "双向", "运营开始": "06:00", "运营结束": "22:00",
     "路段状态": "运营中", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    {"id": 2, "路段编号": "SEG-R1-02", "线路编号": "R1", "线路名称": "1路 火车站—大学城",
     "起点": "文化宫", "终点": "市政府", "方向": "双向", "运营开始": "06:00", "运营结束": "22:00",
     "路段状态": "运营中", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    {"id": 3, "路段编号": "SEG-R1-03", "线路编号": "R1", "线路名称": "1路 火车站—大学城",
     "起点": "市政府", "终点": "大学城", "方向": "双向", "运营开始": "06:00", "运营结束": "22:00",
     "路段状态": "运营中", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    # R2：中途失败线路（一段达标、一段停运、一段尖峰采集中断）
    {"id": 4, "路段编号": "SEG-R2-01", "线路编号": "R2", "线路名称": "2路 机场—客运中心",
     "起点": "机场", "终点": "会展中心", "方向": "双向", "运营开始": "06:30", "运营结束": "21:30",
     "路段状态": "运营中", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    {"id": 5, "路段编号": "SEG-R2-02", "线路编号": "R2", "线路名称": "2路 机场—客运中心",
     "起点": "会展中心", "终点": "高新园", "方向": "双向", "运营开始": "06:30", "运营结束": "21:30",
     "路段状态": "暂停运营", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    {"id": 6, "路段编号": "SEG-R2-03", "线路编号": "R2", "线路名称": "2路 机场—客运中心",
     "起点": "高新园", "终点": "客运中心", "方向": "双向", "运营开始": "06:30", "运营结束": "21:30",
     "路段状态": "采集中断", "中断开始": f"{ANALYSIS_DATE} 08:00:00",
     "中断结束": f"{ANALYSIS_DATE} 09:30:00", "样本门槛": SAMPLE_THRESHOLD},
    # R3：全日停运线路
    {"id": 7, "路段编号": "SEG-R3-01", "线路编号": "R3", "线路名称": "3路 港区环线（停运）",
     "起点": "港务大厦", "终点": "保税区", "方向": "双向", "运营开始": "07:00", "运营结束": "20:00",
     "路段状态": "暂停运营", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
    {"id": 8, "路段编号": "SEG-R3-02", "线路编号": "R3", "线路名称": "3路 港区环线（停运）",
     "起点": "保税区", "终点": "港务大厦", "方向": "双向", "运营开始": "07:00", "运营结束": "20:00",
     "路段状态": "暂停运营", "中断开始": None, "中断结束": None, "样本门槛": SAMPLE_THRESHOLD},
]


def _event(eid: int, code: str, segment: str, trip: str, seq: int, kind: str,
           direction: str, t: str | None) -> dict[str, Any]:
    """构造一条上下车事件；t 为 None 表示抵达事件缺失（采集中断后仍未恢复）。"""
    return {
        "id": eid, "事件编号": code, "统计日期": ANALYSIS_DATE, "路段编号": segment,
        "车辆班次": trip, "通过序号": seq, "事件类型": kind, "方向": direction,
        "事件时间": t, "采集来源": "车载终端",
    }


def _report(rid: int, code: str, segment: str, trip: str, seq: int, direction: str,
            board: str | None, arrive: str | None, duration: int | None,
            note: str = "") -> dict[str, Any]:
    """构造一条行驶时长上报；duration 为 None 表示抵达缺失，禁止补零。"""
    return {
        "id": rid, "上报编号": code, "统计日期": ANALYSIS_DATE, "路段编号": segment,
        "车辆班次": trip, "通过序号": seq, "方向": direction,
        "上车时间": board, "抵达时间": arrive, "行驶时长分钟": duration,
        "备注": note,
    }


# ---------------------------------------------------------------------------
# 上报的上下车事件
# ---------------------------------------------------------------------------
SEGMENT_EVENT_SEED: list[dict[str, Any]] = [
    # ===== R1 / SEG-R1-01 去程：6 个班次，含重复抵达、缺失抵达、超时抵达 =====
    _event(1, "EVT-0001", "SEG-R1-01", "R1-0701", 1, "上车", "去程", f"{ANALYSIS_DATE} 07:01:00"),
    _event(2, "EVT-0002", "SEG-R1-01", "R1-0701", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:13:00"),
    # 同一车辆班次+通过序号的重试补报抵达，只允许形成一个有效计时样本
    _event(3, "EVT-0003", "SEG-R1-01", "R1-0701", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:13:30"),
    _event(4, "EVT-0004", "SEG-R1-01", "R1-0715", 2, "上车", "去程", f"{ANALYSIS_DATE} 07:15:00"),
    _event(5, "EVT-0005", "SEG-R1-01", "R1-0715", 2, "抵达", "去程", f"{ANALYSIS_DATE} 07:25:00"),
    _event(6, "EVT-0006", "SEG-R1-01", "R1-0731", 3, "上车", "去程", f"{ANALYSIS_DATE} 07:31:00"),
    _event(7, "EVT-0007", "SEG-R1-01", "R1-0731", 3, "抵达", "去程", f"{ANALYSIS_DATE} 07:42:00"),
    _event(8, "EVT-0008", "SEG-R1-01", "R1-0805", 4, "上车", "去程", f"{ANALYSIS_DATE} 08:05:00"),
    _event(9, "EVT-0009", "SEG-R1-01", "R1-0805", 4, "抵达", "去程", f"{ANALYSIS_DATE} 08:16:00"),
    _event(10, "EVT-0010", "SEG-R1-01", "R1-0840", 5, "上车", "去程", f"{ANALYSIS_DATE} 08:40:00"),
    # 超时抵达：32 分钟，应进入样本并把高分位（P90）拉高
    _event(11, "EVT-0011", "SEG-R1-01", "R1-0840", 5, "抵达", "去程", f"{ANALYSIS_DATE} 09:12:00"),
    _event(12, "EVT-0012", "SEG-R1-01", "R1-0910", 6, "上车", "去程", f"{ANALYSIS_DATE} 09:10:00"),
    # 采集中断恢复后仍缺抵达事件：原记录必须可查，且绝不能以 0 分钟进入分位数
    # SEG-R1-01 返程：独立方向分组
    _event(13, "EVT-0013", "SEG-R1-01", "R1-1005", 7, "上车", "返程", f"{ANALYSIS_DATE} 10:05:00"),
    _event(14, "EVT-0014", "SEG-R1-01", "R1-1005", 7, "抵达", "返程", f"{ANALYSIS_DATE} 10:16:00"),
    _event(15, "EVT-0015", "SEG-R1-01", "R1-1040", 8, "上车", "返程", f"{ANALYSIS_DATE} 10:40:00"),
    _event(16, "EVT-0016", "SEG-R1-01", "R1-1040", 8, "抵达", "返程", f"{ANALYSIS_DATE} 10:53:00"),
    # 反向经过：与返程不是同一分组，单独统计
    _event(17, "EVT-0017", "SEG-R1-01", "R1-1110", 9, "上车", "反向", f"{ANALYSIS_DATE} 11:10:00"),
    _event(18, "EVT-0018", "SEG-R1-01", "R1-1110", 9, "抵达", "反向", f"{ANALYSIS_DATE} 11:24:00"),

    # ===== R1 / SEG-R1-02 去程：5 个有效班次 =====
    _event(19, "EVT-0019", "SEG-R1-02", "R1-0701", 1, "上车", "去程", f"{ANALYSIS_DATE} 07:14:00"),
    _event(20, "EVT-0020", "SEG-R1-02", "R1-0701", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:22:00"),
    _event(21, "EVT-0021", "SEG-R1-02", "R1-0715", 2, "上车", "去程", f"{ANALYSIS_DATE} 07:26:00"),
    _event(22, "EVT-0022", "SEG-R1-02", "R1-0715", 2, "抵达", "去程", f"{ANALYSIS_DATE} 07:35:00"),
    _event(23, "EVT-0023", "SEG-R1-02", "R1-0731", 3, "上车", "去程", f"{ANALYSIS_DATE} 07:43:00"),
    _event(24, "EVT-0024", "SEG-R1-02", "R1-0731", 3, "抵达", "去程", f"{ANALYSIS_DATE} 07:50:00"),
    _event(25, "EVT-0025", "SEG-R1-02", "R1-0805", 4, "上车", "去程", f"{ANALYSIS_DATE} 08:17:00"),
    _event(26, "EVT-0026", "SEG-R1-02", "R1-0805", 4, "抵达", "去程", f"{ANALYSIS_DATE} 08:27:00"),
    _event(27, "EVT-0027", "SEG-R1-02", "R1-0840", 5, "上车", "去程", f"{ANALYSIS_DATE} 09:13:00"),
    _event(28, "EVT-0028", "SEG-R1-02", "R1-0840", 5, "抵达", "去程", f"{ANALYSIS_DATE} 09:20:00"),

    # ===== R1 / SEG-R1-03 去程：5 个有效班次 =====
    _event(29, "EVT-0029", "SEG-R1-03", "R1-0701", 1, "上车", "去程", f"{ANALYSIS_DATE} 07:23:00"),
    _event(30, "EVT-0030", "SEG-R1-03", "R1-0701", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:34:00"),
    _event(31, "EVT-0031", "SEG-R1-03", "R1-0715", 2, "上车", "去程", f"{ANALYSIS_DATE} 07:36:00"),
    _event(32, "EVT-0032", "SEG-R1-03", "R1-0715", 2, "抵达", "去程", f"{ANALYSIS_DATE} 07:49:00"),
    _event(33, "EVT-0033", "SEG-R1-03", "R1-0731", 3, "上车", "去程", f"{ANALYSIS_DATE} 07:51:00"),
    _event(34, "EVT-0034", "SEG-R1-03", "R1-0731", 3, "抵达", "去程", f"{ANALYSIS_DATE} 08:00:00"),
    _event(35, "EVT-0035", "SEG-R1-03", "R1-0805", 4, "上车", "去程", f"{ANALYSIS_DATE} 08:28:00"),
    _event(36, "EVT-0036", "SEG-R1-03", "R1-0805", 4, "抵达", "去程", f"{ANALYSIS_DATE} 08:41:00"),
    _event(37, "EVT-0037", "SEG-R1-03", "R1-0840", 5, "上车", "去程", f"{ANALYSIS_DATE} 09:21:00"),
    _event(38, "EVT-0038", "SEG-R1-03", "R1-0840", 5, "抵达", "去程", f"{ANALYSIS_DATE} 09:35:00"),

    # ===== R2 / SEG-R2-01 去程：5 个有效班次（中断线路上唯一达标路段） =====
    _event(39, "EVT-0039", "SEG-R2-01", "R2-0700", 1, "上车", "去程", f"{ANALYSIS_DATE} 07:00:00"),
    _event(40, "EVT-0040", "SEG-R2-01", "R2-0700", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:18:00"),
    _event(41, "EVT-0041", "SEG-R2-01", "R2-0730", 2, "上车", "去程", f"{ANALYSIS_DATE} 07:30:00"),
    _event(42, "EVT-0042", "SEG-R2-01", "R2-0730", 2, "抵达", "去程", f"{ANALYSIS_DATE} 07:47:00"),
    _event(43, "EVT-0043", "SEG-R2-01", "R2-0940", 3, "上车", "去程", f"{ANALYSIS_DATE} 09:40:00"),
    _event(44, "EVT-0044", "SEG-R2-01", "R2-0940", 3, "抵达", "去程", f"{ANALYSIS_DATE} 10:00:00"),
    _event(45, "EVT-0045", "SEG-R2-01", "R2-1020", 4, "上车", "去程", f"{ANALYSIS_DATE} 10:20:00"),
    _event(46, "EVT-0046", "SEG-R2-01", "R2-1020", 4, "抵达", "去程", f"{ANALYSIS_DATE} 10:37:00"),
    _event(47, "EVT-0047", "SEG-R2-01", "R2-1105", 5, "上车", "去程", f"{ANALYSIS_DATE} 11:05:00"),
    _event(48, "EVT-0048", "SEG-R2-01", "R2-1105", 5, "抵达", "去程", f"{ANALYSIS_DATE} 11:21:00"),
    # SEG-R2-02 暂停运营：无任何车辆经过，无事件

    # ===== R2 / SEG-R2-03 去程：尖峰采集中断，中断前 4 个有效班次 + 2 个缺抵达 =====
    _event(49, "EVT-0049", "SEG-R2-03", "R2-0700", 1, "上车", "去程", f"{ANALYSIS_DATE} 07:19:00"),
    _event(50, "EVT-0050", "SEG-R2-03", "R2-0700", 1, "抵达", "去程", f"{ANALYSIS_DATE} 07:31:00"),
    _event(51, "EVT-0051", "SEG-R2-03", "R2-0730", 2, "上车", "去程", f"{ANALYSIS_DATE} 07:48:00"),
    _event(52, "EVT-0052", "SEG-R2-03", "R2-0730", 2, "抵达", "去程", f"{ANALYSIS_DATE} 07:58:00"),
    _event(53, "EVT-0053", "SEG-R2-03", "R2-0755", 3, "上车", "去程", f"{ANALYSIS_DATE} 07:55:00"),
    _event(54, "EVT-0054", "SEG-R2-03", "R2-0755", 3, "抵达", "去程", f"{ANALYSIS_DATE} 08:09:00"),
    _event(55, "EVT-0055", "SEG-R2-03", "R2-0940", 4, "上车", "去程", f"{ANALYSIS_DATE} 10:01:00"),
    _event(56, "EVT-0056", "SEG-R2-03", "R2-0940", 4, "抵达", "去程", f"{ANALYSIS_DATE} 10:14:00"),
    # 中断窗口内的两个班次：抵达事件当时缺失，恢复后仍缺，等待补报
    _event(57, "EVT-0057", "SEG-R2-03", "R2-0810", 5, "上车", "去程", f"{ANALYSIS_DATE} 08:10:00"),
    _event(58, "EVT-0058", "SEG-R2-03", "R2-0835", 6, "上车", "去程", f"{ANALYSIS_DATE} 08:35:00"),
    # SEG-R3 全日停运：无事件
]

# ---------------------------------------------------------------------------
# 上报的行驶时长（与事件同口径；缺抵达时为 null，绝不写 0）
# ---------------------------------------------------------------------------
DURATION_REPORT_SEED: list[dict[str, Any]] = [
    # R1 / SEG-R1-01 去程
    _report(1, "DUR-0001", "SEG-R1-01", "R1-0701", 1, "去程",
            f"{ANALYSIS_DATE} 07:01:00", f"{ANALYSIS_DATE} 07:13:00", 12, "含一条重复抵达补报"),
    _report(2, "DUR-0002", "SEG-R1-01", "R1-0715", 2, "去程",
            f"{ANALYSIS_DATE} 07:15:00", f"{ANALYSIS_DATE} 07:25:00", 10, ""),
    _report(3, "DUR-0003", "SEG-R1-01", "R1-0731", 3, "去程",
            f"{ANALYSIS_DATE} 07:31:00", f"{ANALYSIS_DATE} 07:42:00", 11, ""),
    _report(4, "DUR-0004", "SEG-R1-01", "R1-0805", 4, "去程",
            f"{ANALYSIS_DATE} 08:05:00", f"{ANALYSIS_DATE} 08:16:00", 11, ""),
    _report(5, "DUR-0005", "SEG-R1-01", "R1-0840", 5, "去程",
            f"{ANALYSIS_DATE} 08:40:00", f"{ANALYSIS_DATE} 09:12:00", 32, "超时抵达"),
    _report(6, "DUR-0006", "SEG-R1-01", "R1-0910", 6, "去程",
            f"{ANALYSIS_DATE} 09:10:00", None, None, "抵达事件缺失，禁止按 0 分钟处理"),
    # R1 / SEG-R1-01 返程、反向
    _report(7, "DUR-0007", "SEG-R1-01", "R1-1005", 7, "返程",
            f"{ANALYSIS_DATE} 10:05:00", f"{ANALYSIS_DATE} 10:16:00", 11, ""),
    _report(8, "DUR-0008", "SEG-R1-01", "R1-1040", 8, "返程",
            f"{ANALYSIS_DATE} 10:40:00", f"{ANALYSIS_DATE} 10:53:00", 13, ""),
    _report(9, "DUR-0009", "SEG-R1-01", "R1-1110", 9, "反向",
            f"{ANALYSIS_DATE} 11:10:00", f"{ANALYSIS_DATE} 11:24:00", 14, "反向经过，单独成组"),
    # R1 / SEG-R1-02 去程
    _report(10, "DUR-0010", "SEG-R1-02", "R1-0701", 1, "去程",
            f"{ANALYSIS_DATE} 07:14:00", f"{ANALYSIS_DATE} 07:22:00", 8, ""),
    _report(11, "DUR-0011", "SEG-R1-02", "R1-0715", 2, "去程",
            f"{ANALYSIS_DATE} 07:26:00", f"{ANALYSIS_DATE} 07:35:00", 9, ""),
    _report(12, "DUR-0012", "SEG-R1-02", "R1-0731", 3, "去程",
            f"{ANALYSIS_DATE} 07:43:00", f"{ANALYSIS_DATE} 07:50:00", 7, ""),
    _report(13, "DUR-0013", "SEG-R1-02", "R1-0805", 4, "去程",
            f"{ANALYSIS_DATE} 08:17:00", f"{ANALYSIS_DATE} 08:27:00", 10, ""),
    _report(14, "DUR-0014", "SEG-R1-02", "R1-0840", 5, "去程",
            f"{ANALYSIS_DATE} 09:13:00", f"{ANALYSIS_DATE} 09:20:00", 7, ""),
    # R1 / SEG-R1-03 去程
    _report(15, "DUR-0015", "SEG-R1-03", "R1-0701", 1, "去程",
            f"{ANALYSIS_DATE} 07:23:00", f"{ANALYSIS_DATE} 07:34:00", 11, ""),
    _report(16, "DUR-0016", "SEG-R1-03", "R1-0715", 2, "去程",
            f"{ANALYSIS_DATE} 07:36:00", f"{ANALYSIS_DATE} 07:49:00", 13, ""),
    _report(17, "DUR-0017", "SEG-R1-03", "R1-0731", 3, "去程",
            f"{ANALYSIS_DATE} 07:51:00", f"{ANALYSIS_DATE} 08:00:00", 9, ""),
    _report(18, "DUR-0018", "SEG-R1-03", "R1-0805", 4, "去程",
            f"{ANALYSIS_DATE} 08:28:00", f"{ANALYSIS_DATE} 08:41:00", 13, ""),
    _report(19, "DUR-0019", "SEG-R1-03", "R1-0840", 5, "去程",
            f"{ANALYSIS_DATE} 09:21:00", f"{ANALYSIS_DATE} 09:35:00", 14, ""),
    # R2 / SEG-R2-01 去程
    _report(20, "DUR-0020", "SEG-R2-01", "R2-0700", 1, "去程",
            f"{ANALYSIS_DATE} 07:00:00", f"{ANALYSIS_DATE} 07:18:00", 18, ""),
    _report(21, "DUR-0021", "SEG-R2-01", "R2-0730", 2, "去程",
            f"{ANALYSIS_DATE} 07:30:00", f"{ANALYSIS_DATE} 07:47:00", 17, ""),
    _report(22, "DUR-0022", "SEG-R2-01", "R2-0940", 3, "去程",
            f"{ANALYSIS_DATE} 09:40:00", f"{ANALYSIS_DATE} 10:00:00", 20, ""),
    _report(23, "DUR-0023", "SEG-R2-01", "R2-1020", 4, "去程",
            f"{ANALYSIS_DATE} 10:20:00", f"{ANALYSIS_DATE} 10:37:00", 17, ""),
    _report(24, "DUR-0024", "SEG-R2-01", "R2-1105", 5, "去程",
            f"{ANALYSIS_DATE} 11:05:00", f"{ANALYSIS_DATE} 11:21:00", 16, ""),
    # R2 / SEG-R2-03 去程：中断前 4 条有效，2 条缺抵达（等待补报）
    _report(25, "DUR-0025", "SEG-R2-03", "R2-0700", 1, "去程",
            f"{ANALYSIS_DATE} 07:19:00", f"{ANALYSIS_DATE} 07:31:00", 12, ""),
    _report(26, "DUR-0026", "SEG-R2-03", "R2-0730", 2, "去程",
            f"{ANALYSIS_DATE} 07:48:00", f"{ANALYSIS_DATE} 07:58:00", 10, ""),
    _report(27, "DUR-0027", "SEG-R2-03", "R2-0755", 3, "去程",
            f"{ANALYSIS_DATE} 07:55:00", f"{ANALYSIS_DATE} 08:09:00", 14, ""),
    _report(28, "DUR-0028", "SEG-R2-03", "R2-0940", 4, "去程",
            f"{ANALYSIS_DATE} 10:01:00", f"{ANALYSIS_DATE} 10:14:00", 13, ""),
    _report(29, "DUR-0029", "SEG-R2-03", "R2-0810", 5, "去程",
            f"{ANALYSIS_DATE} 08:10:00", None, None, "尖峰采集中断，抵达待补报"),
    _report(30, "DUR-0030", "SEG-R2-03", "R2-0835", 6, "去程",
            f"{ANALYSIS_DATE} 08:35:00", None, None, "尖峰采集中断，抵达待补报"),
]
