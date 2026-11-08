"""Lazily bind a loopback socket, falling back to an OS-assigned free port."""
from __future__ import annotations

import asyncio
import socket
import threading
import time

import uvicorn

from .app import create_app


class UIHost:
    def __init__(self, service, port: int = 8765):
        if not 0 <= port <= 65535:
            raise ValueError("port 必须在 0 到 65535 之间")
        self.service = service
        self.port = port
        self.server = None
        self.thread = None
        self.socket = None
        self._lock = threading.Lock()
        self._error = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?session={self.service.state.session_id}"

    def ensure_started(self) -> bool:
        with self._lock:
            if self.thread and self.thread.is_alive() and self.server.started:
                return False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(("127.0.0.1", self.port))
            except OSError:
                sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            sock.setblocking(False)
            self.socket = sock
            self.port = sock.getsockname()[1]
            self._error = None
            self.server = uvicorn.Server(uvicorn.Config(create_app(self.service), host="127.0.0.1", port=self.port,
                                                       log_level="warning", access_log=False, log_config=None))

            def serve():
                try:
                    asyncio.run(self.server.serve(sockets=[sock]))
                except BaseException as exc:
                    self._error = exc
                finally:
                    sock.close()

            self.thread = threading.Thread(target=serve, name="nuwa-local-ui", daemon=True)
            self.thread.start()
            deadline = time.monotonic() + 8
            while not self.server.started:
                if self._error or not self.thread.is_alive() or time.monotonic() > deadline:
                    self.server.should_exit = True
                    raise RuntimeError("本地规则界面启动失败，请检查本机端口或进程") from self._error
                time.sleep(.01)
            return True

    def stop(self):
        with self._lock:
            if self.server:
                self.server.should_exit = True
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join(timeout=5)
