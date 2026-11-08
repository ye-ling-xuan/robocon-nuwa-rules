from __future__ import annotations

import argparse
import sys
import threading
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .service import RuleService
from .tools.calc_score import ScoreItem
from .tools.check_protection import Tower

INSTRUCTIONS = """回答 ROBOCON 女娲补天 V3 规则问题时，先调用 search_rules，或调用相应的计分/犯规/保护法则工具。
模型由你（宿主 Agent）提供，不需要 API Key。所有页码、原文和坐标必须取自工具返回的 citations。
首次返回 ui_url 时告诉用户：已打开规则查询界面：<ui_url>。本地页面已经由工具自动启动。
回答先给结论，再按 [条款号 · P页码] 引用依据。没有依据时回答：规则未明确，请以原文/裁判为准。
给用户完整回答后必须调用 sync_answer(question, answer, citations, turn_id)，原样传回本次引用和 turn_id。
用户想看原文时使用 get_clause 或 open_ui。check_protection 缺少塔的现场事实时先问清楚，禁止猜测。
"""


def create_mcp(service: RuleService | None = None) -> FastMCP:
    service = service or RuleService()
    mcp = FastMCP("robocon-nuwa-rules", instructions=INSTRUCTIONS)
    annotations = ToolAnnotations(destructiveHint=False, openWorldHint=False)

    @mcp.tool(annotations=annotations)
    async def search_rules(query: str, ctx: Context, limit: int = 5) -> dict[str, Any]:
        """检索 V3 原文；自动启动本地界面、同步问题与引用并翻页。首次展示 ui_url；回答后必须 sync_answer。limit=1..12。"""
        service.bind_host(ctx)
        return service.search_rules(query, limit)

    @mcp.tool(annotations=annotations)
    async def sync_answer(question: str, answer: str, citations: list[dict[str, Any]], ctx: Context, turn_id: str | None = None) -> dict[str, Any]:
        """每次规则回答后必须调用，更新同一条问答。传回检索工具的 citations/turn_id；拒绝虚构条款、页码、引用。无依据强制返回未明确。"""
        service.bind_host(ctx)
        return service.sync_answer(question, answer, citations, turn_id)

    @mcp.tool(annotations=annotations)
    async def get_clause(clause_id: str, ctx: Context) -> dict[str, Any]:
        """读取真实条款及关联条款，同时在原文中跳页高亮；不新增问答。"""
        service.bind_host(ctx)
        return service.get_clause(clause_id)

    @mcp.tool(annotations=annotations)
    async def open_ui(ctx: Context) -> dict[str, Any]:
        """启动或返回已有本地集成界面链接，包含本次宿主的 Sampling 支持状态。"""
        service.bind_host(ctx)
        return service.open_ui()

    @mcp.tool(annotations=annotations)
    async def calc_score(items: list[ScoreItem], level: Literal["L1", "L2"], ctx: Context, question: str | None = None) -> dict[str, Any]:
        """算分并同步到界面。items=[{kind:塔顶,count:1,mode:build,eligible:true}]。仅按已满足计分条件估算；搬运用 transport。question 传用户原问题；完成后 sync_answer。"""
        service.bind_host(ctx)
        return service.calc_score(items, level, question)

    @mcp.tool(annotations=annotations)
    async def judge_foul(action: str, ctx: Context) -> dict[str, Any]:
        """核对动作及可能犯规；明确超限携带才给出处罚。含否定/先后关系或事实不足时请澄清。同步问题及引用；完成后 sync_answer。"""
        service.bind_host(ctx)
        return service.judge_foul(action)

    @mcp.tool(annotations=annotations)
    async def check_protection(towers: list[Tower], ctx: Context, previously_satisfied: bool = False, question: str | None = None) -> dict[str, Any]:
        """按 3.6.1/3.6.2 核对保护法则。每座塔需要唯一 id、zone(L1_private/L1_public/L2)、standing、complete、in_build_site、top_matches_team；未知字段留 null，禁止猜测。previously_satisfied 仅在用户确认此前满足时为 true。"""
        service.bind_host(ctx)
        return service.check_protection(towers, previously_satisfied, question)

    return mcp


def main():
    parser = argparse.ArgumentParser(description="ROBOCON Nuwa V3 rules MCP; no model API configuration required")
    parser.add_argument("--port", type=int, default=8765, help="preferred local UI port; auto fallback if occupied")
    parser.add_argument("--ui", action="store_true", help="open standalone UI, without an MCP host")
    parser.add_argument("--demo", action="store_true", help="standalone UI with clearly identified, deterministic demo Q&A")
    args = parser.parse_args()
    service = RuleService(port=args.port)
    try:
        if args.ui or args.demo:
            if args.demo:
                from .demo import populate
                populate(service)
            print(service.open_ui()["ui_url"], flush=True)
            threading.Event().wait()
        else:
            create_mcp(service).run(transport="stdio")
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == "__main__":
    main()
