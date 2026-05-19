"""
COGMAN cognitive agent loop — stateful multi-provider agent with parallel tool execution.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from agents.events import (
    AgentEvent, AgentStartEvent, AgentEndEvent, TurnStartEvent, TurnEndEvent,
    MessageStartEvent, MessageUpdateEvent, MessageEndEvent,
    ToolExecutionStartEvent, ToolExecutionEndEvent, EventListener,
)
from agents.providers import LLMProvider, ProviderRegistry

log = logging.getLogger("cogman.loop")


class CogmanCore:
    """
    COGMAN's stateful cognitive loop:
      - Multi-provider LLM (Anthropic / OpenAI / Groq / Gemini / Ollama)
      - Parallel tool execution (ReAct pattern)
      - Real-time event streaming
      - Abort / steer / follow-up queues
    """

    def __init__(
        self,
        registry,
        memory,
        system_prompt: str,
        provider_registry: Optional[ProviderRegistry] = None,
        preferred_provider: Optional[str] = None,
        max_tool_turns: int = 25,
        parallel_tools: bool = True,
    ):
        self.registry = registry
        self.memory = memory
        self.system_prompt = system_prompt
        self.providers = provider_registry or ProviderRegistry()
        self.preferred_provider = preferred_provider
        self.max_tool_turns = max_tool_turns
        self.parallel_tools = parallel_tools

        self._listeners: List[EventListener] = []
        self._abort = threading.Event()
        self._steer_queue: List[str] = []
        self._followup_queue: List[str] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: EventListener) -> Callable:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _emit(self, event: AgentEvent):
        for fn in self._listeners:
            try:
                fn(event)
            except Exception:
                pass

    def interrupt(self):
        self._abort.set()

    def steer(self, message: str):
        with self._lock:
            self._steer_queue.append(message)

    def follow_up(self, message: str):
        with self._lock:
            self._followup_queue.append(message)

    def _get_provider(self) -> Optional[LLMProvider]:
        if self.preferred_provider:
            p = self.providers.get(self.preferred_provider)
            if p and p.is_available():
                return p
        return self.providers.best_available()

    def process(self, user_input: str, extra_context: str = "") -> str:
        self._abort.clear()
        provider = self._get_provider()
        if not provider:
            return (
                "No LLM provider available.\n"
                "Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY\n"
                "Or start Ollama: ollama run mistral"
            )

        messages = list(self.memory.get_context())
        if not messages or messages[-1].get("content") != user_input:
            messages.append({"role": "user", "content": user_input})

        system = self.system_prompt
        memories = self.memory.recall(user_input[:100])
        if memories:
            system += "\n\nRelevant memories:\n" + "\n".join(f"- {m}" for m in memories)
        if extra_context:
            system += f"\n\n{extra_context}"

        tools = self.registry.all_schemas()

        self._emit(AgentStartEvent())
        final_text = self._run_loop(messages, system, tools, provider)

        with self._lock:
            followups = self._followup_queue[:]
            self._followup_queue.clear()
        for fu in followups:
            if self._abort.is_set():
                break
            ctx = list(self.memory.get_context())
            ctx.append({"role": "user", "content": fu})
            final_text = self._run_loop(ctx, system, tools, provider)

        self._emit(AgentEndEvent(final_text=final_text))
        return final_text

    def _run_loop(self, messages: List[Dict], system: str, tools: List[Dict], provider: LLMProvider) -> str:
        current = list(messages)
        final_text = ""

        for _turn in range(self.max_tool_turns):
            if self._abort.is_set():
                break

            with self._lock:
                steered = self._steer_queue[:]
                self._steer_queue.clear()
            for s in steered:
                current.append({"role": "user", "content": s})

            self._emit(TurnStartEvent())
            streaming = []

            def on_stream(delta: str):
                streaming.append(delta)
                self._emit(MessageUpdateEvent(delta=delta, content="".join(streaming)))

            self._emit(MessageStartEvent())
            try:
                resp = provider.chat_with_tools(
                    messages=current, system=system, tools=tools,
                    max_tokens=4096, stream_callback=on_stream,
                )
            except Exception as e:
                err = f"LLM error ({provider.name}): {e}"
                self._emit(MessageEndEvent(content=err))
                self._emit(TurnEndEvent())
                return err

            text = resp.get("text", "")
            tool_calls = resp.get("tool_calls", [])
            self._emit(MessageEndEvent(role="assistant", content=text))

            if text:
                final_text = text

            if not tool_calls:
                self._emit(TurnEndEvent(tool_calls_made=0))
                break

            results = self._execute_tools(tool_calls)
            self._emit(TurnEndEvent(tool_calls_made=len(tool_calls)))

            # Append to message history (Anthropic format preferred)
            if provider.name == "anthropic":
                assistant_content = []
                if text:
                    assistant_content.append({"type": "text", "text": text})
                for tc in tool_calls:
                    assistant_content.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]})
                current.append({"role": "assistant", "content": assistant_content})
                current.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["tool_call_id"], "content": r["result"]}
                    for r in results
                ]})
            else:
                current.append({
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [{"id": tc["id"], "type": "function",
                                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                                   for tc in tool_calls],
                })
                for r in results:
                    current.append({"role": "tool", "tool_call_id": r["tool_call_id"], "content": r["result"]})

        self.memory.add_message("assistant", final_text or "(done)")
        return final_text or "(Task completed)"

    def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        if self.parallel_tools and len(tool_calls) > 1:
            with ThreadPoolExecutor(max_workers=min(len(tool_calls), 8)) as ex:
                futures = {ex.submit(self._run_tool, tc): tc for tc in tool_calls}
                ordered = {tc["id"]: None for tc in tool_calls}
                for future in as_completed(futures):
                    tc = futures[future]
                    try:
                        ordered[tc["id"]] = future.result()
                    except Exception as e:
                        ordered[tc["id"]] = {"tool_call_id": tc["id"], "result": f"Error: {e}", "is_error": True}
                return [ordered[tc["id"]] for tc in tool_calls]
        else:
            return [self._run_tool(tc) for tc in tool_calls if not self._abort.is_set()]

    def _run_tool(self, tc: Dict) -> Dict:
        tid, name, args = tc["id"], tc["name"], tc["args"]
        self._emit(ToolExecutionStartEvent(tool_call_id=tid, tool_name=name, args=args))
        try:
            result = self.registry.run(name, args)
            is_error = result.startswith("Error") or result.startswith("Unknown tool")
        except Exception as e:
            result = f"Tool error: {e}"
            is_error = True
        self._emit(ToolExecutionEndEvent(tool_call_id=tid, tool_name=name, result=result, is_error=is_error))
        return {"tool_call_id": tid, "result": result, "is_error": is_error}
