"""AI conversation orchestration loop — shared by all chat interfaces.

Extracted so the CLI, web server, and any future adapter can all use
the same turn-running logic without duplicating it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from explicator.ai.dispatcher import ToolDispatcher
    from explicator.ai.providers.base import AIMessage, AIProvider


def run_turn(
    messages: list[AIMessage],
    provider: AIProvider,
    dispatcher: ToolDispatcher,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """Run one turn of the AI conversation loop and return the final text.

    Calls the provider, dispatches any tool calls, and loops until the model
    produces a text response. Appends all intermediate messages (assistant tool
    calls and tool results) to ``messages`` in place.

    If ``on_event`` is provided it is called synchronously at each step with a
    structured event dict:

    * ``{"type": "thinking"}`` — provider call is about to be made
    * ``{"type": "tool_call", "name": str, "arguments": dict}``
    * ``{"type": "tool_result", "name": str, "result": dict}``
    * ``{"type": "assistant_text", "content": str}``
    """
    from explicator.ai.tools.definitions import TOOL_DEFINITIONS

    while True:
        if on_event:
            on_event({"type": "thinking"})

        response = provider.chat(messages, tools=TOOL_DEFINITIONS)
        messages.append(response.message)

        if not response.tool_calls:
            content = response.message.content or ""
            if on_event:
                on_event({"type": "assistant_text", "content": content})
            return content

        for tc in response.tool_calls:
            if on_event:
                on_event(
                    {
                        "type": "tool_call",
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    }
                )
            result = dispatcher.dispatch(tc["name"], tc["arguments"])
            if on_event:
                on_event({"type": "tool_result", "name": tc["name"], "result": result})

            from explicator.ai.providers.base import AIMessage

            messages.append(
                AIMessage(
                    role="tool",
                    content=json.dumps(result),
                    tool_call_id=tc["id"],
                    name=tc["name"],
                )
            )
