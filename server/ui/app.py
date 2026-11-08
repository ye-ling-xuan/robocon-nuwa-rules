from __future__ import annotations

from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .sse import event_stream

STATIC = Path(__file__).resolve().parent / "static"


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class JumpRequest(BaseModel):
    clause_id: str = Field(min_length=1, max_length=32, pattern=r"^\d+(?:\.\d+){0,2}$")


def create_app(service) -> FastAPI:
    app = FastAPI(title="女娲补天 · 规则工作台", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # No cross-origin API access, including browser-to-loopback requests.
        origin = request.headers.get("origin")
        local_origins = {f"http://127.0.0.1:{service.ui.port}", f"http://localhost:{service.ui.port}"}
        if origin and origin not in local_origins:
            return JSONResponse({"detail": "只接受本地同源请求"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "不接受跨站请求"}, status_code=403)
        protected = request.url.path in ("/", "/events", "/rules.pdf") or request.url.path.startswith("/api/")
        if protected and not secrets.compare_digest(request.query_params.get("session", "").encode(), service.state.session_id.encode()):
            return JSONResponse({"detail": "请使用 Agent 返回的完整会话链接"}, status_code=403)
        if request.method == "POST" and request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"detail": "需要 JSON 请求"}, status_code=415)
        length = request.headers.get("content-length", "0") or "0"
        if not length.isdigit():
            return JSONResponse({"detail": "无效请求长度"}, status_code=400)
        if int(length) > 32768:
            return JSONResponse({"detail": "请求过大"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data: blob:; connect-src 'self'; "
            "worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if protected:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    async def health():
        return {"service": "robocon-nuwa-rules", "version": "0.1.0"}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state():
        return {**service.state.snapshot(), "rule_meta": service.store.meta,
                "clause_count": len(service.store.clauses), "pdf_url": f"/rules.pdf?session={service.state.session_id}"}

    @app.get("/rules.pdf")
    async def pdf():
        return FileResponse(service.store.data_dir / "rules.pdf", media_type="application/pdf")

    @app.get("/events")
    async def events(request: Request):
        last_id = request.headers.get("last-event-id", "")
        cursor = int(last_id) if last_id.isdigit() else None
        return StreamingResponse(event_stream(request, service.state, cursor), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/jump")
    async def jump(payload: JumpRequest):
        try:
            citation = service.store.citation(payload.clause_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        service.state.select(citation)
        return {"citation": citation}

    @app.post("/api/clear")
    async def clear():
        service.state.clear()
        return {"cleared": True}

    @app.post("/api/ask")
    async def ask(payload: AskRequest):
        try:
            return await service.sample_question(payload.question.strip())
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
