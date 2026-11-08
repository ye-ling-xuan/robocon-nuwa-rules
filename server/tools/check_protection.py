from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Tower(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    zone: Literal["L1_private", "L1_public", "L2"] | None = None
    standing: bool | None = None
    complete: bool | None = None
    in_build_site: bool | None = None
    top_matches_team: bool | None = None


def check(store, towers: list[Tower], previously_satisfied: bool = False) -> dict:
    if len(towers) > 100:
        raise ValueError("最多输入 100 座塔")
    if len({t.id for t in towers}) != len(towers):
        raise ValueError("每座塔的 id 必须唯一，不能重复计算同一座塔")
    citations = store.citations(["3.6.1", "3.6.2", "2.22", "3.5.7"])
    if previously_satisfied:
        return {"satisfied": True, "reason": "此前已满足保护法则，此后被对手修改仍视为永久满足。", "citations": citations}
    if not towers:
        return {"satisfied": None, "reason": "尚未提供塔的情况，请补充至少两座塔的位置及状态。", "missing": ["towers"], "citations": citations}
    eligible, possible, missing = [], [], []
    for t in towers:
        values = (t.standing, t.complete, t.in_build_site, t.top_matches_team)
        valid = all(v is True for v in values) and t.zone is not None
        if valid:
            eligible.append(t)
        if not any(v is False for v in values):
            possible.append(t)
            for name in ("zone", "standing", "complete", "in_build_site", "top_matches_team"):
                if getattr(t, name) is None:
                    missing.append({"tower_id": t.id, "field": name})
    public = [t for t in eligible if t.zone in ("L1_public", "L2")]
    if len(eligible) >= 2 and public:
        satisfied, reason = True, "同时耸立且属于本队的全塔至少两座，其中至少一座位于 L1 公共区或 L2 的建塔处。"
    elif missing:
        satisfied, reason = None, "信息不足；请补充塔的位置、是否同时耸立、结构完整、位于建塔处及塔顶是否与本队同色。"
    elif len(possible) < 2 or (possible and not any(t.zone in (None, "L1_public", "L2") for t in possible)):
        satisfied, reason = False, "当前输入不满足两座同时耸立的本队全塔及至少一座公共区全塔的条件；若此前曾满足，请提供该事实。"
    else:
        satisfied, reason = False, "当前输入不满足保护法则。"
    return {"satisfied": satisfied, "reason": reason, "eligible_towers": [t.id for t in eligible],
            "public_towers": [t.id for t in public], "missing": missing, "citations": citations}
