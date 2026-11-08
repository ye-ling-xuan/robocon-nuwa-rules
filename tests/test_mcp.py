import asyncio
import json
from pathlib import Path
import sys

import httpx
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import pytest

ROOT = Path(__file__).resolve().parents[1]


def parameters():
    return StdioServerParameters(command=sys.executable, args=["-m", "server", "--port", "0"], cwd=str(ROOT))


async def test_real_stdio_mcp_tools_and_sync():
    async with asyncio.timeout(30):
        async with stdio_client(parameters()) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                assert "sync_answer" in initialized.instructions
                listing = await client.list_tools()
                assert {t.name for t in listing.tools} == {"search_rules", "sync_answer", "get_clause", "open_ui", "calc_score", "judge_foul", "check_protection"}
                r = await client.call_tool("search_rules", {"query": "TR拿着五色石还能拿塔基吗？"})
                assert not r.isError
                data = r.structuredContent
                assert [c["page"] for c in data["citations"]] == [17, 20]
                synced = await client.call_tool("sync_answer", {"question": data["question"], "answer": "不能。", "citations": data["citations"], "turn_id": data["turn_id"]})
                assert not synced.isError and synced.structuredContent["synced"]
                invalid = await client.call_tool("sync_answer", {"question": data["question"], "answer": "不能。", "citations": [{"clause_id": "3.6.8", "page": 99}]})
                assert invalid.isError
                score = await client.call_tool("calc_score", {"items": [{"kind": "塔顶"}], "level": "L2", "question": "L2 塔顶多少分？"})
                assert score.structuredContent["total"] == 80
                foul = await client.call_tool("judge_foul", {"action": "TR携带4个塔基会怎样"})
                assert foul.structuredContent["disposition"] == "强制重试"
                protection = await client.call_tool("check_protection", {"towers": [{"id": "a"}]})
                assert protection.structuredContent["satisfied"] is None
                ui = (await client.call_tool("open_ui", {})).structuredContent
                assert ui["sampling_supported"] is False


@pytest.mark.parametrize("valid", [True, False])
async def test_real_mcp_sampling_via_web_without_provider_api(valid):
    requests = []

    async def sampling_callback(context, params):
        requests.append(params)
        assert params.modelPreferences is None
        return types.CreateMessageResult(role="assistant", content=types.TextContent(type="text", text=json.dumps({
            "answer": "80 分。[8.1.3 · P24]" if valid else "虚构回答。[99.9.9 · P99]",
            "clause_ids": ["8.1.3"] if valid else ["99.9.9"],
        }, ensure_ascii=False)), model="test-host-model", stopReason="endTurn")

    async with asyncio.timeout(30):
        async with stdio_client(parameters()) as (reader, writer):
            async with ClientSession(reader, writer, sampling_callback=sampling_callback) as client:
                await client.initialize()
                ui = (await client.call_tool("open_ui", {})).structuredContent
                assert ui["sampling_supported"] is True
                base = ui["ui_url"].split("/?")[0]
                async with httpx.AsyncClient(timeout=20) as http:
                    response = await http.post(base + "/api/ask", params={"session": ui["session"]}, json={"question": "L2 塔顶多少分？"})
                    assert response.status_code == 200
                    result = response.json()
                    if valid:
                        assert "80" in result["answer"] and result["citations"][0]["page"] == 24
                    else:
                        assert result["answer"] == "规则未明确，请以原文/裁判为准。"
                        assert result["citations"] == []
                assert len(requests) == 1
