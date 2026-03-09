"""Web server adapter for Explicator.

Provides a browser-based interface for interacting with a ModelService.
Uses Server-Sent Events (SSE) to stream the AI tool-calling trace in real time,
so users can watch each tool call and result appear as it happens.

Usage::

    import explicator
    from myapp.model import build_service

    service = build_service()
    explicator.run_web(service)          # opens http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from explicator.application.service import ModelService

_service: ModelService | None = None
_static = Path(__file__).parent / "static"

app = FastAPI(title="Explicator")


def _get_service() -> ModelService:
    """Return the active service, raising if not yet initialised."""
    if _service is None:
        raise RuntimeError("Service not initialised — call run() first.")
    return _service


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the single-page web UI."""
    return (_static / "index.html").read_text()


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


@app.get("/api/schema")
def get_schema() -> dict[str, Any]:
    """Return the model schema."""
    return _get_service().get_model_schema().to_dict()


@app.get("/api/scenarios")
def get_scenarios() -> list[dict[str, Any]]:
    """Return all available scenario definitions."""
    return [s.to_dict() for s in _get_service().get_available_scenarios()]


@app.get("/api/overrides")
def get_overrides() -> list[dict[str, Any]]:
    """Return all currently active session-level overrides."""
    return [o.to_dict() for o in _get_service().get_active_overrides()]


@app.post("/api/reset")
def reset_overrides() -> dict[str, str]:
    """Clear all active overrides and restore model defaults."""
    return {"message": _get_service().reset_overrides()}


# ---------------------------------------------------------------------------
# SSE chat stream
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Request body for the streaming chat endpoint."""

    messages: list[dict[str, Any]]  # [{role, content}] — user/assistant only


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream the AI conversation trace as Server-Sent Events.

    Each event is a JSON object on a ``data:`` line. Event types:

    * ``thinking``      — provider call starting
    * ``tool_call``     — AI is calling a tool (includes name + arguments)
    * ``tool_result``   — tool returned (includes name + result)
    * ``assistant_text``— final AI response text
    * ``error``         — something went wrong
    """
    service = _get_service()

    from explicator.ai.dispatcher import ToolDispatcher
    from explicator.ai.orchestrator import run_turn
    from explicator.ai.providers.base import AIMessage
    from explicator.config import build_provider

    provider = build_provider()
    dispatcher = ToolDispatcher(service)
    messages = [
        AIMessage(role=m["role"], content=m.get("content")) for m in request.messages
    ]

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def on_event(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run_in_thread() -> None:
        try:
            run_turn(messages, provider, dispatcher, on_event=on_event)
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(exc)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=run_in_thread, daemon=True).start()

    async def generate() -> AsyncGenerator[str, None]:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    service: ModelService,
    host: str = "localhost",
    port: int = 8000,
) -> None:
    """Start the Uvicorn server and open the browser."""
    import webbrowser

    import uvicorn

    global _service
    _service = service

    url = f"http://{host}:{port}"
    print(f"\nExplicator web UI → {url}\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=port)
