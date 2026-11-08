"""Process-local, thread-safe conversation state, with bounded SSE replay."""
from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import secrets
import threading
from uuid import uuid4


class SessionState:
    def __init__(self):
        self.session_id = secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.turns: list[dict] = []
        self.selected: dict | None = None
        self.sampling_supported = False
        self.sampling_busy = False
        self.demo = False
        self.sequence = 0
        self.events: deque[dict] = deque(maxlen=512)
        self.subscribers: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy({"turns": self.turns, "selected": self.selected,
                             "sampling_supported": self.sampling_supported, "sampling_busy": self.sampling_busy,
                             "sequence": self.sequence, "demo": self.demo})

    def publish(self, event: str, data: dict) -> dict:
        with self.lock:
            self.sequence += 1
            item = {"id": self.sequence, "event": event, "data": deepcopy(data)}
            self.events.append(item)
            recovery = {"id": self.sequence, "event": "snapshot", "data": self.snapshot()}
            for key, (loop, queue) in list(self.subscribers.items()):
                if loop.is_closed():
                    self.subscribers.pop(key, None)
                    continue

                def enqueue(q=queue, value=item, reset=recovery):
                    if q.full():
                        while not q.empty():
                            q.get_nowait()
                        q.put_nowait(reset)
                    else:
                        q.put_nowait(value)
                loop.call_soon_threadsafe(enqueue)
            return deepcopy(item)

    def subscribe(self, last_id: int | None = None) -> tuple[str, asyncio.Queue]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=512)
        key = uuid4().hex
        with self.lock:
            replayable = last_id is not None and self.events and self.events[0]["id"] - 1 <= last_id <= self.sequence
            if replayable:
                for item in self.events:
                    if item["id"] > last_id:
                        queue.put_nowait(deepcopy(item))
            else:
                queue.put_nowait({"id": self.sequence, "event": "snapshot", "data": self.snapshot()})
            self.subscribers[key] = (loop, queue)
        return key, queue

    def unsubscribe(self, key: str):
        with self.lock:
            self.subscribers.pop(key, None)

    def question(self, question: str, citations: list[dict]) -> dict:
        question = question.strip()
        if not question or len(question) > 4000:
            raise ValueError("问题应为 1 到 4000 字符")
        with self.lock:
            pending = next((t for t in reversed(self.turns) if t["question"] == question and t["status"] == "pending"), None)
            if pending:
                pending["citations"] = deepcopy(citations)
                turn = pending
            else:
                turn = {"id": uuid4().hex, "question": question, "answer": None, "citations": deepcopy(citations),
                        "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}
                self.turns.append(turn)
                if len(self.turns) > 200:
                    self.turns.pop(0)
                    self.publish("snapshot", self.snapshot())
            self.publish("question", {"turn": turn})
            self.publish("citations", {"turn_id": turn["id"], "citations": citations})
            if citations:
                self.select(citations[0])
            else:
                self.clear()
            return deepcopy(turn)

    def answer(self, question: str, answer: str, citations: list[dict], turn_id: str | None = None) -> dict:
        with self.lock:
            if turn_id:
                turn = next((t for t in self.turns if t["id"] == turn_id), None)
                if turn is None or turn["question"] != question.strip():
                    raise ValueError("turn_id 与问题不匹配")
            else:
                turn = next((t for t in reversed(self.turns) if t["question"] == question.strip() and t["status"] == "pending"), None)
                if turn is None:
                    created = self.question(question, citations)
                    turn = next(t for t in self.turns if t["id"] == created["id"])
            same_citations = [c["clause_id"] for c in turn["citations"]] == [c["clause_id"] for c in citations]
            turn.update(answer=answer, citations=deepcopy(citations), status="answered")
            self.publish("answer", {"turn": turn})
            self.publish("citations", {"turn_id": turn["id"], "citations": citations})
            # Preserve a user-selected citation while its question is completed.
            selected_is_current = self.selected and self.selected["clause_id"] in {c["clause_id"] for c in citations}
            if citations and not (same_citations and selected_is_current):
                self.select(citations[0])
            elif not citations:
                self.clear()
            return deepcopy(turn)

    def select(self, citation: dict):
        with self.lock:
            self.selected = deepcopy(citation)
            self.publish("jump", {"citation": citation})

    def clear(self):
        with self.lock:
            self.selected = None
            self.publish("clear", {})

    def set_sampling(self, supported: bool):
        with self.lock:
            if self.sampling_supported != supported:
                self.sampling_supported = supported
                self.publish("capabilities", {"sampling_supported": supported})
