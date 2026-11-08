from __future__ import annotations

import asyncio
import json


def encode_event(item: dict) -> str:
    return f"id: {item['id']}\nevent: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False, separators=(',', ':'))}\n\n"


async def event_stream(request, state, last_id: int | None = None):
    key, queue = state.subscribe(last_id)
    try:
        yield "retry: 1500\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
                yield encode_event(item)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        state.unsubscribe(key)
