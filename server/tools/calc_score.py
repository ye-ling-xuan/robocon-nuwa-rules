from __future__ import annotations

from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field


class ScoreItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["塔基", "中段", "塔顶", "五色石", "base", "middle", "top", "stone"]
    count: int = Field(default=1, strict=True, ge=0, le=1000)
    mode: Literal["build", "transport"] = "build"
    eligible: bool = True


def calculate(store, items: list[ScoreItem], level: Literal["L1", "L2"]) -> dict:
    if not items or len(items) > 100:
        raise ValueError("items 应包含 1 到 100 项")
    # Read the actual table values, so replacing the dataset cannot leave stale scores.
    table = {"L1": {}, "L2": {}}
    source = re.sub(r"\s+", "", store.get("8.1.3")["text"])
    for kind, suffix in (("塔基", "塔底部"), ("中段", "塔中部"), ("塔顶", "塔上部")):
        match = re.search(rf"{kind}/{suffix}(\d+)分(\d+)分", source)
        if not match:
            raise ValueError("计分表结构变化，请人工校对 8.1.3 后再使用算分工具")
        table["L1"][kind], table["L2"][kind] = map(int, match.groups())
    transport_match = re.search(r"每个记\s*(\d+)\s*分", store.get("8.1.1")["text"])
    stone_match = re.search(r"获得\s*(\d+)\s*分", store.get("8.1.5")["text"])
    if not transport_match or not stone_match:
        raise ValueError("计分条款结构变化，请人工校对")
    aliases = {"base": "塔基", "middle": "中段", "top": "塔顶", "stone": "五色石"}
    rows, ids = [], []
    stone_count = sum(item.count for item in items if aliases.get(item.kind, item.kind) == "五色石")
    if stone_count > 1:
        raise ValueError("只有首个安放的五色石有效；每队不能累计多个五色石得分")
    for item in items:
        kind = aliases.get(item.kind, item.kind)
        if item.mode == "transport":
            unit, cid = (0 if kind == "五色石" else int(transport_match[1])), "8.1.1"
        elif kind == "五色石":
            if level != "L2":
                raise ValueError("五色石仅在 L2 中央基座成功安放后计分")
            unit, cid = int(stone_match[1]), "8.1.5"
        else:
            unit, cid = table[level][kind], "8.1.3"
        subtotal = unit * item.count if item.eligible else 0
        ids.append(cid)
        if not item.eligible:
            ids.append("8.1.6")
        rows.append({"kind": kind, "count": item.count, "mode": item.mode, "unit_score": unit,
                     "eligible": item.eligible, "subtotal": subtotal, "clause_id": cid})
    return {"level": level, "breakdown": rows, "total": sum(row["subtotal"] for row in rows),
            "assumptions": "按输入物品已满足正确放置、脱离机器人及颜色归属等计分条件估算；未自动判定比赛现场状态或两队归属。搬运分须显式使用 transport。",
            "citations": store.citations(ids)}
