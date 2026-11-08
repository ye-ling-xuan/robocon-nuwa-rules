"""Test host for the real stdio MCP server; JSON lines control only this harness."""
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


async def sample(context, params):
    return types.CreateMessageResult(role="assistant", content=types.TextContent(type="text", text=json.dumps({
        "answer": "80 分。[8.1.3 · P24]", "clause_ids": ["8.1.3"],
    }, ensure_ascii=False)), model="test-host-model", stopReason="endTurn")


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "server", "--port", "0"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, sampling_callback=sample if "--sampling" in sys.argv else None) as client:
            await client.initialize()
            emit({"ready": True})
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                command = json.loads(line)
                if command["tool"] == "_quit":
                    break
                result = await client.call_tool(command["tool"], command.get("args", {}))
                emit({"id": command["id"], "error": result.isError, "data": result.structuredContent,
                      "message": "\n".join(c.text for c in result.content if hasattr(c, "text")) if result.isError else None})


asyncio.run(main())
