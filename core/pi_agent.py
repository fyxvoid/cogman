"""
Pi Agent Core — Python port of pi-agent-core (badlogic/pi-mono).

Multi-provider LLM base with event streaming, parallel tool execution,
abort/steer/follow-up queues, and before/after tool hooks.

Provider auto-detection from env:
  ANTHROPIC_API_KEY       → Anthropic (claude-*)
  OPENAI_API_KEY          → OpenAI (gpt-*, o1-*)
  GROQ_API_KEY            → Groq (llama-*, mixtral-*, gemma-*)
  GEMINI_API_KEY          → Google Gemini (gemini-*)
  COGMAN_OPENAI_BASE_URL  → any OpenAI-compatible endpoint
  COGMAN_LOCAL_LLM=true   → Ollama (local, offline)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

log = logging.getLogger("cogman.pi_agent")

# ── Event types (ported from pi-agent-core types.ts) ─────────────────────────

@dataclass
class AgentEvent:
    type: str

@dataclass
class AgentStartEvent(AgentEvent):
    type: str = field(default="agent_start", init=False)

@dataclass
class TurnStartEvent(AgentEvent):
    type: str = field(default="turn_start", init=False)

@dataclass
class MessageStartEvent(AgentEvent):
    type: str = field(default="message_start", init=False)
    role: str = "assistant"
    content: str = ""

@dataclass
class MessageUpdateEvent(AgentEvent):
    type: str = field(default="message_update", init=False)
    delta: str = ""
    content: str = ""

@dataclass
class MessageEndEvent(AgentEvent):
    type: str = field(default="message_end", init=False)
    role: str = "assistant"
    content: str = ""

@dataclass
class ToolExecutionStartEvent(AgentEvent):
    type: str = field(default="tool_execution_start", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    args: Dict = field(default_factory=dict)

@dataclass
class ToolExecutionUpdateEvent(AgentEvent):
    type: str = field(default="tool_execution_update", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    partial_result: str = ""

@dataclass
class ToolExecutionEndEvent(AgentEvent):
    type: str = field(default="tool_execution_end", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    result: str = ""
    is_error: bool = False

@dataclass
class TurnEndEvent(AgentEvent):
    type: str = field(default="turn_end", init=False)
    tool_calls_made: int = 0

@dataclass
class AgentEndEvent(AgentEvent):
    type: str = field(default="agent_end", init=False)
    final_text: str = ""
    tool_calls_made: int = 0
    error: Optional[str] = None

EventListener = Callable[[AgentEvent], None]

# ── Provider abstraction ──────────────────────────────────────────────────────

class LLMProvider(ABC):
    name: str = "base"
    priority: int = 0  # higher = tried first

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """Return dict: {text, tool_calls: [{id, name, args}], stop_reason}"""
        ...

    def get_default_model(self) -> str:
        return ""


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    priority = 100

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 4096):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        client = self._get_client()
        model = model or self._model

        # Streaming with tool support
        try:
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools or [],
                messages=messages,
            ) as stream:
                text_parts = []
                for text in stream.text_stream:
                    text_parts.append(text)
                    if stream_callback:
                        stream_callback(text)
                response = stream.get_final_message()

            tool_calls = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls.append({"id": block.id, "name": block.name, "args": block.input})

            return {
                "text": "".join(text_parts),
                "tool_calls": tool_calls,
                "stop_reason": response.stop_reason,
                "raw": response,
            }
        except Exception as e:
            log.error("Anthropic call failed: %s", e)
            raise


class OpenAICompatibleProvider(LLMProvider):
    """Supports OpenAI, Groq, Mistral, LM Studio, Ollama OpenAI-compat, etc."""
    name = "openai"
    priority = 80

    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-4o", provider_name: str = "openai"):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self.name = provider_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            from openai import OpenAI  # noqa: F401
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        client = self._get_client()
        model = model or self._model

        # Convert Anthropic tool schema → OpenAI tool schema
        oai_tools = []
        for t in (tools or []):
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })

        msgs = [{"role": "system", "content": system}] + messages

        try:
            if stream_callback:
                stream = client.chat.completions.create(
                    model=model, messages=msgs, tools=oai_tools or None,
                    max_tokens=max_tokens, stream=True,
                )
                text_parts = []
                tool_calls_raw = {}
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        text_parts.append(delta.content)
                        stream_callback(delta.content)
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_raw:
                                tool_calls_raw[idx] = {"id": "", "name": "", "args": ""}
                            if tc.id:
                                tool_calls_raw[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_raw[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_raw[idx]["args"] += tc.function.arguments

                tool_calls = []
                for tc in tool_calls_raw.values():
                    try:
                        args = json.loads(tc["args"]) if tc["args"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({"id": tc["id"], "name": tc["name"], "args": args})

                return {"text": "".join(text_parts), "tool_calls": tool_calls, "stop_reason": "end_turn"}
            else:
                resp = client.chat.completions.create(
                    model=model, messages=msgs, tools=oai_tools or None, max_tokens=max_tokens,
                )
                msg = resp.choices[0].message
                tool_calls = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except Exception:
                            args = {}
                        tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})
                return {
                    "text": msg.content or "",
                    "tool_calls": tool_calls,
                    "stop_reason": resp.choices[0].finish_reason,
                }
        except Exception as e:
            log.error("%s call failed: %s", self.name, e)
            raise


class GeminiProvider(LLMProvider):
    name = "gemini"
    priority = 70

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import google.generativeai  # noqa: F401
            return True
        except ImportError:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        model_name = model or self._model

        # Convert tools to Gemini format
        gemini_tools = []
        if tools:
            fn_decls = []
            for t in tools:
                schema = t.get("input_schema", {})
                fn_decls.append(genai.protos.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            k: genai.protos.Schema(type=genai.protos.Type.STRING)
                            for k in schema.get("properties", {})
                        },
                    ),
                ))
            gemini_tools = [genai.protos.Tool(function_declarations=fn_decls)]

        gemini_msgs = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            gemini_msgs.append({"role": role, "parts": [m["content"]]})

        gemini_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
        )
        chat = gemini_model.start_chat(history=gemini_msgs[:-1] if len(gemini_msgs) > 1 else [])
        last_msg = gemini_msgs[-1]["parts"][0] if gemini_msgs else ""

        try:
            response = chat.send_message(last_msg, tools=gemini_tools or None)
            text = ""
            tool_calls = []
            for part in response.parts:
                if hasattr(part, "text") and part.text:
                    text += part.text
                    if stream_callback:
                        stream_callback(part.text)
                if hasattr(part, "function_call") and part.function_call.name:
                    fc = part.function_call
                    tool_calls.append({"id": str(uuid.uuid4()), "name": fc.name, "args": dict(fc.args)})
            return {"text": text, "tool_calls": tool_calls, "stop_reason": "end_turn"}
        except Exception as e:
            log.error("Gemini call failed: %s", e)
            raise


class OllamaProvider(LLMProvider):
    name = "ollama"
    priority = 50

    def __init__(self, host: str = "http://localhost:11434", model: str = "mistral"):
        self._host = host
        self._model = model

    def is_available(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self._host}/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def get_default_model(self) -> str:
        return self._model

    def chat_with_tools(self, messages, system, tools, model=None, max_tokens=4096, stream_callback=None):
        import urllib.request
        model = model or self._model

        # Ollama supports OpenAI-compat tool calling on recent versions
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": bool(stream_callback),
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }
        if tools:
            # Ollama /api/chat tools format (0.3+)
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            if stream_callback:
                text_parts = []
                with urllib.request.urlopen(req, timeout=60) as resp:
                    for line in resp:
                        line = line.decode().strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            text_parts.append(delta)
                            stream_callback(delta)
                        if chunk.get("done"):
                            break
                return {"text": "".join(text_parts), "tool_calls": [], "stop_reason": "end_turn"}
            else:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                msg = result.get("message", {})
                text = msg.get("content", "")
                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    tool_calls.append({
                        "id": str(uuid.uuid4()),
                        "name": fn.get("name", ""),
                        "args": fn.get("arguments", {}),
                    })
                return {"text": text, "tool_calls": tool_calls, "stop_reason": "end_turn"}
        except Exception as e:
            log.error("Ollama call failed: %s", e)
            raise


# ── Provider registry (auto-detects from env) ─────────────────────────────────

class ProviderRegistry:
    """Discovers and ranks all available LLM providers."""

    def __init__(self):
        self._providers: List[LLMProvider] = []
        self._load_from_env()

    def _load_from_env(self):
        # Anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if key:
            model = os.getenv("COGMAN_MODEL", "claude-sonnet-4-6")
            self.register(AnthropicProvider(key, model))

        # Groq
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            self.register(OpenAICompatibleProvider(
                groq_key,
                base_url="https://api.groq.com/openai/v1",
                model=os.getenv("COGMAN_GROQ_MODEL", "llama-3.3-70b-versatile"),
                provider_name="groq",
            ))

        # OpenAI
        oai_key = os.getenv("OPENAI_API_KEY", "")
        if oai_key:
            self.register(OpenAICompatibleProvider(
                oai_key,
                model=os.getenv("COGMAN_OPENAI_MODEL", "gpt-4o"),
                provider_name="openai",
            ))

        # Gemini
        gem_key = os.getenv("GEMINI_API_KEY", "")
        if gem_key:
            self.register(GeminiProvider(gem_key, os.getenv("COGMAN_GEMINI_MODEL", "gemini-2.0-flash")))

        # Custom OpenAI-compatible (e.g. LM Studio, vLLM, Together, Mistral)
        custom_base = os.getenv("COGMAN_OPENAI_BASE_URL", "")
        custom_key = os.getenv("COGMAN_OPENAI_API_KEY", "sk-local")
        custom_model = os.getenv("COGMAN_OPENAI_MODEL", "local-model")
        if custom_base:
            self.register(OpenAICompatibleProvider(
                custom_key, base_url=custom_base, model=custom_model, provider_name="custom"
            ))

        # Ollama (local)
        if os.getenv("COGMAN_LOCAL_LLM", "true").lower() == "true":
            host = os.getenv("COGMAN_OLLAMA_HOST", "http://localhost:11434")
            model = os.getenv("COGMAN_OLLAMA_MODEL", "mistral")
            self.register(OllamaProvider(host, model))

    def register(self, provider: LLMProvider):
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def best_available(self) -> Optional[LLMProvider]:
        for p in self._providers:
            if p.is_available():
                return p
        return None

    def get(self, name: str) -> Optional[LLMProvider]:
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def list_available(self) -> List[str]:
        return [p.name for p in self._providers if p.is_available()]

    def summary(self) -> str:
        lines = []
        for p in self._providers:
            ok = p.is_available()
            lines.append(f"  [{'✓' if ok else '✗'}] {p.name:<12} {p.get_default_model()}")
        return "\n".join(lines) or "  No providers configured."


# ── Pi Agent Core ─────────────────────────────────────────────────────────────

class PiAgentCore:
    """
    Stateful agent loop ported from pi-agent-core.

    Handles: multi-provider LLM, parallel tool execution, event streaming,
    abort, steer/follow-up queues, before/after tool hooks.
    """

    def __init__(
        self,
        registry,
        memory,
        system_prompt: str,
        provider_registry: Optional[ProviderRegistry] = None,
        preferred_provider: Optional[str] = None,
        max_tool_turns: int = 20,
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
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                log.debug("Event listener error: %s", e)

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

    def _build_messages(self, user_input: str) -> List[Dict]:
        """Build LLM message list from memory + user input."""
        ctx = list(self.memory.get_context())
        # The context already includes the latest user message from memory.add_message
        # Check if last message is the current user input to avoid duplication
        if not ctx or ctx[-1].get("content") != user_input:
            ctx.append({"role": "user", "content": user_input})
        return ctx

    def _build_system(self) -> str:
        return self.system_prompt

    def process(self, user_input: str) -> str:
        """Run the full ReAct loop. Emits events. Returns final text."""
        self._abort.clear()
        provider = self._get_provider()
        if not provider:
            return "No LLM provider available. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or start Ollama."

        messages = self._build_messages(user_input)
        system = self._build_system()

        # Append relevant memories to system
        memories = self.memory.recall(user_input[:100])
        if memories:
            system += "\n\nRelevant memories:\n" + "\n".join(f"- {m}" for m in memories)

        tools = self.registry.all_schemas()

        self._emit(AgentStartEvent())
        final_text = self._run_loop(messages, system, tools, provider)
        self._emit(AgentEndEvent(final_text=final_text))

        # Process follow-up queue
        with self._lock:
            followups = self._followup_queue[:]
            self._followup_queue.clear()
        for fu in followups:
            if self._abort.is_set():
                break
            final_text = self._run_loop(
                list(self.memory.get_context()) + [{"role": "user", "content": fu}],
                system, tools, provider,
            )

        return final_text

    def _run_loop(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        provider: LLMProvider,
    ) -> str:
        """Core ReAct loop: call LLM → execute tools → repeat."""
        current_messages = list(messages)
        final_text = ""
        total_tool_calls = 0

        for turn in range(self.max_tool_turns):
            if self._abort.is_set():
                break

            # Inject any steered messages
            with self._lock:
                steered = self._steer_queue[:]
                self._steer_queue.clear()
            for s in steered:
                current_messages.append({"role": "user", "content": s})

            self._emit(TurnStartEvent())

            # Stream text to terminal in real-time
            streaming_text = []

            def on_stream(delta: str):
                streaming_text.append(delta)
                self._emit(MessageUpdateEvent(delta=delta, content="".join(streaming_text)))

            self._emit(MessageStartEvent(role="assistant", content=""))

            try:
                response = provider.chat_with_tools(
                    messages=current_messages,
                    system=system,
                    tools=tools,
                    max_tokens=4096,
                    stream_callback=on_stream,
                )
            except Exception as e:
                log.error("LLM call failed: %s", e)
                err_msg = f"LLM error ({provider.name}): {e}"
                self._emit(MessageEndEvent(content=err_msg))
                self._emit(TurnEndEvent())
                return err_msg

            text = response.get("text", "")
            tool_calls = response.get("tool_calls", [])

            self._emit(MessageEndEvent(role="assistant", content=text))

            if text:
                final_text = text

            if not tool_calls:
                self._emit(TurnEndEvent(tool_calls_made=0))
                break

            # Execute tool calls (parallel by default, like pi-agent-core)
            tool_results = self._execute_tools(tool_calls, tools)
            total_tool_calls += len(tool_calls)
            self._emit(TurnEndEvent(tool_calls_made=len(tool_calls)))

            # Build tool result messages for next turn (Anthropic format)
            if hasattr(provider, '_api_key') and hasattr(provider, '_model') and provider.name == "anthropic":
                # Anthropic: assistant content = original + tool_use blocks
                assistant_content = []
                if text:
                    assistant_content.append({"type": "text", "text": text})
                for tc in tool_calls:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["args"],
                    })
                current_messages.append({"role": "assistant", "content": assistant_content})
                tool_result_content = []
                for tr in tool_results:
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": tr["tool_call_id"],
                        "content": tr["result"],
                    })
                current_messages.append({"role": "user", "content": tool_result_content})
            else:
                # OpenAI/compatible format
                tool_call_entries = []
                for tc in tool_calls:
                    tool_call_entries.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                    })
                current_messages.append({
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": tool_call_entries,
                })
                for tr in tool_results:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["result"],
                    })

        self.memory.add_message("assistant", final_text or "(done)")
        return final_text or "(Task completed)"

    def _execute_tools(self, tool_calls: List[Dict], tool_schemas: List[Dict]) -> List[Dict]:
        """Execute tool calls in parallel (Pi-style) or sequential."""
        results = []

        if self.parallel_tools and len(tool_calls) > 1:
            with ThreadPoolExecutor(max_workers=min(len(tool_calls), 8)) as ex:
                futures = {
                    ex.submit(self._execute_single_tool, tc): tc
                    for tc in tool_calls
                }
                # Preserve order of results
                ordered = {tc["id"]: None for tc in tool_calls}
                for future in as_completed(futures):
                    tc = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = {"tool_call_id": tc["id"], "result": f"Error: {e}", "is_error": True}
                    ordered[tc["id"]] = result
                results = [ordered[tc["id"]] for tc in tool_calls]
        else:
            for tc in tool_calls:
                if self._abort.is_set():
                    break
                results.append(self._execute_single_tool(tc))

        return results

    def _execute_single_tool(self, tc: Dict) -> Dict:
        tool_call_id = tc["id"]
        name = tc["name"]
        args = tc["args"]

        self._emit(ToolExecutionStartEvent(tool_call_id=tool_call_id, tool_name=name, args=args))

        try:
            result = self.registry.run(name, args)
            is_error = result.startswith("Error") or result.startswith("Unknown tool")
        except Exception as e:
            result = f"Tool error: {e}"
            is_error = True

        self._emit(ToolExecutionEndEvent(
            tool_call_id=tool_call_id, tool_name=name, result=result, is_error=is_error
        ))
        return {"tool_call_id": tool_call_id, "result": result, "is_error": is_error}
