"""Explicator — provider-agnostic AI interface for scenario-driven modelling."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from explicator.adapters.data.in_memory import (
    FunctionalScenarioRunner,
    InMemoryModelRepository,
)
from explicator.application.service import ModelService
from explicator.domain.models import (
    InputField,
    ModelSchema,
    OutputField,
    Override,
    ScenarioComparison,
    ScenarioDefinition,
    ScenarioResult,
)
from explicator.domain.ports import ModelRepository, ScenarioRunner

if TYPE_CHECKING:
    from explicator.ai.providers.base import AIProvider

__version__ = "0.1.0"

__all__ = [
    "ModelService",
    "ModelSchema",
    "InputField",
    "OutputField",
    "ScenarioDefinition",
    "ScenarioResult",
    "ScenarioComparison",
    "Override",
    "FunctionalScenarioRunner",
    "InMemoryModelRepository",
    "ModelRepository",
    "ScenarioRunner",
    "create",
    "run_mcp",
    "run_chat",
    "run_web",
    "load_service",
]


def create(
    model_fn: Callable[[dict[str, Any]], dict[str, Any]],
    base_inputs: dict[str, Any],
    schema: ModelSchema,
    scenarios: list[ScenarioDefinition],
) -> ModelService:
    """Create a ModelService from a model function, schema, and scenario list.

    This is the quickest way to wrap a plain Python model function.
    For custom storage or execution backends, instantiate ModelService directly
    using your own ModelRepository and ScenarioRunner implementations.

    Example::

        service = explicator.create(
            model_fn=my_model,
            base_inputs={"rate": 5.0},
            schema=my_schema,
            scenarios=my_scenarios,
        )
    """
    repo = InMemoryModelRepository(schema=schema, scenarios=scenarios)
    runner = FunctionalScenarioRunner(model_fn=model_fn, base_inputs=base_inputs)
    return ModelService(runner=runner, repository=repo)


def run_mcp(service: ModelService) -> None:
    """Start the MCP server backed by the given service.

    Intended as the entry point in your run script::

        if __name__ == "__main__":
            explicator.run_mcp(service)
    """
    from explicator.adapters.mcp_server.server import mcp, set_service

    set_service(service)
    mcp.run()


def run_chat(
    service: ModelService,
    *,
    question: str | None = None,
) -> None:
    """Start an interactive chat REPL, or answer a single question.

    Requires an AI provider to be configured (e.g. ANTHROPIC_API_KEY).

    Args:
        service: The ModelService to query.
        question: If provided, answer this single question and return.
                  If omitted, start an interactive REPL.
    """
    from explicator.ai.dispatcher import ToolDispatcher
    from explicator.ai.orchestrator import run_turn
    from explicator.ai.providers.base import AIMessage
    from explicator.config import build_provider

    provider = build_provider()
    dispatcher = ToolDispatcher(service)

    if question:
        print(
            run_turn([AIMessage(role="user", content=question)], provider, dispatcher)
        )
        return

    print("Explicator chat — type 'exit' or Ctrl+D to quit.\n")
    messages: list[AIMessage] = []
    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        messages.append(AIMessage(role="user", content=user_input))
        print(f"\n{run_turn(messages, provider, dispatcher)}\n")


def run_web(
    service: ModelService,
    *,
    host: str = "localhost",
    port: int = 8000,
) -> None:
    """Start the web server backed by the given service.

    Opens a browser-based interface where users can chat with the model
    and watch the AI tool-calling trace unfold in real time.

    Requires ``fastapi`` and ``uvicorn`` (``pip install 'explicator[web]'``).

    Args:
        service: The ModelService to query.
        host: Host to bind the server to (default: localhost).
        port: Port to listen on (default: 8000).
    """
    from explicator.adapters.web.app import run

    run(service, host=host, port=port)


def load_service(path: str) -> ModelService:
    """Load a ModelService from a dotted import path.

    The path format is ``'module.path:attribute'``, where the attribute is
    either a ``ModelService`` instance or a zero-argument callable that returns
    one.

    Example::

        service = explicator.load_service("myapp.model:build_service")
        service = explicator.load_service("myapp.model:service")
    """
    import importlib

    if ":" not in path:
        raise ValueError(
            f"Service path must be 'module:attribute', got '{path}'. "
            "Example: 'myapp.model:build_service'"
        )
    module_path, attr = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    obj = getattr(module, attr)
    return obj() if callable(obj) else obj
