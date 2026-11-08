"""Conservative, explicit-pattern foul triage; never interprets arbitrary prose as a verdict."""
from __future__ import annotations

import re
from ..rules import UNSPECIFIED, normalize

CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def quantity(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value and value.count("十") == 1:
        left, right = value.split("十")
        if len(left) <= 1 and len(right) <= 1:
            return CN_NUMBERS.get(left, 1) * 10 + CN_NUMBERS.get(right, 0)
    if value in CN_NUMBERS:
        return CN_NUMBERS[value]
    raise ValueError("请用阿拉伯数字说明持有数量")


def judge(store, action: str) -> dict:
    if not action.strip() or len(action) > 4000:
        raise ValueError("action 应为 1 到 4000 字符")
    text = normalize(action)
    robot = "TR" if "tr" in text else "BR" if "br" in text else None
    if "tr" in text and "br" in text:
        return {"verdict": "needs_clarification", "reason": "请分别描述 TR 和 BR 的动作与各自持有的数量。", "citations": store.citations(["4.4.2", "6.5"])}
    # Questions with conditions, negations or explicit releases need context.
    uncertain = bool(re.search(r"没|不|未|如果|假如|假设|放下|放开|释放|分.{0,3}次|分别|轮流|还是|之前|之后|先.{0,20}(?:再|然后)|-\d+个", text))
    carry = bool(re.search(r"携带|拿着|拿了|持有|抬起|带着|同时拿|拿", text))
    counts = []
    for value in re.findall(r"(\d+|[一二两三四五六七八九十百]+)个(?:塔基|中段|塔顶)", text):
        try:
            counts.append(quantity(value))
        except ValueError:
            uncertain = True
    mixed_stone = "五色石" in text and any(k in text for k in ("塔基", "中段", "塔顶")) and carry
    limit = {"TR": 3, "BR": 2}.get(robot)
    if carry and (counts or mixed_stone):
        if uncertain or (limit is None and not mixed_stone):
            return {"verdict": "needs_clarification", "reason": "请确认机器人类型、是否同一时刻持有，以及塔基/中段/塔顶合计数量。", "citations": store.citations(["6.5", "4.4.2"])}
        if mixed_stone or (limit is not None and sum(counts) > limit):
            detail = "携带五色石时同时持有的所有塔基/中段/塔顶，须在强制性重试时取出并禁用。" if mixed_stone else "超出限制后拿取的所有塔基/中段/塔顶，须在强制性重试时取出并禁用。"
            return {"verdict": "foul", "foul_type": "超限携带犯规", "disposition": "强制重试", "reason": detail,
                    "robot": robot, "count": sum(counts) if counts else None, "limit": limit,
                    "citations": store.citations(["6.5", "4.4.2", "5.3.3"])}
        return {"verdict": "no_overcarry_foul", "reason": "输入数量未超过该机器人的携带上限；其它行为是否犯规仍须分别核对。", "citations": store.citations(["4.4.2", "6.5"])}
    # Other situations return candidate clauses, never an unsupported penalty.
    found = store.search(action, 8)
    related = [c for c in found if c["clause_id"].startswith(("6.", "7.", "5."))]
    return {"verdict": "needs_referee" if related else "unspecified",
            "reason": "请结合所列原文及现场情况由裁判确认。" if related else UNSPECIFIED, "citations": related[:5]}
